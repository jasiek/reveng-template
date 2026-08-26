# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is

This is **not** a software project — there is nothing to build, lint, or test. It is a
**Ghidra reverse-engineering workspace** for a single piece of embedded firmware (typically a
handheld transceiver / HT radio, but anything Cortex-M-ish works). The "source of truth" is a
live Ghidra program driven over an MCP bridge; git tracks the analysis state (the binary Ghidra
DB), a replayable rename ledger, and prose findings.

This repo starts as a **template**. Everything target-specific lives in one file, `TARGET.md`,
which is written by `/re-bootstrap` when you point it at a firmware image. Until `TARGET.md`
says otherwise, treat every address, size and subsystem name below as a placeholder.

**Read `TARGET.md` first, every session.** It holds the firmware path, CPU, image base, memory
map, program name in Ghidra, and the current phase. If it is still the unfilled template, the
project has not been bootstrapped — run `/re-bootstrap <firmware-file>`.

## Getting started on a fresh fork

1. `git clone` (or fork) this repo, drop the firmware image in `firmware/`.
2. Start Ghidra with the GhidraMCP plugin listening on `http://127.0.0.1:8089`.
3. Run `/re-bootstrap firmware/<image>` — triage, import, base address, analysis, `TARGET.md`.
4. Run `/re-name-wave` repeatedly until coverage plateaus (`docs/NAMING_PLAYBOOK.md`).
5. Run `/re-verify` after every wave and after every crash; `/re-factcheck` at each phase end.

## Working with the Ghidra program (the "commands")

All analysis happens through the **`ghidra-mcp`** MCP server (`.mcp.json`), which talks to a
running Ghidra GUI with the GhidraMCP plugin and the program open. If MCP calls fail, the Ghidra
GUI/plugin is not running — **tell the user; you cannot start it.**

- MCP tools are **deferred** — load them per task with one `ToolSearch` call
  (`select:decompile_function,rename_function_by_address,...`) or `load_tool_group`. The bridge
  exposes ~250 tools; only `listing`, `function`, `program` load by default. Common working set:
  `decompile_function`, `batch_decompile`, `rename_function_by_address`,
  `get_function_callers`/`get_function_callees`, `get_xrefs_to`, `get_bulk_xrefs`,
  `set_plate_comment`, `list_functions_enhanced`, `get_full_call_graph`, `save_program`.
- The same bridge also exposes a debugger endpoint (`GHIDRA_DEBUGGER_URL`, port 8099).
- **Live Ghidra is authoritative — never trust a subagent's self-reported counts.** After any
  batch of renames, diff the live function list against `ledger/renames.csv` to learn what
  actually landed: `python3 tools/verify_wave.py` (procedure in `docs/NAMING_PLAYBOOK.md` §4).
- Jython/Java scripts run *inside* Ghidra (`run_script_inline`, Script Manager, or headless
  `analyzeHeadless … -postScript`) — they are not standalone Python. `run_script_inline` needs
  `GHIDRA_MCP_ALLOW_SCRIPTS=1` in the plugin's environment.

## Non-negotiable invariants

1. **One git commit per renamed function**, appended to `ledger/renames.csv`
   (`address,old_name,new_name,confidence,justification`). The **driver/orchestrator commits,
   never subagents** — parallel agents committing causes git-lock contention. Use
   `tools/commit_renames.sh`.
2. Every rename carries a **confidence tag (HIGH / MEDIUM / LOW)** and a Ghidra plate comment
   starting `[confidence: …]`, so guesses are auditable and revertible. MEDIUM = dataflow-
   inferred. **Never invent a role** — a wrong name is worse than none; skip empty stubs,
   trivial getters/setters, and opaque register glue.
3. `save_program` at each wave boundary, then commit the binary `.rep` DB **per-batch, not
   per-function** (it is a git-tracked binary blob — per-function commits would be churn).
4. Names: valid C identifiers, PascalCase, `Category_Action`, <40 chars. The prefix vocabulary
   lives in `docs/NAMING_CONVENTIONS.md` — it is driver-owned; regenerate it each wave from the
   names actually in the program rather than letting it drift.
5. Every prose claim in a `.md` file carries an **address**. A claim with no address is a guess.

## Operating rhythm (how work actually runs here)

- **Bulk campaigns are multi-hour and outlive a single session.** Naming/typing runs fan out
  ~6 parallel subagents (or a `Workflow`) over batches and routinely hit the token/5-hour
  session ceiling mid-run. This is expected, not a failure. Pace the work: grind until near
  exhaustion, then **wait for the next window and resume** — do not wind down early.
- **Resume is cheap and always the same move:** reconnect MCP, diff the live function/symbol
  list against the ledger, recover any orphaned renames' confidence from their plate comments,
  commit them, then relaunch only the still-`FUN_` slice (`/re-verify`, playbook §9). Because
  subagents set plate comments *immediately* after each rename, an interruption costs only a
  re-run of the unfinished slice.
- **Terse autonomous mode is the default.** Approvals like "carry on", "grind", "keep going",
  "do it", "make it so" mean *proceed autonomously through the whole batch without re-confirming
  each step*. Two standing expectations: **commit every batch as you go**, and **write durable
  findings/handoff notes to a file** (not just chat) so context can be cleared and work resumed
  later — this is why `FINDINGS.md` and the TODO files exist. When you produce something worth
  keeping, save it to a file without being asked twice.

### Model choice for subagents — the failure mode that hides

**Apparent productivity is inversely correlated with skip discipline.** In the
reference campaign the cheap tier posted a *higher* hit rate (~96%) than the
frontier tier (~90% on the hardest residue) — because it named things that should
have been skipped. Coverage is not correctness, and the two are indistinguishable
in a report: a wrong name and a right name look identical until you decompile the
function yourself.

Why this one is worse than it looks: a wrong name **propagates**. The next wave's
agents read neighbouring names as context and build inferences on top of them, and
the name then flows into `FINDINGS.md` as prose. A skipped function costs one
re-run of a slice; a wrong name costs a corruption that survives to the docs and
is only caught by `/re-factcheck`, phases later.

- **Default to the mid tier** for the tail; frontier tier for the residue and for
  anything whose answer changes the plan.
- **Audit a cheap tier before trusting a wave of it**: sample ~10 of its names,
  decompile them yourself, and check that each name is *accurate* — not merely
  that a name exists. This is the whole audit; it takes minutes.
- **Distrust cheap-tier self-reports specifically.** "22 renames in 7 tool calls"
  is arithmetically impossible and was really produced. The live-Ghidra diff exists
  because of this, and it is not optional.
- The niche for a cheap model is **narrow by construction**: rules should be
  scripted (§2 of `docs/ORCHESTRATION.md`), and judgment needs a capable model.
  What is left is bulk work on easy, already-anchored clusters.

## Repository layout

- `TARGET.md` — **the only target-specific file.** Firmware path, CPU, memory map, phase.
- `firmware/` — the raw image(s) and any dumps. Large binaries; see `.gitignore`.
- `<project>.gpr` / `<project>.rep/` — the Ghidra project + binary program DB (**git-tracked
  blob**; the real analysis state lives here, not in text files).
- `ledger/renames.csv` — the replayable rename ledger. To rebuild names on a fresh import,
  replay each row with `rename_function_by_address`. **Source of truth for names.**
- `FINDINGS.md` — architecture map, per-subsystem discoveries, run-by-run progress log. Created
  from `docs/templates/FINDINGS.template.md` at bootstrap. Read this to understand the firmware.
- `docs/NAMING_PLAYBOOK.md` — the reproducible multi-agent naming procedure (wave loop, target
  selection, verification diff, collision reconciliation, model tiering). Follow it verbatim
  when doing bulk naming.
- `docs/ORCHESTRATION.md` — standing instructions for the driver, distilled from a completed
  campaign. **Read before launching any fan-out.**
- `docs/SUBAGENT_CONTRACT.md` — the contract to paste into every subagent prompt.
- `docs/NAMING_CONVENTIONS.md` — the prefix vocabulary (living glossary).
- `tools/triage.py` — offline firmware triage: entropy, vector tables, load base, container
  header, strings, crypto constants, repeating-XOR obfuscation. Runs before Ghidra.
- `tools/verify_wave.py` — the live-Ghidra diff. The one verification you must never skip.
- `tools/make_batches.py` — target selection → batch files for the wave loop.
- `tools/commit_renames.sh` — driver-side one-commit-per-function ledger append.
- `tools/swd/` — hardware dump path (probe → dump → carve). **`probe.sh` is read-only; check
  the readout-protection level before any dump.**
- `scratchpad/` — **ephemeral** per-wave agent batch/result files. Safe to treat as scratch.

## Phase map (typical HT firmware project)

Each phase ends with a `/re-factcheck` sweep. Record the current phase in `TARGET.md`.

0. **Triage** — `/re-bootstrap`. What is this file? Container header, load base, arch, RTOS,
   crypto, obfuscation. Kill the load-bearing assumption before building on it.
1. **Naming** — the wave loop until coverage plateaus (~95–97% is the realistic ceiling).
2. **Globals/SRAM** — name and type every code-referenced RAM address. Mostly *scripted*, not
   agent work (`/re-type-globals`).
3. **Bootloader / secure boot** — the bootloader is usually **not** in the vendor update file.
   Dump it over SWD (`tools/swd/`) and import it as its own Ghidra program with its own ledger.
   The headline question — "is the image authenticated?" — gets a dedicated refutation pass.
4. **Subsystem deep-dives** — codeplug/EEPROM map, host/CPS serial protocol, crypto, DSP.
   Cross-check against external ground truth (e.g. an open-source CPS) wherever one exists.
5. **Reimplementation** (optional) — clean-room source with the reversed firmware as a
   behavioral oracle. Every transcribed magic block cites the stock function + address.
