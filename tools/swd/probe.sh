#!/usr/bin/env bash
# SAFE, READ-ONLY first contact with the target MCU. No erase, no write, no reset.
#
# Reports: DAP/core, device ID, readout-protection level, flash size, and the
# vector table at the flash base. Run this and read the output BEFORE dump.sh —
# dumping a read-protected part gives you a file full of zeros that looks real.
#
# Usage: ./tools/swd/probe.sh [targets/<mcu>.cfg]
#
# GETTING THE CORE TO RESPOND (the part that is never in the datasheet):
#   Many radios remap the SWD pins (PA13/PA14 on STM32/GD32) within milliseconds
#   of boot, and NRST is usually not wired to the debug header — so a normal
#   attach fails with "unable to connect to the target" and connect-under-reset
#   cannot help either. Put the radio into its firmware-update / bootloader state
#   FIRST (usually a power-on button combination), which leaves SWD alive, THEN
#   attach. That is why these scripts attach passively: reset_config none, and
#   they never issue `reset halt` — a reset would drop the radio back into the
#   running application and kill the connection.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="${1:-${SCRIPT_DIR}/targets/gd32f303.cfg}"

[[ -f "${CFG}" ]] || { echo "no such target config: ${CFG}" >&2
  echo "available:" >&2; ls "${SCRIPT_DIR}/targets/" >&2; exit 1; }

# Register addresses are Cortex-M / STM32-family; adjust per target config.
IDCODE_ADDR="${IDCODE_ADDR:-0xE0042000}"
OPTBYTE_ADDR="${OPTBYTE_ADDR:-0x1FFFF800}"
FLASHSIZE_ADDR="${FLASHSIZE_ADDR:-0x1FFFF7E0}"
FLASH_BASE="${FLASH_BASE:-0x08000000}"

echo "### OpenOCD passive probe (READ ONLY, no reset) — ${CFG##*/} ###"
openocd -f "${CFG}" \
  -c "init" \
  -c "echo {--- DBGMCU IDCODE (low 12 bits = DEV_ID) ---}" \
  -c "mdw ${IDCODE_ADDR}" \
  -c "echo {--- Option bytes (byte0 = readout protection) ---}" \
  -c "mdw ${OPTBYTE_ADDR} 4" \
  -c "echo {--- Flash size in KB ---}" \
  -c "mdh ${FLASHSIZE_ADDR}" \
  -c "echo {--- Vector table at the flash base (SP then reset vector) ---}" \
  -c "mdw ${FLASH_BASE} 8" \
  -c "shutdown"

cat <<EOT

Interpreting the results — all four must look right before you dump:
  * Core line names the expected part            -> connection is good.
  * Option byte0 == 0xA5 (STM32/GD32 F1)         -> RDP Level 0, flash is READABLE.
      Anything else (commonly 0x00) means readout protection is ON: do NOT dump,
      a dump would read back zeros or garbage that looks like a real image.
      Do not "fix" this by clearing RDP — on these parts that mass-erases the
      flash and destroys the firmware you came for.
  * Flash-size half-word                          -> e.g. 0x0400 = 1024 KB.
  * Vector table: SP in SRAM (0x2000xxxx) and a reset vector in flash -> real code.

If all four look right:  ./tools/swd/dump.sh ${CFG}
EOT
