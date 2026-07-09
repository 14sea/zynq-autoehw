#!/usr/bin/env python3
"""Validate v2 same-boot A/B long-run heartbeat mailbox telemetry."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.uart_stream_v1 import mailbox_page_checksum  # noqa: E402
from sim.uart_stream_v2 import (  # noqa: E402
    encode_genome,
    mutate_genome,
    random_genome,
    same_boot_ab_search,
    score_set,
)


HEX_RE = re.compile(r"(?:0x)?([0-9a-fA-F]{8})")
BUDGET = 8
FRAMES = 4
SEED = 0xC0DE
HEARTBEAT = 2
TRAIN_TOTAL = 4 * FRAMES


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


def train_passed(genome) -> int:
    return sum(score.passed for score in score_set("train", genome, FRAMES).conditions)


def expected_progress_payloads(arm_id: int) -> list[tuple[int, ...]]:
    payloads: list[tuple[int, ...]] = []
    if arm_id == 1:
        state = (SEED ^ 0x4A4A) & 0xFFFF
        state, best_genome = random_genome(state)
        best_passed = train_passed(best_genome)
        evals = TRAIN_TOTAL
        start_gen = 1
        if HEARTBEAT == 1 or BUDGET == 1:
            payloads.append(progress_payload(arm_id, 1, best_genome, best_passed, evals, BUDGET == 1))
        for gen in range(start_gen, BUDGET):
            state, candidate = mutate_genome(state, best_genome)
            candidate_passed = train_passed(candidate)
            evals += TRAIN_TOTAL
            if candidate_passed >= best_passed:
                best_passed = candidate_passed
                best_genome = candidate
            if ((gen + 1) % HEARTBEAT) == 0 or (gen + 1) == BUDGET:
                payloads.append(progress_payload(arm_id, gen + 1, best_genome, best_passed, evals, (gen + 1) == BUDGET))
    else:
        state = (SEED ^ 0xBEEF) & 0xFFFF
        best_passed = -1
        best_genome = None
        evals = 0
        for gen in range(BUDGET):
            state, genome = random_genome(state)
            candidate_passed = train_passed(genome)
            evals += TRAIN_TOTAL
            if candidate_passed > best_passed:
                best_passed = candidate_passed
                best_genome = genome
            if ((gen + 1) % HEARTBEAT) == 0 or (gen + 1) == BUDGET:
                payloads.append(progress_payload(arm_id, gen + 1, best_genome, best_passed, evals, (gen + 1) == BUDGET))
    return payloads


def progress_payload(arm_id: int, generation: int, genome, best_passed: int, evals: int, done: bool) -> tuple[int, ...]:
    raw = encode_genome(genome)
    status = 0xF1 if done else 0x01
    return (
        (0x06 << 16) | (arm_id << 8) | status,
        generation & 0x3FFFFF,
        (generation >> 22) & 0x3FFFFF,
        raw & 0x3FFFFF,
        (raw >> 22) & 0x3FFFFF,
        pack_score(best_passed, TRAIN_TOTAL),
        evals & 0x3FFFFF,
        (evals >> 22) & 0x3FFFFF,
    )


def expected_arm_payload(arm_id: int, result) -> tuple[int, ...]:
    raw = encode_genome(result.best_genome)
    train = score_set("train", result.best_genome, FRAMES)
    holdout = score_set("holdout", result.best_genome, FRAMES)
    train_passed_sum = sum(score.passed for score in train.conditions)
    train_total_sum = sum(score.frames for score in train.conditions)
    holdout_passed = sum(score.passed for score in holdout.conditions)
    holdout_total = sum(score.frames for score in holdout.conditions)
    evals = BUDGET * train_total_sum
    return (
        (0x04 << 16) | arm_id,
        raw & 0x3FFFFF,
        (raw >> 22) & 0x3FFFFF,
        pack_score(train_passed_sum, train_total_sum),
        pack_score(holdout_passed, holdout_total),
        evals & 0x3FFFFF,
        (evals >> 22) & 0x3FFFFF,
    )


def main() -> int:
    words = parse_words(sys.stdin.read())
    expected_len = 3 + 4 * 10 + 4 * 10 + 2 * 9
    if len(words) != expected_len:
        return fail(f"need exactly {expected_len} words, got {len(words)}")
    if words[:3] != [0xA7000000, 0xA8000804, 0xAD00C0DE]:
        return fail("v2 A/B long-run smoke prefix mismatch")

    offset = 3
    for payload in expected_progress_payloads(1):
        observed = decode_page(words, offset, 6, 8)
        if observed != payload:
            return fail(f"GA progress page mismatch at offset {offset}")
        offset += 10
    for payload in expected_progress_payloads(2):
        observed = decode_page(words, offset, 7, 8)
        if observed != payload:
            return fail(f"random progress page mismatch at offset {offset}")
        offset += 10

    result = same_boot_ab_search(BUDGET, SEED, FRAMES)
    ga_payloads = decode_page(words, offset, 4, 7)
    if ga_payloads != expected_arm_payload(1, result.ga):
        return fail("GA final page mismatch")
    offset += 9
    random_payloads = decode_page(words, offset, 5, 7)
    if random_payloads != expected_arm_payload(2, result.random):
        return fail("random final page mismatch")

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
