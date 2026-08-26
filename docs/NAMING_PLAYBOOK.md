# Function-Naming Playbook (reproducible, model-agnostic)

How to name the `FUN_*` functions in a large stripped firmware Ghidra project using fanned-out
subagents, and commit the results safely. Written so a DIFFERENT driver model and different
subagent model can reproduce the process. Companion to `FINDINGS.md` (discoveries),
`ledger/renames.csv` (the ledger) and `docs/ORCHESTRATION.md` (what to do differently).

Paths assume this repo layout and the `ghidra-mcp` MCP server. Target facts come from
`TARGET.md`.

## 0. Roles

- **Driver** (you): orchestrates. Never trusts a subagent's self-reported counts. Picks targets,
  launches subagents, VERIFIES against live Ghidra, commits.
- **Subagents**: each takes ~30 addresses, decompiles, and applies renames + plate comments
  directly in Ghidra via MCP. Their prose summaries are unreliable — treat their *effect on
  Ghidra* as the only source of truth.

## 1. Invariants (never violate)

1. **Live Ghidra is the source of truth, not agent reports.** Some models confidently claim
   "renamed 28" in 7 tool calls (impossible). After every wave, diff the live function list
   against the ledger to learn what ACTUALLY landed.
2. **One git commit per renamed function**, appended to `ledger/renames.csv`
   (`address,old_name,new_name,confidence,justification`). Commits are created by the DRIVER,
   never by subagents (avoids git-lock contention across parallel agents).
3. **Confidence is tagged** (HIGH / MEDIUM / LOW). MEDIUM = dataflow-inferred. Plate comments in
   Ghidra start with `[confidence: …]` so guesses are auditable and revertible.
4. **Never invent a role.** A wrong name is worse than none. Skip empty stubs, trivial
   single-global getters/setters, and opaque register glue.
5. **Save the Ghidra program** (`save_program`) at each wave boundary; commit the binary `.rep`
   DB periodically (git-tracked but a binary blob — commit per-batch, not per-function).

## 2. The wave loop (the core procedure)

Repeat until coverage plateaus:

1. **Pick ~180 targets** (see §3), split into 6 batch files of ~30:
   `scratchpad/<wave>_batch_{0..5}.txt` (comma-separated addresses).
   `python3 tools/make_batches.py --wave <wave> --strategy contiguous --count 180 --batches 6`
2. **Launch 6 subagents in parallel**, one per batch, with the prompt template in §6 plus
   `docs/SUBAGENT_CONTRACT.md`. Each writes its results to `scratchpad/result_<wave>_{i}.json`
   as the LAST step and sets each plate comment IMMEDIATELY after each rename (so an
   interruption is recoverable).
3. **Wait for all 6.** Ignore the prose summaries.
4. **Verify via live-Ghidra diff** (§4) → the authoritative set of what landed.
5. **Consolidate + reconcile collisions** (§5).
6. **Commit one-per-function** (§7), then `save_program`, then commit the DB + docs.
7. Update `FINDINGS.md` (new discoveries) and the coverage line.

## 3. Target selection (this determines yield)

Priority order — **use it in this order from wave 1**; it is the single biggest lever on
hit-rate (see `docs/ORCHESTRATION.md` §1).

1. **String-anchored functions** (early game): map defined strings → referencing functions via
   `get_bulk_xrefs` in chunks. This builds the spine that everything else hangs off.
   `tools/make_batches.py --strategy strings`
2. **Call-graph propagation**: callers/callees of already-named subsystem anchors.
3. **Contiguous-address batching** (the workhorse): sort remaining unnamed by ADDRESS and batch
   contiguously. Adjacent functions are almost always the same subsystem, so each batch is a
   coherent cluster → hit-rate jumps (~50% scattered → ~90%+ contiguous).
   `--strategy contiguous`
4. **Fresh-band tactic**: never re-process a picked-over band. Low-address regions accumulate
   hard stubs that get re-skipped every wave. Always take the **lowest un-swept** band, and
   record swept bands so they are not revisited. `--strategy fresh --min-addr 0x08040000`
5. **Zero-caller functions** (the hidden tail — this was ~245 real functions in the reference
   project): the static call graph MISSES functions reached only via function-pointer / jump /
   vector tables. They are invisible to caller-count ranking but MANY are real, nameable
   handlers. Get them from the full function list (not the call graph); in the subagent use
   `get_xrefs_to` on the function ADDRESS to find the dispatch-table reference for context.
   `--strategy zero-caller`
6. **Most-called-first** ranking (from `get_full_call_graph`, format=edges): useful for picking
   *anchors* early, but as a batching strategy it underperforms contiguous batching. Do not
   spend 15 waves walking the in-degree curve.

Quarantine hard stubs as you meet them and give them **one** final top-model pass at the end.

## 4. Verification: the live-Ghidra diff (do this EVERY wave)

```bash
python3 tools/verify_wave.py --wave <wave>          # queries live Ghidra over HTTP
python3 tools/verify_wave.py --wave <wave> --from-file <saved list_functions_enhanced json>
```

It reports, for the wave's target set:

- **landed** — now non-`FUN_`, non-thunk, not already in the ledger → the authoritative set.
- **missing-meta** — landed but no result-file entry (an interrupted batch). Recover confidence
  and role from each function's plate comment (`get_plate_comment`), which the subagent set
  before dying.
- **collisions** — the new name already exists elsewhere in the ledger.
- **dups** — the same name assigned twice within this wave.

It writes `scratchpad/<wave>_consolidated.tsv` (ready for §7) and
`scratchpad/<wave>_orphans.json`. The live name in Ghidra is AUTHORITATIVE for the ledger —
agent JSON may disagree; trust Ghidra.

## 5. Consolidation & collision reconciliation

- **Name collides with an existing ledger name** (different address, same name): the two are
  genuinely different functions. Rename the NEW one to a distinct name in Ghidra
  (`rename_function_by_address`, strict_mode=false), and use that in the ledger. Decompile both
  if needed to pick a meaningful distinguisher (e.g. `Radio_ApplyModeChange` vs
  `Radio_ApplyBandChange`).
- **Dup within the wave**: same as above.
- **Exclude thunks**: `thunk_FUN_*` and inherited thunk names are not genuine renames — drop.
- **Cheapest collision prevention** needs no new infrastructure: have the subagent
  `search_functions` for the name before renaming, plus driver-side dedup here.

## 6. Subagent prompt template

Launch with the Agent tool, `model: <MODEL>`, `subagent_type: general-purpose`. Fill the
`<…>` from `TARGET.md`, and append `docs/SUBAGENT_CONTRACT.md` verbatim.

```
Naming functions in <PROGRAM> (Ghidra, ghidra-mcp MCP). <CPU>, <RTOS>.
~<N> functions already named. Targets are deep-tail unnamed functions, ADDRESS-CONTIGUOUS
(adjacent = same subsystem). Some have NO direct callers (reached via pointer/jump/vector
tables) — for those, get_xrefs_to on the ADDRESS + read the body.

SETUP — ONE ToolSearch call selecting: decompile_function, rename_function_by_address,
get_function_callees, get_function_callers, get_xrefs_to, set_plate_comment, batch_decompile,
search_functions (add disassemble_function for a stub-confirming final pass).

TARGETS: read comma-separated addresses from <BATCH_FILE>. Stay inside this band.

NAMED CLUSTERS to reuse as prefixes: <paste the current list from docs/NAMING_CONVENTIONS.md>

SKIP DISCIPLINE: SKIP empty `return;`/`bx lr` stubs, trivial single-global getters/setters with
no context, and opaque register writes you cannot map. Do NOT invent a role.

METHOD: batch_decompile in groups of ~8; infer each role from structure + named callees + the
ONE caller / xref site. HIGH only when unambiguous, MEDIUM when strongly implied, else SKIP.
Set the plate comment IMMEDIATELY after each rename: "[confidence: HIGH|MEDIUM] <one line role>".
Write the output file LAST. Names: valid C identifiers, PascalCase, <40 chars. Do NOT rename
non-FUN_ functions.

OUTPUT — Write <RESULT_FILE> = {"renamed":[{addr,old,new,confidence,justification}],
"skipped":[{addr,reason}]}. Justification has NO COMMAS. DO NOT run git.
RETURN only a 3-line count summary (the driver verifies against live Ghidra, not your report).
```

## 7. Per-function commit (driver-side)

```bash
./tools/commit_renames.sh scratchpad/<wave>_consolidated.tsv "<MODEL>"
```

Then `save_program` and `git add -A && git commit` for the binary DB + `FINDINGS.md`.

## 8. Model tiering (empirical, from the reference campaign)

| Model tier | Hit rate (fresh band) | HIGH share | Skip discipline | Self-report | Use for |
|---|---|---|---|---|---|
| Small/cheap | ~96% | ~50% | weak (names un-nameable things) | unreliable | cheap bulk on easy clusters |
| Mid | ~94% | ~65% | good | good | DEFAULT for the tail |
| Frontier | ~90%+ on hardest | high | strict | good | final cleanup; hardest residue |

- **Read the hit-rate column as a warning, not a recommendation.** The cheap tier scores
  *highest* precisely because its skip discipline is weakest: it names the un-nameable. In the
  reference project it named a function the frontier tier had explicitly skipped, and reported
  "22 renames in 7 tool calls" — arithmetically impossible. Coverage ≠ correctness.
- **Audit before trusting a cheaper model**: sample ~10 of its names, decompile them yourself,
  check each is *accurate* — not merely that a name exists. Minutes of work, and the only thing
  separating a good wave from a plausible-looking bad one.
- **Cost the error asymmetrically.** A skipped function costs one re-run of a slice. A wrong
  name propagates into the next wave's context and into `FINDINGS.md`, and surfaces phases
  later in a fact-check sweep. Cheap tokens, expensive corrections.
- Recommended sequence for a big remainder: **mid tier over everything**, then **one frontier
  pass** over what it skipped/left.

## 9. Crash / rate-limit recovery (happens often with big waves)

If the driver process dies or a wave is interrupted mid-flight: **the Ghidra process keeps
whatever renames already landed.** Recover with the SAME live-Ghidra diff (§4), i.e.
`/re-verify`:

1. Reconnect the MCP tools.
2. Diff live function list vs `ledger/renames.csv` → orphan renames (applied, not yet in ledger).
3. Recover their confidence/role from plate comments (`get_plate_comment`).
4. Commit them; `save_program`.
5. Recompute the still-`FUN_` subset of the wave and relaunch only those.

Because subagents set plate comments immediately and the diff is authoritative, interruptions
cost nothing but a re-run of the unfinished slice.

## 10. Stopping criteria

- Track the per-batch **skip rate** and **HIGH share**. When skip rate is dominated by confirmed
  empty stubs / thunks / dead code across models, you have hit the floor.
- Realistic ceiling for a stripped firmware: **~95–97%**. The residue is genuinely un-nameable
  (empty `bx lr` stubs, compiler thunks, unreachable code, a few opaque dispatch handlers) —
  naming it would be inventing labels. Stop there; do not force it.
- Final deliverables: `ledger/renames.csv` (replayable, confidence-tagged), `FINDINGS.md`
  (architecture + discoveries), the saved Ghidra DB, and one commit per function.
