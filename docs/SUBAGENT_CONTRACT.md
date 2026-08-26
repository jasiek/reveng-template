# The standing contract for every subagent

Paste this verbatim into every subagent prompt, under the task-specific instructions.

---

- **Your effect on Ghidra is your output.** Prose summaries are ignored; do not report counts.
  The driver verifies against the live program, not against what you say you did.
- **Plate comment immediately after each rename** — `[confidence: HIGH|MEDIUM] <one-line role>` —
  and write your result file **last**. Never run git. This is what makes an interruption cost
  nothing: if you are killed mid-batch, everything already applied is recoverable from Ghidra.
- **You are not scored on how many functions you name.** The driver measures accuracy, by
  decompiling a sample of your names. A batch of 8 correct names beats 30 plausible ones, and
  there is no penalty for returning mostly skips.
- **Skipping is a first-class result and costs you nothing.** A wrong name is worse than no name.
  Confirm a skip by disassembly before declaring something an empty stub.
- **Cite evidence in the justification** — address, string, caller/xref site, constant.
  "Same base+offset pattern as `Track_GetFlashSlotAddr` @0x0801f2c4" is a justification;
  "appears to handle radio config" is not.
- **Never silently overwrite a name, type or plate comment you disagree with.** Record the
  conflict (`set_bookmark`, category `CONFLICT`) and leave the existing state alone.
- **Check for a name collision before renaming** (`search_functions` on your intended name).
- **One `ToolSearch` call up front** to select your whole tool set; `batch_decompile` ~8 at a
  time.
- **Zero-caller target** → `get_xrefs_to` on the **address** to find its dispatch table, then
  read the table's other entries for subsystem context.
- **Stay inside your assigned address band.** Interesting things outside it go in the leads
  queue (`set_bookmark`, category `LEAD`), not in your batch.
- **HIGH** = unambiguous (a string, a known algorithm's constants, an unmistakable register
  sequence). **MEDIUM** = strongly implied by dataflow or by named callees. Anything weaker is a
  **SKIP**, not a LOW.
