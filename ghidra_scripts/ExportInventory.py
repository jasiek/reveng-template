# Export the program's function inventory (address, name, thunk flag, plate
# comment, caller count) to JSON.
#
# Two uses:
#   * feed tools/verify_wave.py --from-file when the HTTP bridge is unavailable
#   * recover confidence/role metadata for orphaned renames in bulk, instead of
#     one get_plate_comment call per address after a crash
#
# @category ReverseEngineering
# @runtime Jython

import json


def main():
    program = currentProgram                                    # noqa: F821
    fm = program.getFunctionManager()
    out = []

    funcs = fm.getFunctions(True)
    for func in funcs:
        if monitor.isCancelled():                               # noqa: F821
            break
        entry = func.getEntryPoint()
        callers = func.getCallingFunctions(monitor)              # noqa: F821
        out.append({
            "address": str(entry),
            "name": func.getName(),
            "isThunk": func.isThunk(),
            "plate": func.getComment() or "",
            "callers": len(callers),
            "size": func.getBody().getNumAddresses(),
        })

    path = askFile("Write inventory JSON", "Save")               # noqa: F821
    fh = open(path.getAbsolutePath(), "w")
    json.dump({"functions": out}, fh, indent=1)
    fh.close()
    named = len([f for f in out if not f["name"].startswith(("FUN_", "thunk_FUN_"))])
    print("wrote %d functions (%d named, %.1f%%) to %s"
          % (len(out), named, 100.0 * named / max(1, len(out)), path))


main()
