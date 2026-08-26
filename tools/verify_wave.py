#!/usr/bin/env python3
"""The live-Ghidra diff — the one verification step you must never skip.

Subagent prose is not evidence. This asks the running program what actually
landed, and reconciles it against the ledger.

    python3 tools/verify_wave.py --wave run07              # after a wave
    python3 tools/verify_wave.py --orphans                 # after a crash: whole program
    python3 tools/verify_wave.py --glossary                # regenerate the prefix vocabulary
    python3 tools/verify_wave.py --wave run07 --from-file live.json

Outputs (for --wave):
    scratchpad/<wave>_consolidated.tsv   ->  feed to tools/commit_renames.sh
    scratchpad/<wave>_orphans.json       ->  addresses whose metadata must be
                                             recovered from their plate comments

Exit status is 0 even when there are collisions — they are a normal result to be
reconciled, not an error.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "ledger" / "renames.csv"
SCRATCH = REPO / "scratchpad"
DEFAULT_URL = os.environ.get("GHIDRA_MCP_URL", "http://127.0.0.1:8089")

UNNAMED = ("FUN_", "thunk_FUN_", "SUB_", "LAB_")


def norm(addr: str) -> str:
    """Normalise an address to bare lowercase hex, zero-stripped."""
    a = addr.strip().lower().replace("0x", "")
    a = a.split(":")[-1]          # space-qualified addresses, e.g. "ram:08004000"
    return a.lstrip("0") or "0"


def fetch_functions(url: str, from_file: Path | None) -> dict[str, dict]:
    """Return {normalised address: {name, isThunk}} from live Ghidra or a saved dump."""
    if from_file:
        raw = from_file.read_text()
    else:
        endpoint = f"{url.rstrip('/')}/list_functions_enhanced?limit=100000"
        try:
            with urllib.request.urlopen(endpoint, timeout=60) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except (urllib.error.URLError, OSError) as exc:
            sys.exit(
                f"cannot reach Ghidra at {endpoint}: {exc}\n"
                "The Ghidra GUI with the GhidraMCP plugin is not running, or is on another\n"
                "port. Start it (you cannot start it from here), or pass --from-file with a\n"
                "saved list_functions_enhanced result."
            )

    data = json.loads(raw)
    # Unwrap every shape the bridge/plugin can hand back.
    for _ in range(3):
        if isinstance(data, str):
            data = json.loads(data)
        elif isinstance(data, dict) and "result" in data:
            data = data["result"]
        elif isinstance(data, dict) and "functions" in data:
            data = data["functions"]
        else:
            break
    if not isinstance(data, list):
        sys.exit(f"unexpected response shape: {type(data).__name__}")

    out = {}
    for f in data:
        addr = f.get("address") or f.get("entry") or f.get("entryPoint")
        if not addr:
            continue
        out[norm(str(addr))] = {
            "name": f.get("name", ""),
            "thunk": bool(f.get("isThunk") or f.get("thunk")),
            "raw_address": str(addr),
        }
    return out


def read_ledger() -> tuple[dict[str, str], dict[str, str]]:
    """Return ({address: new_name}, {new_name: address})."""
    by_addr, by_name = {}, {}
    if not LEDGER.exists():
        return by_addr, by_name
    with LEDGER.open(newline="") as fh:
        for row in csv.reader(fh):
            if not row or row[0].strip().lower() in ("address", "#address"):
                continue
            if len(row) < 3:
                continue
            by_addr[norm(row[0])] = row[2]
            by_name[row[2]] = norm(row[0])
    return by_addr, by_name


def read_wave_targets(wave: str) -> set[str]:
    targets: set[str] = set()
    files = sorted(SCRATCH.glob(f"{wave}_batch_*.txt"))
    if not files:
        sys.exit(f"no batch files matching {SCRATCH}/{wave}_batch_*.txt")
    for path in files:
        for tok in re.split(r"[,\s]+", path.read_text().strip()):
            if tok:
                targets.add(norm(tok))
    return targets


def read_wave_meta(wave: str) -> dict[str, dict]:
    meta: dict[str, dict] = {}
    for path in sorted(SCRATCH.glob(f"result_{wave}_*.json")):
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            print(f"  ! {path.name} is not valid JSON — ignoring it "
                  f"(its renames still land via the live diff)", file=sys.stderr)
            continue
        for item in payload.get("renamed", []):
            addr = norm(str(item.get("addr") or item.get("address", "")))
            if not addr:
                continue
            just = re.sub(r"[,\n\t]+", " ", str(item.get("justification", ""))).strip()
            meta[addr] = {
                "conf": str(item.get("confidence", "MEDIUM")).upper(),
                "just": just,
                "old": item.get("old", ""),
            }
    return meta


def disp(addr: str, fns: dict | None = None) -> str:
    """Display form of an address: prefer exactly what Ghidra calls it."""
    if fns and addr in fns:
        return "0x" + fns[addr]["raw_address"].lower().replace("0x", "")
    return "0x" + addr.rjust(8, "0")


def is_named(name: str) -> bool:
    return bool(name) and not name.startswith(UNNAMED)


def report_wave(wave: str, fns: dict, ledger_addr: dict, ledger_name: dict) -> None:
    targets = read_wave_targets(wave)
    meta = read_wave_meta(wave)

    landed = {
        a: fns[a]["name"]
        for a in targets
        if a in fns and is_named(fns[a]["name"]) and not fns[a]["thunk"]
        and a not in ledger_addr
    }
    still_fun = sorted(a for a in targets if a in fns and not is_named(fns[a]["name"]))
    absent = sorted(a for a in targets if a not in fns)
    missing_meta = sorted(a for a in landed if a not in meta)
    collisions = [(a, n) for a, n in landed.items() if n in ledger_name]
    by_name = defaultdict(list)
    for a, n in landed.items():
        by_name[n].append(a)
    dups = {n: a for n, a in by_name.items() if len(a) > 1}

    print(f"wave {wave}: {len(targets)} targets")
    print(f"  landed        {len(landed)}")
    print(f"  still FUN_    {len(still_fun)}   <- relaunch only these")
    print(f"  not in program{len(absent):>4}   (bad address in the batch file)" if absent
          else "  not in program   0")
    print(f"  missing meta  {len(missing_meta)}   <- recover from plate comments")
    print(f"  collisions    {len(collisions)}   <- rename one side before committing")
    print(f"  dups in wave  {len(dups)}")

    if collisions:
        print("\ncollisions (new name already in the ledger at another address):")
        for a, n in collisions:
            print(f"  {disp(a, fns)}  {n}  (ledger has it at {disp(ledger_name[n], fns)})")
    if dups:
        print("\nduplicate names inside this wave:")
        for n, addrs in dups.items():
            print(f"  {n}: {', '.join(disp(a, fns) for a in addrs)}")
    if missing_meta:
        print("\nmissing metadata — run get_plate_comment on each and fill the TSV:")
        print("  " + ", ".join(disp(a, fns) for a in missing_meta[:40]))
        if len(missing_meta) > 40:
            print(f"  … and {len(missing_meta) - 40} more (see the orphans file)")

    SCRATCH.mkdir(exist_ok=True)
    tsv = SCRATCH / f"{wave}_consolidated.tsv"
    with tsv.open("w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        for a in sorted(landed):
            m = meta.get(a, {})
            w.writerow([
                fns[a]["raw_address"],
                m.get("old") or "FUN_" + fns[a]["raw_address"].upper().replace("0X", ""),
                landed[a],                      # live Ghidra name is authoritative
                m.get("conf", "UNKNOWN"),
                m.get("just", "RECOVER FROM PLATE COMMENT"),
            ])
    orphans = SCRATCH / f"{wave}_orphans.json"
    orphans.write_text(json.dumps(
        {"missing_meta": missing_meta, "still_fun": still_fun,
         "landed": {a: landed[a] for a in landed}}, indent=2))

    print(f"\nwrote {tsv.relative_to(REPO)}  ({len(landed)} rows)")
    print(f"wrote {orphans.relative_to(REPO)}")
    if any(m.get("conf") == "UNKNOWN" or "RECOVER" in m.get("just", "")
           for m in (meta.get(a, {}) for a in landed)):
        print("\nFill the UNKNOWN/RECOVER rows from plate comments BEFORE committing —\n"
              "an unjustified ledger row is exactly the thing the ledger exists to prevent.")


def report_orphans(fns: dict, ledger_addr: dict) -> None:
    """Whole-program reconciliation — the crash-recovery move."""
    named = {a: v["name"] for a, v in fns.items() if is_named(v["name"]) and not v["thunk"]}
    orphans = {a: n for a, n in named.items() if a not in ledger_addr}
    stale = {a: n for a, n in ledger_addr.items()
             if a in fns and fns[a]["name"] != n}
    ghosts = {a: n for a, n in ledger_addr.items() if a not in fns}
    total = len(fns)

    print(f"program: {total} functions, {len(named)} named ({100*len(named)/total:.1f}%), "
          f"{total - len(named)} still FUN_/thunk")
    print(f"ledger:  {len(ledger_addr)} rows")
    print(f"  orphan renames (in Ghidra, not in ledger): {len(orphans)}  <- commit these")
    print(f"  ledger disagrees with Ghidra:              {len(stale)}   <- Ghidra wins")
    print(f"  ledger rows with no function in Ghidra:    {len(ghosts)}")

    SCRATCH.mkdir(exist_ok=True)
    out = SCRATCH / "orphans.json"
    out.write_text(json.dumps({
        "orphans": orphans, "ledger_disagrees": stale, "ledger_ghosts": ghosts,
        "still_unnamed": sorted(a for a, v in fns.items() if not is_named(v["name"])),
    }, indent=2))
    print(f"\nwrote {out.relative_to(REPO)}")
    if orphans:
        print("Next: get_plate_comment on each orphan for its [confidence: …] role, then\n"
              "      commit_renames.sh. Only then relaunch the still-FUN_ slice.")


def report_glossary(fns: dict) -> None:
    """Regenerate the prefix vocabulary from the names actually in the program."""
    prefixes = Counter()
    for v in fns.values():
        name = v["name"]
        if not is_named(name):
            continue
        m = re.match(r"([A-Za-z][A-Za-z0-9]*)_", name)
        prefixes[m.group(1) if m else "(none)"] += 1
    print("| Prefix | Functions |")
    print("|---|---|")
    for pfx, count in prefixes.most_common():
        label = "(no prefix)" if pfx == "(none)" else f"`{pfx}_`"
        print(f"| {label} | {count} |")
    lower = defaultdict(list)
    for pfx in (p for p in prefixes if p != "(none)"):
        lower[pfx.lower()].append(pfx)
    drift = {k: v for k, v in lower.items() if len(v) > 1}
    if drift:
        print("\nPREFIX DRIFT — pick one spelling and normalise the other:")
        for k, variants in drift.items():
            print(f"  {' vs '.join(f'{v}_ ({prefixes[v]})' for v in variants)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--wave", help="wave prefix, e.g. run07")
    mode.add_argument("--orphans", action="store_true",
                      help="whole-program reconciliation (crash recovery)")
    mode.add_argument("--glossary", action="store_true",
                      help="regenerate the prefix vocabulary from live names")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"Ghidra plugin URL (default {DEFAULT_URL})")
    ap.add_argument("--from-file", type=Path,
                    help="use a saved list_functions_enhanced result instead of HTTP")
    args = ap.parse_args()

    fns = fetch_functions(args.url, args.from_file)
    if not fns:
        sys.exit("Ghidra returned no functions — is the right program open?")
    ledger_addr, ledger_name = read_ledger()

    if args.glossary:
        report_glossary(fns)
    elif args.orphans:
        report_orphans(fns, ledger_addr)
    else:
        report_wave(args.wave, fns, ledger_addr, ledger_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
