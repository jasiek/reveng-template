#!/usr/bin/env python3
"""Campaign state: what has been done, what is in flight, what to do next.

    python3 tools/campaign_state.py snapshot     # recompute from live Ghidra + ledger, write state
    python3 tools/campaign_state.py status       # print the resume brief (read-only)

Writes CAMPAIGN_STATE.json at the repo root. It is DERIVED, never hand-edited: every number comes
from the live program or from ledger/renames.csv, so it cannot drift from the artifact the way a
prose note does. Commit it — a fresh session (or a fresh agent) reads it to answer "where were we"
without re-deriving anything.

Free-text notes that are NOT derivable (pending reconciliations, standing leads) live in
`notes` and are preserved across snapshots; edit them with `note --add` / `note --clear`.
"""
import argparse, csv, datetime, json, os, pathlib, re, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / "CAMPAIGN_STATE.json"
SCRATCH = ROOT / "scratchpad"
LEDGER = ROOT / "ledger" / "renames.csv"
URL = os.environ.get("GHIDRA_MCP_URL", "http://127.0.0.1:8089")
# the Ghidra program name, for the snapshot header; TARGET.md is the authority
PROGRAM = os.environ.get("GHIDRA_PROGRAM", "")
UNNAMED = ("FUN_", "SUB_", "thunk_FUN_")


def program_name() -> str:
    """The Ghidra program name, asked of the bridge. Never hard-code a target name in a tool:
    the template is target-agnostic and TARGET.md is the authority for humans."""
    for ep in ("get_metadata", "check_connection"):
        try:
            with urllib.request.urlopen(f"{URL}/{ep}", timeout=30) as r:
                txt = r.read().decode("utf-8", "replace")
        except Exception:
            continue
        try:
            d = json.loads(txt)
        except ValueError:
            m = re.search(r"[\w.\-]+\.(?:bin|hex|elf|img|spi|dfu)", txt)
            if m:
                return m.group(0)
            continue
        if isinstance(d, dict):
            for k in ("program", "name", "program_name", "programName"):
                if d.get(k):
                    return str(d[k])
    return "unknown"


def live_functions() -> list[dict]:
    with urllib.request.urlopen(f"{URL}/list_functions_enhanced?limit=10000", timeout=120) as r:
        data = json.load(r)
    return data["functions"] if isinstance(data, dict) else data


def ledger_final() -> dict[str, tuple[str, str]]:
    """address -> (final name, confidence); later rows win, so CORRECTION rows supersede."""
    out: dict[str, tuple[str, str]] = {}
    with LEDGER.open() as f:
        for row in csv.reader(f):
            if len(row) >= 4 and row[0] != "address":
                out[row[0].lower()] = (row[2], row[3])
    return out


def param_coverage() -> dict:
    """Parameter-naming coverage, derived from the ExportSignatures dump + ledger.

    sigs.json lives in the gitignored scratchpad because it is a derived artifact of
    the live program, so its export time is recorded here: a stale export must be
    visible as staleness rather than reported as coverage.
    """
    sigs_path = ROOT / "scratchpad" / "params" / "sigs.json"
    out = {"exported": None, "functions_with_params": 0, "params_total": 0,
           "params_named": 0, "percent": 0.0, "ledger_rows": 0,
           "uncommitted": 0, "confidence": {"HIGH": 0, "MEDIUM": 0, "LOW": 0}}
    if not sigs_path.exists():
        out["note"] = "no export - run ghidra_scripts/ExportSignatures.py"
        return out
    out["exported"] = datetime.datetime.fromtimestamp(
        sigs_path.stat().st_mtime).isoformat(timespec="seconds")
    fns = json.loads(sigs_path.read_text())["functions"]
    named = 0
    for f in fns:
        if not f["params"]:
            continue
        out["functions_with_params"] += 1
        for p in f["params"]:
            out["params_total"] += 1
            if p["name"] != f"param_{p['ord'] + 1}":
                named += 1
    out["params_named"] = named
    out["percent"] = round(100 * named / out["params_total"], 1) if out["params_total"] else 0.0

    pledger = ROOT / "ledger" / "params.csv"
    if pledger.exists():
        rows = list(csv.DictReader(pledger.open()))
        out["ledger_rows"] = len(rows)
        for r in rows:
            c = r.get("confidence", "")
            if c in out["confidence"]:
                out["confidence"][c] += 1
        out["uncommitted"] = named - len(rows)
    else:
        out["uncommitted"] = named
    return out


def snapshot(load_only: bool = False) -> dict:
    prev = json.loads(STATE.read_text()) if STATE.exists() else {}
    if load_only:
        return prev

    fns = live_functions()
    named = [f for f in fns if not f["name"].startswith(UNNAMED)]
    led = ledger_final()
    # a row can revert an address back to FUN_ (a driver correction of a wrong name);
    # the final ledger state for that address is then "unnamed" and it must not count
    # toward ledger_addresses, or the comparison against live-Ghidra `named` is off by
    # however many corrections have happened.
    led_named = {a: v for a, v in led.items() if not v[0].startswith(UNNAMED)}

    waves = {}
    for batch in sorted(SCRATCH.glob("*_batch_*.txt")):
        m = re.match(r"(.+)_batch_(\d+)$", batch.stem)
        if not m:
            continue
        wave, idx = m.group(1), int(m.group(2))
        targets = [t.strip().lower() for t in batch.read_text().strip().split(",") if t.strip()]
        by_addr = {f["address"].lower(): f["name"] for f in fns}
        landed = [t for t in targets if not by_addr.get(t, "FUN_").startswith(UNNAMED)]
        # current convention first, then the legacy name earlier waves used
        result = SCRATCH / f"result_{wave}_{idx}.json"
        if not result.exists():
            result = SCRATCH / f"{wave}_result_{idx}.json"
        w = waves.setdefault(wave, {"batches": []})
        w["batches"].append({
            "index": idx,
            "batch_file": str(batch.relative_to(ROOT)),
            "targets": len(targets),
            "landed": len(landed),
            "still_FUN_": len(targets) - len(landed),
            "result_file": str(result.relative_to(ROOT)) if result.exists() else None,
            "band": f"0x{targets[0].upper()}-0x{targets[-1].upper()}" if targets else None,
        })
    for w in waves.values():
        w["targets"] = sum(b["targets"] for b in w["batches"])
        w["landed"] = sum(b["landed"] for b in w["batches"])
        w["complete"] = all(b["result_file"] for b in w["batches"])

    # scratchpad/ is disposable, so a wave whose batch files have been cleaned would otherwise
    # vanish from the history on the next snapshot. Carry forward what we already recorded and
    # mark it, rather than silently deleting the record of finished work.
    for name, old_w in (prev.get("waves") or {}).items():
        if name not in waves:
            old_w["batch_files_gone"] = True
            waves[name] = old_w

    conf = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for _, c in led_named.values():
        if c in conf:
            conf[c] += 1

    state = {
        "program": PROGRAM or program_name(),
        "updated": datetime.datetime.now().isoformat(timespec="seconds"),
        "coverage": {
            "functions_defined": len(fns),
            "functions_named": len(named),
            "ledger_addresses": len(led_named),
            "percent": round(100 * len(named) / len(fns), 1) if fns else 0,
            "confidence": conf,
            "uncommitted_renames": len(named) - len(led_named),
            "caveat": "functions_defined counts only DEFINED functions; see docs/UNDEFINED_CODE.md "
                      "- 8.4% of flash text (34KB, measured from function body extents) is in no "
                      "Function object, so this denominator is "
                      "incomplete and the true percentage is lower",
        },
        "params": param_coverage(),
        "waves": waves,
        "notes": prev.get("notes", []),
    }
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    return state


def render(s: dict) -> str:
    c = s["coverage"]
    L = [f"CAMPAIGN STATE  ({s['updated']})  program {s['program']}", ""]
    L.append(f"  named {c['functions_named']}/{c['functions_defined']} = {c['percent']}%  "
             f"(HIGH {c['confidence']['HIGH']} / MEDIUM {c['confidence']['MEDIUM']})")
    L.append(f"  ledger rows (unique addresses): {c['ledger_addresses']}")
    u = c.get("uncommitted_renames", 0)
    if u > 0:
        L.append(f"  ** {u} renames are in the program but NOT in the ledger — commit them:")
        L.append(f"     verify_wave.py --wave <w>  then  commit_renames.sh <w>_consolidated.tsv")
    elif u < 0:
        L.append(f"  ** ledger has {-u} addresses the program does not name — investigate before trusting it")
    L.append(f"  !! {c['caveat']}")
    p = s.get("params")
    if p:
        L.append("")
        if p.get("note"):
            L.append(f"  parameters: {p['note']}")
        else:
            L.append(f"  parameters named {p['params_named']}/{p['params_total']} = "
                     f"{p['percent']}%  over {p['functions_with_params']} functions "
                     f"(HIGH {p['confidence']['HIGH']} / MEDIUM {p['confidence']['MEDIUM']})")
            L.append(f"  parameter ledger rows: {p['ledger_rows']}  "
                     f"(export taken {p['exported']})")
            if p["uncommitted"] > 0:
                L.append(f"  ** {p['uncommitted']} parameter names are in the program but NOT "
                         f"in ledger/params.csv — tools/verify_params.py --ledger")
            elif p["uncommitted"] < 0:
                L.append(f"  ** ledger/params.csv has {-p['uncommitted']} rows the program does "
                         f"not carry — re-export before trusting it")
    L.append("")
    for wave in sorted(s["waves"], key=lambda w: (len(w), w)):
        w = s["waves"][wave]
        flag = "complete" if w["complete"] else "IN FLIGHT"
        L.append(f"  wave {wave}: {w['landed']}/{w['targets']} landed  [{flag}]")
        for b in w["batches"]:
            miss = "" if b["result_file"] else "   <- no result file"
            L.append(f"      batch {b['index']}  {b['landed']:3d}/{b['targets']:<3d} "
                     f"{b['band']}{miss}")
    if s.get("notes"):
        L += ["", "  OPEN NOTES (not derivable — kept by hand):"]
        L += [f"    - {n}" for n in s["notes"]]
    L += ["", "  RESUME: reconnect MCP, run `snapshot` again, then relaunch only the still-FUN_",
          "          slice. Never hand-type addresses — tools/emit_batch_prompts.py."]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot")
    sub.add_parser("status")
    n = sub.add_parser("note")
    n.add_argument("--add")
    n.add_argument("--clear", action="store_true")
    a = ap.parse_args()

    if a.cmd == "note":
        s = snapshot(load_only=True)
        s.setdefault("notes", [])
        if a.clear:
            s["notes"] = []
        if a.add:
            s["notes"].append(a.add)
        STATE.write_text(json.dumps(s, indent=2) + "\n")
        print("\n".join(f"  - {x}" for x in s["notes"]) or "  (no notes)")
        return 0

    s = snapshot(load_only=(a.cmd == "status"))
    if not s:
        sys.exit("no CAMPAIGN_STATE.json yet — run `snapshot` first (needs Ghidra running)")
    print(render(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
