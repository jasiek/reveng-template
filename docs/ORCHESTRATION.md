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

10. **In the reimplementation phase the same discipline applies:** every transcribed-magic block
    cites the stock function + address it came from, so it stays auditable and re-derivable.

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
