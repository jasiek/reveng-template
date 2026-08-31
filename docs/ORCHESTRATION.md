# Standing instructions for the driver / orchestrator

Distilled from a completed campaign on a 3000-function stripped HT firmware (28 naming runs, a
SRAM/typing/struct pass, an SWD + bootloader phase, a codeplug campaign, and a doc fact-check).
**Read this before launching any fan-out.** The playbook says *how*; this says *what we would do
differently*.

## The ten

1. **Fix the target ordering — this is the single biggest win available.** Walking the
   call-graph in-degree curve gave 50–70% hit rates for 19 runs. Switching to
   **address-contiguous** batching, then to **fresh, never-swept bands**, took it to **96%**.
   The final run swept **zero-caller** functions (invisible to the call graph, reached only via
   pointer/jump/vector tables, found with `get_xrefs_to` on the *address*) and cracked ~245 more.
   Do it in that order from wave 1: string anchors for a spine → contiguous fresh bands, lowest
   un-swept first → zero-caller sweep. Never re-process a picked-over band; quarantine hard stubs
   for one final top-model pass. This ordering alone would have saved ~15 waves.

2. **If it's derivable, script it — don't spend agents on it.** The best cost/benefit of the
   whole project was the SRAM typing pass: 2106 scalar + 1053 array types applied by a Ghidra
   script (the type follows from the Hungarian prefix), 0 failures, **zero agent tokens**;
   likewise 157 width ambiguities resolved deterministically from the observed access width
   (`ldrb`/`ldrh`/`ldr`). Before every fan-out ask: is this a *judgment* call or a *rule*?
   Agents for judgment, `run_script_inline`/Jython for rules.

3. **Budget in windows, not in tasks.** The ceiling is ~2.8–3.2M subagent tokens per 5-hour
   rolling window. Size batches at ~1M, fire back-to-back until agents start reporting limit
   errors, then stop and resume at the reset. **Regenerate the worklist from live Ghidra at the
   start of every window** — never resume from a stale list. That one habit makes partial
   failure self-healing.

4. **Verify by diffing live Ghidra; never by reading agent reports.** (Playbook invariant §1 —
   restated because it is what made every crash recovery free.) `python3 tools/verify_wave.py`.

5. **Kill the plan's load-bearing assumption in phase 0.** The reference project's codeplug plan
   asserted that four serial opcodes wrote codeplug records; phase 4 proved they were the
   *factory RF-calibration* protocol — after three phases had been built on top. Write the
   central assumption as **one falsifiable sentence** in `TARGET.md` and spend one agent trying
   to refute it *before* building on it.

6. **Adversarially verify anything that changes project direction.** "No firmware authentication
   at either layer" is trustworthy because it got a dedicated refutation pass. Any headline claim
   gets one agent whose only job is to break it.

7. **Cross-check against external ground truth whenever it exists** — an open-source CPS for the
   codeplug layout, an SWD flash dump against the vendor update file. It caught real errors both
   times. List what is available in `TARGET.md` § "Ground truth available".

8. **Every prose claim carries an address, and docs get a scheduled fact-check wave.** In the
   reference project a scrambled task table survived a month; a GPIO port mix-up, a wrong
   signature-string claim, and stale counts all survived until a sweep parsed every statement in
   every `.md` against live Ghidra. Make `/re-factcheck` **the last wave of each phase**, not an
   afterthought.

9. **Commits: driver only.** One per named unit + ledger row; the binary `.rep` DB batched.

    **Never hand-copy the PREFIXES line from the previous wave's prompt.** Regenerate it from
    `docs/NAMING_CONVENTIONS.md` — which is itself regenerated from the live program — every
    single wave. In wave 8 the driver normalised `RF_`→`Rf_` in the program and *then* pasted
    wave 7's prompt verbatim, which still said `RF_`; three agents dutifully reintroduced the
    drift the driver had just spent five commits removing. The prompt is an input to the
    artifact, so a stale prompt silently rewrites the artifact back. Same rule as rule 8: the
    live program is the source, and anything copied forward is a stale claim until re-derived.

10. **In the reimplementation phase the same discipline applies:** every transcribed-magic block
    cites the stock function + address it came from, so it stays auditable and re-derivable.

11. **The driver must not retype anything the tools can emit — addresses least of all.**
    In wave 9 the driver hand-typed six 30-address target lists into subagent prompts instead of
    reading `scratchpad/9_batch_*.txt`. All 180 were fabricated. The failure did not stop at wrong
    addresses: the invented lists had regular strides, so the driver "noticed" a family of
    near-identical handlers differing by one constant, made that the centrepiece of three briefs,
    and sent agents hunting for a discriminator that did not exist. When the first agent reported
    the addresses were wrong, the driver "verified" it was mistaken — by checking the real batch
    file against Ghidra rather than the list it had actually sent, thereby validating the wrong
    thing and contradicting a correct agent. Six agents each rediscovered the problem alone.

    Three properties made this expensive, and all three are worth generalising:
    - **Fabrication is invisible to its author.** Every address was well-formed, in-range and
      plausibly spaced. Nothing about it looked wrong from the inside.
    - **It manufactured a false signal.** The strides were an artifact of invention, but they read
      as a discovery about the firmware, and the driver reasoned onward from them.
    - **The obvious check can be aimed at the wrong object.** Verifying "the batch file is
      correct" says nothing about what was transmitted. Verify the thing you actually sent.

    The fix is structural, not vigilance. `tools/emit_batch_prompts.py` writes a prompt that tells
    the agent to `cat` its own batch file, and refuses to emit if any target is not a live function
    entry — so a stale or malformed list fails loudly at the driver instead of quietly across six
    agents. The prefix line is generated from `docs/NAMING_CONVENTIONS.md` (rule 9). Generalise it:
    if a value can be derived, deriving it is not an optimisation, it is the correctness argument.

12. **`CAMPAIGN_STATE.json` is the resume contract.** `tools/campaign_state.py snapshot` derives
    it from live Ghidra plus the ledger; `status` prints it. It exists because these campaigns
    outlive their sessions, and prose handoff notes rot while derived state cannot. It surfaces
    the one thing a resuming agent most needs and would otherwise have to notice: **renames that
    are in the program but not in the ledger** (live named minus ledger rows). Snapshot at every
    wave boundary, commit it, and put non-derivable open items in `notes`.

13. **Audit the substrate before scaling work on top of it.** The disassembler, the processor
    module, the analyser and the bridge are artifacts written by someone else, and a campaign
    multiplies whatever they get wrong by 3000 functions. The specific case that cost this
    project a re-run: a third-party sleigh module that stopped at two unimplemented opcodes
    (16 functions truncated, one to a third of its real length) and produced **0** for every
    high-immediate load, so every peripheral address in the image resolved to a tiny number —
    with a listing that looked perfectly healthy throughout. `/re-isa-audit`, before wave 1.

    Generalised: **before a fan-out, ask what would have to be true of the tools for the output
    to mean what you think it means, and test that one thing.** It is one script and an
    afternoon; redoing a phase is a week.

14. **When a question can be executed, do not infer it.** The judgement-call budget is finite and
    should be spent on things that cannot be run. Three sessions of this project were spent
    reconstructing a per-frame calling convention from decompilation — argument order, buffer
    slots, a flag word — and all three reconstructions were wrong in different ways, each
    producing believable output that was then explained with algorithmic theories. Running the
    *real* caller in the emulator, with the calls that leave the subsystem stubbed, settled it in
    one pass (`docs/ORACLE_PLAYBOOK.md` §4). The same move applies far outside emulation:

    - an omission you think is harmless → **poison the memory and re-run**; identical output is a
      result, an argument is not;
    - a probe or fixture you built → **validate the instrument first** (a clipping synthetic
      input once invalidated a day of amplitude conclusions);
    - a claim about an aggregate → **report per item**; a mean hid a working path and a broken
      one in the same run.

15. **Settle orchestration questions with a pre-registered A/B, not with intuition.** Write the
    design, the measurements and the *prediction* down and commit them **while the agents are
    still running**, so the conclusion cannot be a post-hoc rationalisation. `docs/BATCH_SIZE_EXPERIMENT.md`
    is the worked example, and its prediction was wrong in both directions — which is the point:
    12x15 tied 6x30 on yield with zero extra collisions, so **contiguity is the lever, not batch
    size**, and the real gain was somewhere else entirely (the hub/sink pre-pass, rule 1b of the
    playbook). Two intuitions that felt obvious were simply false, and only the measurement said so.

## Do agents need a messageboard?

**Mostly no for the naming work — and Ghidra already is the board.** Batches are
address-contiguous, so agents work on disjoint subsystems; the state that actually matters
(names, plate comments, labels, types) is written into Ghidra live and is instantly visible to
every peer. Free-form chat would erode the property that made the campaign reliable — *prose is
not evidence* — by letting one agent's hallucinated claim become another's premise (cheap-tier
waves produced "22 renames in 7 tool calls"-grade self-reports). Chatter also spends the scarcest
resource, window tokens, and broadcast reads scale O(N²).

Where coordination genuinely *was* missing, the fix is a **structured, append-only,
evidence-anchored board that agents WRITE to and only the driver READS**:

1. **Name claims** — cross-wave and within-wave collisions were all reconciled post-hoc. Cheapest
   fix: `search_functions` for the name before renaming, plus driver-side dedup.
2. **Leads queue** — one primitive (a GF(2⁸) `xtime`) unlocked a whole AES/RC4 cluster, but only
   at the next wave boundary. One line per lead (address, observation, why interesting), drained
   by the driver to seed the next wave's targets, would have compressed three runs into one.
3. **Conflict log** — contradicting evidence, per the subagent contract.
4. **Living glossary** — the prefix vocabulary drifts (`UI_`/`Ui_`, `Storage_`/`Nvm_`/`Flash_`).
   Driver-owned, read-only to agents, regenerated each wave from the names actually in the
   program (`docs/NAMING_CONVENTIONS.md`).

**Preferred medium: not a text file — Ghidra's own metadata.** `add_function_tag` for
claims/subsystems, `set_bookmark` for leads and conflicts. Then the board is queryable, versioned
with the DB, and structurally incapable of drifting from the artifact it describes.

## Fan-out sizing cheat sheet

| Work | Shape | Agents | Notes |
|---|---|---|---|
| String-anchor spine | 1 batch/subsystem | 3–6 | early; highest confidence names |
| Contiguous tail | ~30 addrs/agent | 6 | the workhorse; ~1M tokens/wave |
| Zero-caller sweep | ~30 addrs/agent | 6 | needs `get_xrefs_to` on the address |
| Global/SRAM typing | **script** | 0 | rule, not judgment |
| Struct recovery | 1 struct/agent | 2–4 | judgment; conflicts logged, never overwritten |
| Headline claim | 1 refuter | 1 | its only job is to break the claim |
| Doc fact-check | 1 doc/agent | 3–6 | last wave of every phase |
