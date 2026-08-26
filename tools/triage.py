#!/usr/bin/env python3
"""Offline triage for an embedded firmware image — run this before touching Ghidra.

Answers the phase-0 questions deterministically (no agent tokens):

  * What is this file?   container magic, Intel-HEX/SREC text, vendor wrapper
  * Where does it load?  Cortex-M vector-table scan -> header size + image base
  * Is it obfuscated?    entropy profile + repeating-XOR key recovery
  * What is inside?      strings, version/date, RTOS + library + crypto markers

Usage:
    python3 tools/triage.py firmware/IMAGE.bin
    python3 tools/triage.py firmware/IMAGE.bin --json
    python3 tools/triage.py firmware/IMAGE.bin --markdown        # paste into TARGET.md
    python3 tools/triage.py firmware/IMAGE.hex --convert out.bin # HEX/SREC -> raw
    python3 tools/triage.py firmware/IMAGE.bin --xor --write-deobf out.bin

Every number it prints is a measurement. Nothing here is inferred by a model.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
from collections import Counter
from pathlib import Path

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# Plausible initial-SP windows for Cortex-M parts (SRAM aliases).
SRAM_RANGES = [
    (0x20000000, 0x20100000),   # standard SRAM
    (0x10000000, 0x10020000),   # CCM / SRAM2 on some parts
    (0x1FFF0000, 0x20000000),   # low SRAM alias
    (0x00200000, 0x00280000),   # Kinetis SRAM_U
]

# Flash bases worth testing once the handler window is known.
KNOWN_BASES = [
    0x00000000, 0x00008000, 0x00010000,
    0x08000000, 0x08002000, 0x08004000, 0x08008000, 0x0800C000,
    0x08010000, 0x08020000, 0x08040000,
    0x01000000, 0x10000000, 0x1FFF0000, 0x60000000, 0x90000000,
]

CONTAINER_MAGIC = [
    (b"\x7fELF", 0, "ELF object — use Ghidra's ELF loader, not a raw import"),
    (b"MZ", 0, "PE/DOS image"),
    (b"UF2\n", 0, "UF2 container"),
    (b"DfuSe", 0, "DfuSe (ST DFU) container"),
    (b"PK\x03\x04", 0, "ZIP archive — unpack first"),
    (b"\x1f\x8b", 0, "gzip stream"),
    (b"BZh", 0, "bzip2 stream"),
    (b"\xfd7zXZ", 0, "xz stream"),
    (b"\x5d\x00\x00", 0, "raw LZMA stream (heuristic)"),
    (b"hsqs", 0, "SquashFS"),
    (b"UBI#", 0, "UBI volume"),
    (b"\x27\x05\x19\x56", 0, "U-Boot legacy image"),
    (b"\xd0\x0d\xfe\xed", 0, "Flattened device tree"),
]

CRYPTO_CONSTANTS = [
    (bytes.fromhex("637c777bf26b6fc53001672bfed7ab76"), "AES forward S-box"),
    (bytes.fromhex("52096ad53036a538bf40a39e81f3d7fb"), "AES inverse S-box"),
    (bytes.fromhex("c66363a5f87c7c84ee777799f67b7b8d"), "AES Te0 table"),
    (bytes.fromhex("00000000963007770e6e740697e14bee"), "CRC-32 (reflected 0xEDB88320) table"),
    (bytes.fromhex("00000000c0c1c1810281c3400381c1c1"), "CRC-16/MODBUS table (low bytes)"),
    (bytes.fromhex("982f8a42914434d7"), "SHA-256 K[0..1]"),
    (bytes.fromhex("78a46ad7"), "MD5 T[0]"),
    (bytes.fromhex("0123456789abcdeffedcba9876543210"), "SHA-1 / MD5 init vector"),
    (bytes.fromhex("99798265"), "SHA-1 K (0x5a827999, LE)"),
    (b"expand 32-byte k", "ChaCha20/Salsa20 sigma"),
]

MARKER_STRINGS = [
    # RTOS / libraries
    (rb"uC/OS-?I{1,3}", "uC/OS-II/III RTOS"),
    (rb"FreeRTOS", "FreeRTOS"),
    (rb"RT-Thread", "RT-Thread"),
    (rb"embOS", "SEGGER embOS"),
    (rb"ThreadX", "Azure/Express ThreadX"),
    (rb"newlib|__cxa_|GCC: \(", "GCC/newlib toolchain artefacts"),
    (rb"IAR |__iar", "IAR toolchain"),
    (rb"ARM Compiler|__ARMCC", "ARM Compiler (Keil)"),
    (rb"deflate 1\.|inflate 1\.|zlib", "zlib"),
    (rb"lwIP|lwip", "lwIP TCP/IP"),
    # radio-domain markers
    (rb"DMR|dmr", "DMR"),
    (rb"D-?STAR", "D-STAR"),
    (rb"P25|APCO", "P25"),
    (rb"NXDN", "NXDN"),
    (rb"C4FM|Fusion", "Yaesu System Fusion"),
    (rb"APRS", "APRS"),
    (rb"AX\.?25", "AX.25"),
    (rb"\$GP[A-Z]{3}|\$GN[A-Z]{3}", "NMEA / GPS"),
    (rb"AMBE|ambe", "AMBE vocoder"),
    (rb"CTCSS|DCS", "analog subtone signalling"),
    (rb"Bluetooth|BLE|HCI", "Bluetooth"),
    (rb"CPS|codeplug", "CPS / codeplug tooling"),
    # vendors
    (rb"AnyTone|ANYTONE", "AnyTone"),
    (rb"Baofeng|BAOFENG|BF-", "Baofeng"),
    (rb"TYT|Tytera", "TYT"),
    (rb"Retevis", "Retevis"),
    (rb"Radioddity", "Radioddity"),
    (rb"Hytera", "Hytera"),
    (rb"Motorola|MOTOTRBO", "Motorola"),
    (rb"Kenwood", "Kenwood"),
    (rb"Icom", "Icom"),
    (rb"Alinco", "Alinco"),
    (rb"Quansheng|UV-K5", "Quansheng"),
]

VERSION_RE = re.compile(
    rb"(?:[Vv]er(?:sion)?[ .:]?)?[Vv]?\d+\.\d+[A-Za-z0-9._-]*|"
    rb"20[0-3]\d[-/.]?[01]\d[-/.]?[0-3]\d|"
    rb"[A-Z][a-z]{2} [ 0-3]\d 20[0-3]\d"
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def entropy(buf: bytes) -> float:
    if not buf:
        return 0.0
    counts = Counter(buf)
    n = len(buf)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def in_sram(value: int) -> bool:
    return any(lo <= value < hi for lo, hi in SRAM_RANGES)


def hx(value: int) -> str:
    return f"0x{value:08X}"


# --------------------------------------------------------------------------- #
# Text formats (Intel HEX / Motorola S-record)
# --------------------------------------------------------------------------- #


def parse_intel_hex(text: str):
    """Return (bytes, base_address) or None."""
    out, base, upper, lowest = {}, None, 0, None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith(":"):
            continue
        raw = bytes.fromhex(line[1:])
        count, addr, rtype, payload = raw[0], (raw[1] << 8) | raw[2], raw[3], raw[4:4 + raw[0]]
        if len(payload) != count:
            return None
        if rtype == 0x00:
            full = upper + addr
            lowest = full if lowest is None else min(lowest, full)
            for i, b in enumerate(payload):
                out[full + i] = b
        elif rtype == 0x04:
            upper = int.from_bytes(payload, "big") << 16
        elif rtype == 0x02:
            upper = int.from_bytes(payload, "big") << 4
        elif rtype == 0x01:
            break
    if not out:
        return None
    lo, hi = min(out), max(out)
    blob = bytearray(b"\xff" * (hi - lo + 1))
    for a, b in out.items():
        blob[a - lo] = b
    return bytes(blob), lo


def parse_srec(text: str):
    out = {}
    addr_len = {"1": 2, "2": 3, "3": 4}
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 4 or line[0] != "S" or line[1] not in addr_len:
            continue
        alen = addr_len[line[1]]
        raw = bytes.fromhex(line[2:])
        addr = int.from_bytes(raw[1:1 + alen], "big")
        payload = raw[1 + alen:-1]
        for i, b in enumerate(payload):
            out[addr + i] = b
    if not out:
        return None
    lo, hi = min(out), max(out)
    blob = bytearray(b"\xff" * (hi - lo + 1))
    for a, b in out.items():
        blob[a - lo] = b
    return bytes(blob), lo


def maybe_text_image(data: bytes):
    head = data[:4096]
    if not all(c in b"\r\n\t " or 0x20 <= c < 0x7F for c in head):
        return None
    text = data.decode("ascii", "ignore")
    if text.lstrip().startswith(":"):
        got = parse_intel_hex(text)
        if got:
            return ("Intel HEX", *got)
    if text.lstrip().startswith("S"):
        got = parse_srec(text)
        if got:
            return ("Motorola S-record", *got)
    return None


# --------------------------------------------------------------------------- #
# Vector-table scan
# --------------------------------------------------------------------------- #


def scan_vector_tables(data: bytes, min_handlers: int = 8, min_distinct: int = 5):
    """Find Cortex-M vector tables at ANY file offset (vendor headers are rarely aligned)."""
    n = len(data)
    found = []
    # Candidate offsets: positions where the top byte of a plausible SP lives.
    tops = {(lo >> 24) & 0xFF for lo, _ in SRAM_RANGES}
    candidates = set()
    for top in tops:
        start = 0
        needle = bytes([top])
        while True:
            i = data.find(needle, start)
            if i < 0 or i >= n - 64:
                break
            if i >= 3:
                candidates.add(i - 3)
            start = i + 1
    for off in sorted(candidates):
        if off + 64 > n:
            continue
        words = struct.unpack_from("<16I", data, off)
        sp = words[0]
        if not in_sram(sp) or sp % 8:
            continue
        reset = words[1]
        if reset == 0 or not reset & 1:          # Thumb bit required
            continue
        handlers = [w for w in words[1:] if w not in (0, 0xFFFFFFFF)]
        if len(handlers) < min_handlers:
            continue
        if any(not w & 1 for w in handlers):     # every entry must be a Thumb address
            continue
        addrs = sorted(w & ~1 for w in handlers)
        span = addrs[-1] - addrs[0]
        if span > n or span == 0:
            continue
        if len(set(addrs)) < min_distinct:
            continue
        hmin, hmax = addrs[0], addrs[-1]
        # Image base L must satisfy: L <= hmin  and  L + n > hmax
        lo_bound = max(0, hmax - n + 1)
        bases = [b for b in KNOWN_BASES if lo_bound <= b <= hmin]
        # Derived candidate: table sits at the very start of the image region.
        derived = (hmin >> 12) << 12
        if lo_bound <= derived <= hmin and derived not in bases:
            bases.append(derived)
        found.append({
            "file_offset": off,
            "initial_sp": sp,
            "reset_handler": reset & ~1,
            "handler_count": len(handlers),
            "distinct_handlers": len(set(addrs)),
            "handler_window": [hmin, hmax],
            "base_range": [lo_bound, hmin],
            "candidate_bases": sorted(set(bases), reverse=True),
        })
    # Drop near-duplicate detections (same SP within 64 bytes).
    found.sort(key=lambda d: (-d["distinct_handlers"], d["file_offset"]))
    deduped, seen = [], []
    for f in found:
        if any(abs(f["file_offset"] - s) < 64 for s in seen):
            continue
        seen.append(f["file_offset"])
        deduped.append(f)
    return sorted(deduped, key=lambda d: d["file_offset"])


# --------------------------------------------------------------------------- #
# Entropy profile
# --------------------------------------------------------------------------- #


def entropy_profile(data: bytes, block: int = 4096):
    blocks = []
    for off in range(0, len(data), block):
        chunk = data[off:off + block]
        blocks.append((off, entropy(chunk), chunk))
    high, pad = [], []
    run_start = None
    for off, ent, chunk in blocks:
        if ent > 7.4:
            if run_start is None:
                run_start = off
        else:
            if run_start is not None:
                high.append((run_start, off))
                run_start = None
    if run_start is not None:
        high.append((run_start, len(data)))
    run_start = None
    for off, ent, chunk in blocks:
        blank = chunk.count(0x00) > len(chunk) * 0.98 or chunk.count(0xFF) > len(chunk) * 0.98
        if blank:
            if run_start is None:
                run_start = off
        else:
            if run_start is not None:
                pad.append((run_start, off))
                run_start = None
    if run_start is not None:
        pad.append((run_start, len(data)))
    return {
        "overall": entropy(data),
        "high_entropy_runs": [r for r in high if r[1] - r[0] >= block * 2],
        "padding_runs": [r for r in pad if r[1] - r[0] >= block * 2],
    }


# --------------------------------------------------------------------------- #
# Strings & markers
# --------------------------------------------------------------------------- #


def extract_strings(data: bytes, minlen: int = 5):
    ascii_re = re.compile(rb"[\x20-\x7e]{%d,}" % minlen)
    out = [(m.start(), m.group().decode("ascii")) for m in ascii_re.finditer(data)]
    utf16_re = re.compile(rb"(?:[\x20-\x7e]\x00){%d,}" % minlen)
    out += [(m.start(), m.group().decode("utf-16-le", "ignore")) for m in utf16_re.finditer(data)]
    out.sort()
    return out


def find_markers(data: bytes):
    hits = []
    for pattern, label in MARKER_STRINGS:
        m = re.search(pattern, data)
        if m:
            hits.append({"marker": label, "file_offset": m.start(),
                         "sample": m.group()[:32].decode("latin-1")})
    return hits


def find_crypto(data: bytes):
    hits = []
    for needle, label in CRYPTO_CONSTANTS:
        i = data.find(needle)
        if i >= 0:
            hits.append({"constant": label, "file_offset": i})
    return hits


def find_versions(strings):
    out = []
    for off, s in strings:
        for m in VERSION_RE.finditer(s.encode("latin-1", "ignore")):
            frag = m.group().decode("latin-1")
            if len(frag) >= 5:
                out.append({"file_offset": off, "string": s[:80], "match": frag})
                break
    return out[:25]


# --------------------------------------------------------------------------- #
# Repeating-XOR obfuscation
# --------------------------------------------------------------------------- #


def _reduce_period(key: bytes) -> bytes:
    """Collapse a key that is itself a repetition of a shorter key."""
    n = len(key)
    for p in range(1, n):
        if n % p == 0 and key == key[:p] * (n // p):
            return key[:p]
    return key


def xor_scan(data: bytes, max_period: int = 256, sample: int = 1 << 22):
    """Recover a repeating-XOR key and VERIFY it, rather than guessing.

    Primary method (exact, not heuristic): find a stretch where the ciphertext is
    itself periodic with period p. Constant plaintext XOR a repeating key is
    periodic, and every firmware image has a padding run of 0x00 or 0xFF. Inside
    such a run the ciphertext *is* the key, so we read it straight off.

    Each candidate is then verified by decoding the image and scanning for a
    Cortex-M vector table — a candidate that produces one is correct, not merely
    plausible. The modal-byte guess is kept only as a last-resort fallback for
    images with no padding at all.
    """
    buf = data[:sample]
    n = len(buf)
    seen: dict[bytes, dict] = {}

    def consider(key: bytes, method: str, detail: str) -> None:
        key = _reduce_period(key)
        if not any(key) or key in seen:
            return
        dec = apply_xor(data[:min(len(data), 1 << 18)], key)
        # Verification demands a *convincing* table: a handful of repeated
        # handlers appears in random data, ten distinct ones does not.
        tables = scan_vector_tables(dec, min_distinct=8)
        printable = sum(1 for b in dec if 0x20 <= b < 0x7F or b in (9, 10, 13)) / len(dec)
        seen[key] = {
            "period": len(key),
            "key": key.hex(),
            "method": method,
            "evidence": detail,
            "verified": bool(tables),
            "vector_tables": len(tables),
            "printable_ratio": round(printable, 3),
            "entropy_after": round(entropy(dec), 3),
        }

    # --- primary: periodic stretch in the ciphertext -----------------------
    if n > 8:
        head = int.from_bytes(buf, "big")
        for period in range(1, min(max_period, n // 4) + 1):
            shifted = int.from_bytes(buf[period:], "big")
            diff = (head >> (period * 8)) ^ shifted
            xr = diff.to_bytes(n - period, "big")
            m = None
            for run in (8 * period, 4 * period, 2 * period):
                m = re.search(rb"\x00{%d,}" % run, xr)
                if m:
                    break
            if not m:
                continue
            pos = m.start()
            if pos + period > n:
                continue
            for const, label in ((0x00, "0x00 padding"), (0xFF, "0xFF padding")):
                # Inside a constant-plaintext run the ciphertext IS the key,
                # rotated to the run's alignment. Undo the rotation.
                key = bytes(buf[pos + ((i - pos) % period)] ^ const for i in range(period))
                consider(key, "periodic-run",
                         f"{m.end() - m.start() + period} byte constant run at 0x{pos:X}, assumed {label}")

    # --- fallback: modal byte per residue class ----------------------------
    if not any(c["verified"] for c in seen.values()):
        for period in range(1, min(64, max_period) + 1):
            key = bytes(Counter(buf[i::period]).most_common(1)[0][0] for i in range(period))
            consider(key, "modal-byte", "assumed the plaintext's most common byte is 0x00")

    out = list(seen.values())
    out.sort(key=lambda r: (not r["verified"], -r["vector_tables"], r["period"],
                            -r["printable_ratio"]))
    return out[:6]


def apply_xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def triage(data: bytes, path: Path, do_xor: bool, xor_period: int = 256):
    import hashlib
    report = {
        "file": str(path),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "containers": [m[2] for m in CONTAINER_MAGIC if data.startswith(m[0])],
        "entropy": entropy_profile(data),
        "vector_tables": scan_vector_tables(data),
        "crypto_constants": find_crypto(data),
        "markers": find_markers(data),
    }
    strings = extract_strings(data)
    report["string_count"] = len(strings)
    report["version_candidates"] = find_versions(strings)
    report["longest_strings"] = [
        {"file_offset": o, "string": s[:100]}
        for o, s in sorted(strings, key=lambda t: -len(t[1]))[:15]
    ]
    if do_xor or (not report["vector_tables"] and report["entropy"]["overall"] > 5.5):
        report["xor_candidates"] = xor_scan(data, max_period=xor_period)
    return report


def print_report(r: dict) -> None:
    p = print
    p("=" * 78)
    p(f"  TRIAGE  {r['file']}")
    p("=" * 78)
    p(f"size        {r['size']} bytes ({r['size']/1024:.1f} KiB)")
    p(f"sha256      {r['sha256']}")
    ent = r['entropy']['overall']
    verdict = ("plain code+data" if ent < 6.5 else
               "code + compressed assets (normal for firmware with fonts/images)" if ent < 7.4
               else "HIGH — packed, compressed or encrypted throughout")
    p(f"entropy     {ent:.3f} bits/byte ({verdict})")
    if r["containers"]:
        p(f"container   {'; '.join(r['containers'])}")

    p("\n-- Vector tables " + "-" * 60)
    if not r["vector_tables"]:
        p("  none found. Either this is not a Cortex-M raw image, or it is obfuscated")
        p("  (see the XOR section), or the table is not in the first bytes you have.")
    for v in r["vector_tables"]:
        p(f"  file offset 0x{v['file_offset']:X}  "
          f"SP={hx(v['initial_sp'])}  reset={hx(v['reset_handler'])}  "
          f"{v['distinct_handlers']} distinct handlers")
        p(f"      handler window {hx(v['handler_window'][0])}–{hx(v['handler_window'][1])}")
        p(f"      feasible image base {hx(v['base_range'][0])}–{hx(v['base_range'][1])}")
        p(f"      candidate bases: {', '.join(hx(b) for b in v['candidate_bases']) or '(none known)'}")
        if v["file_offset"] and len(r["vector_tables"]) == 1:
            p(f"      => a {v['file_offset']} (0x{v['file_offset']:X})-byte vendor/container "
              f"header sits before the image")
    if len(r["vector_tables"]) > 1:
        p("  NOTE: more than one table — this file holds several images (typically")
        p("        bootloader + application, one per flash region). Import EACH as its own")
        p("        Ghidra program with its own base; do not treat the gap as a header.")

    p("\n-- Entropy structure " + "-" * 56)
    for a, b in r["entropy"]["high_entropy_runs"][:8]:
        p(f"  high entropy  0x{a:08X}–0x{b:08X}  ({(b-a)/1024:.0f} KiB) — compressed/encrypted/media?")
    for a, b in r["entropy"]["padding_runs"][:8]:
        p(f"  padding       0x{a:08X}–0x{b:08X}  ({(b-a)/1024:.0f} KiB) — image likely ends at 0x{a:X}")
    if not r["entropy"]["high_entropy_runs"] and not r["entropy"]["padding_runs"]:
        p("  uniform — no obvious packed regions or padding")

    p("\n-- Markers " + "-" * 65)
    for m in r["markers"]:
        p(f"  {m['marker']:<34} @0x{m['file_offset']:08X}  {m['sample']!r}")
    if not r["markers"]:
        p("  none — unusual for an unencrypted image; check the XOR section")
    for c in r["crypto_constants"]:
        p(f"  CRYPTO  {c['constant']:<26} @0x{c['file_offset']:08X}")

    p("\n-- Strings " + "-" * 65)
    p(f"  {r['string_count']} ASCII/UTF-16 strings >= 5 chars")
    for v in r["version_candidates"][:8]:
        p(f"  version?  @0x{v['file_offset']:08X}  {v['string']!r}")

    if r.get("xor_candidates"):
        p("\n-- Repeating-XOR obfuscation " + "-" * 48)
        for c in r["xor_candidates"]:
            flag = "VERIFIED" if c["verified"] else "unverified"
            p(f"  [{flag}] period {c['period']:>3}  key {c['key'][:64]}")
            p(f"      via {c['method']}: {c['evidence']}")
            p(f"      after decode: {c['vector_tables']} vector table(s), "
              f"entropy {c['entropy_after']:.3f}, printable {c['printable_ratio']:.2f}")
        best = r["xor_candidates"][0]
        if best["verified"]:
            p("  => a Cortex-M vector table appears after decoding: this key is CORRECT.")
            p("     Re-run with --write-deobf OUT.bin and import OUT.bin, not the original.")
        else:
            p("  => nothing verified. Either the obfuscation is not a repeating XOR, or the")
            p("     image has no constant-padding run to read the key from. Try a longer")
            p("     --xor-period, or look for a vendor unpacker in the CPS software.")

    p("\n-- Next " + "-" * 68)
    if r["vector_tables"]:
        v = r["vector_tables"][0]
        base = v["candidate_bases"][0] if v["candidate_bases"] else v["base_range"][1]
        p(f"  import with language ARM:LE:32:Cortex, base {hx(base)}"
          + (f", skipping the first 0x{v['file_offset']:X} header bytes" if v["file_offset"] else ""))
        p(f"  VA = file_offset - 0x{v['file_offset']:X} + {hx(base)}")
    else:
        p("  no load address to propose yet — resolve the container/obfuscation first")
    p("=" * 78)


def print_markdown(r: dict) -> None:
    v = r["vector_tables"][0] if r["vector_tables"] else None
    base = (v["candidate_bases"][0] if v and v["candidate_bases"]
            else (v["base_range"][1] if v else 0))
    print("| Field | Value |")
    print("|---|---|")
    print(f"| Firmware file | `{r['file']}` |")
    print(f"| Size | {r['size']} bytes |")
    print(f"| SHA-256 | `{r['sha256']}` |")
    print(f"| Overall entropy | {r['entropy']['overall']:.3f} bits/byte |")
    if v:
        print(f"| Container header | {v['file_offset']} (0x{v['file_offset']:X}) bytes |")
        print(f"| Image base | `{hx(base)}` |")
        print(f"| Initial SP | `{hx(v['initial_sp'])}` |")
        print(f"| Reset vector | `{hx(v['reset_handler'])}` |")
        print(f"| Vector tables found | {len(r['vector_tables'])} |")
    print(f"| Markers | {', '.join(m['marker'] for m in r['markers']) or 'none'} |")
    print(f"| Crypto constants | {', '.join(c['constant'] for c in r['crypto_constants']) or 'none'} |")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("firmware", type=Path)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--markdown", action="store_true", help="a TARGET.md table")
    ap.add_argument("--xor", action="store_true", help="force the repeating-XOR scan")
    ap.add_argument("--xor-period", type=int, default=256, metavar="N",
                    help="largest XOR key length to try (default 256)")
    ap.add_argument("--write-deobf", metavar="PATH", type=Path,
                    help="write the best XOR-decoded image here")
    ap.add_argument("--convert", metavar="PATH", type=Path,
                    help="convert Intel HEX / S-record input to a raw binary here")
    args = ap.parse_args()

    if not args.firmware.exists():
        print(f"no such file: {args.firmware}", file=sys.stderr)
        return 2
    data = args.firmware.read_bytes()

    text = maybe_text_image(data)
    if text:
        kind, blob, lo = text
        print(f"# {kind} text image: {len(blob)} bytes, lowest address {hx(lo)}", file=sys.stderr)
        if args.convert:
            args.convert.write_bytes(blob)
            print(f"# wrote raw image -> {args.convert} (load base {hx(lo)})", file=sys.stderr)
            return 0
        print("# re-run with --convert OUT.bin, then triage the raw binary", file=sys.stderr)
        data = blob

    report = triage(data, args.firmware, args.xor, args.xor_period)

    if args.write_deobf and report.get("xor_candidates"):
        key = bytes.fromhex(report["xor_candidates"][0]["key"])
        args.write_deobf.write_bytes(apply_xor(data, key))
        print(f"# wrote XOR-decoded image -> {args.write_deobf} (key {key.hex()})",
              file=sys.stderr)

    if args.json:
        print(json.dumps(report, indent=2))
    elif args.markdown:
        print_markdown(report)
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
