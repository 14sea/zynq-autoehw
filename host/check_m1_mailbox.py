#!/usr/bin/env python3
"""Validate an M1 mailbox carousel with the paged extension."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.uart_stream_v1 import mailbox_page_checksum


HEX_RE = re.compile(r"(?:0x)?([0-9a-fA-F]{8})")


def parse_words(text: str) -> list[int]:
    return [int(match.group(1), 16) for match in HEX_RE.finditer(text)]


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def main() -> int:
    words = parse_words(sys.stdin.read())
    if len(words) < 23:
        return fail(f"need at least 23 words, got {len(words)}")

    expected_prefix = [
        0xA7000000,
        0xA8001008,
        0xA90F05B7,
        0xAA013020,
        0xAB011020,
        0xAC000200,
        0xAD00C0DE,
    ]
    if words[:7] != expected_prefix:
        return fail("legacy prefix words 0..6 mismatch")
    if (words[7] & 0xFF000000) != 0xAE000000 or (words[7] & 0x00FFFFFF) == 0:
        return fail("AE evals/sec word missing or zero")
    if words[8:11] != [0xAF011020, 0xB00013E8, 0xB10F05B7]:
        return fail("random/write/persist words mismatch")
    if words[11:13] not in ([0xB2000001, 0xB3000000], [0xB2010101, 0xB30F05B7]):
        return fail("restore status/config words mismatch")
    if words[13:15] != [0xB4010101, 0xB5010101]:
        return fail("reject/recovery words mismatch")

    page = words[15:23]
    if page[0] != 0xC0010006:
        return fail("summary page header mismatch")
    if any((word & 0xFF000000) != 0xC1000000 for word in page[1:7]):
        return fail("summary page data tag mismatch")
    payloads = tuple(word & 0x00FFFFFF for word in page[1:7])
    if payloads[0] != 0x01000F:
        return fail("summary page version/legacy-count mismatch")
    if payloads[1] != (words[7] & 0x00FFFFFF):
        return fail("summary page evals/sec payload does not mirror AE")
    if payloads[2] != 0x011020:
        return fail("summary page random-baseline payload mismatch")
    if payloads[3] != (words[11] & 0x00FFFFFF):
        return fail("summary page restore payload does not mirror B2")
    if payloads[4:] != (0x010101, 0x010101):
        return fail("summary page event payloads mismatch")
    checksum = mailbox_page_checksum(1, payloads)
    if page[7] != (0xC2000000 | checksum):
        return fail("summary page checksum mismatch")

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
