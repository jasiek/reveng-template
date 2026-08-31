# Patches to third-party tooling

Fixes this project needed in tools it does not own — a Ghidra processor module,
an analyser, a decoder. **One section per patch**, and each one records a real
defect that produced wrong analysis, not a preference.

Every section states, in this order:

1. **What it applies to** — tool, repo, version, and the exact file inside it.
2. **What was wrong**, quoting the original.
3. **How it was proven wrong** — the evidence, not the reasoning. An independent
   decoder's opcode table; surrounding code that only makes sense under the new
   reading; a numerical result the old semantics could not produce.
4. **The impact on this image** — how many sites, and what the wrong output
   looked like. This is what tells a future reader whether to re-derive anything.
5. **The fix**, and the command to rebuild:
   `<ghidra>/support/sleigh -a <extension>/data/languages`, then restart Ghidra.

Standing rules, learned the hard way (`docs/ISA_AUDIT_PLAYBOOK.md`):

- **Re-apply after every reinstall of the tool.** A silently reverted patch looks
  exactly like a firmware mystery.
- **Fix properly or leave visibly broken.** An encoding with no sites in this
  image, or with more than one plausible reading, stays unimplemented — a decode
  stop is loud, invented arithmetic is silent and propagates into every name and
  every document downstream.
- **A sleigh patch changes nothing until the program is re-disassembled.** Ghidra
  does not retry a decode it has already failed: run
  `ghidra_scripts/RepairStops.java` and record the before/after counts.
- **Decode correctness and p-code correctness are different claims.** A patch
  that fixes the listing can still be semantically wrong; only execution tests
  that (`docs/ORACLE_PLAYBOOK.md`).

Keep the patches as `.patch` files here so they can be re-applied mechanically,
and cite the section from `docs/ISA_AUDIT.md`.
