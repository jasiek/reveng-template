# ISA audit — does the processor module actually decode this ISA?

**Run this before the first naming wave, not after the campaign.** Everything the
project produces — every name, every decompilation, every prose claim — is
downstream of the disassembler. "Ghidra decoded it" and "Ghidra decoded it
correctly" are different claims, and only one of them normally has evidence.

The risk scales with how exotic the target is:

| processor module | risk | audit |
|---|---|---|
| ARM, x86, MIPS, PowerPC (shipped with Ghidra, decades of use) | low | skim: run §2, expect zero stops |
| Ghidra-shipped but rare (SuperH, TriCore, RH850, HCS12, 6502 variants) | medium | §2 + §3 |
| **third-party sleigh module** (C-SKY, Xtensa, ARC, nios2, MCS-51 forks, anything from a GitHub extension) | **high — assume broken until measured** | the whole playbook |
| any module at all, if you will *emulate* or trust the decompiler's arithmetic | **high** — see §6 | the whole playbook + `docs/ORACLE_PLAYBOOK.md` |

The failure this catches is not cosmetic. A processor module can be wrong in
three independent ways, and they need three different tests:

1. **Decode coverage** — the disassembler stops at an unimplemented opcode.
   Everything after the stop, inside that function, is missing. Functions come
   out short and the decompiler emits `halt_baddata`. *Visible in the listing.*
2. **Decode correctness** — an instruction is decoded as the wrong instruction
   or the wrong length. A length error desyncs the stream: every instruction
   after it in that function is fiction that still *looks* like code.
   *Invisible from inside Ghidra.*
3. **P-code (semantic) correctness** — the mnemonic is right and the semantics
   the module attaches to it are wrong. The listing is perfect; the decompiler
   and any emulation are quietly wrong. *Invisible to any disassembler — §6.*

## 0. Establish the ISA independently of the part number

Do this at bootstrap, before choosing a language id. A vendor part number is a
claim; the bytes are the evidence, and the two should be made to agree.

- Look for the ISA's structural fingerprints in a histogram of aligned halfwords
  or words: call encodings, prologue/epilogue patterns, return instructions.
- Walk the stream with the ISA's *length rule* and check that call targets land
  aligned, in-range, and on plausible prologues. A wrong ISA produces targets
  that are neither aligned nor clustered.
- Record the argument in `TARGET.md` under "How the ISA was established". If the
  part number arrives later and agrees, you have two independent lines of
  evidence instead of one assumption.

## 1. Find an independent decoder

The audit compares Ghidra against **a second implementation of the same ISA
written by someone else**. Re-reading the same sleigh is not evidence.

Sources, in order of preference:

1. **binutils** `opcodes/<arch>-dis.c` — exists for essentially every arch that
   has ever had a GCC port, and is usually written by the silicon vendor.
   Build `--target=<arch>-elf`; a couple of minutes, and the only network step.
2. **LLVM** (`llvm-objdump`, `llvm-mc --disassemble`) where the target exists.
3. **capstone** / **libopcodes** Python bindings, if the arch is supported.
4. The vendor's own ISA manual, hand-checked against the encodings that matter.
   Slowest, and the fallback when nothing else exists — but a manual settles the
   cases the other tools disagree about, so keep it to hand anyway.

**Drive the decoder one instruction at a time, at addresses Ghidra chose.** A
linear sweep by the reference decoder will desync on the first data island and
then disagree with Ghidra about everything, which tells you nothing.
`tools/isa_audit/examples/csky/cskydis.c` is a ~60-line worked example of such a
harness around binutils' `print_insn_*`; the same shape works for any arch.

### The `-b binary` trap

`<arch>-elf-objdump -D -b binary -m <arch>` **looks** like it works and can be
silently, partially wrong: many `*-dis.c` decoders gate whole instruction
classes on `mach_flag`, which comes from the ELF header's `e_flags` — which a
raw binary does not have. In the reference campaign this made every 32-bit
C-SKY instruction print as `.long: 0x0000cXXX`, which reads like a literal pool
rather than like a failure. Wrap the slice in a real ELF with correct `e_flags`
(`examples/csky/mkelf.py`), or set `info.mach` directly in your own harness.

## 2. Measure decode coverage — where does the disassembler stop?

```
# in Ghidra (Script Manager, or run_script over MCP)
IsaGaps.java
```

Reports every address where an instruction's fall-through **or branch/call
target** is bytes Ghidra never decoded, histogrammed by the encoding sitting
there, plus the functions those stops truncate.

Two things about that scan are load-bearing and were both learned by getting
them wrong:

- **Scan flows, not just fall-through.** A *call or branch* into never-decoded
  bytes costs the decompiler exactly what a fall-through into them does, and a
  fall-through-only scan cannot see it. In the reference campaign the
  fall-through scan found 20 stops; widening to `Instruction.getFlows()` found
  **69 more**, nearly all newly exposed by fixing the first 20.
- **A defined data item at the target is not a stop.** Somebody deliberately
  called it data; skip it, or the report drowns in literal pools.

Decode the histogram's encodings with the reference decoder. You now know
exactly which opcodes are unimplemented, and how many sites each has.

## 3. Measure decode correctness — differential disassembly

```
DumpInsns.java scratchpad/ghidra_insns.txt      # addr len mnemonic bytes
python3 tools/isa_audit/diff_ghidra_vs_binutils.py \
    --insns scratchpad/ghidra_insns.txt --decoder ./refdis \
    --region scratchpad/iram.bin:10000:2f098 \
    --region scratchpad/flash.bin:300c000:30de000
```

Read the result in this order:

| finding | severity | meaning |
|---|---|---|
| **length mismatch** | fatal | one decoder desynced; everything after it in that function is fiction |
| **Ghidra decodes, reference rejects** | fatal | Ghidra invented an instruction |
| **mnemonic disagreement** | check each *pair*, once | usually alias spellings, sometimes a silent semantic error |

Do not wave mnemonic disagreements through as "aliases" in bulk. Check each
distinct pair against the sleigh and the reference's own opcode table, and prove
the alias condition holds **at every site**: `movf` vs `incf rz,rx,imm` is an
alias only while `imm == 0`, and that is a property of the sites, not of the
mnemonic. In the reference campaign 969 disagreements collapsed to 3 pairs, all
genuine aliases, verified site-by-site — and 176,702 instructions had **zero**
length mismatches. That result is worth having: it converts "the disassembly is
probably fine" into a measurement, and it narrows the remaining problem to
coverage alone.

## 4. Confirm there is no second wall behind the first

Two cheap checks that the residue really is only the opcodes §2 found:

1. **Forward sweep.** From each stop point, linear-decode forward with the
   reference decoder (a few hundred instructions) and collect every mnemonic
   that appears *nowhere* in Ghidra's listing. Anything unexpected is a second
   unimplemented family hiding behind the first.
2. **Byte scan.** For each affected instruction *group*, scan both code regions
   for every encoding in the group and count sites. This finds the encodings
   that exist in the image but happen not to sit at a stop point — and, by
   returning zero, justifies *not* implementing the ones that do not occur.

## 5. Patch the module — and only where you can check the answer

Patches to a third-party sleigh belong in `docs/patches/` with a README entry
per patch: what was wrong, how it was proven wrong, the impact on this image,
and the recompile command. Re-apply after every reinstall of the extension.

Rules that kept the reference campaign's patches honest:

- **Encoding first, semantics second.** A `(sop, pcode)`-style table learned from
  the instructions the module *does* decode tells you where an encoding sits.
  It does not tell you what the instruction means.
- **Structural reasoning is a hypothesis, not evidence.** "It has the shape of
  the family one opcode lower" earns a patch attempt, never a merge. What earns
  it: the reference decoder's opcode table naming the same encoding; the
  surrounding code only making sense under that reading (a multiply into an
  accumulator followed by the accumulator read); or a numerical result that
  wrong semantics could not produce (see §6).
- **Fix properly or leave visibly broken.** An encoding with zero sites in this
  image, or whose meaning has more than one plausible reading, is *deliberately
  not implemented*. Inventing p-code for a MAC instruction is worse than the
  stop it replaces: a stop is loud, wrong arithmetic is silent.
- Recompile the sleigh and restart Ghidra:
  `<ghidra>/support/sleigh -a <extension>/data/languages`

## 6. The p-code is a separate claim, and a disassembler cannot test it

§3 proves the *decode* exact. It says nothing about semantics — mnemonics and
lengths are all a disassembler has. In the reference campaign the module decoded
176,702 instructions with zero mismatches and still had **four** semantic bugs
that only emulation exposed:

1. `push`/`pop` did not round-trip — sleigh's implicit build order for a table
   constructor is not its display order, so `pop` restored the link register
   from the wrong stack slot. Nearly invisible in the decompiler, which models a
   prologue/epilogue pair *structurally* rather than by simulating it.
2. A bitfield extract masked `(1 << msb) - 1`, dropping the msb.
3. `sext` never sign-extended: sleigh's `sext()` from 4 bytes to 4 bytes is a
   no-op.
4. A field-insert used `msb + 1` as the width instead of `msb - lsb + 1`.

And one class that is invisible in the *listing* but poisons every decompilation:
an immediate built with `zext(imm:2 << 16)` — the shift happens in 2 bytes, so
the value is discarded **before** the widening. Every `movih`-style
high-immediate load produced 0, so every MMIO base in the image resolved to a
tiny address (`_UNK_00000004` for a GPIO register). The disassembly was right;
only the p-code was wrong. **If peripheral addresses look absurd, suspect the
module before you suspect the firmware.**

Testing semantics needs execution: `docs/ORACLE_PLAYBOOK.md`. Pick a
hardware-free subgraph, run it, and compare against an independent
implementation. That is also the only test that will ever catch bug 1.

## 7. Repair the program — the patch does not fix what is already recorded

**Ghidra does not retry a decode it has already failed.** After recompiling the
sleigh, the addresses where the old module gave up are still error code units,
and every affected function is still short. This is the step that gets forgotten,
and it makes the patch look ineffective.

```
RepairStops.java
```

It re-disassembles at each stop and calls `CreateFunctionCmd.fixupFunctionBody`,
iterating because repairing one stop exposes the next wall behind it. It is
deliberately **non-destructive**: it never removes the function, so names,
signatures, parameter names and plate comments survive. The
remove-clear-disassemble-recreate cycle (`RepairRange`-style scripts) throws all
of that away — in a campaign that has committed signatures and plate comments as
its audit trail, that is a self-inflicted data loss.

Expect the recovered functions to grow *a lot*: in the reference campaign one
went from 1,762 to 5,110 bytes, and three functions that had a `Function` object
and a body but **zero instructions** came back from the dead.

## 8. Re-verify, and record the numbers

Re-run §2 and §3 and put the before/after table in `docs/ISA_AUDIT.md` — the
findings file for this playbook, with an address on every claim:

| | before | after |
|---|---|---|
| instructions decoded | | |
| length mismatches vs reference | | |
| decodes the reference rejects | | |
| fall-through / flow stop points | | |
| functions decompiling to `halt_baddata` | | |
| bytes covered per code region | | |

The `halt_baddata` sweep is the strong one: decompile every function and grep.
**Strip `/* … */` comments first** — plate comments that *describe* an
already-fixed `halt_baddata` are part of the decompiler's C output, so a naive
scan reports those functions as broken forever.

A remaining stop is not automatically an ISA gap. Check whether it is in an
unmapped region (mask ROM you do not have), or reached only from an impossible
address (an odd address on an arch with 2-byte alignment, inside a data
section) — that is a spurious reference, and the honest write-up says so.

## 9. What this changes downstream

- **Coverage denominators are only meaningful after the audit.** "92% of flash
  text is inside a function" computed against a truncated program is not the
  same number.
- **Re-run the naming targets that were truncated.** A function that grew 3× was
  named from a third of its body. Feed the repaired ones back into a wave.
- **Anything derived from the broken arithmetic is suspect** — MMIO maps built
  from a broken high-immediate load, struct offsets, table strides. Re-derive
  rather than spot-fix.
