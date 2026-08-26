# SWD dump procedure

Repeatable recipe for pulling flash (bootloader + application) off the radio's
main MCU with an ST-Link. **The bootloader is usually not in the vendor update
file** — this is normally the only way to get it.

## Steps

1. Identify the MCU from the board (photograph the markings into `board_photos/`)
   and pick or write a config in `targets/`.
2. Wire the ST-Link: `SWDIO`, `SWCLK`, `GND`, and 3V3 as a voltage sense. NRST is
   deliberately unused.
3. Power the radio into its **firmware-update / bootloader state** (a power-on
   button combination). With the stock firmware running, SWD will not attach —
   the application remaps the SWD pins within milliseconds of boot.
4. `./probe.sh targets/<mcu>.cfg` — read-only. Confirm all four lines it prints.
   **Stop here if readout protection is on.** Do not clear it: on these parts
   clearing RDP mass-erases the flash and destroys the firmware you came for.
5. `./dump.sh targets/<mcu>.cfg` — dumps flash, reads it a second time and
   byte-compares for integrity, carves the bootloader. Output lands in `dumps/`.
6. `python3 ../../tools/triage.py dumps/flash_<ts>.bin` — tells you how many
   images the dump holds and where each starts.
7. Import each image as its **own Ghidra program** with its own base address and
   its own ledger (`ledger/renames_bootloader.csv`). Record both in `TARGET.md`.

## Cross-check (worth the ten minutes)

Compare the dump against the vendor update file. Where they are byte-identical
you have proved the update file's load offset; where they differ is the region
the update file does not cover — normally the bootloader. In the reference
project this comparison caught a real error in the load address.

## Requirements

`openocd` 0.12+. `st-info`/`dfu-util` are usually not helpful: `st-info` cannot
enter SWD mode on clone silicon with an unknown IDCODE, and a radio's update mode
is often reached over SWD rather than USB DFU.

## Safety

`probe.sh` only reads. `dump.sh` only reads. Neither erases, writes, or resets.
Keep it that way — a debug session that bricks the radio ends the project.
