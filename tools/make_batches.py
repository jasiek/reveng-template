#!/usr/bin/env python3
"""Target selection for a naming wave — the lever with the biggest effect on yield.

Reads the live function list from Ghidra, subtracts everything already named and
every band already swept, applies a selection strategy, and writes the batch files
the subagents read.

    python3 tools/make_batches.py --wave run07 --strategy contiguous --count 180
    python3 tools/make_batches.py --wave run08 --strategy fresh --min-addr 0x08040000
    python3 tools/make_batches.py --wave run09 --strategy zero-caller

Strategies, in the order you should use them across a campaign (see
docs/NAMING_PLAYBOOK.md §3 — this ordering is worth ~15 waves):

  contiguous   sort the unnamed by address, take the lowest un-swept run. The
               workhorse: adjacent functions are the same subsystem, so a batch is
               a coherent cluster and hit-rate roughly doubles vs scattered picks.
  fresh        contiguous, but starting above --min-addr, so picked-over low bands
               full of hard stubs are not re-swept every wave.
  zero-caller  functions no other function calls: reached only through pointer,
               jump and vector tables. Invisible to call-graph ranking, and in the
               reference project ~245 of them were real, nameable handlers.
  hubs         highest caller in-degree first. Good for picking early ANCHORS,
               poor as a bulk strategy — do not spend a campaign on it.

Swept bands are recorded in scratchpad/swept.json so `contiguous` and `fresh`
never hand the same addresses out twice.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_wave import fetch_functions, is_named, norm, read_ledger  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SCRATCH = REPO / "scratchpad"
SWEPT = SCRATCH / "swept.json"
DEFAULT_URL = os.environ.get("GHIDRA_MCP_URL", "http://127.0.0.1:8089")


def http_json(url: str, path: str, timeout: int = 120):
    with urllib.request.urlopen(f"{url.rstrip('/')}/{path}", timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    data = json.loads(raw)
    for _ in range(3):
        if isinstance(data, str):
            data = json.loads(data)
        elif isinstance(data, dict) and "result" in data:
            data = data["result"]
        else:
            break
    return data


def caller_counts(url: str) -> dict[str, int]:
    """Caller in-degree per function address, from the full call graph."""
    try:
        graph = http_json(url, "get_full_call_graph?format=edges&limit=200000")
    except Exception as exc:                                    # noqa: BLE001
        sys.exit(f"could not fetch the call graph: {exc}\n"
                 "Use --strategy contiguous, which needs only the function list.")
    edges = graph.get("edges", graph) if isinstance(graph, dict) else graph
    counts: dict[str, int] = {}
    for e in edges:
        if isinstance(e, dict):
            callee = e.get("to") or e.get("callee") or e.get("target")
        elif isinstance(e, (list, tuple)) and len(e) >= 2:
            callee = e[1]
        else:
            continue
        if callee:
            counts[norm(str(callee))] = counts.get(norm(str(callee)), 0) + 1
    return counts


def load_swept() -> list[list[int]]:
    if SWEPT.exists():
        return json.loads(SWEPT.read_text())
    return []


def save_swept(bands: list[list[int]]) -> None:
    SCRATCH.mkdir(exist_ok=True)
    SWEPT.write_text(json.dumps(sorted(bands), indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wave", required=True, help="wave prefix, e.g. run07")
    ap.add_argument("--strategy", default="contiguous",
                    choices=["contiguous", "fresh", "zero-caller", "hubs"])
    ap.add_argument("--count", type=int, default=180, help="total targets (default 180)")
    ap.add_argument("--batches", type=int, default=6, help="batch files / subagents (default 6)")
    ap.add_argument("--min-addr", default="0", help="lower bound for --strategy fresh")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--from-file", type=Path, help="saved list_functions_enhanced result")
    ap.add_argument("--no-record", action="store_true",
                    help="do not record this band as swept (dry run)")
    args = ap.parse_args()

    fns = fetch_functions(args.url, args.from_file)
    ledger_addr, _ = read_ledger()
    unnamed = sorted(
        (int(a, 16), a) for a, v in fns.items()
        if not is_named(v["name"]) and not v["thunk"] and a not in ledger_addr
    )
    if not unnamed:
        print("nothing left unnamed — the campaign has hit its floor. "
              "See docs/NAMING_PLAYBOOK.md §10.")
        return 0
    print(f"{len(unnamed)} unnamed functions in the program")

    swept = load_swept()
    if args.strategy in ("contiguous", "fresh"):
        floor = int(args.min_addr, 0)
        pool = [(n, a) for n, a in unnamed if n >= floor
                and not any(lo <= n <= hi for lo, hi in swept)]
        if not pool:
            print("every band above --min-addr has been swept. Either lower the bound to\n"
                  "re-attack the quarantined stubs with a frontier model, or stop.")
            return 1
        picked = pool[:args.count]
    elif args.strategy == "zero-caller":
        counts = caller_counts(args.url)
        picked = [(n, a) for n, a in unnamed if counts.get(a, 0) == 0][:args.count]
        print(f"{len(picked)} zero-caller targets — subagents must use get_xrefs_to on the "
              f"ADDRESS to find each dispatch table")
    else:  # hubs
        counts = caller_counts(args.url)
        picked = sorted(unnamed, key=lambda t: -counts.get(t[1], 0))[:args.count]

    if not picked:
        print("strategy produced no targets")
        return 1

    lo, hi = picked[0][0], picked[-1][0]
    SCRATCH.mkdir(exist_ok=True)
    per = (len(picked) + args.batches - 1) // args.batches
    written = []
    for i in range(args.batches):
        chunk = picked[i * per:(i + 1) * per]
        if not chunk:
            break
        path = SCRATCH / f"{args.wave}_batch_{i}.txt"
        path.write_text(",".join(fns[a]["raw_address"] for _, a in chunk))
        written.append((path, len(chunk), chunk[0][0], chunk[-1][0]))

    print(f"\nwave {args.wave}: {len(picked)} targets, {len(written)} batches, "
          f"strategy {args.strategy}")
    for path, count, first, last in written:
        print(f"  {path.relative_to(REPO)}  {count:>3} targets  "
              f"0x{first:08X}–0x{last:08X}")

    if args.strategy in ("contiguous", "fresh") and not args.no_record:
        swept.append([lo, hi])
        save_swept(swept)
        print(f"\nrecorded 0x{lo:08X}–0x{hi:08X} as swept "
              f"({SWEPT.relative_to(REPO)}) — it will not be handed out again")
    print("\nLaunch one subagent per batch with the §6 template plus "
          "docs/SUBAGENT_CONTRACT.md, then verify with:\n"
          f"  python3 tools/verify_wave.py --wave {args.wave}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
