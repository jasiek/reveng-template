---
name: re-bootstrap
description: Point this repo at a firmware image and set the whole project up — triage the file (container header, load base, obfuscation, RTOS/crypto markers), import it into Ghidra at the right base address, and write TARGET.md and FINDINGS.md. Use when starting a new fork, when the user says "reverse engineer this firmware", gives a path to a .bin/.CDD/.hex/.spi/.dfu image, or asks what a firmware file is. Run this before any naming work.
---

# Bootstrap a firmware reverse-engineering project

The entry point for a fresh fork. One argument: the firmware file.

## 0. Preconditions

- The image is somewhere readable — copy or move it to `firmware/`.
- Ghidra is running with the GhidraMCP plugin on `http://127.0.0.1:8089` and the
  MCP server is connected. **If MCP calls fail, the GUI/plugin is not running —
  say so and stop. You cannot start it.**

Steps 1–2 need no Ghidra at all. Do them even if Ghidra is not up yet.

## 1. Triage the file — measurement before opinion

```bash
python3 tools/triage.py firmware/<image>
```

Read the output carefully; it answers phase 0 deterministically. What to do with
each outcome:

| Triage says | Do this |
|---|---|
| one vector table at offset 0 | straightforward raw import at the reported base |
| one table at offset N | the first N bytes are a vendor/container header. Import the **whole file** and set the base to `reported_base − N`, or strip the header first — record which you chose in `TARGET.md`, because every future file-offset↔VA conversion depends on it |
| two or more tables | the file holds several images (usually bootloader + application). Import **each** as its own Ghidra program with its own base and its own ledger |
| no vector table, VERIFIED XOR key | re-run with `--write-deobf firmware/<image>.dec` and bootstrap the decoded file instead. Note the key in `TARGET.md` |
| no vector table, nothing verified | stop and report. Options: the image is compressed or encrypted with something other than a repeating XOR; it is not Cortex-M; or you have only part of it. Look for an unpacker in the vendor's CPS software before guessing |
| Intel HEX / S-record | `--convert firmware/<image>.bin`, then triage that |

Never invent a load address. If triage gives a range rather than a single base,
say so and pick the candidate that puts the reset handler just past the vector
table — then verify it in step 3 by checking that the decompiler produces sane
code at the reset vector.

## 2. Write TARGET.md

`python3 tools/triage.py firmware/<image> --markdown` gives you the identity and
memory-map tables. Fill in the rest from the markers triage found, from the
version strings, and from the user. Anything you do not know stays a `<…>`
placeholder — a confidently wrong MCU in `TARGET.md` will mislead every future
session.

Also write, as **one falsifiable sentence**, the load-bearing assumption of the
project ("the update file contains the bootloader", "the codeplug is stored in the
external flash"). This is the sentence you will spend one agent trying to refute
(`/re-refute`) before building phases on it.

## 3. Import into Ghidra

Load the tools you need in **one** `ToolSearch` call:
`select:import_file,set_image_base,create_memory_block,run_analysis,analysis_status,list_functions_enhanced,list_strings,get_metadata,save_program,list_open_programs`

1. `import_file(file_path=<abs path>, language="ARM:LE:32:Cortex", compiler_spec="default", auto_analyze=false)`
   — auto-analyse *after* the base is right, not before.
2. `set_image_base(address=<base from triage>)`.
3. Create the SRAM block so data references resolve instead of dangling:
   `create_memory_block(name="SRAM", address=0x20000000, size=<from the part>, ...)`.
   Also add any peripheral region you know (`0x40000000`).
4. `run_analysis()`, then poll `analysis_status()`. On a 1 MiB image this takes
   minutes.
5. `save_program()`.

Sanity-check the base before going further: decompile the reset vector. If it
reads like startup code (stack setup, clock init, a jump to main), the base is
right. If it is garbage or dangling references, it is not — go back to step 1.

## 4. Seed FINDINGS.md

```bash
cp docs/templates/FINDINGS.template.md FINDINGS.md
```

Fill in Target and Viability from triage + the import (`get_metadata`,
`list_functions_enhanced` for the count, `list_strings` for the string count).
Record the counts at import — later coverage percentages are measured against them.

## 5. First real analysis: the string spine

Before any bulk naming, build the spine that everything hangs off:
`get_bulk_xrefs` over the defined strings maps the obvious subsystems in one pass
and produces the highest-confidence names in the whole campaign. That is wave 1.

While you are in the strings, **inventory the code that is not this vendor's**:
an RTOS banner (`uC/OS-III Idle Task`, `FreeRTOS`, `Nucleus`), a GCC/toolchain
version string, libc format strings, a zlib/mbedTLS/lwIP banner. Record each with
its address in `TARGET.md` under *Known code*, with the **version** where the
string gives one. These are the only functions in the image whose names can be
*checked* against a public source of truth rather than inferred, and they are
called from everywhere, so they are the first naming targets
(`docs/NAMING_PLAYBOOK.md` §3.0) — not a footnote.

## 5b. Is the disassembly trustworthy? — the gate before naming

Two cheap checks now, because everything after this is built on them:

1. **Establish the ISA from the bytes**, not only from the part number — call
   encodings, prologue patterns, and whether call targets resolve aligned and
   in-range under the ISA's length rule. Write the argument into `TARGET.md`
   under *How the ISA was established*. When the part number later agrees, you
   have two independent lines of evidence instead of one assumption.
2. **Run `ghidra_scripts/IsaGaps.java`** — every place the disassembler stopped.
   Zero is a result worth recording; anything else means functions are truncated
   and names derived from them will have to be redone.

If the language module is a **third-party extension**, or the stop scan is
non-zero, or peripheral addresses look absurd, stop and run `/re-isa-audit`
before the first naming wave. `docs/ISA_AUDIT_PLAYBOOK.md`.

## 6. Commit and hand off

```bash
git add -A && git commit -m "Bootstrap: <device> <version> imported at <base>"
```

Then tell the user, in a few lines: what the file is, where it loads, what the
markers say is inside it, what the load-bearing assumption is, whether the
disassembler stopped anywhere, and that the next move is `/re-isa-audit` (or
`/re-name-wave` if the module is mainstream and the stop scan came back clean). Point out anything triage found that changes the plan —
a second image, an encryption layer, an unexpected RTOS.
