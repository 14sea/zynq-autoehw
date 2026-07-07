#!/usr/bin/env python3
"""Generate a deterministic host-side M1 smoke report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.uart_stream_v1 import (
    DEFAULT_FRAMES,
    build_run_log_fixture,
    random_search_train_only,
    score_set,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=int, default=16)
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES)
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0xC0DE)
    parser.add_argument("--out", type=Path, default=Path("build/host/m1_run_log_fixture.json"))
    args = parser.parse_args()

    search = random_search_train_only(args.budget, args.seed, args.frames)
    run_log = build_run_log_fixture(search, args.frames)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(run_log, indent=2, sort_keys=True) + "\n")

    train = score_set("train", search.best_config, args.frames)
    holdout = score_set("holdout", search.best_config, args.frames)
    print(f"best_config={search.best_config}")
    print(f"train_fitness={train.fitness:.6f}")
    print(f"final_holdout_fitness={holdout.fitness:.6f}")
    print(f"wrote={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
