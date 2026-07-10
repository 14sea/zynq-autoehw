#!/usr/bin/env python3
"""Run the preregistered v3 search variants against random on host."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import statistics
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLI = ROOT / "build" / "host" / "uart_stream_v2_cli"
SET_A = (
    0x1357, 0x2468, 0x369C, 0x47AD,
    0x58BE, 0x69CF, 0x7AD0, 0x8BE1,
    0x9CF2, 0xAD03, 0xBE14, 0xCF25,
    0xD036, 0xE147, 0xF258, 0x0ACE,
)
VARIANTS = (
    "current_hillclimb",
    "restart_hillclimb_v3",
    "immigrant_hillclimb_v3",
    "beam4_ga_v3",
)
TRAIN_FRAMES = 64
HOLDOUT_FRAMES = 256
BOARD_V2_EPS = 1592
TARGET_SECONDS = 7200
ARM_COUNT = 2
TRAIN_EVALS_PER_CANDIDATE = 4 * TRAIN_FRAMES
DEFAULT_BUDGET = (BOARD_V2_EPS * TARGET_SECONDS) // (ARM_COUNT * TRAIN_EVALS_PER_CANDIDATE)


def parse_seed_list(value: str) -> tuple[int, ...]:
    if value == "setA":
        return SET_A
    return tuple(int(item, 0) for item in value.replace(",", " ").split())


def run_arm(cli: Path, variant: str, budget: int, seed: int, train_frames: int, holdout_frames: int) -> dict[str, int]:
    proc = subprocess.run(
        [
            str(cli),
            "variant",
            variant,
            str(budget),
            hex(seed),
            str(train_frames),
            str(holdout_frames),
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    fields = proc.stdout.strip().split()
    return {
        "raw": int(fields[2], 16),
        "train_passed": int(fields[12]),
        "train_total": int(fields[13]),
        "holdout_passed": int(fields[15]),
        "holdout_total": int(fields[16]),
        "evals": int(fields[18]),
    }


def run_comparison(
    cli: Path,
    variant: str,
    budget: int,
    seed: int,
    train_frames: int,
    holdout_frames: int,
) -> dict[str, object]:
    variant_result = run_arm(
        cli,
        variant,
        budget,
        seed ^ 0x4A4A,
        train_frames,
        holdout_frames,
    )
    random_result = run_arm(
        cli,
        "random",
        budget,
        seed ^ 0xBEEF,
        train_frames,
        holdout_frames,
    )
    return {
        "seed": f"0x{seed:04X}",
        "variant_holdout": variant_result["holdout_passed"],
        "random_holdout": random_result["holdout_passed"],
        "holdout_delta": int(variant_result["holdout_passed"]) - int(random_result["holdout_passed"]),
        "variant_train": variant_result["train_passed"],
        "random_train": random_result["train_passed"],
        "variant_raw": f"0x{variant_result['raw']:010x}",
        "random_raw": f"0x{random_result['raw']:010x}",
    }


def percentile_10(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[int(0.10 * (len(ordered) - 1))]


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    deltas = [int(row["holdout_delta"]) for row in rows]
    wins = sum(1 for delta in deltas if delta > 0)
    losses = sum(1 for delta in deltas if delta < 0)
    ties = sum(1 for delta in deltas if delta == 0)
    mean_delta = statistics.fmean(deltas) if deltas else 0.0
    median_delta = statistics.median(deltas) if deltas else 0.0
    p10 = percentile_10(deltas)
    board_eligible = (
        wins >= 10 and
        losses <= 4 and
        mean_delta >= 8.0 and
        median_delta >= 4.0 and
        p10 >= -16
    )
    return {
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "mean_holdout_delta": mean_delta,
        "median_holdout_delta": median_delta,
        "p10_holdout_delta": p10,
        "board_eligible": board_eligible,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, default=DEFAULT_CLI)
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    parser.add_argument("--train-frames", type=int, default=TRAIN_FRAMES)
    parser.add_argument("--holdout-frames", type=int, default=HOLDOUT_FRAMES)
    parser.add_argument("--seeds", default="setA")
    parser.add_argument("--variants", default=",".join(VARIANTS))
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()

    seeds = parse_seed_list(args.seeds)
    variants = tuple(item for item in args.variants.replace(",", " ").split() if item)
    report: dict[str, object] = {
        "budget": args.budget,
        "train_frames": args.train_frames,
        "holdout_frames": args.holdout_frames,
        "seeds": [f"0x{seed:04X}" for seed in seeds],
        "variants": {},
    }

    any_pass = False
    for variant in variants:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
            rows = list(executor.map(
                lambda seed: run_comparison(
                    args.cli,
                    variant,
                    args.budget,
                    seed,
                    args.train_frames,
                    args.holdout_frames,
                ),
                seeds,
            ))
        summary = summarize(rows)
        any_pass = any_pass or bool(summary["board_eligible"])
        report["variants"][variant] = {
            "summary": summary,
            "rows": rows,
        }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"budget={args.budget} train_frames={args.train_frames} holdout_frames={args.holdout_frames}")
        for variant, data in report["variants"].items():
            summary = data["summary"]
            print(
                f"{variant}: wins={summary['wins']} losses={summary['losses']} ties={summary['ties']} "
                f"mean_delta={summary['mean_holdout_delta']:.2f} median_delta={summary['median_holdout_delta']:.2f} "
                f"p10={summary['p10_holdout_delta']} board_eligible={summary['board_eligible']}"
            )

    if args.require_pass and not any_pass:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
