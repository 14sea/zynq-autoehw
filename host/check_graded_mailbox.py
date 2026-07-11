#!/usr/bin/env python3
"""Validate the graded-score board smoke mailbox page."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.uart_stream_v1 import frame_passes, mailbox_page_checksum  # noqa: E402
from sim.uart_stream_v2 import CONDITIONS, decode_genome, effective_config, frame_bit_matches  # noqa: E402


HEX_RE = re.compile(r"(?:0x)?([0-9a-fA-F]{8})")
PAGE_ID = 9
PAYLOAD_COUNT = 10
VECTORS = (
    (0, 0x60894268A2, 0),
    (1, 0x6A8BA845D4, 3),
    (2, 0x09571273CE, 5),
    (3, 0x08D590F3EE, 7),
    (4, 0x4E85CBC206, 1),
    (5, 0x6CBFB15FD8, 7),
    (6, 0x60894268A2, 2),
    (7, 0x6A8BA845D4, 4),
)


def parse_words(text: str) -> list[int]:
    return [int(match.group(1), 16) for match in HEX_RE.finditer(text)]


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def decode_page(words: list[int], page_id: int, count: int) -> tuple[int, ...] | None:
    header = 0xC0000000 | ((page_id & 0xFF) << 16) | count
    for offset, word in enumerate(words):
        if word != header:
            continue
        page = words[offset:offset + count + 2]
        if len(page) != count + 2:
            continue
        if any((item & 0xFF000000) != 0xC1000000 for item in page[1:1 + count]):
            continue
        seqs = tuple((item >> 22) & 0x03 for item in page[1:1 + count])
        if seqs != tuple(idx & 0x03 for idx in range(count)):
            continue
        payloads = tuple(item & 0x003FFFFF for item in page[1:1 + count])
        checksum = mailbox_page_checksum(page_id, payloads)
        if page[-1] != (0xC2000000 | checksum):
            continue
        return payloads
    return None


def expected_payloads() -> tuple[int, ...]:
    payloads: list[int] = [(0x09 << 16) | len(VECTORS)]
    graded_sum = 0
    for idx, raw, frame_idx in VECTORS:
        condition = CONDITIONS[idx]
        genome = decode_genome(raw)
        config = effective_config(condition, genome)
        hard = 1 if frame_passes(condition, config, frame_idx) else 0
        graded = frame_bit_matches(condition, genome, frame_idx)
        graded_sum += graded
        payloads.append(((idx & 0x0F) << 18) | ((hard & 1) << 17) | (graded & 0x03FF))
    payloads.append(graded_sum & 0x003FFFFF)
    return tuple(payloads)


def main() -> int:
    words = parse_words(sys.stdin.read())
    if not words:
        return fail("no mailbox words found")
    payloads = decode_page(words, PAGE_ID, PAYLOAD_COUNT)
    if payloads is None:
        return fail("graded page framing/sequence/checksum mismatch")
    expected = expected_payloads()
    if payloads != expected:
        return fail(f"graded payload mismatch: got {payloads}, expected {expected}")
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
