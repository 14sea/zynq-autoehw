#!/usr/bin/env python3
"""Validate long-run live page-3 telemetry captured from mailbox polling."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.uart_stream_v1 import mailbox_page_checksum  # noqa: E402


HEX_RE = re.compile(r"(?:0x)?([0-9a-fA-F]{8})")
PAGE_HEADER_TAG = 0xC0000000
PAGE_DATA_TAG = 0xC1000000
PAGE_END_TAG = 0xC2000000
MONITOR_PAGE_ID = 3
MONITOR_PAYLOADS = 7
TRAIN_EVALS_PER_CANDIDATE = 32


def parse_words(text: str) -> list[int]:
    return [int(match.group(1), 16) for match in HEX_RE.finditer(text)]


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def decode_page_at(words: list[int], offset: int) -> tuple[int, tuple[int, ...]] | None:
    header = words[offset]
    if (header & 0xFF000000) != PAGE_HEADER_TAG:
        return None
    page_id = (header >> 16) & 0xFF
    count = header & 0xFF
    page = words[offset:offset + count + 2]
    if len(page) != count + 2:
        return None
    if any((word & 0xFF000000) != PAGE_DATA_TAG for word in page[1:1 + count]):
        return None
    payloads = tuple(word & 0x003FFFFF for word in page[1:1 + count])
    seqs = tuple((word >> 22) & 0x03 for word in page[1:1 + count])
    if seqs != tuple(idx & 0x03 for idx in range(count)):
        return None
    if page[-1] != (PAGE_END_TAG | mailbox_page_checksum(page_id, payloads)):
        return None
    return page_id, payloads


def decode_u44(lo: int, hi: int) -> int:
    return (hi << 22) | lo


def config_payload_is_valid(payload: int) -> bool:
    phase = (payload >> 16) & 0x1F
    majority = (payload >> 8) & 0x07
    threshold = payload & 0xFF
    return phase <= 31 and majority in (1, 3, 5) and threshold <= 255


def validate_monitor_pages(words: list[int], require_final: bool) -> tuple[int, int, int] | None:
    previous_generation = -1
    previous_evals = -1
    final_seen = False
    pages_seen = 0
    final_generation = 0

    for offset, word in enumerate(words):
        if (word & 0xFF000000) != PAGE_HEADER_TAG:
            continue
        decoded = decode_page_at(words, offset)
        if decoded is None:
            continue
        page_id, payloads = decoded
        if page_id != MONITOR_PAGE_ID:
            continue
        if len(payloads) != MONITOR_PAYLOADS:
            print(f"FAIL: monitor page at word {offset} has {len(payloads)} payloads", file=sys.stderr)
            return None

        status = payloads[0]
        generation = decode_u44(payloads[1], payloads[2])
        evals = decode_u44(payloads[3], payloads[4])
        score = payloads[5]
        passed = (score >> 12) & 0x0FFF
        total = score & 0x0FFF
        config_payload = payloads[6]

        if status not in (0x030001, 0x0300F1):
            print(f"FAIL: monitor page at word {offset} has bad status 0x{status:06x}", file=sys.stderr)
            return None
        if generation <= previous_generation or evals <= previous_evals:
            print(f"FAIL: monitor page at word {offset} is not monotonic", file=sys.stderr)
            return None
        if evals != generation * TRAIN_EVALS_PER_CANDIDATE:
            print(f"FAIL: monitor page at word {offset} evals/generation mismatch", file=sys.stderr)
            return None
        if total != TRAIN_EVALS_PER_CANDIDATE or passed > total:
            print(f"FAIL: monitor page at word {offset} has bad train score", file=sys.stderr)
            return None
        if not config_payload_is_valid(config_payload):
            print(f"FAIL: monitor page at word {offset} has invalid config payload", file=sys.stderr)
            return None

        final_seen = final_seen or status == 0x0300F1
        final_generation = generation
        previous_generation = generation
        previous_evals = evals
        pages_seen += 1

    if pages_seen == 0:
        print("FAIL: no monitor page-3 telemetry found", file=sys.stderr)
        return None
    if require_final and not final_seen:
        print("FAIL: final monitor page not found", file=sys.stderr)
        return None
    return pages_seen, final_generation, previous_evals


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-final", action="store_true")
    args = parser.parse_args()

    words = parse_words(sys.stdin.read())
    result = validate_monitor_pages(words, args.require_final)
    if result is None:
        return 1
    pages_seen, final_generation, final_evals = result
    print(f"PASS pages={pages_seen} generation={final_generation} evals={final_evals}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
