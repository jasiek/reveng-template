#!/usr/bin/env python3
"""Find the hub/sink functions a band bottoms out in, so the DRIVER can name them
before fanning out subagents.

    python3 tools/find_hubs.py --wave run15            # after make_batches
    python3 tools/find_hubs.py --from-batches scratchpad/run15_batch_*.txt

WHY THIS EXISTS
---------------
Wave run14 ran a pre-registered A/B on batch size (docs/BATCH_SIZE_EXPERIMENT.md) and found
batch size does not matter. What limited BOTH arms was the same thing: targets whose identity
depends on one unnamed function nobody had named yet.

The pattern repeats every wave. In run13, naming two event sinks (Key_PostKeyEvent,
Key_ArmHoldTimer) cost the driver about six tool calls and unlocked targets across FOUR separate
batches -- but it happened *after* the fan-out, so 26 targets had already been skipped against a
blocker that no longer existed and had to be re-run. Agents say it out loud in their reports:
"naming FUN_0305C0D4 would unlock four of my skips".

A sink is invisible to any single agent: agent 3 sees it called twice, agent 5 sees it called
twice, and neither knows it has twenty callers in total. Only a whole-band view finds it. That is
the driver's job, and it is cheap.

WHAT IT REPORTS
---------------
  SINKS   unnamed functions called by many of THIS WAVE's targets. Naming one of these resolves
          the "what does this constant/queue/flag mean" question for every target that calls it.
  HUBS    unnamed functions with high in-degree across the WHOLE program that also sit in or near
          the band. Broader leverage, and a wrong name here is expensive -- so these are exactly
          the ones a capable driver should name by hand rather than delegate.

Both are ranked. Name the top few yourself, THEN emit the batch prompts so the agents start with
the answer instead of discovering the question.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_wave import fetch_functions, is_named, read_ledger  # noqa: E402

DEFAULT_URL = "http://127.0.0.1:8089"
SCRATCH = Path(__file__).resolve().parent.parent / "scratchpad"


def call_edges(url: str) -> list[tuple[str, str]]:
    """(caller_name, callee_name) pairs. See make_batches.caller_counts for the format traps."""
    with urllib.request.urlopen(
            f"{url.rstrip('/')}/get_full_call_graph?limit=200000", timeout=300) as r:
        raw = r.read().decode("utf-8", "replace")
    edges = [(a.strip(), b.strip())
             for a, _, b in (ln.partition("->") for ln in raw.splitlines()) if b.strip()]
    if len(edges) <= 600:
        sys.exit(f"call graph returned only {len(edges)} edges - that is the bridge's default "
                 "cap, not the whole program. Refusing to report misleading hubs.")
    return edges


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wave", help="wave prefix; reads scratchpad/<wave>_batch_*.txt")
    ap.add_argument("--from-batches", nargs="*", help="explicit batch files")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()

    files = a.from_batches or sorted(glob.glob(str(SCRATCH / f"{a.wave}_batch_*.txt")))
    if not files:
        sys.exit("no batch files; run make_batches.py first or pass --from-batches")
    targets = set()
    for f in files:
        targets |= {t.strip().lower().lstrip("0")
                    for t in re.split(r"[,\s]+", Path(f).read_text()) if t.strip()}

    fns = fetch_functions(a.url, None)
    ledger_addr, _ = read_ledger()
    by_name = {v["name"]: k for k, v in fns.items()}
    unnamed = {k for k, v in fns.items()
               if not is_named(v["name"]) and not v["thunk"] and k not in ledger_addr}
    norm = lambda x: x.lower().lstrip("0")  # noqa: E731
    tgt_names = {fns[k]["name"] for k in fns if norm(k) in targets}

    edges = call_edges(a.url)
    from_targets: Counter = Counter()
    total_in: Counter = Counter()
    callers_of: dict[str, set] = defaultdict(set)
    for caller, callee in edges:
        total_in[callee] += 1
        callers_of[callee].add(caller)
        if caller in tgt_names:
            from_targets[callee] += 1

    def row(name, n_t, n_all):
        addr = by_name.get(name)
        return f"  {addr or '????????'}  {name:<28} in-band {n_t:3d}   program-wide {n_all:4d}"

    print(f"{len(targets)} targets, {len(edges)} call edges, {len(unnamed)} unnamed functions\n")

    print(f"=== SINKS - unnamed, called by THIS WAVE's targets (top {a.top})")
    print("    naming these before fan-out is the highest-leverage driver work")
    sinks = [(n, c) for n, c in from_targets.most_common()
             if by_name.get(n) in unnamed and c >= 2]
    for n, c in sinks[:a.top]:
        print(row(n, c, total_in[n]))
    if not sinks:
        print("  (none - this band does not bottom out in a shared unnamed function)")

    print(f"\n=== HUBS - unnamed, high program-wide in-degree (top {a.top})")
    print("    broad leverage; a wrong name here propagates furthest, so name these by hand")
    hubs = [(n, c) for n, c in total_in.most_common()
            if by_name.get(n) in unnamed and c >= 5]
    for n, c in hubs[:a.top]:
        print(row(n, from_targets.get(n, 0), c))
    if not hubs:
        print("  (none)")

    out = SCRATCH / f"{a.wave or 'hubs'}_hubs.json"
    out.write_text(json.dumps({
        "sinks": [{"addr": by_name.get(n), "name": n, "in_band": c,
                   "program_wide": total_in[n]} for n, c in sinks[:a.top]],
        "hubs": [{"addr": by_name.get(n), "name": n, "in_band": from_targets.get(n, 0),
                  "program_wide": c} for n, c in hubs[:a.top]],
    }, indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
