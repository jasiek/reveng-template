#!/usr/bin/env bash
# FULL FLASH DUMP via passive SWD memory reads. No flash-driver writes, no erase,
# no reset — purely reads memory.
#
# PREREQUISITE: run ./probe.sh first and confirm the core, the readout-protection
# level (must be off) and a plausible vector table. The radio must be in its
# firmware-update / bootloader state (see probe.sh).
#
# Usage: ./tools/swd/dump.sh [target.cfg] [FLASH_SIZE] [BOOT_SIZE] [FLASH_BASE]
#   FLASH_SIZE  default 0x100000 (1 MiB). Match what probe.sh reported.
#   BOOT_SIZE   default 0x4000 (16 KiB) — the bootloader carve. Set it to the
#               offset of the SECOND vector table that tools/triage.py found in
#               the dump; that offset is where the application starts.
#   FLASH_BASE  default 0x08000000.
#
# Produces, in dumps/ (timestamped): the full image, a second independent read
# for integrity, the carved bootloader, and the option bytes.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="${1:-${SCRIPT_DIR}/targets/gd32f303.cfg}"
SIZE="${2:-0x100000}"
BOOT_SIZE="${3:-0x4000}"
BASE="${4:-0x08000000}"
OPTBYTE_ADDR="${OPTBYTE_ADDR:-0x1FFFF800}"

cd "${SCRIPT_DIR}"
mkdir -p dumps
TS=$(date +%Y%m%d_%H%M%S)
OUT="dumps/flash_${TS}.bin"
VER="dumps/flash_${TS}.verify.bin"
BOOT="dumps/bootloader_${TS}.bin"
OPT="dumps/optionbytes_${TS}.bin"

echo "Dumping ${SIZE} bytes from ${BASE} (passive, no reset)..."
openocd -f "${CFG}" \
  -c "init" \
  -c "dump_image ${OUT} ${BASE} ${SIZE}" \
  -c "dump_image ${OPT} ${OPTBYTE_ADDR} 16" \
  -c "shutdown"

echo "Verification read (second independent dump)..."
openocd -f "${CFG}" -c "init" -c "dump_image ${VER} ${BASE} ${SIZE}" -c "shutdown"

echo
if cmp -s "${OUT}" "${VER}"; then
  echo "INTEGRITY: MATCH — two independent reads are byte-identical."
  rm -f "${VER}"
else
  echo "INTEGRITY: MISMATCH — read glitch. Keeping ${VER} for inspection:"
  cmp "${OUT}" "${VER}" | head
  echo "Re-run before trusting this dump. A silently glitched dump costs days."
fi

dd if="${OUT}" of="${BOOT}" bs=1 count="$((BOOT_SIZE))" status=none

echo
echo "=== Artifacts ==="; ls -la "${OUT}" "${BOOT}" "${OPT}"
echo; echo "=== sha256 ==="; shasum -a 256 "${OUT}" "${BOOT}" "${OPT}"
echo; echo "Vector table at ${BASE}:"; xxd -l 32 "${OUT}"
echo
echo "Next:"
echo "  python3 ../../tools/triage.py ${SCRIPT_DIR}/${OUT}"
echo "    -> confirms how many images this dump holds and where each one starts."
echo "  Compare against the vendor update file: a byte-identical region proves the"
echo "  update file's load offset; a difference is where the bootloader lives."
