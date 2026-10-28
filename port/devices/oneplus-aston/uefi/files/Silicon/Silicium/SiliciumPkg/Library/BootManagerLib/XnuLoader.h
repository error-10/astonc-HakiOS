#ifndef _XNU_LOADER_H_
#define _XNU_LOADER_H_

//
// The boot shim copies everything appended after the UEFI FD to this address.
// The region is marked reserved in the device memory map
// (Platforms/OnePlus/astonPkg/Library/MemoryMapLib/MemoryMapLib.c).
//
// Aston (SM8550 / Ace 3) address choice: 0xF0000000 (oneplus-dodge) is unusable here,
// because aston firmware reserves 0xF3800000-0xF7AFC000 (Trusted VM) and 0xF7AFC000+
// (OEM VM). 0xE2000000 sits in the free DDR gap between "TZApps Reserved"
// (0xD8800000+0x08A00000, ends 0xE1200000) and "HW Fence" (0xE6440000).
//
#define XNU_PAYLOAD_BASE      0xE2000000ULL
#define XNU_PAYLOAD_MAX_SIZE  0x04000000ULL
#define XNU_PAYLOAD_MAGIC     0x50554E58 // "XNUP"

typedef struct {
  UINT32 Magic;
  UINT32 Size;
} XNU_PAYLOAD_HEADER;

// The header is followed by entries; an empty name ends the list.
typedef struct {
  CHAR8  Name[16];
  UINT32 Size;
  UINT32 Reserved;
  // UINT8 Data[Size], padded to 16 bytes
} XNU_PAYLOAD_ENTRY;

// Raw GPT partition that receives the text log (read back from Android or TWRP).
#define XNU_LOG_PARTITION  L"rawdump"

EFI_STATUS
XnuLogInit ();

VOID
EFIAPI
XnuLog (
  IN CONST CHAR8 *Format,
  ...
  );

VOID
XnuLogFlush ();

VOID
WdtNeutralize ();

VOID
XnuLoaderMain ();

#endif /* _XNU_LOADER_H_ */
