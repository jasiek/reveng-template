---
name: re-verify
description: Reconcile the live Ghidra program against the rename ledger — after a wave, or to recover after a crash, rate limit, or cleared context. Use when a session was interrupted mid-campaign, when the user asks "where were we", "what landed", "resume", or before trusting any coverage number.
---

# Reconcile live Ghidra with the ledger

The single most useful habit in the project: **the live program is the truth, and
recovery is cheap and always the same move.** Because subagents set plate comments
immediately after each rename, an interruption costs only a re-run of the
unfinished slice.

## Resume after a crash, rate limit, or cleared context

```bash
python3 tools/verify_wave.py --orphans
```

This reports, for the whole program:

- **orphan renames** — applied in Ghidra, not yet in the ledger. These are the
  renames the dying session earned. Recover their confidence and role from their
  plate comments (`get_plate_comment`, or `ghidra_scripts/ExportInventory.py` for
  bulk), write them into a TSV, and commit with `tools/commit_renames.sh`.
- **ledger disagrees with Ghidra** — Ghidra wins. Update the ledger row.
- **ledger ghosts** — a ledger row with no function at that address. Usually a
  wrong image base or a re-import; check `TARGET.md`.
- **still unnamed** — regenerate the worklist from this, never from a stale list.

Then relaunch only the still-`FUN_` slice. Do not re-run finished batches.

## After a wave

```bash
python3 tools/verify_wave.py --wave <wave>
```

See `/re-name-wave` step 3. The rule that matters: **ignore what the agents said
they did.** Prose is not evidence.

## Keep the glossary honest

```bash
python3 tools/verify_wave.py --glossary
```

Prints the prefix vocabulary as it actually exists in the program and flags drift
(`Ui_` vs `UI_`, `Nvm_` vs `Storage_`). Paste the result into
`docs/NAMING_CONVENTIONS.md` and into the next wave's subagent prompts. The
glossary is driver-owned and regenerated, never hand-maintained.

## If Ghidra is not reachable

`verify_wave.py` will say so. Either the GUI/plugin is not running — tell the user,
you cannot start it — or run `ghidra_scripts/ExportInventory.py` inside Ghidra and
pass the JSON with `--from-file`.

## Before reporting any number

Coverage percentages, "we named N functions", "the campaign is complete" — all of
these come from this tool, never from adding up what agents claimed. If you have
not run it this session, you do not know.
