#!/usr/bin/env python3
"""Emit PS framebuf restore writes for M1 champion-store restore smoke.

Default mode preserves the historical 5-word v1 restore fixture. The
M1-engineering addendum mode converts a board-written high-half v2 store dump
back into low-half restore words so the NV round trip can be tested after a
power cycle.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.uart_stream_v1 import SamplerConfig, champion_store_words

HEX_RE = re.compile(r"(?:0x)?([0-9a-fA-F]{8})")
STORE_V2_MAGIC = 0x43484D50
STORE_V2_VERSION = 0x00020000
STORE_V2_WORDS = 16
FNV_OFFSET = 0x811C9DC5
FNV_PRIME = 0x01000193


def checksum_words(words: list[int]) -> int:
    acc = FNV_OFFSET
    for word in words:
        for byte in range(4):
            acc ^= (word >> (byte * 8)) & 0xFF
            acc = (acc * FNV_PRIME) & 0xFFFFFFFF
    return acc


def parse_hex_words(path: Path) -> list[int]:
    words: list[int] = []
    for line in path.read_text().splitlines():
        data = line.split(":", 1)[1] if ":" in line else line
        words.extend(int(match.group(1), 16) for match in HEX_RE.finditer(data))
    return words


def v2_restore_words_from_store(path: Path) -> list[int]:
    words = parse_hex_words(path)
    if len(words) < STORE_V2_WORDS:
        raise ValueError(f"need at least {STORE_V2_WORDS} words, got {len(words)}")
    record = words[:STORE_V2_WORDS]
    if record[0] != STORE_V2_MAGIC:
        raise ValueError(f"record magic mismatch: 0x{record[0]:08x}")
    if record[1] != STORE_V2_VERSION:
        raise ValueError(f"record version mismatch: 0x{record[1]:08x}")
    if record[15] != checksum_words(record[:15]):
        raise ValueError("record checksum mismatch")
    return record


def emit_mw(words: list[int], base: int) -> None:
    for idx, word in enumerate(words):
        print(f"mw.l 0x{base + idx * 4:08x} 0x{word:08x}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-store-hex", type=Path, help="hex words dumped from the board-store high half")
    parser.add_argument("--base", type=lambda value: int(value, 0), default=0x40000000)
    args = parser.parse_args()

    try:
        if args.from_store_hex:
            emit_mw(v2_restore_words_from_store(args.from_store_hex), args.base)
        else:
            emit_mw(champion_store_words(SamplerConfig(sample_phase=15, threshold=-73, majority_window=5)), args.base)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
