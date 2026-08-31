# Ghidra-side scripts

These run **inside** Ghidra — Script Manager, `analyzeHeadless -postScript`, or
the MCP bridge's `run_script_inline` (which needs `GHIDRA_MCP_ALLOW_SCRIPTS=1` in
the plugin's environment). They are not standalone Python; `currentProgram`,
`monitor` and `askFile` come from Ghidra's script API.

| Script | What it does | Why it is a script and not an agent |
|---|---|---|
| `TypeGlobalsFromNames.py` | types every `g_*` global from its Hungarian prefix, falling back to the observed load/store width | the type *follows* from evidence — it is a rule, and rules cost zero tokens and never hallucinate |
| `ReplayRenames.py` | rebuilds every name and plate comment from `ledger/renames.csv` | makes the ledger genuinely replayable, which is the whole point of keeping one |
| `ExportInventory.py` | dumps functions + plate comments to JSON | bulk metadata recovery after a crash, and offline input for `verify_wave.py` |
| `DumpInsns.java` | every decoded instruction as `addr len mnemonic bytes` | the Ghidra half of the differential ISA audit (`tools/isa_audit/`) |
| `IsaGaps.java` | every address where the disassembler **stopped**, histogrammed by the undecoded encoding, plus the functions it truncated | which opcodes are unimplemented is a measurement, not a guess |
| `RepairStops.java` | re-disassembles at each stop and fixes up the function body, iterating — **without removing the function** | Ghidra never retries a failed decode, so a sleigh patch changes nothing until this runs. Non-destructive: names, signatures and plate comments survive |
| `ClosureAudit.java` | transitive callee closure of an entry point with its MMIO references and indirect calls | decides whether a subsystem can be emulated as an oracle, before a day is spent on it (`docs/ORACLE_PLAYBOOK.md`) |

Add to this list rather than to your fan-out. Before launching agents at anything,
ask: is this a judgment call, or a rule? (`docs/ORCHESTRATION.md` §2.)

To point Ghidra at this directory: Script Manager → *Manage Script Directories* →
add `<repo>/ghidra_scripts`.
