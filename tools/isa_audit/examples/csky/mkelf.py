#!/usr/bin/env python3
"""Wrap a raw C-SKY code slice in a minimal ELF so csky-elf-objdump decodes it.

This exists because of a trap.  `csky-elf-objdump -D -b binary -m csky` looks
like it works -- it prints 16-bit instructions correctly -- but it decodes
*nothing* 32-bit.  binutils' csky disassembler only takes the 32-bit path when
`IS_CSKY_V2(mach_flag)` holds (opcodes/csky-dis.c), and `mach_flag` comes from
the ELF header's `e_flags`.  With `-b binary` there is no ELF header, so every
`0xC...` halfword comes out as `.long: 0x0000cXXX` and the disassembly silently
degrades to nonsense.  Wrapping the bytes in an ELF whose e_flags say
"ABI v2, CK803" fixes it.

usage: mkelf.py <raw.bin> <vaddr_hex> <out.elf> [e_flags_hex]
default e_flags 0x22000009 = CSKY_ABI_V2 | CSKY_VERSION_V2 | CSKY_ARCH_803
"""
import struct
import sys

EM_CSKY = 252


def mkelf(data, vaddr, out, e_flags=0x22000009):
    shstr = b"\0.text\0.shstrtab\0"
    ehsize, shentsize = 52, 40
    off_text = ehsize
    off_shstr = off_text + len(data)
    off_sh = (off_shstr + len(shstr) + 3) & ~3
    eh = struct.pack("<16sHHIIIIIHHHHHH",
                     b"\x7fELF\x01\x01\x01" + b"\0" * 9, 1, EM_CSKY, 1,
                     vaddr, 0, off_sh, e_flags, ehsize, 0, 0, shentsize, 3, 2)

    def sh(name, typ, flags, addr, off, size, align=1):
        return struct.pack("<IIIIIIIIII", name, typ, flags, addr, off, size, 0, 0, align, 0)

    shs = sh(0, 0, 0, 0, 0, 0)
    shs += sh(1, 1, 0x6, vaddr, off_text, len(data), 4)   # .text, ALLOC|EXEC
    shs += sh(7, 3, 0, 0, off_shstr, len(shstr))          # .shstrtab
    pad = b"\0" * (off_sh - (off_shstr + len(shstr)))
    open(out, "wb").write(eh + data + shstr + pad + shs)


if __name__ == "__main__":
    flags = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x22000009
    mkelf(open(sys.argv[1], "rb").read(), int(sys.argv[2], 16), sys.argv[3], flags)
