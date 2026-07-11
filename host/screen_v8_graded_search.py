#!/usr/bin/env python3
"""Run preregistered v8 graded-fitness search variants on host."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from host.screen_v3_search import (  # noqa: E402
    DEFAULT_BUDGET,
    DEFAULT_CLI,
    HOLDOUT_FRAMES,
    TRAIN_FRAMES,
    parse_seed_list,
)


VARIANTS = (
    "pbil_graded_v8",
    "pbil_island4_graded_v8",
    "pbil_island4_deep_graded_v8",
    "pbil_island4_v6",
)
DEEP_VARIANTS = frozenset(("pbil_island4_deep_graded_v8",))
DEEP_BUDGET = 22371


def percentile_10(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[int(0.10 * (len(ordered) - 1))]


def summarize_delta(rows: list[dict[str, object]], delta_key: str, *, board_gate: bool) -> dict[str, object]:
    deltas = [int(row[delta_key]) for row in rows]
    wins = sum(1 for delta in deltas if delta > 0)
    losses = sum(1 for delta in deltas if delta < 0)
    ties = sum(1 for delta in deltas if delta == 0)
    mean_delta = statistics.fmean(deltas) if deltas else 0.0
    median_delta = statistics.median(deltas) if deltas else 0.0
    p10 = percentile_10(deltas)
    board_eligible = (
        board_gate and
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
        "mean_delta": mean_delta,
        "median_delta": median_delta,
        "p10_delta": p10,
        "board_eligible": board_eligible,
    }


def budget_for_variant(variant: str, search_budget: int, deep_budget: int) -> int:
    return deep_budget if variant in DEEP_VARIANTS else search_budget


def run_arm(cli: Path, variant: str, budget: int, seed: int, train_frames: int, holdout_frames: int) -> dict[str, int]:
    proc = subprocess.run(
        [
            str(cli),
            "variant-graded",
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
    lines = proc.stdout.strip().splitlines()
    if len(lines) != 2:
        raise RuntimeError(f"unexpected variant-graded output: {proc.stdout!r}")
    fields = lines[0].split()
    graded_fields = lines[1].split()
    if graded_fields[:1] != ["graded_holdout"]:
        raise RuntimeError(f"unexpected graded holdout row: {lines[1]!r}")
    return {
        "raw": int(fields[2], 16),
        "train_score": int(fields[12]),
        "train_total": int(fields[13]),
        "hard_holdout": int(fields[15]),
        "hard_holdout_total": int(fields[16]),
        "evals": int(fields[18]),
        "graded_holdout": int(graded_fields[1]),
        "graded_holdout_total": int(graded_fields[2]),
    }


def run_comparison(
    cli: Path,
    variant: str,
    search_budget: int,
    deep_budget: int,
    seed: int,
    train_frames: int,
    holdout_frames: int,
) -> dict[str, object]:
    variant_budget = budget_for_variant(variant, search_budget, deep_budget)
    variant_result = run_arm(
        cli,
        variant,
        variant_budget,
        seed ^ 0x4A4A,
        train_frames,
        holdout_frames,
    )
    random_result = run_arm(
        cli,
        "random",
        search_budget,
        seed ^ 0xBEEF,
        train_frames,
        holdout_frames,
    )
    return {
        "seed": f"0x{seed:04X}",
        "variant_budget": variant_budget,
        "random_budget": search_budget,
        "variant_hard_holdout": variant_result["hard_holdout"],
        "random_hard_holdout": random_result["hard_holdout"],
        "hard_holdout_delta": int(variant_result["hard_holdout"]) - int(random_result["hard_holdout"]),
        "variant_graded_holdout": variant_result["graded_holdout"],
        "random_graded_holdout": random_result["graded_holdout"],
        "graded_holdout_delta": int(variant_result["graded_holdout"]) - int(random_result["graded_holdout"]),
        "variant_train_score": variant_result["train_score"],
        "random_train_score": random_result["train_score"],
        "variant_raw": f"0x{variant_result['raw']:010x}",
        "random_raw": f"0x{random_result['raw']:010x}",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, default=DEFAULT_CLI)
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    parser.add_argument("--deep-budget", type=int, default=DEEP_BUDGET)
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
        "protocol": "prereg_search_v8_graded",
        "primary_gate": "hard_holdout_delta",
        "secondary_metric": "graded_holdout_delta",
        "budget": args.budget,
        "deep_budget": args.deep_budget,
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
                    args.deep_budget,
                    seed,
                    args.train_frames,
                    args.holdout_frames,
                ),
                seeds,
            ))
        hard_summary = summarize_delta(rows, "hard_holdout_delta", board_gate=True)
        graded_summary = summarize_delta(rows, "graded_holdout_delta", board_gate=False)
        any_pass = any_pass or bool(hard_summary["board_eligible"])
        report["variants"][variant] = {
            "hard_holdout_summary": hard_summary,
            "graded_holdout_summary": graded_summary,
            "rows": rows,
        }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"budget={args.budget} deep_budget={args.deep_budget} "
            f"train_frames={args.train_frames} holdout_frames={args.holdout_frames}"
        )
        for variant, data in report["variants"].items():
            hard = data["hard_holdout_summary"]
            graded = data["graded_holdout_summary"]
            print(
                f"{variant}: hard_wins={hard['wins']} hard_losses={hard['losses']} "
                f"hard_mean={hard['mean_delta']:.2f} hard_median={hard['median_delta']:.2f} "
                f"hard_p10={hard['p10_delta']} board_eligible={hard['board_eligible']} "
                f"graded_mean={graded['mean_delta']:.2f}"
            )

    if args.require_pass and not any_pass:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
