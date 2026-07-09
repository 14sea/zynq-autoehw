#!/usr/bin/env python3
"""Validate the v2 GA/random A/B mailbox scaffold."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.uart_stream_v1 import mailbox_page_checksum  # noqa: E402
from sim.uart_stream_v2 import encode_genome, same_boot_ab_search, score_set  # noqa: E402


HEX_RE = re.compile(r"(?:0x)?([0-9a-fA-F]{8})")
BUDGET = 16
FRAMES = 4
SEED = 0xC0DE


def parse_words(text: str) -> list[int]:
    return [int(match.group(1), 16) for match in HEX_RE.finditer(text)]


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def decode_page(words: list[int], offset: int, page_id: int, count: int) -> tuple[int, ...] | None:
    page = words[offset:offset + count + 2]
    if len(page) != count + 2:
        return None
    if page[0] != (0xC0000000 | ((page_id & 0xFF) << 16) | count):
        return None
    if any((word & 0xFF000000) != 0xC1000000 for word in page[1:1 + count]):
        return None
    seqs = tuple((word >> 22) & 0x03 for word in page[1:1 + count])
    if seqs != tuple(idx & 0x03 for idx in range(count)):
        return None
    payloads = tuple(word & 0x003FFFFF for word in page[1:1 + count])
    checksum = mailbox_page_checksum(page_id, payloads)
    if page[-1] != (0xC2000000 | checksum):
        return None
    return payloads


def pack_score(passed: int, total: int) -> int:
    return ((passed & 0x0FFF) << 12) | (total & 0x0FFF)


def expected_arm_payload(arm_id: int, result) -> tuple[int, ...]:
    raw = encode_genome(result.best_genome)
    train = score_set("train", result.best_genome, FRAMES)
    holdout = score_set("holdout", result.best_genome, FRAMES)
    train_passed = sum(score.passed for score in train.conditions)
    train_total = sum(score.frames for score in train.conditions)
    holdout_passed = sum(score.passed for score in holdout.conditions)
    holdout_total = sum(score.frames for score in holdout.conditions)
    evals = BUDGET * train_total
    return (
        (0x04 << 16) | arm_id,
        raw & 0x3FFFFF,
        (raw >> 22) & 0x3FFFFF,
        pack_score(train_passed, train_total),
        pack_score(holdout_passed, holdout_total),
        evals & 0x3FFFFF,
        (evals >> 22) & 0x3FFFFF,
    )


def main() -> int:
    words = parse_words(sys.stdin.read())
    if len(words) != 21:
        return fail(f"need exactly 21 words, got {len(words)}")
    if words[:3] != [0xA7000000, 0xA8001004, 0xAD00C0DE]:
        return fail("v2 A/B prefix mismatch")

    result = same_boot_ab_search(BUDGET, SEED, FRAMES)
    ga_payloads = decode_page(words, 3, 4, 7)
    random_payloads = decode_page(words, 12, 5, 7)
    if ga_payloads is None:
        return fail("GA page framing/sequence/checksum mismatch")
    if random_payloads is None:
        return fail("random page framing/sequence/checksum mismatch")
    if ga_payloads != expected_arm_payload(1, result.ga):
        return fail("GA payload mismatch")
    if random_payloads != expected_arm_payload(2, result.random):
        return fail("random payload mismatch")

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
