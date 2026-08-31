# ISA audit — is the processor module decoding this image correctly?

Everything this project produces is downstream of the disassembler, so "does it
decode every instruction this CPU executes, and decode it *right*?" is a
load-bearing question — and not one that can be answered from inside Ghidra.

It can be answered against an **independent implementation of the same ISA**.
The procedure, the traps and what to do with the answer are in
`docs/ISA_AUDIT_PLAYBOOK.md`; run it with `/re-isa-audit`.

## The pieces

| | |
|---|---|
| `../../ghidra_scripts/DumpInsns.java` | dumps Ghidra's side: `addr len mnemonic bytes` |
| `../../ghidra_scripts/IsaGaps.java` | the other half — every place the disassembler *stopped*, with the undecoded encoding there |
| `diff_ghidra_vs_binutils.py` | compares the two decoders at every address Ghidra decoded |
| `../../ghidra_scripts/RepairStops.java` | non-destructive re-disassembly after a sleigh patch |
| `examples/csky/` | a complete worked example of the reference-decoder side |

## The reference decoder

`diff_ghidra_vs_binutils.py --decoder <prog>` shells out to a harness of your
own with this contract:

```
<prog> <raw-slice> <base-va-hex>        # addresses on stdin, one hex VA per line
                                        # one decoded instruction per line on stdout:
                                        #   <len> <mnemonic> [operands...]
```

**One address at a time — never a linear sweep.** A sweep desyncs on the first
data island and then disagrees with Ghidra about everything after it, which
tells you nothing.

`examples/csky/` builds exactly that around binutils' `print_insn_csky`
(`cskydis.c` + `build.sh`, ~60 lines), with `carve.py` to slice the image into
mapped regions and `mkelf.py` to wrap a slice in an ELF for plain `objdump`.
To port it: change `print_insn_<arch>`, the `info.mach` value, and the
`--target=` in `build.sh`. Building binutils for a new target takes a couple of
minutes and is the only network step.

## The trap this exists to avoid

`<arch>-elf-objdump -D -b binary -m <arch>` **looks** like it works and can be
silently, partially wrong. Many `opcodes/*-dis.c` decoders gate whole
instruction classes on `mach_flag`, which comes from the ELF header's `e_flags`
— which a raw binary does not have.

In the reference campaign this made every 32-bit C-SKY instruction print as
`.long: 0x0000cXXX`, which reads like a literal pool rather than like a failure.
`mkelf.py` supplies real `e_flags`; `cskydis.c` sets `info.mach` directly and
sidesteps the whole thing. Reading that output as "those must be data" is
exactly the kind of quiet wrong answer this audit exists to catch.
