#!/usr/bin/env python3
"""Generate RTL-vs-oracle vectors for uart_stream_eval_core."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.uart_stream_v1 import CONDITIONS, STATIC_BASELINE, SamplerConfig, frame_passes


EDGE_SCORE = {"low": 2, "med": 5, "high": 8}
PAYLOAD_MODE = {"A2": 1, "A3": 2}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("build/rtl/eval_vectors.txt"))
    parser.add_argument("--frames", type=int, default=4)
    args = parser.parse_args()

    configs = [
        STATIC_BASELINE,
        SamplerConfig(sample_phase=15, threshold=-73, majority_window=5),
        SamplerConfig(sample_phase=23, threshold=42, majority_window=3),
    ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for condition in CONDITIONS:
        for frame_idx in range(args.frames):
            for config in configs:
                expected = int(frame_passes(condition, config, frame_idx))
                mode = PAYLOAD_MODE.get(condition.name, 0)
                lines.append(
                    " ".join(
                        str(value)
                        for value in (
                            condition.packet_len,
                            condition.lfsr_seed,
                            condition.baud_ppm,
                            round(condition.jitter_frac * 1000),
                            round(condition.flip_prob * 1000000),
                            EDGE_SCORE[condition.edge_unc],
                            mode,
                            frame_idx,
                            config.sample_phase,
                            config.threshold,
                            config.majority_window,
                            expected,
                        )
                    )
                )
    args.out.write_text("\n".join(lines) + "\n")
    print(f"wrote {len(lines)} vectors to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

