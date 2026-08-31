#!/usr/bin/env python3
"""Differential disassembly audit: Ghidra's processor module vs an independent decoder.

Ghidra's support for a niche architecture is often a third-party module with a
hand-written sleigh specification.  The question "does it decode every
instruction this CPU has, and decode it *right*?" is answerable only against an
independent implementation of the same ISA -- binutils' `opcodes/<arch>-dis.c`
is the usual one, and is normally written by the silicon vendor.

  1. `ghidra_scripts/DumpInsns.java` writes every instruction Ghidra decoded
     as `addr len mnemonic bytes`.
  2. A reference-decoder harness decodes the *same addresses* out of the raw
     image: one address per input line, one instruction per output line, so the
     two can never quietly desync (a linear sweep by the reference decoder will
     desync on the first data island and then disagree about everything).
     `examples/csky/` is a worked example around binutils' `print_insn_csky`;
     the same ~60-line shape works for any arch binutils supports.
  3. This script compares them.

A length mismatch is the serious failure: it means one of the two desynced and
everything after it in that function is fiction.  A decode Ghidra accepted and
the reference rejects is the other direction of the same problem.  Mnemonic
disagreements are usually alias spellings (`not` for `nor rz,rx,rx`) and are
reported in aggregate so each distinct pair can be checked once rather than per
site -- but check every pair, and check that the alias condition holds at
*every* site rather than assuming it from the name.

usage:
  diff_ghidra_vs_binutils.py --insns ghidra_insns.txt --decoder ./refdis \
      --region iram.bin:10000:2f098 --region flash.bin:300c000:30de000
"""
import argparse, collections, subprocess, sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--insns", required=True, help="output of DumpInsns.java")
    ap.add_argument("--decoder", required=True, help="path to the reference-decoder harness (see examples/)")
    ap.add_argument("--region", action="append", required=True,
                    metavar="RAW:LO:HI", help="raw image slice and its VA range, hex")
    ap.add_argument("--show", type=int, default=40)
    args = ap.parse_args()

    ghidra = {}
    for line in open(args.insns):
        p = line.split(None, 3)
        ghidra[int(p[0], 16)] = (int(p[1]), p[2], p[3].strip())

    binu = {}
    for spec in args.region:
        raw, lo, hi = spec.rsplit(":", 2)
        lo, hi = int(lo, 16), int(hi, 16)
        addrs = sorted(a for a in ghidra if lo <= a < hi)
        if not addrs:
            continue
        r = subprocess.run([args.decoder, raw, "%x" % lo],
                           input="\n".join("%x" % a for a in addrs) + "\n",
                           capture_output=True, text=True)
        for line in r.stdout.splitlines():
            p = line.split(None, 2)
            txt = " ".join(p[2].split()) if len(p) > 2 else ""
            binu[int(p[0], 16)] = (int(p[1]), txt.split(" ")[0] if txt else "", txt)
        print("%-40s ghidra=%d  decoded by binutils=%d"
              % (raw, len(addrs), sum(1 for a in addrs if binu.get(a, (0,))[0])))

    lenmis, fails, mnem = [], [], collections.Counter()
    for a, (gl, gm, gb) in ghidra.items():
        if a not in binu:
            continue
        bl, bm, btxt = binu[a]
        if bl == 0:
            fails.append((a, gl, gm, gb))
            continue
        if bl != gl:
            lenmis.append((a, gl, bl, gm, btxt, gb))
        if gm.lower() != bm.lower():
            mnem[(gm, bm)] += 1

    print("\n== length mismatches: %d" % len(lenmis))
    for x in lenmis[:args.show]:
        print("  %08x ghidra len=%d binutils len=%d  %s | %s  bytes=%s" % x)
    print("\n== binutils rejects what Ghidra decoded: %d" % len(fails))
    c = collections.Counter(x[3] for x in fails)
    for k, v in c.most_common(args.show):
        print("  %5d  bytes=%s  e.g. %08x" % (v, k, next(x[0] for x in fails if x[3] == k)))
    print("\n== mnemonic disagreements (%d distinct pairs, %d sites):"
          % (len(mnem), sum(mnem.values())))
    for (gm, bm), v in mnem.most_common(args.show):
        print("  %6d  ghidra=%-12s binutils=%s" % (v, gm, bm))
    return 1 if (lenmis or fails) else 0


if __name__ == "__main__":
    sys.exit(main())
