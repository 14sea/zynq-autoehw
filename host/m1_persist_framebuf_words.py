#!/usr/bin/env python3
"""Emit the PS framebuf words for the M1 champion-store restore smoke."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.uart_stream_v1 import SamplerConfig, champion_store_words


def main() -> int:
    words = champion_store_words(SamplerConfig(sample_phase=15, threshold=-73, majority_window=5))
    base = 0x40000000
    for idx, word in enumerate(words):
        print(f"mw.l 0x{base + idx * 4:08x} 0x{word:08x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
