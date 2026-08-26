---
name: re-refute
description: Adversarially verify a headline claim — spawn agents whose only job is to break it. Use before any conclusion changes the project's direction ("there is no secure boot", "opcode X writes the codeplug", "the update file contains the bootloader"), or when the user asks how confident we are in a finding.
---

# Try to break the claim

Two failures in the reference project came from claims that were never
adversarially tested: a plan built three phases on top of "these four opcodes
write codeplug records" (they were the factory RF-calibration protocol). The one
headline finding that held up — "no firmware authentication at either layer" — is
trustworthy precisely because it got a dedicated refutation pass.

## When to run this

- Any claim that **changes what we do next**.
- The **load-bearing assumption** in `TARGET.md` — before building phases on it,
  not after.
- Anything that would be embarrassing to be wrong about in public.

## Procedure

1. **State the claim as one falsifiable sentence.** If you cannot, that is the
   finding: the claim is too vague to test, and it needs sharpening before
   anything is built on it. Write it down with the addresses it rests on.

2. **Write down what would falsify it.** Concretely: "a call to a hash or
   signature routine anywhere in the update path", "a write to this flash region
   from any other function", "a second dispatch table". Do this *before* looking.

3. **Fan out refuters — 2 or 3, each with a different lens**, in one message so
   they run concurrently. Each agent's brief:

   > Your only job is to REFUTE this claim: `<claim>`. It was derived from
   > `<addresses/evidence>`. Assume it is wrong and find the evidence. Default to
   > "refuted" if you are uncertain. Report `{refuted: bool, evidence: [address,
   > what it shows]}`. Do not confirm it — confirmation is not your job.

   Distinct lenses beat redundancy. For a "no authentication" claim: one agent
   hunts crypto primitives and constants; one walks every write path into the
   flash region; one reads the bootloader's command dispatch for an undocumented
   opcode. Three identical skeptics find one failure mode; three different ones
   find three.

4. **Survives if the majority fail to refute it** — and only then. Record in
   `FINDINGS.md`: the claim, the refutation attempts, what each agent looked at,
   and why it failed to break it. That record is what makes the claim citable
   later.

5. **If it is refuted**, say so plainly and immediately, correct every document
   that depends on it, and re-plan. A refuted assumption caught in phase 0 costs
   an hour; caught in phase 4 it costs the phases in between.

## Cross-check against external ground truth first

If an independent source exists — an open-source CPS, a published protocol
description, a flash dump to compare against the vendor update file — check
against it *before* spending agents. It is cheaper and it caught real errors twice
in the reference project. Record what ground truth exists in `TARGET.md`.
