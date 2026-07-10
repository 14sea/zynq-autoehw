#!/usr/bin/env python3
"""Run the preregistered v4 landscape locality diagnostics on host.

This is a diagnostic harness only. It uses Set A seeds, never Set B, and does
not authorize a board run.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.uart_stream_v1 import _payload, _vote_bit, crc8
from sim.uart_stream_v2 import (
    GENOME_BITS,
    SamplerGenomeV2,
    conditions_for,
    decode_genome,
    effective_config,
    encode_genome,
    landscape_child,
    random_genome,
    score_set,
)


SET_A = (
    0x1357, 0x2468, 0x369C, 0x47AD,
    0x58BE, 0x69CF, 0x7AD0, 0x8BE1,
    0x9CF2, 0xAD03, 0xBE14, 0xCF25,
    0xD036, 0xE147, 0xF258, 0x0ACE,
)
HISTORICAL_CHAMPIONS = (
    0x60894268A2,
    0x6A8BA845D4,
    0x09571273CE,
    0x08D590F3EE,
    0x4E85CBC206,
    0x6CBFB15FD8,
)
KERNELS = ("bitflip_1", "bitflip_4", "field_resample", "full_random")
BOOTSTRAP_SEED = 0x51A7


@dataclass(frozen=True)
class Parent:
    stratum: str
    index: int
    raw: int


@dataclass(frozen=True)
class PairSpec:
    stratum: str
    kernel: str
    parent_index: int
    child_index: int
    parent_raw: int
    child_seed: int
    frames: int


def parse_seed_list(value: str) -> tuple[int, ...]:
    if value == "setA":
        return SET_A
    return tuple(int(item, 0) for item in value.replace(",", " ").split())


def train_passed(genome: SamplerGenomeV2, frames: int) -> int:
    return sum(score.passed for score in score_set("train", genome, frames).conditions)


def frame_soft_matches(condition, genome: SamplerGenomeV2, frame_idx: int) -> int:
    config = effective_config(condition, genome)
    payload = _payload(condition, frame_idx)
    sent = payload + [crc8(payload)]
    state = (condition.lfsr_seed ^ 0xC0DE ^ (frame_idx * 0x1021)) & 0xFFFF
    matches = 0

    for byte in sent:
        decoded = 0
        for bit_idx in range(8):
            state, bit = _vote_bit((byte >> bit_idx) & 1, condition, config, state)
            decoded |= bit << bit_idx
        matches += 8 - ((decoded ^ byte) & 0xFF).bit_count()
    return matches


def train_soft_score(genome: SamplerGenomeV2, frames: int) -> int:
    total = 0
    for condition in conditions_for("train"):
        for frame_idx in range(frames):
            total += frame_soft_matches(condition, genome, frame_idx)
    return total


def child_seed(stratum_index: int, kernel_index: int, parent_index: int, child_index: int, base_seed: int) -> int:
    seed = (
        base_seed ^
        ((stratum_index + 1) * 0x1F3D) ^
        ((kernel_index + 1) * 0x2B21) ^
        (parent_index * 0x1021) ^
        (child_index * 0x0707)
    )
    seed &= 0xFFFF
    return seed if seed else 0xACE1


def generate_uniform_parents(seeds: tuple[int, ...], parents_per_stratum: int) -> list[Parent]:
    per_seed = parents_per_stratum // len(seeds)
    parents: list[Parent] = []
    for seed in seeds:
        state = (seed ^ 0x1111) & 0xFFFF
        for _ in range(per_seed):
            state, genome = random_genome(state)
            parents.append(Parent("uniform_random", len(parents), encode_genome(genome)))
    return parents


def generate_top_decile_parents(
    seeds: tuple[int, ...],
    parents_per_stratum: int,
    top_pool_per_seed: int,
    frames: int,
) -> list[Parent]:
    per_seed = parents_per_stratum // len(seeds)
    parents: list[Parent] = []
    for seed in seeds:
        state = (seed ^ 0x2222) & 0xFFFF
        scored: list[tuple[int, int, int]] = []
        for stream_idx in range(top_pool_per_seed):
            state, genome = random_genome(state)
            raw = encode_genome(genome)
            scored.append((-train_passed(genome, frames), stream_idx, raw))
        for _score, _stream_idx, raw in sorted(scored)[:per_seed]:
            parents.append(Parent("random_stream_top_decile", len(parents), raw))
    return parents


def generate_historical_parents(parents_per_stratum: int) -> list[Parent]:
    parents: list[Parent] = []
    for idx in range(parents_per_stratum):
        raw = HISTORICAL_CHAMPIONS[idx % len(HISTORICAL_CHAMPIONS)] & ((1 << GENOME_BITS) - 1)
        parents.append(Parent("historical_champion", idx, raw))
    return parents


def build_parent_sets(
    seeds: tuple[int, ...],
    parents_per_stratum: int,
    top_pool_per_seed: int,
    frames: int,
) -> dict[str, list[Parent]]:
    if parents_per_stratum <= 0 or parents_per_stratum % len(seeds) != 0:
        raise ValueError("parents-per-stratum must be positive and divisible by seed count")
    if top_pool_per_seed < parents_per_stratum // len(seeds):
        raise ValueError("top-pool-per-seed must be at least parents-per-stratum / seed-count")
    return {
        "uniform_random": generate_uniform_parents(seeds, parents_per_stratum),
        "random_stream_top_decile": generate_top_decile_parents(seeds, parents_per_stratum, top_pool_per_seed, frames),
        "historical_champion": generate_historical_parents(parents_per_stratum),
    }


def evaluate_pair(spec: PairSpec) -> dict[str, int | str]:
    parent = decode_genome(spec.parent_raw)
    _state, child = landscape_child(spec.kernel, spec.child_seed, parent)
    parent_hard = train_passed(parent, spec.frames)
    child_hard = train_passed(child, spec.frames)
    parent_soft = train_soft_score(parent, spec.frames)
    child_soft = train_soft_score(child, spec.frames)
    return {
        "stratum": spec.stratum,
        "kernel": spec.kernel,
        "parent_index": spec.parent_index,
        "child_index": spec.child_index,
        "parent_raw": f"0x{spec.parent_raw:010x}",
        "child_raw": f"0x{encode_genome(child):010x}",
        "parent_hard": parent_hard,
        "child_hard": child_hard,
        "parent_soft": parent_soft,
        "child_soft": child_soft,
    }


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or not xs:
        return 0.0
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = sum((x - mean_x) ** 2 for x in xs)
    den_y = sum((y - mean_y) ** 2 for y in ys)
    den = math.sqrt(den_x * den_y)
    return num / den if den else 0.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def probability(values: list[float]) -> float:
    return sum(1 for value in values if value >= 0) / len(values) if values else 0.0


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * pct))
    return ordered[idx]


def bootstrap_ci(
    parent_values: list[float],
    child_values: list[float],
    metric: str,
    rounds: int,
    seed: int,
) -> tuple[float, float]:
    if not parent_values or rounds <= 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    count = len(parent_values)
    values: list[float] = []
    for _ in range(rounds):
        indexes = [rng.randrange(count) for _idx in range(count)]
        parents = [parent_values[idx] for idx in indexes]
        children = [child_values[idx] for idx in indexes]
        if metric == "corr":
            values.append(pearson(parents, children))
        elif metric == "delta":
            values.append(mean([child - parent for parent, child in zip(parents, children)]))
        elif metric == "p_ge":
            values.append(probability([child - parent for parent, child in zip(parents, children)]))
        else:
            raise ValueError(f"unknown bootstrap metric: {metric}")
    return (percentile(values, 0.025), percentile(values, 0.975))


def summarize_group(rows: list[dict[str, int | str]], bootstrap_rounds: int) -> dict[str, object]:
    parent_hard = [float(row["parent_hard"]) for row in rows]
    child_hard = [float(row["child_hard"]) for row in rows]
    parent_soft = [float(row["parent_soft"]) for row in rows]
    child_soft = [float(row["child_soft"]) for row in rows]
    hard_delta = [child - parent for parent, child in zip(parent_hard, child_hard)]
    soft_delta = [child - parent for parent, child in zip(parent_soft, child_soft)]
    base_seed = BOOTSTRAP_SEED + len(rows)

    return {
        "n_pairs": len(rows),
        "hard": {
            "parent_child_corr": pearson(parent_hard, child_hard),
            "parent_child_corr_ci95": bootstrap_ci(parent_hard, child_hard, "corr", bootstrap_rounds, base_seed + 1),
            "mean_child_minus_parent": mean(hard_delta),
            "mean_child_minus_parent_ci95": bootstrap_ci(parent_hard, child_hard, "delta", bootstrap_rounds, base_seed + 2),
            "p_child_ge_parent": probability(hard_delta),
            "p_child_ge_parent_ci95": bootstrap_ci(parent_hard, child_hard, "p_ge", bootstrap_rounds, base_seed + 3),
        },
        "soft": {
            "parent_child_corr": pearson(parent_soft, child_soft),
            "parent_child_corr_ci95": bootstrap_ci(parent_soft, child_soft, "corr", bootstrap_rounds, base_seed + 4),
            "mean_child_minus_parent": mean(soft_delta),
            "mean_child_minus_parent_ci95": bootstrap_ci(parent_soft, child_soft, "delta", bootstrap_rounds, base_seed + 5),
            "p_child_ge_parent": probability(soft_delta),
            "p_child_ge_parent_ci95": bootstrap_ci(parent_soft, child_soft, "p_ge", bootstrap_rounds, base_seed + 6),
        },
        "hard_soft_child_corr": pearson(child_hard, child_soft),
    }


def build_pair_specs(
    parent_sets: dict[str, list[Parent]],
    children_per_parent: int,
    frames: int,
    base_seed: int,
) -> list[PairSpec]:
    specs: list[PairSpec] = []
    strata = tuple(parent_sets.keys())
    for stratum_index, stratum in enumerate(strata):
        for kernel_index, kernel in enumerate(KERNELS):
            for parent in parent_sets[stratum]:
                for child_index in range(children_per_parent):
                    specs.append(PairSpec(
                        stratum=stratum,
                        kernel=kernel,
                        parent_index=parent.index,
                        child_index=child_index,
                        parent_raw=parent.raw,
                        child_seed=child_seed(stratum_index, kernel_index, parent.index, child_index, base_seed),
                        frames=frames,
                    ))
    return specs


def run_specs(specs: list[PairSpec], jobs: int) -> list[dict[str, int | str]]:
    if jobs <= 1:
        return [evaluate_pair(spec) for spec in specs]
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        return list(executor.map(evaluate_pair, specs))


def summarize(rows: list[dict[str, int | str]], bootstrap_rounds: int) -> dict[str, dict[str, object]]:
    report: dict[str, dict[str, object]] = {}
    for stratum in ("uniform_random", "random_stream_top_decile", "historical_champion"):
        report[stratum] = {}
        for kernel in KERNELS:
            group = [row for row in rows if row["stratum"] == stratum and row["kernel"] == kernel]
            report[stratum][kernel] = summarize_group(group, bootstrap_rounds)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=64)
    parser.add_argument("--parents-per-stratum", type=int, default=256)
    parser.add_argument("--top-pool-per-seed", type=int, default=160)
    parser.add_argument("--children-per-parent", type=int, default=16)
    parser.add_argument("--bootstrap-rounds", type=int, default=1000)
    parser.add_argument("--seeds", default="setA")
    parser.add_argument("--child-base-seed", type=lambda value: int(value, 0), default=0x51A7)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--include-rows", action="store_true")
    args = parser.parse_args()

    seeds = parse_seed_list(args.seeds)
    parent_sets = build_parent_sets(seeds, args.parents_per_stratum, args.top_pool_per_seed, args.frames)
    specs = build_pair_specs(parent_sets, args.children_per_parent, args.frames, args.child_base_seed)
    rows = run_specs(specs, args.jobs)
    results = summarize(rows, args.bootstrap_rounds)
    report: dict[str, object] = {
        "protocol": "prereg_landscape_v4",
        "frames": args.frames,
        "parents_per_stratum": args.parents_per_stratum,
        "top_pool_per_seed": args.top_pool_per_seed,
        "children_per_parent": args.children_per_parent,
        "bootstrap_rounds": args.bootstrap_rounds,
        "seeds": [f"0x{seed:04X}" for seed in seeds],
        "historical_champions": [f"0x{raw:010x}" for raw in HISTORICAL_CHAMPIONS],
        "results": results,
    }
    if args.include_rows:
        report["rows"] = rows

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"frames={args.frames} parents_per_stratum={args.parents_per_stratum} "
            f"children_per_parent={args.children_per_parent} bootstrap={args.bootstrap_rounds}"
        )
        for stratum, by_kernel in results.items():
            for kernel, data in by_kernel.items():
                hard = data["hard"]
                soft = data["soft"]
                print(
                    f"{stratum} {kernel}: "
                    f"hard_corr={hard['parent_child_corr']:.3f} "
                    f"hard_delta={hard['mean_child_minus_parent']:.2f} "
                    f"hard_p_ge={hard['p_child_ge_parent']:.3f} "
                    f"soft_corr={soft['parent_child_corr']:.3f} "
                    f"soft_delta={soft['mean_child_minus_parent']:.2f} "
                    f"soft_p_ge={soft['p_child_ge_parent']:.3f} "
                    f"hard_soft_child_corr={data['hard_soft_child_corr']:.3f}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
