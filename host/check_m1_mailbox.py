#!/usr/bin/env python3
"""Validate an M1 mailbox carousel with the paged extension."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.uart_stream_v1 import mailbox_page_checksum


HEX_RE = re.compile(r"(?:0x)?([0-9a-fA-F]{8})")
LONGRUN_TARGET_SECONDS = 7200
TRAIN_EVALS_PER_CANDIDATE = 32


def parse_words(text: str) -> list[int]:
    return [int(match.group(1), 16) for match in HEX_RE.finditer(text)]


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def decode_page(words: list[int], offset: int, page_id: int, count: int) -> tuple[int, ...] | None:
    page = words[offset:offset + count + 2]
    if len(page) != count + 2:
        return None
    if page[0] != (0xC0000000 | ((page_id & 0xFF) << 16) | count):
        return None
    if any((word & 0xFF000000) != 0xC1000000 for word in page[1:1 + count]):
        return None
    seqs = tuple((word >> 22) & 0x03 for word in page[1:1 + count])
    expected_seqs = tuple(idx & 0x03 for idx in range(count))
    if seqs != expected_seqs:
        return None
    payloads = tuple(word & 0x003FFFFF for word in page[1:1 + count])
    checksum = mailbox_page_checksum(page_id, payloads)
    if page[-1] != (0xC2000000 | checksum):
        return None
    return payloads


def main() -> int:
    words = parse_words(sys.stdin.read())
    if len(words) < 31:
        return fail(f"need at least 31 words, got {len(words)}")

    expected_prefix = [
        0xA7000000,
        0xA8001008,
        0xA90F05B7,
        0xAA013020,
        0xAB011020,
        0xAC000200,
        0xAD00C0DE,
    ]
    if words[:7] != expected_prefix:
        return fail("legacy prefix words 0..6 mismatch")
    if (words[7] & 0xFF000000) != 0xAE000000 or (words[7] & 0x00FFFFFF) == 0:
        return fail("AE evals/sec word missing or zero")
    if words[8:11] != [0xAF011020, 0xB00013E8, 0xB10F05B7]:
        return fail("random/write/persist words mismatch")
    if words[11:13] not in ([0xB2000001, 0xB3000000], [0xB2010101, 0xB30F05B7]):
        return fail("restore status/config words mismatch")
    if words[13:15] != [0xB4010101, 0xB5010101]:
        return fail("reject/recovery words mismatch")

    summary_payloads = decode_page(words, 15, 1, 6)
    if summary_payloads is None:
        return fail("summary page framing/sequence/checksum mismatch")
    if summary_payloads[0] != 0x01000F:
        return fail("summary page version/legacy-count mismatch")
    if summary_payloads[1] != (words[7] & 0x00FFFFFF):
        return fail("summary page evals/sec payload does not mirror AE")
    if summary_payloads[2] != 0x011020:
        return fail("summary page random-baseline payload mismatch")
    if summary_payloads[3] != (words[11] & 0x00FFFFFF):
        return fail("summary page restore payload does not mirror B2")
    if summary_payloads[4:] != (0x010101, 0x010101):
        return fail("summary page event payloads mismatch")

    longrun_payloads = decode_page(words, 23, 2, 6)
    if longrun_payloads is None:
        return fail("long-run page framing/sequence/checksum mismatch")
    evals_per_sec = words[7] & 0x00FFFFFF
    target_evals = evals_per_sec * LONGRUN_TARGET_SECONDS
    candidate_budget = target_evals // TRAIN_EVALS_PER_CANDIDATE
    expected_longrun = (
        (0x02 << 16) | (LONGRUN_TARGET_SECONDS // 60),
        TRAIN_EVALS_PER_CANDIDATE,
        target_evals & 0x3FFFFF,
        (target_evals >> 22) & 0x3FFFFF,
        candidate_budget & 0x3FFFFF,
        (candidate_budget >> 22) & 0x3FFFFF,
    )
    if longrun_payloads != expected_longrun:
        return fail("long-run page derived-budget payload mismatch")

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
