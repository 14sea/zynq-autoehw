#!/usr/bin/env python3
"""Verify a board-origin replay_bundle by rerunning the C twin."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_arm(stdout: str) -> tuple[dict[str, int], dict[str, int]]:
    lines = stdout.strip().splitlines()
    fields = lines[0].split()
    graded = lines[1].split()
    hard = {
        "raw": int(fields[2], 16),
        "train_score": int(fields[12]),
        "train_total": int(fields[13]),
        "holdout_passed": int(fields[15]),
        "holdout_total": int(fields[16]),
        "evals": int(fields[18]),
    }
    soft = {
        "graded_holdout": int(graded[1]),
        "graded_holdout_total": int(graded[2]),
    }
    return hard, soft


def run_variant(cli: Path, variant: str, budget: int, seed: int, train_frames: int, holdout_frames: int) -> tuple[dict[str, int], dict[str, int]]:
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
    return parse_arm(proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--cli", type=Path, default=ROOT / "build" / "host" / "uart_stream_v2_cli")
    args = parser.parse_args()

    bundle = json.loads(args.bundle.read_text())
    search = bundle["search"]
    champion = bundle["champion"]
    random = bundle["random_equal_budget"]
    seed = int(search["search_seed"], 16)
    budget = int(search["arm_budget"])
    train_frames = int(search["train_frames_per_condition"])
    holdout_frames = int(search["holdout_frames_per_condition"])

    variant_hard, variant_soft = run_variant(
        args.cli,
        search["variant"],
        budget,
        seed ^ 0x4A4A,
        train_frames,
        holdout_frames,
    )
    random_hard, random_soft = run_variant(
        args.cli,
        "random",
        budget,
        seed ^ 0xBEEF,
        train_frames,
        holdout_frames,
    )

    expected_variant = {
        "raw": int(champion["raw_genome"], 16),
        "train_score": int(champion["train_score"]),
        "train_total": int(champion["train_total"]),
        "holdout_passed": int(champion["hard_holdout"]["passed"]),
        "holdout_total": int(champion["hard_holdout"]["total"]),
    }
    expected_variant_soft = {
        "graded_holdout": int(champion["graded_holdout"]),
        "graded_holdout_total": int(champion["graded_holdout_total"]),
    }
    expected_random = {
        "raw": int(random["raw_genome"], 16),
        "holdout_passed": int(random["hard_holdout"]["passed"]),
        "holdout_total": int(random["hard_holdout"]["total"]),
    }
    expected_random_soft = {"graded_holdout": int(random["graded_holdout"])}

    for key, value in expected_variant.items():
        if variant_hard[key] != value:
            raise SystemExit(f"variant mismatch for {key}: {variant_hard[key]} != {value}")
    expected_frame_evals = budget * 4 * train_frames
    if int(champion["evals"]) != expected_frame_evals:
        raise SystemExit(f"frame eval mismatch: {champion['evals']} != {expected_frame_evals}")
    if variant_soft != expected_variant_soft:
        raise SystemExit(f"variant graded mismatch: {variant_soft} != {expected_variant_soft}")
    for key, value in expected_random.items():
        if random_hard[key] != value:
            raise SystemExit(f"random mismatch for {key}: {random_hard[key]} != {value}")
    if random_soft["graded_holdout"] != expected_random_soft["graded_holdout"]:
        raise SystemExit("random graded holdout mismatch")
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
