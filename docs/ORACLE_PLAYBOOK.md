# Running the firmware's own code as an oracle

Reverse engineering produces *claims about behaviour*. An oracle turns them into
**tests**: execute the stock code out of the image on real input and compare
against whatever you are building — a reimplementation, a protocol decoder, a
codeplug writer, a checksum.

This is the strongest verification available in this workspace, and it is
cheaper than it sounds. The whole path is Ghidra's own p-code emulator; there is
no CPU port to find, no hardware to attach, and no new instruction semantics to
write. It also happens to be the only test that can catch a **wrong p-code**
bug (`docs/ISA_AUDIT_PLAYBOOK.md` §6).

Use it when:

- you are reimplementing a subsystem (phase 5) and need ground truth per function;
- a claim about an algorithm would change the project's direction;
- a public reference implementation exists and disagrees with your transcription
  — the firmware is the referee;
- the decompilation of a maths-heavy function is plausible but unverifiable by
  reading.

## 1. Feasibility is a measurement, not a judgement call

Emulation is easy for pure computation and hard for anything that touches
hardware. Which one you have is a question with an answer:

```
ClosureAudit.java <entry-address> [<entry-address> ...]
```

Walks the transitive callee closure and reports, for the whole closure:
function count, byte count, **MMIO references**, and **indirect calls**.

| result | verdict |
|---|---|
| 0 MMIO, 0 indirect | run it today |
| 0 MMIO, a few indirect | fine — an emulator just follows the register |
| a handful of MMIO reads | stub them (`hook <addr> ret <value>`) and record each stub as an assumption |
| MMIO everywhere, interrupts, RTOS pends in the closure | wrong entry point — go down a level, or drive the *task* (§4) |

In the reference campaign the DSP/vocoder closure — 149 functions, 67 KB —
touched **zero** MMIO and had **one** indirect call. Codecs, checksums, crypto
primitives, parsers, packers and FEC are all shaped like this. Look for a
subgraph that takes a buffer and a context pointer.

Two preconditions worth checking before spending a day on this:

- **The code must be in the image you have.** Code copied to RAM at boot is
  still in the file — find the copy loop and the source range.
- **Run `docs/ISA_AUDIT_PLAYBOOK.md` first.** An emulator executes the sleigh's
  semantics. If the sleigh is wrong, the oracle is a very convincing liar.

## 2. Why the in-Ghidra p-code emulator, and not QEMU

Reach for QEMU only if a maintained target already exists for the arch *and*
covers the instruction groups your code leans on. For a niche core it usually
does not: in the reference campaign no upstream QEMU target existed at all, the
vendor's fork shipped as an old tarball, and even it was not obviously complete
for the DSP MAC group the firmware depends on.

Ghidra's emulator has the property that matters: it runs **the same sleigh the
listing came from**, so bring-up cost is zero and any semantic disagreement is a
bug in one artifact you already own. The cost is speed — expect on the order of
10⁵ instructions/second, i.e. minutes per second of audio-rate work. That is
slow enough to make a second implementation (a small C interpreter over the
handful of mnemonics the closure actually uses) worth writing once the oracle
has proved out, and the two engines then cross-check each other.

A batch driver script (job file: `load` / `fill` / `poke` / `reg` / `sp` /
`call` / `peek` / `getreg` / `hook … ret` / `hook … break` / `resume` /
`maxsteps` / `trace`) is what makes this usable from the outside; write one
early and drive it from Python rather than clicking through the GUI.

### The memory the emulator has to supply

- every code region the closure spans, from the image;
- the `.bss`/heap range it writes, zero-filled — find the boot memset;
- the initialised-data image, if it is copied from flash at boot;
- a stack, with a plausible SP;
- the **context structure**, which is the hard part — §3.

## 3. Initialise the way the firmware does, then audit the difference

Do not hand-build the context struct from field names. **Replay the firmware's
own init functions in the emulator**, in the order the boot path calls them, and
let them fill it. Read base addresses out of the literal pools rather than from
a previous session's notes.

Then audit what you skipped — and audit it by **experiment, not argument**:

- List every call in the init function you did not replay.
- For each, poison the memory it would have written (`0x1111`, `0x7FFF`) and
  re-run. **No change in the output ⇒ the omission is provably irrelevant** for
  this path. A change ⇒ you just found a real dependency, and the poison value
  usually tells you what kind (a gate, a scale, a mode).
- Record both outcomes in the findings file. "Tested, no effect" is a result;
  "not replayed, assumed harmless" is a liability.

This is how the reference campaign settled a two-session argument about whether
its harness was initialised like the radio: one omission was measured
irrelevant (bit-identical output under poisoning), one was measured decisive
(froze the decoder at a constant), and the real difference turned out not to be
initialisation at all.

## 4. Do not reconstruct the calling convention. Run the caller.

**The single most expensive mistake in the reference campaign's oracle work.**
Three separate sessions guessed at a per-frame calling convention — argument
order, buffer slots, flag words — from decompilation and plausibility. All three
were wrong in different ways, and each wrong guess produced *believable but
subtly wrong* output that was then explained away with algorithmic theories.

The fix is to stop deciding. Give the emulator two primitives:

| `hook <addr> ret <value>` | stub a function: reaching it returns immediately |
| `hook <addr> break` | pause at an address; `resume` continues from exactly there |

and then **run the real task or the real caller**, stubbing only what leaves the
closure (RTOS pends, hardware setup, unrelated subsystems). Break where the
interrupt would have delivered data, poke the input into the buffer *the
firmware's own index arithmetic selects*, and resume.

Everything you were guessing at is then executed rather than inferred: the call
order, which buffer each call reads, the flag word (in the reference campaign
the real value was `0x1840`, where all three reconstructions had used `0x800`),
and the surrounding bookkeeping. When the task's convention was finally
executed, it matched one of the three guesses exactly — which is the point:
guessing right is indistinguishable from guessing wrong until you run it.

If you must infer a convention, infer it from the **disassembly**, not the
decompiler's rendering: index arithmetic like `idx = (idx + 80) mod 160` is
explicit in the listing and tells you the buffer layout outright.

## 5. Validate the instrument before you trust the measurement

A probe you built is an artifact too, and it can be wrong in ways that look like
a finding about the firmware.

- **Check the input.** In the reference campaign a synthetic probe was clipping,
  so the entire "amplitude" axis of a day's conclusions was meaningless.
  Autocorrelate / measure the stimulus and confirm it is what you think.
- **Check that the input arrives intact.** Peek the firmware's own input buffer
  mid-run and verify it holds what you poked, in the layout the code expects.
- **Prefer captured real-world data to synthetic probes** for the headline
  result, and keep the synthetic probe for isolating single stages.
- **Report per-item, not aggregate.** A mean over frames hid both a working path
  and a broken one in the same run; the per-frame table showed the pattern
  immediately.

## 6. Differential testing: three implementations, one referee

The strongest configuration is **firmware ⟷ your reimplementation ⟷ an
independent public implementation** of the same standard. Any two agreeing
against the third localises the bug immediately, and the third is what stops a
shared assumption from passing as truth.

Lessons from running it:

- **Expect to find bugs in your reimplementation *and* in the firmware
  transcription *and* in your understanding of the reference.** In the reference
  campaign the head-to-head found a real encoder bug in the reimplementation, a
  25 dB level-convention offset that was a convention rather than a defect, and
  two of its own earlier conclusions that had to be formally withdrawn.
- **A per-function oracle beats an end-to-end one.** Run the stock function and
  your transcription of it on the same inputs and diff the outputs. That is a
  unit test with ground truth, and it is where transcription errors actually
  surface. End-to-end agreement can hide two compensating errors.
- **Certify the transcribable subset.** The useful deliverable is not "it
  matches" but *which functions are proven to match* — those are the ones that
  may be transcribed into the clean implementation, each citing the stock
  function and address it came from.
- **When two implementations differ, ask whether they are the same algorithm
  family before calling one wrong.** Two spectral analysers can both be correct
  and differ by design; the referee, on the same input, is what settles it.
- **Withdraw claims explicitly.** When the oracle refutes something the findings
  file already asserts, edit the claim *and* leave a line saying it was
  withdrawn and why. `/re-factcheck` depends on that trail.

## 7. What to write down

In `docs/EMULATION.md` (or a subsystem findings file), with an address on every
claim:

- the closure audit table (functions, bytes, MMIO, indirect calls) — the
  feasibility argument;
- the init replay, and the poisoning audit of every omission;
- the harness's convention, and whether it was **executed or inferred**;
- the head-to-head numbers, per item, with the referee's numbers beside them;
- an explicit list of what is *not* yet verified. The open item is the most
  useful line in the file for the next session.
