#!/usr/bin/env python3
"""Run the preregistered v6 multi-island PBIL variants against random on host."""

from __future__ import annotations

import argparse
import json
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
    run_comparison,
    summarize,
)


VARIANTS = (
    "pbil_island2_v6",
    "pbil_island3_v6",
    "pbil_island4_v6",
    "pbil_eda_v4",
)


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
        "protocol": "prereg_search_v6",
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
