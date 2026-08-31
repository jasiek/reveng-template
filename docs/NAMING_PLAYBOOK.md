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
1b. **Run the hub/sink pre-pass BEFORE emitting prompts** (added after wave run14's A/B):
   `python3 tools/find_hubs.py --wave <wave>`
   It ranks unnamed functions that many of this wave's targets call (SINKS) and unnamed functions
   with high program-wide in-degree (HUBS). **Name the top few YOURSELF, then write the brief so
   agents start with the answer.** A sink is invisible to any single agent - it sees only its own
   two or three calls - so only the whole-band view finds it.
   Wave run15 is the worked example: 15 driver tool calls identified the band as GCC soft-float
   plus libc and named 10 functions, after which six agents landed 128/143 = 89.5%, against
   74/68/54/62% for the four preceding waves. Caveat: that band was library code, which is
   inherently easier than radio logic, so the pre-pass does not own the whole gap.
   Two practical notes: driver pre-pass renames appear as UNKNOWN confidence in the consolidated
   TSV because `verify_wave` reads metadata from the agents' result JSONs - fill those rows from
   the plate comments before committing. And do not over-generalise from the sinks to the whole
   band: run15's brief claimed the band was all C runtime, and two agents correctly pushed back.

2. **Emit the prompts programmatically — never retype a target list:**
   `python3 tools/emit_batch_prompts.py --wave <wave> --brief scratchpad/run<NN>_prompt_common.txt`
   It writes `scratchpad/<wave>_prompt_{0..5}.txt`, each telling its agent to `cat` its own batch
   file, and it **refuses to emit if any target is not a live function entry**. Then launch 6
   subagents in parallel whose entire prompt is one line:
   `Read scratchpad/<wave>_prompt_<i>.txt and follow it exactly.`
   Each writes its results to `scratchpad/result_<wave>_{i}.json` as the LAST step and sets each
   plate comment IMMEDIATELY after each rename (so an interruption is recoverable).
   *Wave 9 is why this is mechanical: the driver hand-typed all six lists and fabricated 180
   addresses, then read a phantom "handler family" out of the fake strides — see
   `docs/ORCHESTRATION.md` rule 11.*
3. **Wait for all 6.** Ignore the prose summaries.
4. **Verify via live-Ghidra diff** (§4) → the authoritative set of what landed.
5. **Consolidate + reconcile collisions** (§5).
6. **Commit one-per-function** (§7), then `save_program`, then commit the DB + docs.
7. Update `FINDINGS.md` (new discoveries) and the coverage line.
8. **Snapshot the resume point:** `python3 tools/campaign_state.py snapshot`, and commit
   `CAMPAIGN_STATE.json`. It is derived from live Ghidra + the ledger, so it cannot drift.

## 3. Target selection (this determines yield)

Priority order — **use it in this order from wave 1**; it is the single biggest lever on
hit-rate (see `docs/ORCHESTRATION.md` §1).

0. **Known code first — anything with a public source of truth.** Before any judgement-call
   naming, sweep the parts of the image that are *not* this vendor's invention: the RTOS, the C
   runtime, the compiler's soft-float and integer helpers, and any third-party library whose
   banner string is in the image. Identify them at bootstrap from strings (`uC/OS-III Idle Task`,
   `FreeRTOS`, `Nucleus`, a GCC version banner, zlib/mbedTLS/lwIP banners) and record it in
   `TARGET.md`.

   Why it is first, and it is not just tidiness:
   - **They can be checked against ground truth.** A public header or source tree gives the real
     name, the real signature and the real semantics. These are the only names in the campaign
     that are *verifiable* rather than inferred — in the reference project 118 of 148 RTOS names
     landed HIGH confidence.
   - **They are the highest-value anchors.** Kernel and libc functions are called from everywhere,
     so naming `OSSemPend`, `memcpy` or `__aeabi_fdiv` gives every later agent context for
     hundreds of callers it has not seen. Naming vendor logic first buys nothing in the other
     direction.
   - **They are the cheapest yield in the campaign.** The reference project's one wave that
     happened to land on the GCC soft-float + libc band scored **89.5%** against 54-74% for the
     four waves around it. (Caveat, recorded honestly: library code is inherently easier, so the
     hub pre-pass in §2 step 1b does not own that whole gap.)
   - **They shrink the real problem.** Every function positively identified as library code is
     one that never needs a judgement call, and it stops later waves from re-deriving it. It also
     stops an agent inventing a radio-sounding name for `strtod`.

   Two cautions. Identify the *version* where you can — an RTOS API drifts between majors, and a
   name copied from the wrong major is a wrong name that looks authoritative. And do not
   over-generalise a band to "all C runtime": in the reference campaign a brief that claimed this
   was corrected by two agents who found real application code in the same band.

1. **String-anchored functions** (early game): map defined strings → referencing functions via
   `get_bulk_xrefs` in chunks. This builds the spine that everything else hangs off.
   `tools/make_batches.py --strategy strings`
2. **Call-graph propagation**: callers/callees of already-named subsystem anchors.
3. **Contiguous-address batching** (the workhorse): sort remaining unnamed by ADDRESS and batch
   contiguously. Adjacent functions are almost always the same subsystem, so each batch is a
   coherent cluster → hit-rate jumps (~50% scattered → ~90%+ contiguous).
   `--strategy contiguous`

   **Contiguity is the lever, NOT batch size.** Measured in wave run14 (`docs/BATCH_SIZE_EXPERIMENT.md`):
   6 agents x 30 and 12 agents x 15 over the same interleaved territory landed 112 and 109 of 180
   respectively — a tie — with zero collisions in either arm and no accuracy difference. Halving the
   batch cost nothing because each half was *still a contiguous run*. Keep 6x30 anyway: equal yield
   from half the agents means half the per-agent fixed overhead. Prefer 12x15 only when wall-clock,
   not token cost, is the binding constraint.
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

0. `python3 tools/campaign_state.py snapshot` — one command answers "where were we": coverage,
   per-batch landed counts, which batches never wrote a result file, and **how many renames are
   in the program but not in the ledger**. Start here; it turns recovery into a checklist.
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
