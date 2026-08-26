---
name: re-name-wave
description: Run one function-naming wave — pick targets, fan out parallel subagents that rename and plate-comment in Ghidra, verify against the live program, and commit one-per-function. Use when the user says "name the functions", "run a wave", "keep naming", "grind", or when a large stripped firmware still has FUN_ functions left.
---

# Run one naming wave

Full procedure in `docs/NAMING_PLAYBOOK.md`; the standing corrections in
`docs/ORCHESTRATION.md`. This is the loop, not a summary of it.

**You are the driver.** You pick targets, you launch, you verify, you commit.
Subagents touch Ghidra and nothing else.

## 1. Regenerate the worklist from live Ghidra

Never resume from a stale list — that habit is what makes a partially failed wave
self-healing.

```bash
python3 tools/make_batches.py --wave <wave> --strategy contiguous --count 180 --batches 6
```

Strategy order across a campaign (this ordering is worth ~15 waves — see
`docs/ORCHESTRATION.md` §1):

1. **string anchors** — wave 1 only, to build the subsystem spine
2. **contiguous** — the workhorse, lowest un-swept band first
3. **fresh** (`--min-addr`) — once low bands are picked over
4. **zero-caller** — the hidden tail; do this before you conclude you are done

`make_batches.py` records swept bands, so it will not hand the same addresses out
twice. Quarantine hard stubs for one final frontier-model pass rather than
re-sweeping them every wave.

## 2. Launch the subagents

One agent per batch file, in a **single message** so they run concurrently.
`subagent_type: general-purpose`. Default to the mid model tier; use the frontier
tier for the residue pass (`docs/NAMING_PLAYBOOK.md` §8).

The prompt is the template in playbook §6 — filled in from `TARGET.md` — plus
`docs/SUBAGENT_CONTRACT.md` pasted verbatim, plus the current prefix list from
`docs/NAMING_CONVENTIONS.md`.

Non-negotiables to keep in the prompt:

- plate comment **immediately** after each rename, result file **last**
- **never run git**
- skipping is a first-class result; a wrong name is worse than none
- justifications cite an address, string, xref or constant — and contain no commas
- stay inside the assigned band; leads outside it go in a `set_bookmark`

## 3. Verify against live Ghidra — never against their reports

```bash
python3 tools/verify_wave.py --wave <wave>
```

Ignore the agents' prose summaries entirely; some models confidently report
renames they never made. The diff is the truth. It writes
`scratchpad/<wave>_consolidated.tsv`.

Then:

- **missing-meta** rows: `get_plate_comment` on each address to recover the
  confidence and role the subagent wrote there before it died, and fill the TSV.
- **collisions / dups**: the two functions are genuinely different. Rename the new
  one to a distinct name in Ghidra (`rename_function_by_address`, decompile both
  if you need a meaningful distinguisher) and use that name in the ledger.

## 4. Commit

```bash
./tools/commit_renames.sh scratchpad/<wave>_consolidated.tsv "<model>"
```

It refuses rows that still say UNKNOWN or RECOVER — that is deliberate. Then
`save_program` (MCP), then one commit for the binary `.rep` DB and `FINDINGS.md`.

## 5. Record and continue

Append a run entry to `FINDINGS.md`: strategy, targets, landed, HIGH/MEDIUM split,
new discoveries, new coverage percentage. Drain any leads the wave produced into
the next wave's targets.

Then **keep going**. Bulk campaigns are multi-hour and outlive a session; grind
until agents start reporting limit errors, then stop and resume at the next
window. Do not wind down early, and do not ask whether to continue — "grind",
"carry on" and "keep going" mean run the whole campaign.

## When to stop

When the skip rate is dominated by confirmed empty stubs, thunks and dead code
across model tiers. The realistic ceiling on a stripped firmware is ~95–97%.
Naming the residue would be inventing labels. Record what is left un-named and
why, in `FINDINGS.md` § Residue.
