#!/usr/bin/env python3
"""Carve the two code regions of the DM-32UV image out for the ISA audit.

The audit compares Ghidra against binutils *at the same virtual addresses*, so
each raw slice has to be paired with the VA it is mapped at.  Both mappings are
from TARGET.md:

  flash text   file 0x000100          -> VA 0x0300C000   (VA = off + 0x0300BF00)
  IRAM overlay file 0x0B1868, 0x1F098 -> VA 0x00010000   (copied by the startup
                                                          code out of flash
                                                          0x030BD768)

usage: carve.py <firmware.bin> <outdir>
"""
import os
import sys

HDR = 0x100                    # vendor container header, not mapped
IRAM_SRC_VA = 0x030BD768
IRAM_LEN = 0x1F098
VA_BIAS = 0x0300BF00           # VA = file_offset + VA_BIAS


def main(fw, outdir):
    b = open(fw, "rb").read()
    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, "flash.bin"), "wb").write(b[HDR:])
    off = IRAM_SRC_VA - VA_BIAS
    open(os.path.join(outdir, "iram.bin"), "wb").write(b[off:off + IRAM_LEN])
    print("flash.bin  VA 0x%08X  %d bytes" % (HDR + VA_BIAS, len(b) - HDR))
    print("iram.bin   VA 0x%08X  %d bytes (from file 0x%06X)" % (0x00010000, IRAM_LEN, off))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
