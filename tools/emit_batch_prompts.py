#!/usr/bin/env python3
"""Build one ready-to-launch agent prompt per batch — WITHOUT the driver ever typing an address.

    python3 tools/emit_batch_prompts.py --wave 9 --brief scratchpad/run09_prompt_common.txt

Writes scratchpad/<wave>_prompt_<i>.txt. Launch each with a one-line Agent prompt:

    Read scratchpad/9_prompt_3.txt and follow it exactly.

WHY THIS EXISTS
---------------
In wave 9 the driver hand-typed the 30-address target lists into six subagent prompts instead of
reading scratchpad/9_batch_*.txt. All 180 addresses were fabricated. Worse, the fabricated lists
had suspiciously regular strides, so the driver "noticed a family of near-identical handlers" that
did not exist and told three agents to go find its distinguishing constant. Every agent had to
discover the problem and re-derive the real entries itself.

The fix is structural, not a reminder to be careful: the addresses live in a file, the agent reads
that file, and the driver never handles them. This script also verifies every target against the
live program before emitting, so a stale or malformed batch file fails loudly here rather than
silently wasting six agents.
"""
import argparse, json, os, pathlib, re, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRATCH = ROOT / "scratchpad"
URL = os.environ.get("GHIDRA_MCP_URL", "http://127.0.0.1:8089")


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


def live_entries() -> set[str]:
    with urllib.request.urlopen(f"{URL}/list_functions_enhanced?limit=10000", timeout=120) as r:
        data = json.load(r)
    fns = data["functions"] if isinstance(data, dict) else data
    return {f["address"].lower().lstrip("0") for f in fns}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", required=True)
    ap.add_argument("--brief", required=True, help="the shared band brief, pasted into every prompt")
    ap.add_argument("--no-verify", action="store_true", help="skip the live-program check")
    a = ap.parse_args()

    brief = pathlib.Path(a.brief).read_text().rstrip()
    batches = sorted(SCRATCH.glob(f"{a.wave}_batch_*.txt"))
    if not batches:
        sys.exit(f"no batch files matching {SCRATCH}/{a.wave}_batch_*.txt — run make_batches.py first")

    live = set() if a.no_verify else live_entries()
    program = os.environ.get("GHIDRA_PROGRAM") or program_name()
    bad = 0
    for path in batches:
        i = path.stem.split("_")[-1]
        targets = [t.strip().lower() for t in path.read_text().strip().split(",") if t.strip()]
        if live:
            missing = [t for t in targets if t.lstrip("0") not in live]
            if missing:
                bad += 1
                print(f"  !! {path.name}: {len(missing)} targets are NOT live function entries: "
                      f"{missing[:6]}{'...' if len(missing) > 6 else ''}", file=sys.stderr)
        out = SCRATCH / f"{a.wave}_prompt_{i}.txt"
        out.write_text(
            f"You are a Ghidra reverse-engineering subagent working over the ghidra-mcp bridge\n"
            f"(program `{program}`, cwd {ROOT}).\n\n"
            f"YOUR TARGETS ARE THE ADDRESSES IN: {path.relative_to(ROOT)}\n"
            f"Read that file yourself — `cat {path.relative_to(ROOT)}` — and work exactly those\n"
            f"{len(targets)} comma-separated addresses. They were generated from the live program\n"
            f"and verified against it. Do not infer targets from any address list quoted in prose,\n"
            f"and do not read structure (strides, families, spacing) into the ORDER of that file.\n\n"
            f"{brief}\n\n"
            f"--- OUTPUT ---\n"
            f"Rename with `mcp__ghidra-mcp__rename_function_by_address`; plate-comment IMMEDIATELY\n"
            f"after each rename with `mcp__ghidra-mcp__set_plate_comment`, starting the comment\n"
            f"`[confidence: HIGH]` or `[confidence: MEDIUM]`.\n\n"
            f"WRITE YOUR RESULT FILE LAST, exactly this path and shape:\n"
            f"  scratchpad/result_{a.wave}_{i}.json\n"
            f'  {{"renamed":[{{"address":"<addr>","new_name":"...","confidence":"HIGH",'
            f'"justification":"no commas"}}]}}\n'
            f"Include ONLY renames you actually made. NEVER run git.\n")
        print(f"  {out.relative_to(ROOT)}   {len(targets)} targets   -> result_{a.wave}_{i}.json")

    if bad:
        print(f"\nREFUSING TO VOUCH: {bad} batch file(s) contain non-entry addresses.", file=sys.stderr)
        return 1
    print(f"\nAll targets verified against the live program. Launch each agent with:\n"
          f'  "Read scratchpad/{a.wave}_prompt_<i>.txt and follow it exactly."')
    return 0


if __name__ == "__main__":
    sys.exit(main())
