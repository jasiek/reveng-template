# Replay ledger/renames.csv onto a freshly imported program.
#
# This is what makes the ledger a real artifact rather than a changelog: given the
# same binary and the same import settings, this script reconstructs every name.
# Use it to migrate to a new Ghidra version, to re-import after a botched analysis
# pass, or to apply the analysis to a different firmware revision of the same
# radio (addresses shift — see the offset option).
#
# Run from Ghidra's Script Manager. It will ask for the CSV.
#
# @category ReverseEngineering
# @runtime Jython

import csv

from ghidra.program.model.symbol import SourceType

APPLY_PLATE_COMMENTS = True     # re-create "[confidence: X] role" plate comments
ADDRESS_OFFSET = 0              # add this to every ledger address (revision shift)


def main():
    program = currentProgram                                    # noqa: F821
    fm = program.getFunctionManager()
    space = program.getAddressFactory().getDefaultAddressSpace()

    path = askFile("Rename ledger (renames.csv)", "Replay")     # noqa: F821
    renamed = missing = mismatched = 0

    reader = csv.reader(open(path.getAbsolutePath()))
    for row in reader:
        if not row or row[0].strip().lower() in ("address", "#address"):
            continue
        if len(row) < 3:
            continue
        addr_s, old, new = row[0].strip(), row[1].strip(), row[2].strip()
        conf = row[3].strip() if len(row) > 3 else ""
        just = row[4].strip() if len(row) > 4 else ""

        addr = space.getAddress(int(addr_s.replace("0x", ""), 16) + ADDRESS_OFFSET)
        func = fm.getFunctionAt(addr)
        if func is None:
            missing += 1
            print("no function at %s (ledger says %s)" % (addr, new))
            continue
        current = func.getName()
        if current != old and not current.startswith("FUN_"):
            # Somebody has already named this differently. Report, do not clobber.
            mismatched += 1
            print("MISMATCH %s: ledger %s -> %s, program has %s" % (addr, old, new, current))
            continue
        func.setName(new, SourceType.USER_DEFINED)
        if APPLY_PLATE_COMMENTS and (conf or just):
            func.setComment("[confidence: %s] %s" % (conf or "UNKNOWN", just))
        renamed += 1

    print("")
    print("replayed  : %d" % renamed)
    print("missing   : %d  (no function at that address — re-check the import base)" % missing)
    print("mismatched: %d  (program already had a different name; left alone)" % mismatched)
    if missing:
        print("")
        print("A large 'missing' count almost always means the image base or the")
        print("container-header offset differs from the import this ledger came from.")
        print("Check TARGET.md, and re-run tools/triage.py on the image.")


main()
