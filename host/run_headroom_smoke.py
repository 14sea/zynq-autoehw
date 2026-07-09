#!/usr/bin/env python3
"""Generate the uart_stream_v2_headroom host-gate fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.uart_stream_v2 import (  # noqa: E402
    GENOME_BITS,
    build_run_log_fixture,
    genome_space_size,
    same_boot_ab_search,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=int, default=16)
    parser.add_argument("--frames", type=int, default=4)
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0xC0DE)
    parser.add_argument("--out", type=Path, default=Path("build/host/headroom_run_log_fixture.json"))
    args = parser.parse_args()

    result = same_boot_ab_search(args.budget, args.seed, args.frames)
    fixture = build_run_log_fixture(result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n")

    print(f"genome_bits={GENOME_BITS}")
    print(f"genome_space={genome_space_size()}")
    print(f"ga_train={fixture['final_evaluation']['ga']['train_fitness']:.6f}")  # type: ignore[index]
    print(f"ga_holdout={fixture['final_evaluation']['ga']['holdout_fitness']:.6f}")  # type: ignore[index]
    print(f"random_holdout={fixture['final_evaluation']['random_equal_budget']['holdout_fitness']:.6f}")  # type: ignore[index]
    print(f"wrote={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
