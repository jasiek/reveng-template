---
name: re-type-globals
description: Name and type the firmware's RAM globals — a scripted, rule-driven pass, not an agent fan-out. Use when the user asks to map SRAM, type globals, apply data types, clean up undefined data, or when the decompiler output is full of untyped DAT_ references.
---

# Map and type the globals

The best cost/benefit pass in the whole method. In the reference project it typed
2106 scalars and 1053 arrays with **zero failures and zero agent tokens**, plus
157 width ambiguities resolved deterministically.

**The principle this skill exists to enforce:** before every fan-out, ask whether
the task is a *judgment* call or a *rule*. Agents for judgment, scripts for rules.
Typing globals is almost entirely a rule.

## 1. Name the globals (judgment — a small fan-out)

Only the *naming* needs agents, and only for globals that code actually touches.
Rank `DAT_*` addresses by xref count (`list_data_items_by_xrefs`) and hand out
contiguous bands, exactly as in `/re-name-wave`, with one addition to the prompt:

> Name each global `g_<hungarian><Role>` — `b` byte, `w` ushort, `dw` uint,
> `qw` ulonglong, `f` float, `d` double, `sz` string, `p` pointer, `a` array.
> The prefix must match how the code actually accesses it (`ldrb` → `b`,
> `ldrh` → `w`, `ldr` → `dw`). Getting the prefix right is the whole job: the
> type is applied later by a script that reads it.

That last sentence is what turns thousands of typing decisions into a script run.

## 2. Type them (rule — a script)

In Ghidra: Script Manager → `TypeGlobalsFromNames.py` (add `<repo>/ghidra_scripts`
via *Manage Script Directories*), or over MCP with `run_script_inline`.

It types from the Hungarian prefix, falls back to the **observed load/store
width** when the name says nothing, and **never overwrites an existing type** — a
disagreement is reported as a conflict and left alone.

Set `DRY_RUN = True` first and read the report. Then run it for real.

## 3. Handle what is left

The script prints the unresolved globals: no name evidence *and* no observable
access width. That list is short and it is the only part worth a human or a
frontier model. Put it in a `PHASE_TODO` file
(`docs/templates/PHASE_TODO.template.md`) rather than guessing — a global nothing
accesses has no observable width, so any type you pick is invention.

## 4. Structs

Where a cluster of globals is accessed as `base + constant offset`, it is a struct,
not scalars. That *is* judgment: one agent per struct, and the contract's rule
applies with force — **never silently overwrite a field name or offset you
disagree with**; log the conflict and leave the existing state alone.

## 5. Commit

`save_program`, then one commit for the DB plus a note in `FINDINGS.md` saying how
many were typed from names, how many from access width, and how many remain
unresolved. Those three numbers are the honest summary of the pass.
