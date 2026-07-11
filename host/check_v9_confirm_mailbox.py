#!/usr/bin/env python3
"""Validate v9 Set-B confirmatory mailbox telemetry."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.uart_stream_v1 import mailbox_page_checksum  # noqa: E402


HEX_RE = re.compile(r"(?:0x)?([0-9a-fA-F]{8})")
SEED = 0xB17D
TRAIN_FRAMES = 64
HOLDOUT_FRAMES = 256
VARIANT = "pbil_island8_graded_v9"
PAGE_CAL = 10
PAGE_VARIANT = 11
PAGE_RANDOM = 12


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
        if page[-1] != (0xC2000000 | mailbox_page_checksum(page_id, payloads)):
            continue
        return payloads
    return None


def run_arm(cli: Path, variant: str, budget: int, seed: int) -> dict[str, int]:
    proc = subprocess.run(
        [
            str(cli),
            "variant-graded",
            variant,
            str(budget),
            hex(seed),
            str(TRAIN_FRAMES),
            str(HOLDOUT_FRAMES),
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    lines = proc.stdout.strip().splitlines()
    fields = lines[0].split()
    graded = lines[1].split()
    return {
        "raw": int(fields[2], 16),
        "train_score": int(fields[12]),
        "train_total": int(fields[13]),
        "hard_holdout": int(fields[15]),
        "hard_holdout_total": int(fields[16]),
        "evals": int(fields[18]),
        "graded_holdout": int(graded[1]),
        "graded_holdout_total": int(graded[2]),
    }


def pack_hard_holdout(passed: int, total: int) -> int:
    return ((passed & 0x0FFF) << 12) | (total & 0x0FFF)


def expected_arm_payload(arm_id: int, result: dict[str, int], evals_override: int | None = None) -> tuple[int, ...]:
    raw = result["raw"]
    evals = result["evals"] if evals_override is None else evals_override
    return (
        (0x0B << 16) | arm_id,
        raw & 0x3FFFFF,
        (raw >> 22) & 0x3FFFFF,
        result["train_score"] & 0x3FFFFF,
        (result["train_score"] >> 22) & 0x3FFFFF,
        result["train_total"] & 0x3FFFFF,
        (result["train_total"] >> 22) & 0x3FFFFF,
        pack_hard_holdout(result["hard_holdout"], result["hard_holdout_total"]),
        result["graded_holdout"] & 0x3FFFFF,
        (result["graded_holdout"] >> 22) & 0x3FFFFF,
        evals & 0x3FFFFF,
        (evals >> 22) & 0x3FFFFF,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, default=ROOT / "build" / "host" / "uart_stream_v2_cli")
    args = parser.parse_args()

    words = parse_words(sys.stdin.read())
    if words[:2] != [0xA7000000, 0xAD000000 | SEED]:
        return fail("v9 confirm prefix mismatch")

    calibration = decode_page(words, PAGE_CAL, 8)
    if calibration is None:
        return fail("calibration page mismatch")
    budget = calibration[3] | (calibration[4] << 22)
    if budget <= 0:
        return fail("invalid derived budget")

    variant_expected = expected_arm_payload(8, run_arm(args.cli, VARIANT, budget, SEED ^ 0x4A4A), budget * 4 * TRAIN_FRAMES)
    random_expected = expected_arm_payload(2, run_arm(args.cli, "random", budget, SEED ^ 0xBEEF))
    variant_payload = decode_page(words, PAGE_VARIANT, 12)
    random_payload = decode_page(words, PAGE_RANDOM, 12)
    if variant_payload != variant_expected:
        return fail("variant final page mismatch")
    if random_payload != random_expected:
        return fail("random final page mismatch")

    delta = variant_expected[7] >> 12
    delta -= random_expected[7] >> 12
    if delta < 8:
        return fail(f"hard holdout delta below confirmatory threshold: {delta}")

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
