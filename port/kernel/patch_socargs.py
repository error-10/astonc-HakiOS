#!/usr/bin/env python3
"""
Teach the HakiOS kernel where *this* phone keeps the two blocks the first phone hardcoded.

Upstream every driver that talks to RPMh maps the application processor's sequencer at
0x18220000 ("DRV 2" of rsc@18200000) and the boot loader's command DB at 0x80860000. On the
Ace 3 those are 0x17a20000 and 0x81c60000, so the drivers would take an external abort the
moment they touched them.

This patches the kernel tree so the two addresses come from boot-args (soc_rsc / soc_cmd_db,
which devices/<device>/soc.args already carries) and keeps the old values as defaults, so the
first phone still needs no arguments. Idempotent: running it twice changes nothing.

    python3 port/kernel/patch_socargs.py [kernel-tree]
"""

import pathlib
import sys

DEFAULT_TREE = pathlib.Path.home() / "hackios/hackios-os/xnu-src/xnu-8796.121.2"

GETTERS = """
/*
 * The two blocks a port moves. Everything that talks to RPMh maps the application processor's
 * sequencer (the "DRV 2" TCS the drivers write their requests into) and the boot loader's
 * command DB; both live somewhere else on another SoC. The port's soc.args carries the
 * addresses as soc_rsc / soc_cmd_db, read once here before any driver starts.
 */
uint32_t hakios_soc_rsc(void);
uint32_t hakios_soc_cmd_db(void);
"""

IMPL = """
/* Where the first phone keeps what the ports may move (see kern/sys/hakios.input.h). */
#define HAKIOS_RSC_DEFAULT      0x18220000u
#define HAKIOS_CMD_DB_DEFAULT   0x80860000u

static uint32_t soc_rsc_phys = HAKIOS_RSC_DEFAULT;
static uint32_t soc_cmd_db_phys = HAKIOS_CMD_DB_DEFAULT;

uint32_t
hakios_soc_rsc(void)
{
	return soc_rsc_phys;
}

uint32_t
hakios_soc_cmd_db(void)
{
	return soc_cmd_db_phys;
}

static void
hakios_soc_args(void)
{
	uint32_t phys = 0;

	if (PE_parse_boot_argn("soc_rsc", &phys, sizeof(phys)) && phys != 0) {
		soc_rsc_phys = phys;
	}
	phys = 0;
	if (PE_parse_boot_argn("soc_cmd_db", &phys, sizeof(phys)) && phys != 0) {
		soc_cmd_db_phys = phys;
	}
	if (soc_rsc_phys != HAKIOS_RSC_DEFAULT || soc_cmd_db_phys != HAKIOS_CMD_DB_DEFAULT) {
		printf("hakios: SoC addresses from boot-args: RPMh TCS %#x, command DB %#x\\n", soc_rsc_phys,
		    soc_cmd_db_phys);
	}
}
"""

# Files that map one of the two blocks themselves, and the block argument they pass.
REDIRECT = {
    "hakios.cpufreq.c": ["RSC_PHYS"],
    "hakios.goodix.c": ["RSC_PHYS", "CMD_DB_PHYS"],
    "hakios.camera.c": ["RSC_PHYS", "CMD_DB_PHYS"],
    "hakios.wifi.c": ["CMD_DB_PHYS"],
    "hakios.adsp.c": ["CMD_DB_PHYS"],
}

# Files that keep the sequencer in a `struct block` and map it on first use: point the block at
# the port's address when the driver starts.
BLOCKS = {
    "hakios.wifi.c": ("hakios_wifi_init(void)\n{\n", "\trsc.phys = hakios_soc_rsc();\n"),
    "hakios.adsp.c": ("hakios_adsp_init(void)\n{\n", "\trsc.phys = hakios_soc_rsc();\n"),
}


def once(path: pathlib.Path, old: str, new: str, what: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new.split("\n")[0] in text and old not in text:
        print(f"  already: {what}")
        return
    if old not in text:
        sys.exit(f"anchor missing in {path.name}: {what}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"  patched: {what}")


def main() -> None:
    tree = pathlib.Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_TREE
    dev = tree / "bsd/dev"
    if not dev.is_dir():
        sys.exit(f"no kernel tree at {tree}")

    print("header:")
    header = tree / "bsd/sys/hakios.input.h"
    once(header, "#endif /* _SYS_HAKIOS_INPUT_H_ */", GETTERS + "\n#endif /* _SYS_HAKIOS_INPUT_H_ */",
         "getters declared")

    print("central init (hakios.input.c):")
    central = dev / "hakios.input.c"
    once(central, "void\nhakios_input_init(void)\n{\n", IMPL + "\nvoid\nhakios_input_init(void)\n{\n",
         "addresses read from boot-args")
    once(central, "\tint major = cdevsw_add(-1, &touch_cdevsw);\n",
         "\thakios_soc_args();\n\tint major = cdevsw_add(-1, &touch_cdevsw);\n", "called before the drivers")

    for name, macros in REDIRECT.items():
        path = dev / name
        text = path.read_text(encoding="utf-8")
        for macro in macros:
            getter = "hakios_soc_rsc()" if macro == "RSC_PHYS" else "hakios_soc_cmd_db()"
            # drop the #define, then point every use at the getter
            lines = [l for l in text.split("\n") if not l.startswith(f"#define {macro} ")]
            text = "\n".join(lines)
            uses = text.count(macro)
            if uses == 0 and getter in text:
                print(f"  already: {name} {macro} -> {getter}")
            else:
                text = text.replace(macro, getter)
                print(f"  patched: {name} {macro} -> {getter} ({uses} uses)")
        path.write_text(text, encoding="utf-8")

    for name, (anchor, line) in BLOCKS.items():
        path = dev / name
        text = path.read_text(encoding="utf-8")
        if line in text:
            print(f"  already: {name} block address")
            continue
        if anchor not in text:
            sys.exit(f"anchor missing in {name}: init entry")
        text = text.replace(anchor, anchor + line, 1)
        # the block's built-in address stays as the default for the first phone
        path.write_text(text, encoding="utf-8")
        print(f"  patched: {name} block address at init")

    print("done")


if __name__ == "__main__":
    main()
