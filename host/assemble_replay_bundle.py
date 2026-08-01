#!/usr/bin/env python3
"""Convert a board-written framebuf replay blob into replay_bundle JSON."""

from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path


HEX_RE = re.compile(r"(?:0x)?([0-9a-fA-F]{8})")
STORE_MAGIC = 0x43484D50
STORE_V2 = 0x00020000
REPLAY_MAGIC = 0x52504C59
REPLAY_SCHEMA = 0x00010100
RECORD_WORDS = 16
REPLAY_WORDS = 24
FNV_OFFSET = 0x811C9DC5
FNV_PRIME = 0x01000193


def checksum_words(words: list[int]) -> int:
    acc = FNV_OFFSET
    for word in words:
        for byte in range(4):
            acc ^= (word >> (byte * 8)) & 0xFF
            acc = (acc * FNV_PRIME) & 0xFFFFFFFF
    return acc


def read_words(path: Path, text_hex: bool) -> list[int]:
    data = path.read_bytes()
    if text_hex:
        return [int(match.group(1), 16) for match in HEX_RE.finditer(data.decode("ascii"))]
    if len(data) % 4 != 0:
        raise ValueError("binary blob length is not a multiple of four")
    return list(struct.unpack("<" + "I" * (len(data) // 4), data))


def version_string(encoded: int) -> str:
    major = (encoded >> 16) & 0xFF
    minor = (encoded >> 8) & 0xFF
    patch = encoded & 0xFF
    return f"{major}.{minor}.{patch}"


def split_hard(packed: int) -> dict[str, int]:
    return {"passed": (packed >> 12) & 0x0FFF, "total": packed & 0x0FFF}


def assemble(words: list[int]) -> dict[str, object]:
    if len(words) < RECORD_WORDS + REPLAY_WORDS:
        raise ValueError("not enough store words for record+blob")
    record = words[:RECORD_WORDS]
    blob = words[RECORD_WORDS:RECORD_WORDS + REPLAY_WORDS]
    if record[0] != STORE_MAGIC or record[1] != STORE_V2:
        raise ValueError("champion record v2 magic/version mismatch")
    if record[15] != checksum_words(record[:15]):
        raise ValueError("champion record checksum mismatch")
    if blob[0] != REPLAY_MAGIC or blob[1] != REPLAY_SCHEMA:
        raise ValueError("replay blob magic/schema mismatch")

    raw = blob[11] | (blob[12] << 32)
    random_raw = blob[20] | (blob[21] << 32)
    evals = blob[18] | (blob[19] << 32)
    return {
        "schema": "replay_bundle",
        "schema_version": version_string(blob[1]),
        "source": "board_framebuf_blob",
        "build_id": f"0x{blob[3]:08x}{blob[2]:08x}",
        "build_id_semantics": "semantic replay inputs, not firmware image hash",
        "benchmark_id": "uart_stream_v2_headroom",
        "benchmark_id_word": f"0x{blob[4]:08x}",
        "genome_contract": {
            "genome_id": "uart_sampler_v2_headroom",
            "schema_version": version_string(blob[5]),
        },
        "search": {
            "variant": "pbil_island8_graded_v9",
            "random_baseline": "random",
            "search_seed": f"0x{blob[6]:04x}",
            "arm_budget": blob[7],
            "measured_evals_per_sec": blob[8],
            "train_frames_per_condition": blob[9],
            "holdout_frames_per_condition": blob[10],
        },
        "champion": {
            "raw_genome": f"0x{raw:010x}",
            "train_score": blob[13],
            "train_total": blob[14],
            "hard_holdout": split_hard(blob[15]),
            "graded_holdout": blob[16],
            "graded_holdout_total": blob[17],
            "evals": evals,
        },
        "random_equal_budget": {
            "raw_genome": f"0x{random_raw:010x}",
            "hard_holdout": split_hard(blob[22]),
            "graded_holdout": blob[23],
        },
        "write_budget": {
            "schema_version": "1.1.0",
            "write_count": record[14],
            "enforced_by": "firmware_and_flush_script",
        },
        "integrity": {
            "record_checksum": f"0x{record[15]:08x}",
            "blob_crc": f"0x{checksum_words(blob):08x}",
            "blob_words": len(blob),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--hex-words", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    bundle = assemble(read_words(args.input, args.hex_words))
    text = json.dumps(bundle, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
