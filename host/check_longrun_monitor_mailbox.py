#!/usr/bin/env python3
"""Validate the host-gated long-run monitor mailbox smoke."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.uart_stream_v1 import (  # noqa: E402
    mailbox_page_checksum,
    pack_config_payload,
    random_config,
    score_set,
)


HEX_RE = re.compile(r"(?:0x)?([0-9a-fA-F]{8})")
BUDGET = 8
FRAMES = 8
SEED = 0xC0DE
HEARTBEAT = 2
TRAIN_EVALS_PER_CANDIDATE = 4 * FRAMES


def parse_words(text: str) -> list[int]:
    return [int(match.group(1), 16) for match in HEX_RE.finditer(text)]


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def pack_score(passed: int, total: int) -> int:
    return ((passed & 0x0FFF) << 12) | (total & 0x0FFF)


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


def train_counts(config) -> tuple[int, int]:
    train = score_set("train", config, FRAMES)
    return (
        sum(score.passed for score in train.conditions),
        sum(score.frames for score in train.conditions),
    )


def holdout_counts(config) -> tuple[int, int]:
    holdout = score_set("holdout", config, FRAMES)
    return (
        sum(score.passed for score in holdout.conditions),
        sum(score.frames for score in holdout.conditions),
    )


def expected_progress_payloads() -> list[tuple[int, ...]]:
    state = SEED
    best_config = None
    best_passed = -1
    train_total = 0
    payloads: list[tuple[int, ...]] = []

    for generation in range(1, BUDGET + 1):
        state, config = random_config(state)
        passed, total = train_counts(config)
        if passed > best_passed:
            best_passed = passed
            train_total = total
            best_config = config
        if generation % HEARTBEAT == 0 or generation == BUDGET:
            evals = generation * TRAIN_EVALS_PER_CANDIDATE
            payloads.append((
                (0x03 << 16) | (0x00F1 if generation == BUDGET else 0x0001),
                generation & 0x3FFFFF,
                (generation >> 22) & 0x3FFFFF,
                evals & 0x3FFFFF,
                (evals >> 22) & 0x3FFFFF,
                pack_score(best_passed, train_total),
                pack_config_payload(best_config),
            ))

    return payloads


def main() -> int:
    words = parse_words(sys.stdin.read())
    expected_len = 2 + (4 * 9) + 4
    if len(words) != expected_len:
        return fail(f"need exactly {expected_len} words, got {len(words)}")
    if words[:2] != [0xA7000000, 0xA8000808]:
        return fail("monitor smoke prefix mismatch")

    expected_payloads = expected_progress_payloads()
    for idx, expected in enumerate(expected_payloads):
        offset = 2 + (idx * 9)
        observed = decode_page(words, offset, 3, 7)
        if observed is None:
            return fail(f"monitor page {idx} framing/sequence/checksum mismatch")
        if observed != expected:
            return fail(f"monitor page {idx} payload mismatch")

    final_offset = 2 + (len(expected_payloads) * 9)
    final_config_payload = expected_payloads[-1][6]
    final_train_payload = expected_payloads[-1][5]
    # Recompute the final config object from the last progress payload by
    # replaying the deterministic budget; avoids accepting a forged tail word.
    state = SEED
    best_config = None
    best_passed = -1
    for _ in range(BUDGET):
        state, config = random_config(state)
        passed, _total = train_counts(config)
        if passed > best_passed:
            best_passed = passed
            best_config = config
    holdout_passed, holdout_total = holdout_counts(best_config)
    expected_tail = [
        0xA9000000 | final_config_payload,
        0xAA000000 | final_train_payload,
        0xAB000000 | pack_score(holdout_passed, holdout_total),
        0xAC000000 | (BUDGET * TRAIN_EVALS_PER_CANDIDATE),
    ]
    if words[final_offset:] != expected_tail:
        return fail("monitor smoke final result tail mismatch")

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
