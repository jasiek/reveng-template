# reveng-template

A Ghidra reverse-engineering workspace for embedded handheld-radio (HT) firmware,
set up so that **pointing it at a firmware file is the whole setup step**.

Fork it, drop in an image, run `/re-bootstrap firmware/<image>`, and you have a
project with a load address, an imported Ghidra program, a target dossier, and a
method for turning 3000 `FUN_*` functions into a documented firmware.

Everything here is distilled from a completed campaign on a 3000-function stripped
DMR handheld firmware: 28 naming waves to ~100% coverage, a full SRAM/typing pass,
an SWD bootloader dump, a codeplug map, and a clean reimplementation. The parts
that were learned the hard way are called out as such.

## What you get

| | |
|---|---|
| **A front door** | `tools/triage.py` — container headers, load base, vector tables, entropy, RTOS/crypto markers, and a *verified* repeating-XOR key recovery for obfuscated vendor images |
| **A method** | `docs/NAMING_PLAYBOOK.md` — the fan-out naming loop, target-selection order, verification diff, collision reconciliation, model tiering, stopping criteria |
| **The corrections** | `docs/ORCHESTRATION.md` — what a finished campaign would do differently, including the target ordering worth ~15 waves |
| **An audit of the substrate** | `docs/ISA_AUDIT_PLAYBOOK.md` + `tools/isa_audit/` — differential disassembly against binutils/LLVM, a scan for every place the disassembler *stopped*, and a non-destructive repair. Run it **before** naming: a third-party processor module is a hand-written spec of somebody else's ISA |
| **An oracle** | `docs/ORACLE_PLAYBOOK.md` — execute the firmware's own code in Ghidra's p-code emulator on real input and diff it against your reimplementation. The only test of the processor module's *semantics*, and the only ground truth a reimplementation ever gets |
| **Nine skills** | `/re-bootstrap` `/re-isa-audit` `/re-name-wave` `/re-verify` `/re-type-globals` `/re-factcheck` `/re-refute` `/re-oracle` `/re-hw-dump` |
| **Verification that cannot be faked** | `tools/verify_wave.py` — diffs the live Ghidra program against the ledger. Agent prose is never evidence |
| **Scripts instead of agents** | `ghidra_scripts/` — typing globals, replaying the ledger, exporting inventory. Rules are scripted; only judgment gets a fan-out |
| **A hardware path** | `tools/swd/` — read-only probe, integrity-checked dump, passive-attach configs for parts that remap their SWD pins |

## Setup

1. **Ghidra + the MCP plugin.** Install [GhidraMCP](https://github.com/bethington/ghidra-mcp)
   into Ghidra and start the GUI with your program open; the plugin listens on
   `http://127.0.0.1:8089`.
2. **Point this repo at the bridge.** `.mcp.json` defaults to
   `~/github/ghidra-mcp/bridge_mcp_ghidra.py`; override with environment
   variables if yours lives elsewhere:
   ```bash
   export GHIDRA_MCP_BRIDGE=/path/to/ghidra-mcp/bridge_mcp_ghidra.py
   export GHIDRA_MCP_URL=http://127.0.0.1:8089      # optional
   ```
   Claude Code will ask to enable the project MCP server on first run.
3. **Optional:** to let `run_script_inline` execute Ghidra scripts over MCP, start
   Ghidra with `GHIDRA_MCP_ALLOW_SCRIPTS=1` in its environment.
4. **Add the Ghidra scripts directory:** Script Manager → *Manage Script
   Directories* → add `<repo>/ghidra_scripts`.

**Python 3.7+**, standard library only — nothing to `pip install`. Verified on
3.9, 3.11 and 3.14. `tools/triage.py` needs no Ghidra at all, so you can triage a
firmware image before deciding whether the project is worth starting. (The
`ghidra_scripts/` are Jython 2.7, which is what Ghidra embeds — that is why they
avoid f-strings.)

## Using it

```bash
# 1. fork, then:
cp ~/Downloads/RADIO_V1.23.bin firmware/

# 2. what is this file? (no Ghidra needed)
python3 tools/triage.py firmware/RADIO_V1.23.bin
```

Then, in Claude Code:

```
/re-bootstrap firmware/RADIO_V1.23.bin     # triage -> import -> TARGET.md -> FINDINGS.md
/re-isa-audit                              # does the processor module decode this CPU? do this FIRST
/re-name-wave                              # repeat until coverage plateaus
/re-verify                                 # after every wave, and after every crash
/re-type-globals                           # the scripted pass — do not fan agents at this
/re-refute                                 # before any finding changes the plan
/re-factcheck                              # last wave of every phase
/re-oracle                                 # run the stock code as ground truth (reimplementation, DSP, crypto)
/re-hw-dump                                # when you need the bootloader
```

`TARGET.md` is the only file that is target-specific. Everything else is method.

## The six rules that make it work

1. **Live Ghidra is the source of truth, not agent reports.** Models will
   confidently report renames they never made. Diff, every time.
2. **One commit per renamed function, driver-side only.** Parallel agents
   committing causes git-lock contention; the ledger is what makes the analysis
   replayable onto a fresh import.
3. **Every name carries a confidence tag and a plate comment.** Guesses stay
   auditable and revertible — and a plate comment written immediately means an
   interrupted wave costs nothing.
4. **Never invent a role.** A wrong name is worse than no name. Skipping is a
   first-class result.
5. **Every prose claim carries an address**, and the docs get a scheduled
   fact-check sweep at the end of every phase.
6. **The tools are claims too.** The disassembler can stop early, decode wrongly,
   or attach wrong semantics to a correct mnemonic — three different failures
   needing three different tests, none of them answerable from inside Ghidra.
   Audit the ISA before building 3000 names on top of it.

## Scope

Written for ARM Cortex-M handheld radios — the world of GD32/STM32 parts, uC/OS-II,
DMR/analog, codeplugs and CPS serial protocols. The method (triage → ISA audit →
wave loop → scripted typing → adversarial verification → oracle) is not
radio-specific; the vocabulary in `docs/NAMING_CONVENTIONS.md` and the
vector-table scanner in `tools/triage.py` are. Both are a short edit away from
another target.

It has since been run on a non-ARM target as well (a C-SKY V2 DMR SoC with a
third-party Ghidra processor module), which is where the ISA-audit and oracle
material comes from: the module truncated 16 functions at two unimplemented DSP
opcodes, and produced 0 for every high-immediate load — so every peripheral
address in the image was silently wrong — while the listing looked perfectly
healthy.

## Legal

Reverse-engineering firmware you own, for interoperability, repair and security
research, is lawful in many jurisdictions and not in all of them, and it will void
your warranty regardless. Redistributing vendor firmware images generally is not
lawful — `firmware/` is gitignored by default for that reason. That is a decision
for you and your jurisdiction, not for this README.
