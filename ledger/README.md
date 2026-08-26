# The rename ledger

`renames.csv` — `address,old_name,new_name,confidence,justification`, one row per
named function, appended by `tools/commit_renames.sh` with **one git commit per
row**.

A second program (a bootloader dumped over SWD) gets its own ledger,
`renames_bootloader.csv`.

## Why it exists

The Ghidra `.rep` database is a binary blob: you cannot review it, diff it, or
replay it. The ledger is the reviewable, replayable form of the same information.
Given the same binary imported at the same base, `ghidra_scripts/ReplayRenames.py`
reconstructs every name and plate comment from this file.

That property is what makes the whole method safe to interrupt, and it is why the
commit granularity is per-function: `git log` on this file is a readable history
of how the firmware was understood, and any single name can be reverted with its
justification attached.

## Rules

- **The driver writes it, never a subagent.** Parallel agents committing causes
  git-lock contention.
- **The live Ghidra name wins** when it disagrees with what an agent reported.
- **No commas in justifications** — it is a CSV without quoting by design, so the
  file stays greppable and diffable.
- **Every row has a confidence tag and evidence.** `commit_renames.sh` refuses
  rows still marked UNKNOWN or carrying a RECOVER placeholder; recover them from
  the function's plate comment instead of inventing a justification.
