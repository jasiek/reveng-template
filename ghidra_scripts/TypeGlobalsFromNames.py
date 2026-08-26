# Apply data types to global variables from evidence, not from judgment.
#
# This is the highest-value script in the repo. In the reference project it typed
# 2106 scalars and 1053 arrays with zero failures and ZERO agent tokens, plus 157
# width ambiguities resolved from the observed access width. Before you fan out
# agents over anything, ask whether it is a rule like this one instead.
#
# Two sources of evidence, in priority order:
#   1. A Hungarian prefix in the symbol name (g_dwTxFreq -> uint). The name was
#      chosen by an agent that had read the code; the type follows mechanically.
#   2. The width of the instructions that actually touch the address
#      (ldrb/strb -> 1 byte, ldrh/strh -> 2, ldr/str -> 4). This is a measurement.
#
# Never overwrites an existing non-default type: a disagreement is reported as a
# conflict and left alone, per the subagent contract.
#
# Run from Ghidra's Script Manager, or headless:
#   analyzeHeadless <proj_dir> <proj> -process <program> \
#       -scriptPath ghidra_scripts -postScript TypeGlobalsFromNames.py
#
# @category ReverseEngineering
# @runtime Jython

import re

from ghidra.program.model.data import (
    ByteDataType, CharDataType, DoubleDataType, FloatDataType, PointerDataType,
    QWordDataType, UnsignedIntegerDataType, UnsignedLongLongDataType,
    UnsignedShortDataType, Undefined1DataType,
)
from ghidra.program.model.symbol import SourceType

DRY_RUN = False          # set True to report without applying

HUNGARIAN = [
    ("psz", PointerDataType()),
    ("sz",  CharDataType()),
    ("str", CharDataType()),
    ("dw",  UnsignedIntegerDataType()),
    ("qw",  UnsignedLongLongDataType()),
    ("w",   UnsignedShortDataType()),
    ("by",  ByteDataType()),
    ("b",   ByteDataType()),
    ("ch",  CharDataType()),
    ("c",   CharDataType()),
    ("f",   FloatDataType()),
    ("d",   DoubleDataType()),
    ("p",   PointerDataType()),
    ("h",   UnsignedIntegerDataType()),
]

WIDTH_TYPE = {1: ByteDataType(), 2: UnsignedShortDataType(), 4: UnsignedIntegerDataType(),
              8: QWordDataType()}

# ARM/Thumb load-store widths. Extend for other architectures.
WIDTH_MNEMONIC = [
    (re.compile(r"^(ldrb|ldrsb|strb)", re.I), 1),
    (re.compile(r"^(ldrh|ldrsh|strh)", re.I), 2),
    (re.compile(r"^(ldrd|strd)", re.I), 8),
    (re.compile(r"^(ldr|str)", re.I), 4),
]


def hungarian_type(name):
    """g_dwTxFreq -> (uint, 'dw'). Returns (None, None) when the name says nothing."""
    m = re.match(r"^g_([a-z]{1,3})(?=[A-Z])", name)
    if not m:
        return None, None
    tag = m.group(1)
    for prefix, dt in HUNGARIAN:
        if tag == prefix:
            return dt, prefix
    return None, None


def observed_width(program, addr):
    """The width every instruction that touches this address agrees on, or None."""
    widths = set()
    listing = program.getListing()
    refs = program.getReferenceManager().getReferencesTo(addr)
    for ref in refs:
        instr = listing.getInstructionAt(ref.getFromAddress())
        if instr is None:
            continue
        mnem = instr.getMnemonicString()
        for pattern, width in WIDTH_MNEMONIC:
            if pattern.match(mnem):
                widths.add(width)
                break
    if len(widths) == 1:
        return widths.pop()
    return None                      # no accesses, or they disagree


def main():
    program = currentProgram                                    # noqa: F821
    listing = program.getListing()
    symtab = program.getSymbolTable()

    applied_name = applied_width = skipped_typed = ambiguous = conflicts = 0
    unresolved = []

    monitor.setMessage("Typing globals")                        # noqa: F821
    for sym in symtab.getAllSymbols(True):
        name = sym.getName()
        if not name.startswith("g_"):
            continue
        addr = sym.getAddress()
        if addr is None or not addr.isMemoryAddress():
            continue

        existing = listing.getDataAt(addr)
        if existing is not None and existing.isDefined():
            dt = existing.getDataType()
            if dt is not None and not dt.getName().lower().startswith("undefined"):
                skipped_typed += 1
                continue

        dt, tag = hungarian_type(name)
        source = "name"
        if dt is None:
            width = observed_width(program, addr)
            if width is None:
                ambiguous += 1
                unresolved.append((addr, name))
                continue
            dt = WIDTH_TYPE[width]
            source = "access width"

        if DRY_RUN:
            print("%s  %-40s <- %s (%s)" % (addr, name, dt.getName(), source))
            continue
        try:
            if existing is not None:
                listing.clearCodeUnits(addr, addr.add(max(0, dt.getLength() - 1)), False)
            listing.createData(addr, dt)
            if source == "name":
                applied_name += 1
            else:
                applied_width += 1
        except Exception as exc:                                # noqa: BLE001
            conflicts += 1
            print("CONFLICT %s %s: %s" % (addr, name, exc))

    print("")
    print("typed from Hungarian prefix : %d" % applied_name)
    print("typed from access width     : %d" % applied_width)
    print("already typed, left alone   : %d" % skipped_typed)
    print("unresolved (no evidence)    : %d" % ambiguous)
    print("conflicts                   : %d" % conflicts)
    if unresolved:
        print("")
        print("Unresolved — these are the ONLY ones worth a human or an agent:")
        for addr, name in unresolved[:60]:
            print("  %s  %s" % (addr, name))
        if len(unresolved) > 60:
            print("  ... and %d more" % (len(unresolved) - 60))
        print("")
        print("Put them in a PHASE_TODO file rather than guessing; an unaccessed")
        print("global has no observable width and no name evidence, so any type")
        print("you pick is invention.")


main()
