#!/usr/bin/env python3
"""Emit a small host-only graded-fitness smoke fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.uart_stream_v2 import (  # noqa: E402
    decode_genome,
    encode_genome,
    graded_score_split,
    graded_score_split_total,
    random_genome,
    score_set,
)


HISTORICAL = (
    0x60894268A2,
    0x6A8BA845D4,
    0x09571273CE,
    0x08D590F3EE,
    0x4E85CBC206,
    0x6CBFB15FD8,
)


def split_row(raw: int, split: str, frames: int) -> dict[str, int | str]:
    genome = decode_genome(raw)
    hard = score_set(split, genome, frames)
    hard_passed = sum(score.passed for score in hard.conditions)
    hard_total = sum(score.frames for score in hard.conditions)
    graded = graded_score_split(split, genome, frames)
    graded_total = graded_score_split_total(split, frames)
    return {
        "raw": f"0x{encode_genome(genome):010x}",
        "split": split,
        "frames_per_condition": frames,
        "hard_passed": hard_passed,
        "hard_total": hard_total,
        "graded_score": graded,
        "graded_total": graded_total,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--random-seed", type=lambda value: int(value, 0), default=0x1357)
    parser.add_argument("--random-count", type=int, default=4)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    raws = list(HISTORICAL)
    state = args.random_seed & 0xFFFF
    for _idx in range(args.random_count):
        state, genome = random_genome(state)
        raws.append(encode_genome(genome))

    rows = []
    for raw in raws:
        rows.append(split_row(raw, "train", args.frames))
        rows.append(split_row(raw, "holdout", args.frames))

    report = {
        "protocol": "graded_fitness_v1_smoke",
        "frames_per_condition": args.frames,
        "rows": rows,
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
        print(f"wrote={args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
