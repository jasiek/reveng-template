# Does splitting a wave into more, smaller agents help? (wave run14 A/B)

*Kept in the template as a worked example of two things: the **result** (contiguity, not batch
size, is the lever — so do not spend a wave re-litigating the shape), and the **method** — a
pre-registered A/B is how an orchestration question gets settled here, because both of the
intuitions below turned out to be wrong. `docs/ORCHESTRATION.md` rule 15. The wave numbers and
address ranges are the reference campaign's; the design transfers verbatim.*

Pre-registered 2026-08-27, **before any results were seen**. The design, the measurements and
the prediction below were written and committed while the 18 agents were still running, so the
conclusion at the end cannot be a post-hoc rationalisation of whatever came back.

## The question

The standing wave shape is 6 agents × 30 targets. Would 12 agents × 15 targets be cheaper or
more effective? The intuition for "yes" is that a smaller context per agent is cheaper per agent
and easier to reason over. The intuition for "no" is that the playbook's biggest yield lever is
*subsystem coherence within a batch* — adjacent functions are the same subsystem, so an agent's
early decompiles inform its later ones, and halving the batch halves that effect.

## Design

- **360 targets**, the tightest contiguous run of eligible unnamed functions,
  `0x0300C690–0x030366E8`.
- Eligible = unnamed, non-thunk, not already in the ledger, **and not in a quarantined residue
  file** (`ledger/run1{0,1,2,3}_residue.txt`), so neither arm is loaded with known-impossible
  stubs.
- **Interleaved assignment.** The 360 are sorted by address and cut into twelve contiguous
  blocks of 30. Even blocks → arm A, odd blocks → arm B. Both arms therefore span the *same*
  address territory with the same difficulty distribution; neither gets "the easy half".
  - **Arm A: 6 batches × 30** (each batch = one whole 30-block, contiguous)
  - **Arm B: 12 batches × 15** (each odd block split into two 15s, each still contiguous)
- **Identical brief.** Both arms were emitted from the same
  `scratchpad/run14_prompt_common.txt` via `tools/emit_batch_prompts.py`. Agents were not told
  an experiment was running, so neither arm could try harder.
- Same model (Sonnet) for all 18 agents.
- **Launched simultaneously.** Bridge contention is not treated as a confound to apologise for:
  more concurrent agents contending for one Ghidra bridge is a genuine cost of the strategy under
  test, and both arms experience the same aggregate load.

## What is measured

From the live-Ghidra diff (`tools/verify_wave.py`), never from agent self-reports:

1. **Landed per arm** out of 180 — the headline yield.
2. **Landed per agent** — the productivity of a unit of fixed overhead.
3. **Reconciliation burden** — duplicate names and collisions *within* each arm, i.e. how much
   driver work each arm generates. Two agents inventing the same prefix for different things has
   cost real time twice in this campaign.
4. **Accuracy** — a driver-decompiled sample from each arm. Coverage is not correctness.

## What is NOT measured, and why

**Token cost per agent is not visible to the driver.** There is no per-agent accounting exposed,
so this experiment cannot produce a direct cost-per-name figure. What it can do is measure yield
at equal target count and equal model, and count the agents — the fixed overhead per agent (read
the ~100-line brief, one ToolSearch, a collision check per rename, a result file) is real and
scales with agent count. Any cost claim below is inference from those two, and is labelled as
such.

## Prediction, recorded in advance

Arm A (6×30) lands **more** than arm B (12×15), and the gap comes mostly from batches where a
subsystem spans more than 15 functions. Arm B generates **more** duplicate/collision
reconciliation, because twice as many agents each choose names without seeing the others. I do
not expect a large accuracy difference between arms.

If arm B wins, or the arms tie on yield, the standing 6×30 shape should change — the halved
context would then be strictly cheaper for the same result.

---

## Results

Measured from the live-Ghidra diff, not agent self-reports.

| | Arm A — 6 × 30 | Arm B — 12 × 15 |
|---|---|---|
| Landed / 180 | **112 (62.2%)** | **109 (60.6%)** |
| Landed per agent | **18.7** | **9.1** |
| Duplicate names within arm | **0** | **0** |
| Collisions within arm | **0** | **0** |
| Confidence mix | 59 HIGH / 53 MEDIUM (53% HIGH) | 64 HIGH / 45 MEDIUM (59% HIGH) |
| Per-batch hit rate | 77, 63, 67, 73, 63, 30 % | 93, 27, 53, 53, 47, 40, 60, 67, 93, 73, 67, 53 % |
| Spread (stdev) | 15.2 pp | 18.9 pp |
| Driver accuracy audit | 4 / 4 accurate | 5 / 5 accurate |

## The prediction was wrong

Recorded in advance: *"Arm A lands more … Arm B generates more duplicate/collision reconciliation."*

- **Yield: a tie.** 112 vs 109 out of 180 is a 1.7 pp difference — three functions. Nothing
  survives that as a real effect, especially with arm A's spread running from 30% to 77% between
  its own batches.
- **Reconciliation: flatly wrong.** Arm B produced **zero** duplicates and **zero** collisions,
  exactly like arm A, despite having twice as many agents naming independently. The predicted
  mechanism did not appear at all.
- **Accuracy: no difference.** Nine names decompiled by the driver across both arms, all nine
  accurate, with honest confidence tags on both sides. Arm B in fact had the slightly *higher*
  HIGH fraction (59% vs 53%), which is well inside noise but certainly not worse.

## Why the coherence argument failed — the variable was misidentified

The case for large batches was subsystem coherence: adjacent functions share a subsystem, so an
agent's early decompiles inform its later ones. That argument was used to predict that halving the
batch would hurt. It didn't.

The reason is visible in the design: **every arm-B batch of 15 was still a contiguous address
run.** The experiment halved batch *size* while holding *contiguity* constant — and yield did not
move. So the lever is contiguity, not size. Wave run13 is the corroborating case from the other
direction: same 30-target batches, but *scattered* zero-caller targets, and its hit rate fell to
54% against 74% and 68% for the contiguous waves either side of it.

Restated: what matters is that a batch is a coherent run of neighbours. Whether that run is 15 or
30 long makes no measurable difference in this range.

## What this does and does not say about cost

It says **arm B needs twice the agents to produce the same result** — 9.1 landed per agent versus
18.7. Each of those extra six agents pays the same fixed toll: read the ~100-line brief plus the
subagent contract, one ToolSearch, a `search_functions` collision check per rename, a result file.
That overhead is per-agent and does not shrink with batch size, so at equal yield the 12-agent
shape strictly pays more of it.

It does **not** produce a token figure. Per-agent accounting is not visible to the driver, so
"twice the fixed overhead for the same output" is an inference from agent count, not a
measurement. The decompilation work itself is proportional to targets and identical across arms.

## Verdict

**Keep 6 × 30.** Not because bigger batches name better — they demonstrably do not — but because
the same yield from half the agents carries half the fixed overhead. Splitting finer buys nothing
that was hypothesised for it: no accuracy gain, no reconciliation cost, no yield change.

Two caveats worth carrying:

- **The comparison is at equal target count.** If wall-clock matters more than token cost, arm B
  finished its batches noticeably sooner (all twelve reported before four of arm A's six), because
  each agent carried half the work. Twelve smaller agents are a reasonable choice when latency is
  the binding constraint rather than cost.
- **One arm-B agent reported `batch_decompile` returning "Function not found" for 7 of 15 live
  targets**, which then decompiled fine individually. That is consistent with contention under
  18-way concurrency, but only one agent hit it, so it stays an open question rather than a
  finding. If it is contention, it is a genuine cost of running more agents at once.

## The real lever is elsewhere

Neither arm was limited by batch size. Both were limited by unresolved constants and unnamed hub
functions — the same pattern as wave run13, where naming two event sinks (`Key_PostKeyEvent`,
`Key_ArmHoldTimer`) unlocked targets across four separate batches for about six driver tool calls.
Arm B's own reports repeat it: one agent noted that naming a single unnamed caller
(`FUN_0305C0D4`) would have unlocked four of its skips.

**A short driver pre-pass that names a band's hub and sink functions before fanning out is worth
more than any batch-size choice.** That is where the next optimisation should go.
