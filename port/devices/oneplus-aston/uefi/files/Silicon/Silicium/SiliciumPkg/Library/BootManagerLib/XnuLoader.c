/**
  XNU loader for Silicium devices (aston bring-up), stage 0: diagnostics and payload start.

  Ported from devices/oneplus-dodge (hackios-os_devices_oneplus-dodge), trimmed to what
  aston needs and to aston addresses only: collect exception level / CPU registers /
  framebuffer / memory map / payload, echo the log to the UEFI console, try to persist it
  to a raw GPT partition, neutralize the Qualcomm virtual watchdog, then start "loader.efi"
  out of the XNUP payload when present.

  Nothing here touches hardware blocks; the dodge bring-up experiments (GENI SE4, SPMI
  arbiter) are intentionally NOT carried over: those addresses belong to dodge.

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>

#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/PrintLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>

#include <Protocol/BlockIo.h>
#include <Protocol/GraphicsOutput.h>
#include <Protocol/PartitionInfo.h>
#include <Protocol/SimpleTextOut.h>

#include "XnuLoader.h"

#define LOG_SIZE  SIZE_256KB

// Console echo is what makes a blind bring-up possible: the log shows up on the phone's
// screen, so a serial cable or a readable partition is not required for the first boot.
STATIC BOOLEAN mConsoleOk;

STATIC CHAR8  *mLog;
STATIC UINTN   mLogLen;

STATIC
VOID
ConsoleEcho (
  IN CONST CHAR8 *Text)
{
  CHAR16  Buffer[256];
  UINTN   Index;

  if (!mConsoleOk) {
    return;
  }

  while (*Text != 0) {
    Index = 0;
    while (*Text != 0 && Index < (ARRAY_SIZE (Buffer) - 2)) {
      if (*Text == '\n') {
        Buffer[Index++] = L'\r';
        Buffer[Index++] = L'\n';
      } else {
        Buffer[Index++] = (CHAR16)(UINT8)*Text;
      }
      Text++;
    }
    Buffer[Index] = 0;
    gST->ConOut->OutputString (gST->ConOut, Buffer);
  }
}

VOID
EFIAPI
XnuLog (
  IN CONST CHAR8 *Format,
  ...)
{
  VA_LIST Marker;
  UINTN   Before;

  if (mLog == NULL || mLogLen >= LOG_SIZE - 512) {
    return;
  }

  Before   = mLogLen;
  VA_START (Marker, Format);
  mLogLen += AsciiVSPrint (mLog + mLogLen, LOG_SIZE - mLogLen, Format, Marker);
  VA_END (Marker);

  ConsoleEcho (mLog + Before);
}

#define READ_SYSREG(Name) ({ UINT64 _Value; __asm__ volatile ("mrs %0, " #Name : "=r" (_Value)); _Value; })

// A translation check (AT instruction) first: the payload address is only mapped when the
// device's memory map lists it; reading it unmapped would take the firmware down.
STATIC
BOOLEAN
Mapped (
  IN UINT64 Address)
{
  UINT64 El, Par;

  __asm__ volatile ("mrs %0, CurrentEL" : "=r" (El));
  if (El == 4) {
    __asm__ volatile ("at s1e1r, %1; isb; mrs %0, par_el1" : "=r" (Par) : "r" (Address) : "memory");
  } else {
    __asm__ volatile ("at s1e2r, %1; isb; mrs %0, par_el1" : "=r" (Par) : "r" (Address) : "memory");
  }

  return (Par & BIT0) == 0;
}

// Qualcomm hypervisor virtual watchdog (hh_virt_wdt) SMCs: XBL leaves it running and nothing
// in this firmware pets it, so the phone resets ~30 s in. Stretch and stop the timers.
STATIC
UINT64
SmcCall (
  IN UINT64 X0,
  IN UINT64 X1,
  IN UINT64 X2)
{
  register UINT64 x0 __asm__ ("x0") = X0;
  register UINT64 x1 __asm__ ("x1") = X1;
  register UINT64 x2 __asm__ ("x2") = X2;

  __asm__ volatile ("smc #0" : "+r" (x0), "+r" (x1), "+r" (x2)
                    : : "x3", "x4", "x5", "x6", "x7", "x8", "x9", "x10", "x11", "x12", "x13", "x14", "x15", "x16", "x17");
  return x0;
}

#define VIRT_WDT_CONTROL  0x86000005ULL
#define VIRT_WDT_STATUS   0x86000006ULL
#define VIRT_WDT_PET      0x86000007ULL
#define VIRT_WDT_SETTIME  0x86000008ULL

EFI_STATUS
XnuLogInit ()
{
  if (mLog == NULL) {
    mLog = AllocateZeroPool (LOG_SIZE);
  }

  mConsoleOk = FALSE;
  if (gST != NULL && gST->ConOut != NULL && gST->ConOut->OutputString != NULL) {
    mConsoleOk = TRUE;
  }

  return mLog != NULL ? EFI_SUCCESS : EFI_OUT_OF_RESOURCES;
}

VOID
WdtNeutralize ()
{
  UINT64 SetTime = SmcCall (VIRT_WDT_SETTIME, 0xfff0, 0xfff0); /* 16 bits of ms: ~65 s */
  UINT64 Control = SmcCall (VIRT_WDT_CONTROL, 0, 0);           /* 0: both timers off */
  UINT64 Pet     = SmcCall (VIRT_WDT_PET, 0, 0);
  UINT64 Status  = SmcCall (VIRT_WDT_STATUS, 0, 0);

  XnuLog ("[vwdt] status=%lx set_time=%lx control=%lx pet=%lx\n", Status, SetTime, Control, Pet);
}

STATIC
EFI_BLOCK_IO_PROTOCOL *
FindPartition (
  IN CONST CHAR16 *Name)
{
  EFI_STATUS  Status;
  EFI_HANDLE *Handles;
  UINTN       Count;

  Status = gBS->LocateHandleBuffer (ByProtocol, &gEfiPartitionInfoProtocolGuid, NULL, &Count, &Handles);
  if (EFI_ERROR (Status)) {
    return NULL;
  }

  for (UINTN i = 0; i < Count; i++) {
    EFI_PARTITION_INFO_PROTOCOL *Info;
    EFI_BLOCK_IO_PROTOCOL       *BlockIo;

    Status = gBS->HandleProtocol (Handles[i], &gEfiPartitionInfoProtocolGuid, (VOID **)&Info);
    if (EFI_ERROR (Status) || Info->Type != PARTITION_TYPE_GPT) {
      continue;
    }

    if (StrnCmp (Info->Info.Gpt.PartitionName, Name, 36) != 0) {
      continue;
    }

    Status = gBS->HandleProtocol (Handles[i], &gEfiBlockIoProtocolGuid, (VOID **)&BlockIo);
    if (!EFI_ERROR (Status)) {
      return BlockIo;
    }
  }

  return NULL;
}

// Partition names are device dependent; whichever exists first is used. OnePlus has a
// "rawdump" partition and it is not needed during a RAM boot.
STATIC CONST CHAR16 *mLogPartitions[] = {
  L"rawdump",
  L"logdump",
  L"oplusrawdump",
};

STATIC
VOID
FlushLog ()
{
  EFI_STATUS             Status;
  EFI_BLOCK_IO_PROTOCOL *BlockIo = NULL;
  UINTN                  BlockSize;
  UINTN                  WriteSize;

  if (mLog == NULL || mLogLen == 0) {
    return;
  }

  for (UINTN i = 0; i < ARRAY_SIZE (mLogPartitions) && BlockIo == NULL; i++) {
    BlockIo = FindPartition (mLogPartitions[i]);
  }

  if (BlockIo == NULL || BlockIo->Media == NULL || !BlockIo->Media->MediaPresent) {
    return;
  }

  BlockSize = BlockIo->Media->BlockSize;
  if (BlockSize == 0) {
    return;
  }

  WriteSize = ALIGN_VALUE (mLogLen + 1, BlockSize);

  Status = BlockIo->WriteBlocks (BlockIo, BlockIo->Media->MediaId, 0, WriteSize, mLog);
  if (!EFI_ERROR (Status)) {
    BlockIo->FlushBlocks (BlockIo);
  }
}

STATIC
VOID
LogCpu ()
{
  XnuLog ("[cpu]\n");
  XnuLog ("CurrentEL=%lx\n", READ_SYSREG (CurrentEL) >> 2);
  XnuLog ("MIDR_EL1=%016lx\n", READ_SYSREG (MIDR_EL1));
  XnuLog ("MPIDR_EL1=%016lx\n", READ_SYSREG (MPIDR_EL1));
  XnuLog ("ID_AA64MMFR0_EL1=%016lx\n", READ_SYSREG (ID_AA64MMFR0_EL1));
  XnuLog ("ID_AA64MMFR1_EL1=%016lx\n", READ_SYSREG (ID_AA64MMFR1_EL1));
  XnuLog ("ID_AA64MMFR2_EL1=%016lx\n", READ_SYSREG (ID_AA64MMFR2_EL1));
  XnuLog ("ID_AA64PFR0_EL1=%016lx\n", READ_SYSREG (ID_AA64PFR0_EL1));
  XnuLog ("ID_AA64PFR1_EL1=%016lx\n", READ_SYSREG (ID_AA64PFR1_EL1));
  XnuLog ("ID_AA64ISAR0_EL1=%016lx\n", READ_SYSREG (ID_AA64ISAR0_EL1));
  XnuLog ("ID_AA64ISAR1_EL1=%016lx\n", READ_SYSREG (ID_AA64ISAR1_EL1));
  XnuLog ("ID_AA64DFR0_EL1=%016lx\n", READ_SYSREG (ID_AA64DFR0_EL1));
  XnuLog ("SCTLR_EL1=%016lx\n", READ_SYSREG (SCTLR_EL1));
  XnuLog ("TCR_EL1=%016lx\n", READ_SYSREG (TCR_EL1));
  XnuLog ("TTBR0_EL1=%016lx\n", READ_SYSREG (TTBR0_EL1));
  XnuLog ("VBAR_EL1=%016lx\n", READ_SYSREG (VBAR_EL1));
  XnuLog ("CNTFRQ_EL0=%ld\n", READ_SYSREG (CNTFRQ_EL0));
  XnuLog ("DAIF=%lx\n", READ_SYSREG (DAIF));
}

STATIC
VOID
LogDisplay ()
{
  EFI_STATUS                    Status;
  EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop;

  XnuLog ("[display]\n");

  Status = gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&Gop);
  if (EFI_ERROR (Status)) {
    XnuLog ("gop=missing status=%r\n", Status);
    return;
  }

  XnuLog ("fb_base=%lx fb_size=%lx\n", Gop->Mode->FrameBufferBase, (UINT64)Gop->Mode->FrameBufferSize);
  XnuLog ("width=%d height=%d stride=%d format=%d\n",
          Gop->Mode->Info->HorizontalResolution, Gop->Mode->Info->VerticalResolution,
          Gop->Mode->Info->PixelsPerScanLine, Gop->Mode->Info->PixelFormat);
}

STATIC
VOID
LogMemoryMap ()
{
  EFI_STATUS             Status;
  EFI_MEMORY_DESCRIPTOR *Map;
  UINTN                  MapSize = 0;
  UINTN                  MapKey;
  UINTN                  DescSize;
  UINT32                 DescVersion;

  XnuLog ("[memmap]\n");

  Status = gBS->GetMemoryMap (&MapSize, NULL, &MapKey, &DescSize, &DescVersion);
  if (Status != EFI_BUFFER_TOO_SMALL) {
    XnuLog ("getmemorymap status=%r\n", Status);
    return;
  }

  MapSize += SIZE_4KB;
  Map      = AllocatePool (MapSize);
  if (Map == NULL) {
    XnuLog ("getmemorymap: no pool\n");
    return;
  }

  Status = gBS->GetMemoryMap (&MapSize, Map, &MapKey, &DescSize, &DescVersion);
  if (EFI_ERROR (Status)) {
    XnuLog ("getmemorymap status=%r\n", Status);
    FreePool (Map);
    return;
  }

  for (UINTN Offset = 0; Offset < MapSize; Offset += DescSize) {
    EFI_MEMORY_DESCRIPTOR *Desc = (EFI_MEMORY_DESCRIPTOR *)((UINT8 *)Map + Offset);

    XnuLog ("%016lx %016lx type=%d attr=%lx\n", Desc->PhysicalStart,
            Desc->PhysicalStart + EFI_PAGES_TO_SIZE (Desc->NumberOfPages), Desc->Type, Desc->Attribute);
  }

  FreePool (Map);
}

STATIC
VOID
LogPayload (
  IN BOOLEAN PayloadMapped)
{
  XnuLog ("[payload]\n");
  XnuLog ("base=%lx mapped=%d", (UINT64)XNU_PAYLOAD_BASE, PayloadMapped);

  if (PayloadMapped) {
    XNU_PAYLOAD_HEADER *Header = (XNU_PAYLOAD_HEADER *)XNU_PAYLOAD_BASE;

    XnuLog (" magic=%08x size=%x\n", Header->Magic, Header->Size);
  } else {
    XnuLog ("\n");
  }
}

//
// The payload is a list of named blobs. If it carries "loader.efi", that is
// the real XNU loader: start it straight from memory, so the loader can be
// iterated on without rebuilding this firmware.
//
STATIC
VOID
StartPayloadLoader ()
{
  XNU_PAYLOAD_HEADER *Header = (XNU_PAYLOAD_HEADER *)XNU_PAYLOAD_BASE;
  UINT8              *Cursor;
  UINT8              *End;

  if (!Mapped ((UINT64)XNU_PAYLOAD_BASE) ||
      Header->Magic != XNU_PAYLOAD_MAGIC || Header->Size > XNU_PAYLOAD_MAX_SIZE)
  {
    return;
  }

  Cursor = (UINT8 *)(Header + 1);
  End    = Cursor + Header->Size;

  while (Cursor + sizeof (XNU_PAYLOAD_ENTRY) <= End) {
    XNU_PAYLOAD_ENTRY *Entry = (XNU_PAYLOAD_ENTRY *)Cursor;

    if (Entry->Name[0] == 0) {
      break;
    }

    if (AsciiStrnCmp (Entry->Name, "loader.efi", sizeof (Entry->Name)) == 0) {
      EFI_HANDLE Handle;
      EFI_STATUS Status = gBS->LoadImage (FALSE, gImageHandle, NULL, Entry + 1, Entry->Size, &Handle);

      XnuLog ("[loader] LoadImage(size=%x)=%r\n", Entry->Size, Status);
      FlushLog ();
      if (!EFI_ERROR (Status)) {
        Status = gBS->StartImage (Handle, NULL, NULL);
        XnuLog ("[loader] StartImage=%r\n", Status);
        FlushLog ();
      }

      return;
    }

    Cursor += sizeof (XNU_PAYLOAD_ENTRY) + ALIGN_VALUE (Entry->Size, 16);
  }
}

VOID
XnuLoaderMain ()
{
  EFI_TIME Time;
  BOOLEAN  PayloadMapped;

  mLog = AllocateZeroPool (LOG_SIZE);
  if (mLog != NULL) {
    XnuLog ("== XNULOADER LOG v2 (aston) ==\n");

    if (!EFI_ERROR (gRT->GetTime (&Time, NULL))) {
      XnuLog ("time=%04d-%02d-%02d %02d:%02d:%02d\n", Time.Year, Time.Month, Time.Day, Time.Hour, Time.Minute, Time.Second);
    }
  }

  WdtNeutralize ();

  PayloadMapped = Mapped ((UINT64)XNU_PAYLOAD_BASE);

  if (mLog != NULL) {
    LogPayload (PayloadMapped);
    FlushLog ();
    LogCpu ();
    FlushLog ();
    LogDisplay ();
    FlushLog ();
    LogMemoryMap ();
    FlushLog ();
    XnuLog ("== END ==\n");
    FlushLog ();
  }

  // Normally does not return
  StartPayloadLoader ();

  // Nothing started: stay where it is safe to leave the phone unattended, then back to Android.
  XnuLog ("[xnu] no payload started, resetting in 60 s\n");
  FlushLog ();
  gBS->Stall (60 * 1000 * 1000);
  gRT->ResetSystem (EfiResetCold, EFI_SUCCESS, 0, NULL);
}
