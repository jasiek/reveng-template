# Worked example: C-SKY V2 (CK803S) reference decoder

The reference-decoder side of the ISA audit, for one real architecture. Kept as
an example because the shape ports to any arch binutils supports — the audit
found two unimplemented DSP opcodes and confirmed four earlier sleigh patches
against `opcodes/csky-opc.h`.

| | |
|---|---|
| `carve.py` | slice the firmware into its mapped code regions with their VAs |
| `cskydis.c` + `build.sh` | ~60-line harness around `print_insn_csky`: decodes **one instruction at an arbitrary address**, addresses on stdin |
| `mkelf.py` | wrap a raw slice in an ELF (`e_flags = 0x22000009`) so plain `csky-elf-objdump` also works |

```sh
python3 carve.py firmware/<image>.bin scratchpad/
./build.sh <binutils-src> <binutils-build> scratchpad/refdis
# in Ghidra: DumpInsns.java scratchpad/ghidra_insns.txt
python3 ../../diff_ghidra_vs_binutils.py \
    --insns scratchpad/ghidra_insns.txt --decoder scratchpad/refdis \
    --region scratchpad/iram.bin:10000:2f098 \
    --region scratchpad/flash.bin:300c000:30de000
```

**To port:** change `print_insn_<arch>` and the `info.mach` value in
`cskydis.c`, the `--target=` in `build.sh`, and the region layout in `carve.py`
(which is the only file that knows anything about a specific image).
