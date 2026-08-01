#!/usr/bin/env python3
"""Validate M1 engineering addendum page-15 store digest telemetry."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.uart_stream_v1 import mailbox_page_checksum  # noqa: E402


HEX_RE = re.compile(r"(?:0x)?([0-9a-fA-F]{8})")
PAGE_ID = 15
COUNT = 11
REPLAY_SCHEMA_1_1_0 = 0x010100
STORE_MAGIC = 0x43484D50
STORE_V2 = 0x00020000
RECORD_WORDS = 16
GENOME_BITS = 39
FNV_OFFSET = 0x811C9DC5
FNV_PRIME = 0x01000193


def parse_words(text: str) -> list[int]:
    words: list[int] = []
    for line in text.splitlines():
        data = line.split(":", 1)[1] if ":" in line else line
        words.extend(int(match.group(1), 16) for match in HEX_RE.finditer(data))
    return words


def checksum_words(words: list[int]) -> int:
    acc = FNV_OFFSET
    for word in words:
        for byte in range(4):
            acc ^= (word >> (byte * 8)) & 0xFF
            acc = (acc * FNV_PRIME) & 0xFFFFFFFF
    return acc


def expected_raw_from_store(path: Path) -> int:
    words = parse_words(path.read_text())
    if len(words) < RECORD_WORDS:
        raise ValueError(f"need at least {RECORD_WORDS} store words, got {len(words)}")
    record = words[:RECORD_WORDS]
    if record[0] != STORE_MAGIC or record[1] != STORE_V2:
        raise ValueError("store record magic/version mismatch")
    if record[15] != checksum_words(record[:15]):
        raise ValueError("store record checksum mismatch")
    raw = record[6] | (record[7] << 32)
    if raw >> GENOME_BITS:
        raise ValueError(f"store record raw genome exceeds {GENOME_BITS} bits")
    return raw


def decode_page(words: list[int]) -> tuple[int, ...] | None:
    header = 0xC0000000 | (PAGE_ID << 16) | COUNT
    for offset, word in enumerate(words):
        if word != header:
            continue
        page = words[offset:offset + COUNT + 2]
        if len(page) != COUNT + 2:
            continue
        if any((item & 0xFF000000) != 0xC1000000 for item in page[1:1 + COUNT]):
            continue
        seqs = tuple((item >> 22) & 0x03 for item in page[1:1 + COUNT])
        if seqs != tuple(idx & 0x03 for idx in range(COUNT)):
            continue
        payloads = tuple(item & 0x003FFFFF for item in page[1:1 + COUNT])
        if page[-1] != (0xC2000000 | mailbox_page_checksum(PAGE_ID, payloads)):
            continue
        return payloads
    return None


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect-write-count", type=int, default=1)
    parser.add_argument("--require-restore", action="store_true")
    parser.add_argument("--expect-raw-from-store", type=Path)
    args = parser.parse_args()

    try:
        expected_raw = expected_raw_from_store(args.expect_raw_from_store) if args.expect_raw_from_store else None
    except ValueError as exc:
        return fail(str(exc))

    payloads = decode_page(parse_words(sys.stdin.read()))
    if payloads is None:
        return fail("page 15 missing or checksum mismatch")
    if payloads[0] != REPLAY_SCHEMA_1_1_0:
        return fail(f"schema payload mismatch: 0x{payloads[0]:06x}")
    if payloads[5] == 0:
        return fail("blob length is zero")
    if payloads[6] == 0:
        return fail("blob crc is zero")
    if payloads[7] != args.expect_write_count:
        return fail(f"write_count mismatch: {payloads[7]} != {args.expect_write_count}")
    restored = (payloads[8] & 0x000001) != 0
    restored_matches = (payloads[8] & 0x000100) != 0
    restored_raw = payloads[9] | (payloads[10] << 22)
    if expected_raw is not None and restored and restored_raw != expected_raw:
        return fail(f"restored raw mismatch: 0x{restored_raw:010x} != 0x{expected_raw:010x}")
    if args.require_restore and not (restored and restored_matches and restored_raw != 0):
        return fail(
            "restore status mismatch: "
            f"status=0x{payloads[8]:06x} raw=0x{restored_raw:010x}"
        )
    if args.require_restore and expected_raw is not None and restored_raw != expected_raw:
        return fail(f"restored raw mismatch: 0x{restored_raw:010x} != 0x{expected_raw:010x}")
    print(
        "PASS "
        f"schema=0x{payloads[0]:06x} "
        f"blob_words={payloads[5]} "
        f"write_count={payloads[7]} "
        f"restore={'yes' if restored else 'no'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
