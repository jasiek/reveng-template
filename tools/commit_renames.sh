#!/usr/bin/env bash
# Driver-side ledger append + one git commit per renamed function.
#
# SUBAGENTS MUST NEVER RUN THIS. Parallel agents committing causes git-lock
# contention; the driver owns every commit. (Playbook invariant §2.)
#
# Usage: ./tools/commit_renames.sh scratchpad/<wave>_consolidated.tsv "<model>"
#
# Input is the TSV written by verify_wave.py:
#   address<TAB>old_name<TAB>new_name<TAB>confidence<TAB>justification
#
# Rows still carrying UNKNOWN confidence or a RECOVER placeholder are REFUSED:
# recover them from the function's plate comment first. An unjustified ledger row
# is exactly what the ledger exists to prevent.
set -euo pipefail

TSV="${1:?usage: commit_renames.sh <consolidated.tsv> [model]}"
MODEL="${2:-unspecified model}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LEDGER="${REPO}/ledger/renames.csv"

cd "${REPO}"
[[ -f "${TSV}" ]] || { echo "no such file: ${TSV}" >&2; exit 1; }

if grep -qE $'\tUNKNOWN\t|RECOVER FROM PLATE COMMENT' "${TSV}"; then
  echo "REFUSED: ${TSV} still has rows with UNKNOWN confidence or a missing" >&2
  echo "justification. Recover them with get_plate_comment (the subagent set the" >&2
  echo "plate comment before it died) and edit the TSV, then re-run." >&2
  grep -nE $'\tUNKNOWN\t|RECOVER FROM PLATE COMMENT' "${TSV}" | head -10 >&2
  exit 2
fi

[[ -f "${LEDGER}" ]] || { mkdir -p "$(dirname "${LEDGER}")"
  echo 'address,old_name,new_name,confidence,justification' > "${LEDGER}"; }

n=0
while IFS=$'\t' read -r addr old new conf just; do
  [[ -z "${addr:-}" ]] && continue
  # Commas would corrupt the CSV; the contract says justifications carry none.
  just="${just//,/ }"
  printf '%s,%s,%s,%s,%s\n' "$addr" "$old" "$new" "$conf" "$just" >> "${LEDGER}"
  git add "${LEDGER}"
  git commit -q -m "Rename ${old} -> ${new} @ ${addr}

${just} [confidence: ${conf}]

Named by ${MODEL} subagent (verified against live Ghidra state)."
  n=$((n+1))
done < "${TSV}"

echo "committed ${n} renames to ledger/renames.csv"
echo
echo "Now, in this order:"
echo "  1. save_program            (MCP — persist the Ghidra DB)"
echo "  2. git add -A && git commit -m 'Wave <n>: Ghidra DB + findings'"
echo "     (the .rep DB is a binary blob: commit it per-batch, never per-function)"
echo "  3. update FINDINGS.md with what the wave discovered and the new coverage"
