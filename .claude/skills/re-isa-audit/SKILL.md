---
name: re-isa-audit
description: Prove the Ghidra processor module actually decodes this CPU's instruction set — differential disassembly against binutils/LLVM, a decode-coverage scan, sleigh patches, and a non-destructive re-disassembly of everything the old module gave up on. Use before the first naming wave, whenever the language module is third-party, when functions look truncated or decompile to halt_baddata, when peripheral addresses come out absurd, or before any emulation.
---

# Audit the ISA before trusting a single name

Full procedure, with the traps: `docs/ISA_AUDIT_PLAYBOOK.md`. This is the loop.

**Everything downstream is built on the disassembler.** "Ghidra decoded it" and
"Ghidra decoded it correctly" are different claims. A third-party sleigh module
is a hand-written specification of somebody else's ISA: assume it is incomplete
until measured. It is *much* cheaper to find this before 3000 functions are named
from truncated bodies.

## 0. Decide how much of this is warranted

`get_metadata` / `TARGET.md` gives the language id. Ghidra-shipped ARM/x86/MIPS:
run step 1 only and expect zero. A third-party extension, or any plan to emulate:
do the whole thing.

## 1. Where does the disassembler stop? (no external tooling needed)

Run `ghidra_scripts/IsaGaps.java`. It reports every address whose fall-through
**or branch/call target** was never decoded, histogrammed by the encoding there,
plus the functions those stops truncate.

Also decompile the whole program and grep for `halt_baddata` — **stripping
`/* … */` first**, or plate comments describing an already-fixed one will report
healthy functions as broken forever.

Zero stops and zero `halt_baddata` is a real result. Report it and move on.

## 2. Is what it *did* decode correct?

Needs an independent decoder — binutils `--target=<arch>-elf` is the usual one
(§1 of the playbook). Build a one-instruction-at-a-time harness around
`print_insn_*` (worked example: `tools/isa_audit/examples/csky/`); never a linear
sweep, which desyncs on the first data island. Beware `objdump -b binary`: it can
silently drop whole instruction classes because a raw binary has no ELF
`e_flags`.

```bash
# in Ghidra:  DumpInsns.java scratchpad/ghidra_insns.txt
python3 tools/isa_audit/diff_ghidra_vs_binutils.py \
    --insns scratchpad/ghidra_insns.txt --decoder ./refdis \
    --region scratchpad/<slice>.bin:<lo>:<hi>
```

**Length mismatch = fatal** (a desync makes everything after it in that function
fiction). **Ghidra decodes where the reference rejects = fatal.** Mnemonic
disagreements are usually alias spellings — check each distinct *pair* once, and
prove the alias condition holds at every site rather than assuming it.

## 3. Is there a second wall behind the first?

Forward-sweep with the reference decoder from each stop point and list mnemonics
that appear nowhere in Ghidra's listing. Byte-scan each affected opcode *group*
for every encoding in it and count sites — that is also what justifies leaving
the zero-site encodings unimplemented.

## 4. Patch, and only where the answer is checkable

Patches go in `docs/patches/` with a README entry each: what was wrong, how it
was **proven** wrong, the impact on this image, the recompile command.

- Encoding placement can be derived; **semantics must be corroborated** — the
  reference decoder's opcode table, surrounding code that only makes sense under
  that reading, or a numerical result wrong semantics could not produce.
- **Fix properly or leave visibly broken.** Zero-site or ambiguous encodings stay
  unimplemented: a stop is loud, invented arithmetic is silent.
- Recompile: `<ghidra>/support/sleigh -a <extension>/data/languages`, restart Ghidra.

## 5. Repair the program — the patch alone changes nothing

Ghidra never retries a decode it already failed. Run `ghidra_scripts/RepairStops.java`:
it re-disassembles each stop and fixes up the containing function's body,
iterating, and **never removes the function** — names, signatures, parameter
names and plate comments survive. Do not use a remove-and-recreate repair script
on a program that has a naming campaign's plate comments in it.

## 6. Re-verify and record

Re-run steps 1–2 and write the before/after table into `docs/ISA_AUDIT.md`:
instructions decoded, length mismatches, stops, `halt_baddata` functions, bytes
covered per region. Every claim carries an address. A remaining stop in unmapped
memory (mask ROM) or reached only from an impossible address is **not** an ISA
gap — say so explicitly.

Then: `save_program`, commit the DB and the doc.

## 7. Hand the consequences back to the campaign

- Functions that grew were named from a fraction of their body → feed them into
  the next `/re-name-wave`.
- Coverage denominators computed before the repair are stale → recompute.
- Anything derived from arithmetic the patched opcodes affected (MMIO maps,
  struct strides) → re-derive, do not spot-fix.
- **The p-code is still unproven.** Decode correctness says nothing about
  semantics; only execution tests those (`/re-oracle`).
