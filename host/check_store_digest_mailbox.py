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
COUNT = 8
REPLAY_SCHEMA_1_1_0 = 0x010100


def parse_words(text: str) -> list[int]:
    return [int(match.group(1), 16) for match in HEX_RE.finditer(text)]


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
    args = parser.parse_args()

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
    print(
        "PASS "
        f"schema=0x{payloads[0]:06x} "
        f"blob_words={payloads[5]} "
        f"write_count={payloads[7]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
