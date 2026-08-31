# Bridge and GUI quirks

Non-obvious behaviour of the ghidra-mcp bridge and of Ghidra itself. Each one
either produced a **silent wrong result** or cost a wasted agent run the first
time it was met. Check here before blaming the analysis.

## The bridge

- **`batch_decompile` takes function NAMES, not addresses.** `03055000` and
  `0x03055000` both return "Function not found"; `FUN_03055000` works.
  `decompile_function` *does* accept `address="0x…"`. Put this in every subagent
  brief, or six agents each rediscover it independently.
- **`get_full_call_graph` returns plain text**, one `caller -> callee` per line,
  keyed by **name**, not address — and it silently caps at a few hundred edges
  unless an explicit `limit` is passed (`?limit=200000`). A tool that ranks
  targets by in-degree against the capped graph ranks the wrong functions and
  looks like it worked. `tools/make_batches.py` asserts against the default cap
  for exactly this reason.
- **Plate comments must not contain a `/*` sequence.** Ghidra wraps plate
  comments in `/* … */`, so the comment silently truncates at that point. It also
  means a plate comment describing a `halt_baddata` is part of the decompiler's C
  output — see `docs/ISA_AUDIT_PLAYBOOK.md` §8.
- **`open_program` needs a CodeBrowser tool.** With the plugin loaded in the
  project window only, it returns "ProgramManager service not available" and the
  program has to be opened from the GUI.
- **Long tool results can truncate mid-write.** A heredoc appending a large
  section to a file was cut off once. Write the file, then `cat` it into place.
- **The bridge is not a transaction manager.** Parallel agents renaming
  concurrently is fine; parallel *git* commits are not — that is why the driver
  commits (`docs/ORCHESTRATION.md` rule 9).

## The GUI

- **A blank, unresponsive CodeBrowser is usually a window on a detached second
  display, not a hang.** Distinguish in ~30 seconds before restarting anything —
  a restart risks the analysis DB and costs a reload:
  1. `curl -s http://127.0.0.1:8089/check_connection` — if it names the program,
     the backend is fine and only the window is affected.
  2. `jstack <pid>` (`pgrep -f ghidra.GhidraRun`) and look at `AWT-EventQueue-0`.
     Parked in `EventQueue.getNextEvent()` = idle and healthy, i.e. a paint
     problem. Blocked on a Ghidra lock, or a nested `Dialog.show()` in the stack,
     means a real deadlock or a hidden modal dialog instead.
  3. Sample CPU twice a few seconds apart. Flat CPU rules out analysis or a GC
     storm.
- **Work is not blocked while the window is broken.** The bridge keeps working,
  so renames, decompiles and verification all still run.
- **Ghidra never retries a decode it has already failed.** After a sleigh patch,
  the old error code units are still there and the functions are still short.
  `ghidra_scripts/RepairStops.java`.
- **A modal dialog blocks the bridge.** If every MCP call hangs at once and the
  process is idle, something is waiting for a click.
