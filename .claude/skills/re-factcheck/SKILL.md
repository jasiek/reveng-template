---
name: re-factcheck
description: Fact-check every prose claim in the project's markdown against the live Ghidra program. Use at the end of each phase, before publishing or handing off findings, or when the user asks whether the documentation is still accurate. Catches stale counts, wrong addresses, and claims that were never true.
---

# Fact-check the documentation against live Ghidra

Run this as **the last wave of every phase**, not as an afterthought. In the
reference project a scrambled task table survived a month, and a GPIO port mix-up,
a wrong signature-string claim and stale coverage counts all survived until a
sweep parsed every statement in every `.md` against the live program.

## The rule being enforced

**Every prose claim carries an address.** A claim with no address is a guess, and
this sweep is where guesses get caught.

## Procedure

1. **Inventory the claims.** For each `.md` in the repo (`FINDINGS.md`, `TARGET.md`,
   any subsystem docs), extract every factual statement: addresses, function
   names, register names, counts, offsets, protocol opcodes, "X calls Y", "Z is
   stored at W".

2. **Fan out, one agent per document.** Each agent verifies its document's claims
   against live Ghidra — decompile the cited function, check the address really
   holds what is claimed, confirm counts with `list_functions_enhanced` — and
   returns a list of `{claim, verdict, evidence}`. Verdicts are CONFIRMED,
   WRONG (with the correct value and its address), UNVERIFIABLE (no address cited
   — the claim needs one adding or removing), or STALE (was true, is not now).

3. **The driver applies the corrections.** Agents report; you edit. Fix the
   document, and where a claim was unverifiable either attach an address or delete
   the sentence.

4. **Refresh the counts** from `python3 tools/verify_wave.py --orphans` — coverage
   percentages, function totals, named/unnamed splits. Never carry a number
   forward from an earlier session's prose.

5. **Commit** the corrections as one commit per document, so the diff shows what
   was wrong.

## What to look for specifically

These are the errors that actually occurred, in rough order of likelihood:

- **stale counts** — every "N functions", "M%" written before the last wave
- **peripheral confusion** — GPIOB vs GPIOC, TIM2 vs TIM3, USART1 vs USART2:
  check the base address, not the name in the prose
- **address drift** — a claim written before a re-import or a base change
- **table scrambling** — rows in a hand-written table that no longer line up with
  their headings
- **claims with no address at all** — the biggest category, and the one that lets
  everything else hide

## Do not skip this because the docs "look fine"

The point of the sweep is that wrong claims read exactly like right ones. That is
why it is a mechanical pass over every statement, not a review.
