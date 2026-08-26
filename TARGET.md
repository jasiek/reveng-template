# TARGET.md — the one target-specific file

> **STATUS: UNFILLED TEMPLATE.** This fork has not been bootstrapped.
> Run `/re-bootstrap firmware/<image>` and this file gets written for you.
> Every `<…>` below is a placeholder; delete this blockquote once it is filled in.

## Identity

| Field | Value |
|---|---|
| Radio / device | `<vendor + model, e.g. AnyTone AT-D878UV(2) PLUS DMR handheld>` |
| Firmware file | `<firmware/NAME.bin>` |
| Firmware version | `<version string found in the image + its address>` |
| SHA-256 | `<sha256 of the file as shipped>` |
| Obtained from | `<vendor update package / SWD dump / OTA>` |

## Silicon

| Field | Value |
|---|---|
| MCU (marked) | `<e.g. GD32F303VGT6>` |
| MCU (analysed as) | `<Ghidra language id, e.g. ARM:LE:32:Cortex / default>` |
| Peripheral map used | `<e.g. STM32F103xx.svd — closest fit, NOT exact>` |
| Flash size | `<e.g. 1 MiB>` |
| SRAM | `<e.g. 96 KiB @ 0x20000000>` |
| RTOS | `<e.g. uC/OS-II / FreeRTOS / bare superloop>` |

## Memory layout

| Region | Range | Notes |
|---|---|---|
| Bootloader | `<0x08000000–0x08003FFF>` | `<factory-flashed; present in the update file? y/n>` |
| Application | `<0x08004000–…>` | `<vector table SP / reset vector>` |
| SRAM | `<0x20000000–…>` | |
| Peripherals | `<0x40000000–…>` | |

- **Image base:** `<0x08000000>`
- **Container header stripped:** `<N bytes / none>` — the raw file offset of the vector table.
- **File-offset → VA:** `VA = file_offset - <header> + <image base>`

## Ghidra

| Field | Value |
|---|---|
| Project file | `<name>.gpr` |
| Program name (for `program=` args) | `<name>` |
| Second program (bootloader) | `<name_bootloader / not yet dumped>` |
| Function count at import | `<N>` (all `FUN_*`) |
| Defined strings | `<N>` |
| Symbols | stripped / present |

## Ground truth available

Anything external you can check the analysis against — this catches real errors.

- `<e.g. qdmr / dmrconfig source for the codeplug layout>`
- `<e.g. an SWD flash dump to compare against the vendor update file>`
- `<e.g. published serial-protocol notes>`

## Load-bearing assumption (phase 0)

State the central assumption of the current plan as **one falsifiable sentence**, then spend one
agent trying to refute it before building phases on top of it.

> `<assumption>`
>
> Refutation pass: `<not yet run / result + address evidence>`

## Current phase

`<0 triage | 1 naming | 2 globals | 3 bootloader | 4 subsystems | 5 reimpl>` —
`<one line on what is in flight and what the next move is>`
