# <Device> Firmware — Reverse-Engineering Findings

Everything here carries an address. A claim with no address is a guess.
Target facts live in `TARGET.md`; this file is discoveries + the run log.

## Target

<one paragraph: device, firmware version + the address of the version string, MCU, RTOS, image
base, function/string counts at import.>

## Viability summary

<the two or three questions this project exists to answer, and where each stands. e.g. "Is the
image authenticated? — NO at either layer, see §Bootloader. Custom firmware is feasible.">

## Methodology (the pipeline)

<how names got here: waves, models, target-selection strategy. Point at docs/NAMING_PLAYBOOK.md
rather than restating it.>

### Restarting later

<the exact resume move: /re-verify, then relaunch the still-FUN_ slice.>

## Architecture map

| Subsystem | Entry point | Key addresses | Notes |
|---|---|---|---|
| | | | |

## Memory & peripherals

<peripheral bus map: which lines are hardware blocks and which are bit-banged GPIO, with the
address of the code that proves it.>

## Key discoveries

- **<discovery>** — `<address>`. <evidence.>

## Progress log

### Run 1 — <strategy> (<date>)

- Targets: <how selected>, <N> addresses, <M> agents, model <tier>.
- Landed: <N> (HIGH <n> / MEDIUM <n>), skipped <n>.
- New discoveries: <…>
- Coverage: <named>/<total> (<pct>%).

## Open questions / next steps

- [ ] <question> — <what would answer it, and roughly what it costs>

## Residue

<what is deliberately left un-named and why (empty stubs, thunks, dead code). This is the record
that the campaign stopped on purpose, not by exhaustion.>
