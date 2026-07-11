#!/usr/bin/env python3
"""Run preregistered v9 graded-island K sweep on host."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from host.screen_v3_search import DEFAULT_BUDGET, DEFAULT_CLI, HOLDOUT_FRAMES, TRAIN_FRAMES, parse_seed_list  # noqa: E402
from host.screen_v8_graded_search import run_comparison, summarize_delta  # noqa: E402


VARIANTS = (
    "pbil_island6_graded_v9",
    "pbil_island8_graded_v9",
    "pbil_island4_graded_v8",
)
K4_CONTROL = "pbil_island4_graded_v8"
K_SWEEP_VARIANTS = frozenset(("pbil_island6_graded_v9", "pbil_island8_graded_v9"))


def annotate_dilution(report_variants: dict[str, object]) -> None:
    control = report_variants.get(K4_CONTROL)
    if not isinstance(control, dict):
        return
    control_summary = control["hard_holdout_summary"]
    control_mean = float(control_summary["mean_delta"])
    control_median = float(control_summary["median_delta"])

    for variant, data in report_variants.items():
        if not isinstance(data, dict):
            continue
        summary = data["hard_holdout_summary"]
        if variant in K_SWEEP_VARIANTS:
            dilution_failed = (
                float(summary["mean_delta"]) < control_mean or
                float(summary["median_delta"]) < control_median
            )
            summary["dilution_failed_vs_k4"] = dilution_failed
            if dilution_failed:
                summary["board_eligible"] = False
        else:
            summary["dilution_failed_vs_k4"] = False
            if variant == K4_CONTROL:
                summary["control_only"] = True
                summary["board_eligible"] = False


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
        "protocol": "prereg_search_v9_graded_islands",
        "primary_gate": "hard_holdout_delta",
        "secondary_metric": "graded_holdout_delta",
        "control": K4_CONTROL,
        "budget": args.budget,
        "train_frames": args.train_frames,
        "holdout_frames": args.holdout_frames,
        "seeds": [f"0x{seed:04X}" for seed in seeds],
        "variants": {},
    }

    for variant in variants:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
            rows = list(executor.map(
                lambda seed: run_comparison(
                    args.cli,
                    variant,
                    args.budget,
                    args.budget,
                    seed,
                    args.train_frames,
                    args.holdout_frames,
                ),
                seeds,
            ))
        report["variants"][variant] = {
            "hard_holdout_summary": summarize_delta(rows, "hard_holdout_delta", board_gate=(variant in K_SWEEP_VARIANTS)),
            "graded_holdout_summary": summarize_delta(rows, "graded_holdout_delta", board_gate=False),
            "rows": rows,
        }

    annotate_dilution(report["variants"])
    any_pass = any(
        bool(data["hard_holdout_summary"]["board_eligible"])
        for data in report["variants"].values()
    )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"budget={args.budget} train_frames={args.train_frames} holdout_frames={args.holdout_frames}")
        for variant, data in report["variants"].items():
            hard = data["hard_holdout_summary"]
            graded = data["graded_holdout_summary"]
            print(
                f"{variant}: hard_wins={hard['wins']} hard_losses={hard['losses']} "
                f"hard_mean={hard['mean_delta']:.2f} hard_median={hard['median_delta']:.2f} "
                f"hard_p10={hard['p10_delta']} dilution_failed={hard['dilution_failed_vs_k4']} "
                f"board_eligible={hard['board_eligible']} graded_mean={graded['mean_delta']:.2f}"
            )

    if args.require_pass and not any_pass:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
