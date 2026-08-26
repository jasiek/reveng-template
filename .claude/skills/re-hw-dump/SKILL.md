---
name: re-hw-dump
description: Dump the radio's flash over SWD to recover the bootloader, which vendor update files almost never contain. Use when the user asks about the bootloader, secure boot, image authentication, dumping the MCU, ST-Link/OpenOCD/JTAG/SWD, or when triage shows the update file starts above the flash base.
---

# Dump the flash over SWD

The bootloader is where firmware authentication lives, and vendor update files
almost never include it. If the project's question is "can I run custom
firmware?", this is the phase that answers it.

**This touches hardware the user owns and can brick. Read the safety section, and
confirm with the user before running anything that is not read-only.**

## 1. Establish what you are attaching to

Ask the user to photograph the board into `tools/swd/board_photos/` — MCU
markings, flash chip, debug pads. The marked part is often *not* what the firmware
looks like: a GD32F303 presents as an STM32F103 in every way except its DAP IDCODE
(0x2ba01477 vs ST's 0x1ba01477), which makes stock OpenOCD configs reject it.
`tools/swd/targets/` has configs for that case.

## 2. The non-obvious part: getting the core to respond

With the stock firmware running, SWD usually will **not** attach. The application
remaps the SWD pins (PA13/PA14 on STM32/GD32) within milliseconds of boot, and
NRST is typically not wired to the debug header, so connect-under-reset cannot
help either.

**Put the radio into its firmware-update / bootloader state first** — normally a
power-on button combination — which leaves SWD alive, then attach. Everything in
`tools/swd/` therefore attaches passively: `reset_config none`, and it never
issues `reset halt`, because a reset drops the radio back into the running
application and kills the connection.

If the user does not know the button combination, it is usually in the vendor's
update instructions.

## 3. Probe — read-only

```bash
./tools/swd/probe.sh tools/swd/targets/<mcu>.cfg
```

Four things must look right before going further: the core string, the readout
protection level, the flash size, and a plausible vector table at the flash base.

**If readout protection is on, stop.** A dump would return zeros or garbage that
looks like a real image and would waste days. Do **not** clear the protection: on
these parts that mass-erases the flash and destroys the firmware you came for.
Report the situation to the user and stop.

## 4. Dump

```bash
./tools/swd/dump.sh tools/swd/targets/<mcu>.cfg <flash_size> <boot_size>
```

Reads the flash twice and byte-compares the two reads. Treat a mismatch as fatal
and re-run — a silently glitched dump is expensive.

## 5. Make sense of the dump

```bash
python3 tools/triage.py tools/swd/dumps/flash_<ts>.bin
```

It reports every vector table in the image, so you learn exactly where the
bootloader ends and the application begins rather than assuming 16 KiB.

**Then cross-check against the vendor update file.** Where the two are
byte-identical you have proved the update file's load offset; where they differ is
the region the update file does not cover. This comparison caught a real error in
the reference project.

## 6. Import as its own program

The bootloader gets its own Ghidra program, its own base address, and its own
ledger (`ledger/renames_bootloader.csv`). Do not merge it into the application
program. Record both programs in `TARGET.md`, and remember to pass `program=` on
MCP calls once two are open.

## 7. Then answer the real question

With the bootloader reversed, the headline question — "is the image
authenticated?" — becomes answerable. Because that answer changes the project's
direction, run `/re-refute` on it before writing it down as fact.
