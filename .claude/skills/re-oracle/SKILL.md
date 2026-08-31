---
name: re-oracle
description: Execute the firmware's own code as ground truth — emulate a hardware-free subgraph in Ghidra's p-code emulator, drive it with real input, and diff it against a reimplementation or a public reference. Use when reimplementing a subsystem, when a claim about an algorithm would change the project's direction, when a transcription and a reference implementation disagree, or when the decompilation of a maths-heavy function cannot be verified by reading.
---

# Run the stock code as ground truth

Full procedure and the traps: `docs/ORACLE_PLAYBOOK.md`.

Reverse engineering produces claims about behaviour. This turns them into tests,
and it is the only thing that tests the processor module's **semantics** rather
than its spelling.

## 1. Prove it is feasible — measure, do not judge

```
ClosureAudit.java <entry-address>
```

Transitive callee closure with the things that stop an emulator: **MMIO
references** and **indirect calls**. Zero MMIO is the green light, and pure
computation (codec, FEC, checksum, crypto, parser, packer) usually is zero.
MMIO everywhere means you picked the wrong entry point — go down a level, or
drive the task instead (§3).

Preconditions: the code is present in the image (RAM-resident code is still in
the file — find the boot copy loop), and **`/re-isa-audit` has been run**. An
emulator executes the sleigh; a wrong sleigh is a convincing liar.

## 2. Bring it up

Ghidra's p-code emulator needs no new instruction semantics — it runs the same
sleigh the listing came from. (Check for a QEMU target first, but for a niche
core there usually is not one, and a stale vendor fork is worse than this.)

Supply: the code regions, a zero-filled `.bss`, the initialised-data image, a
stack — and the **context struct**, which is the hard part. Do not hand-build it
from field names: **replay the firmware's own init functions** in boot order and
let them fill it. Read base addresses out of literal pools, not out of notes.

Expect the first non-leaf call to fail. That is the p-code audit doing its job:
in the reference campaign it exposed four sleigh semantic bugs (`push`/`pop` not
round-tripping, `sext` as a no-op, two off-by-one field widths) that a
disassembly-level audit had passed clean.

## 3. Do not reconstruct the calling convention — run the caller

The most expensive mistake available here. Guessing argument order, buffer slots
and flag words from decompilation produces *believable but wrong* output that
gets explained away with theories. Instead give the harness `hook <addr> ret
<value>` (stub) and `hook <addr> break` / `resume`, stub only what leaves the
closure (RTOS pends, hardware, other subsystems), and **execute the real task**.
Break where the ISR would have delivered data, poke input into the buffer the
firmware's own index arithmetic selects, resume. If you must infer, infer from
the **disassembly's** index arithmetic, not the decompiler's rendering.

## 4. Audit what you skipped, by experiment

For every init call you did not replay: poison the memory it would have written
and re-run. Identical output ⇒ provably irrelevant, and say so. Changed output ⇒
a real dependency you just found. Record both. "Assumed harmless" is a liability;
"poisoned with 0x1111, output bit-identical" is a result.

## 5. Validate the instrument, then measure

Check the stimulus is what you think (a clipping probe once invalidated a whole
day's amplitude conclusions), check it arrives intact in the firmware's own input
buffer, prefer captured real data for headline results, and report **per item,
not aggregate** — a mean hides a working path and a broken one in the same run.

## 6. Differential test with a referee

Best configuration: **firmware ⟷ your reimplementation ⟷ an independent public
implementation**. Any two agreeing localises the bug. Run per-function oracles,
not just end-to-end — that is where transcription errors surface, and end-to-end
agreement can hide two compensating errors. The deliverable is *which functions
are proven to match*; those are the ones that may be transcribed, each citing
the stock function and address.

When the oracle refutes something already written down, edit the claim **and**
leave a line saying it was withdrawn and why.

## 7. Write it up

`docs/EMULATION.md`: the closure table, the init replay and its poisoning audit,
whether the convention was **executed or inferred**, the head-to-head numbers
per item, and an explicit list of what is still unverified. Commit the harness
and the job files — an oracle nobody can re-run is an anecdote.
