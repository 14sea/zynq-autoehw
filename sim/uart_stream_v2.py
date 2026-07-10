"""Headroom oracle scaffold for the `uart_stream_v2_headroom` benchmark.

This module deliberately does not replace the board-verified v1 oracle. It pins
the next benchmark's search-space, GA-vs-random A/B bookkeeping, and holdout
firewall before firmware/RTL are connected.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from sim.uart_stream_v1 import (
    Condition,
    ConditionScore,
    SamplerConfig,
    SetScore,
    frame_passes,
    lfsr16_step,
    round_nearest_away_from_zero,
)


SCHEMA_VERSION = "2.0.0"
BENCHMARK_ID = "uart_stream_v2_headroom"
GENOME_ID = "uart_sampler_v2_headroom"
GENOME_BITS = 39
DEFAULT_FRAMES = 8
MAJORITY_OPTIONS = (1, 3, 5, 5)
EDGE_UNC_SCORE = {"low": 2, "med": 5, "high": 8}


@dataclass(frozen=True)
class SamplerGenomeV2:
    sample_phase: int
    threshold: int
    majority_idx: int
    tap_word: int

    def __post_init__(self) -> None:
        if not 0 <= self.sample_phase <= 31:
            raise ValueError("sample_phase must be in [0, 31]")
        if not -128 <= self.threshold <= 127:
            raise ValueError("threshold must be in [-128, 127]")
        if not 0 <= self.majority_idx <= 3:
            raise ValueError("majority_idx must be in [0, 3]")
        if not 0 <= self.tap_word <= 0xFFFFFF:
            raise ValueError("tap_word must be a 24-bit unsigned integer")


@dataclass(frozen=True)
class ArmResult:
    arm: str
    best_genome: SamplerGenomeV2
    best_fitness_train: float
    generations: tuple[dict[str, int | float | str | bool], ...]


@dataclass(frozen=True)
class ABResult:
    seed: int
    budget: int
    frames: int
    ga: ArmResult
    random: ArmResult


CONDITIONS: tuple[Condition, ...] = (
    Condition("T0v2", "train", -850, 0.16, 0.026, "med", 32, 0x5111),
    Condition("T1v2", "train", +900, 0.18, 0.030, "high", 32, 0x5222),
    Condition("T2v2", "train", -1250, 0.22, 0.034, "high", 48, 0x5333),
    Condition("T3v2", "train", +1400, 0.20, 0.038, "high", 48, 0x5444),
    Condition("H0v2", "holdout", -700, 0.17, 0.028, "med", 40, 0xA511),
    Condition("H1v2", "holdout", +1100, 0.21, 0.032, "high", 56, 0xB522),
    Condition("H2v2", "holdout", -1500, 0.24, 0.036, "high", 24, 0xC533),
    Condition("H3v2", "holdout", +1650, 0.19, 0.040, "high", 64, 0xD544),
    Condition("A0v2", "adversarial", 0, 0.10, 0.120, "high", 32, 0xE0A0),
    Condition("A1v2", "adversarial", +1800, 0.30, 0.040, "high", 32, 0xE1A1),
    Condition("A2v2", "adversarial", -1800, 0.28, 0.040, "high", 32, 0xE2A2),
    Condition("A3v2", "adversarial", 0, 0.22, 0.080, "med", 32, 0xE3A3),
)


STATIC_BASELINE = SamplerGenomeV2(sample_phase=16, threshold=0, majority_idx=1, tap_word=0)


def genome_space_size() -> int:
    return 1 << GENOME_BITS


def _rand16(state: int) -> tuple[int, int]:
    state = lfsr16_step(state)
    return state, state


def _rand32(state: int) -> tuple[int, int]:
    state, hi = _rand16(state)
    state, lo = _rand16(state)
    return state, ((hi << 16) | lo) & 0xFFFFFFFF


def _signed8(value: int) -> int:
    value &= 0xFF
    return value - 256 if value & 0x80 else value


def encode_genome(genome: SamplerGenomeV2) -> int:
    return (
        (genome.sample_phase & 0x1F) |
        ((genome.threshold & 0xFF) << 5) |
        ((genome.majority_idx & 0x03) << 13) |
        ((genome.tap_word & 0xFFFFFF) << 15)
    )


def decode_genome(word: int) -> SamplerGenomeV2:
    return SamplerGenomeV2(
        sample_phase=word & 0x1F,
        threshold=_signed8((word >> 5) & 0xFF),
        majority_idx=(word >> 13) & 0x03,
        tap_word=(word >> 15) & 0xFFFFFF,
    )


def genome_hash(genome: SamplerGenomeV2) -> str:
    return sha256(encode_genome(genome).to_bytes(5, "little")).hexdigest()


def random_genome(state: int) -> tuple[int, SamplerGenomeV2]:
    state, word0 = _rand32(state)
    state, word1 = _rand16(state)
    raw = (word0 | ((word1 & 0x7F) << 32)) & ((1 << GENOME_BITS) - 1)
    return state, decode_genome(raw)


def mutate_genome(state: int, parent: SamplerGenomeV2) -> tuple[int, SamplerGenomeV2]:
    state, rnd = _rand32(state)
    raw = encode_genome(parent)
    flips = 1 + (rnd & 0x03)
    for idx in range(flips):
        state, bit_rnd = _rand16(state)
        raw ^= 1 << ((bit_rnd + idx * 7) % GENOME_BITS)
    return state, decode_genome(raw)


def landscape_child(kernel: str, state: int, parent: SamplerGenomeV2) -> tuple[int, SamplerGenomeV2]:
    raw = encode_genome(parent)
    if kernel == "bitflip_1":
        state, bit_rnd = _rand16(state)
        raw ^= 1 << (bit_rnd % GENOME_BITS)
        return state, decode_genome(raw)

    if kernel == "bitflip_4":
        used = 0
        flips = 0
        while flips < 4:
            state, bit_rnd = _rand16(state)
            bit = bit_rnd % GENOME_BITS
            mask = 1 << bit
            if used & mask:
                continue
            used |= mask
            raw ^= mask
            flips += 1
        return state, decode_genome(raw)

    if kernel == "field_resample":
        state, field_rnd = _rand16(state)
        field = field_rnd % 6
        genome = parent
        if field == 0:
            state, value = _rand16(state)
            genome = SamplerGenomeV2(value % 32, genome.threshold, genome.majority_idx, genome.tap_word)
        elif field == 1:
            state, value = _rand16(state)
            genome = SamplerGenomeV2(genome.sample_phase, (value % 256) - 128, genome.majority_idx, genome.tap_word)
        elif field == 2:
            state, value = _rand16(state)
            genome = SamplerGenomeV2(genome.sample_phase, genome.threshold, value % 4, genome.tap_word)
        else:
            state, value = _rand16(state)
            shift = (field - 3) * 8
            tap_word = (genome.tap_word & ~(0xFF << shift)) | ((value & 0xFF) << shift)
            genome = SamplerGenomeV2(genome.sample_phase, genome.threshold, genome.majority_idx, tap_word)
        return state, genome

    if kernel == "full_random":
        return random_genome(state)

    raise ValueError(f"unknown landscape kernel: {kernel}")


def _tap_bytes(genome: SamplerGenomeV2) -> tuple[int, int, int]:
    return (
        _signed8(genome.tap_word),
        _signed8(genome.tap_word >> 8),
        _signed8(genome.tap_word >> 16),
    )


def effective_config(condition: Condition, genome: SamplerGenomeV2) -> SamplerConfig:
    tap_baud, tap_jitter, tap_edge = _tap_bytes(genome)
    edge = EDGE_UNC_SCORE[condition.edge_unc]
    jitter_milli = round_nearest_away_from_zero(condition.jitter_frac * 1000)
    phase_adjust = round_nearest_away_from_zero(
        (tap_baud * condition.baud_ppm) / 8192 +
        (tap_jitter * (jitter_milli - 180)) / 512 +
        (tap_edge * (edge - 5)) / 16
    )
    threshold_adjust = round_nearest_away_from_zero(
        (tap_jitter * (condition.flip_prob * 1000 - 30)) / 8 +
        (tap_edge * (edge - 5)) / 3
    )
    phase = max(0, min(31, genome.sample_phase + max(-10, min(10, phase_adjust))))
    threshold = max(-128, min(127, genome.threshold + max(-64, min(64, threshold_adjust))))
    return SamplerConfig(
        sample_phase=phase,
        threshold=threshold,
        majority_window=MAJORITY_OPTIONS[genome.majority_idx],
    )


def conditions_for(split: str) -> tuple[Condition, ...]:
    selected = tuple(condition for condition in CONDITIONS if condition.split == split)
    if not selected:
        raise ValueError(f"unknown split: {split}")
    return selected


def score_condition(condition: Condition, genome: SamplerGenomeV2, frames: int = DEFAULT_FRAMES) -> ConditionScore:
    config = effective_config(condition, genome)
    passed = sum(1 for frame_idx in range(frames) if frame_passes(condition, config, frame_idx))
    return ConditionScore(condition.name, condition.split, passed, frames)


def score_set(split: str, genome: SamplerGenomeV2, frames: int = DEFAULT_FRAMES) -> SetScore:
    return SetScore(split, tuple(score_condition(condition, genome, frames) for condition in conditions_for(split)))


def random_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    if budget <= 0:
        raise ValueError("budget must be positive")
    state = seed & 0xFFFF
    best_genome = STATIC_BASELINE
    best_fitness = -1.0
    generations: list[dict[str, int | float | str | bool]] = []

    for gen in range(budget):
        state, genome = random_genome(state)
        train = score_set("train", genome, frames)
        accepted = train.fitness > best_fitness
        if accepted:
            best_fitness = train.fitness
            best_genome = genome
        generations.append(
            {
                "arm": "random",
                "gen": gen,
                "best_fitness_train": round(best_fitness, 6),
                "evals": (gen + 1) * len(conditions_for("train")) * frames,
                "best_genome_hash": genome_hash(best_genome),
                "accepted": accepted,
            }
        )

    return ArmResult("random", best_genome, best_fitness, tuple(generations))


def ga_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    if budget <= 0:
        raise ValueError("budget must be positive")
    state = seed & 0xFFFF
    state, best_genome = random_genome(state)
    best_train = score_set("train", best_genome, frames)
    best_fitness = best_train.fitness
    generations: list[dict[str, int | float | str | bool]] = [
        {
            "arm": "ga",
            "gen": 0,
            "best_fitness_train": round(best_fitness, 6),
            "evals": len(conditions_for("train")) * frames,
            "best_genome_hash": genome_hash(best_genome),
            "accepted": True,
        }
    ]

    for gen in range(1, budget):
        state, candidate = mutate_genome(state, best_genome)
        train = score_set("train", candidate, frames)
        accepted = train.fitness >= best_fitness
        if accepted:
            best_fitness = train.fitness
            best_genome = candidate
        generations.append(
            {
                "arm": "ga",
                "gen": gen,
                "best_fitness_train": round(best_fitness, 6),
                "evals": (gen + 1) * len(conditions_for("train")) * frames,
                "best_genome_hash": genome_hash(best_genome),
                "accepted": accepted,
            }
        )

    return ArmResult("ga", best_genome, best_fitness, tuple(generations))


def restart_hillclimb_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    if budget <= 0:
        raise ValueError("budget must be positive")
    state = seed & 0xFFFF
    restarts = 16
    best_genome = STATIC_BASELINE
    best_passed = -1
    total = len(conditions_for("train")) * frames

    for restart in range(restarts):
        local_budget = budget // restarts + (1 if restart < (budget % restarts) else 0)
        local_genome = STATIC_BASELINE
        local_passed = -1
        for gen in range(local_budget):
            if gen == 0:
                state, genome = random_genome(state)
            else:
                state, genome = mutate_genome(state, local_genome)
            train = score_set("train", genome, frames)
            passed = sum(score.passed for score in train.conditions)
            if gen == 0 or passed >= local_passed:
                local_genome = genome
                local_passed = passed
        if local_budget > 0 and local_passed > best_passed:
            best_genome = local_genome
            best_passed = local_passed

    return ArmResult("restart_hillclimb_v3", best_genome, best_passed / total, tuple())


def immigrant_hillclimb_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    if budget <= 0:
        raise ValueError("budget must be positive")
    state = seed & 0xFFFF
    best_genome = STATIC_BASELINE
    best_passed = -1
    total = len(conditions_for("train")) * frames

    for gen in range(budget):
        if gen == 0 or (gen % 64) == 0:
            state, genome = random_genome(state)
        else:
            state, genome = mutate_genome(state, best_genome)
        train = score_set("train", genome, frames)
        passed = sum(score.passed for score in train.conditions)
        if gen == 0 or passed >= best_passed:
            best_genome = genome
            best_passed = passed

    return ArmResult("immigrant_hillclimb_v3", best_genome, best_passed / total, tuple())


def beam4_ga_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    if budget <= 0:
        raise ValueError("budget must be positive")
    state = seed & 0xFFFF
    pop: list[SamplerGenomeV2] = []
    scores: list[int] = []
    best_genome = STATIC_BASELINE
    best_passed = -1
    total = len(conditions_for("train")) * frames

    for _gen in range(budget):
        if len(pop) < 4:
            state, genome = random_genome(state)
        else:
            state, parent_rnd = _rand16(state)
            state, genome = mutate_genome(state, pop[parent_rnd % 4])
        train = score_set("train", genome, frames)
        passed = sum(score.passed for score in train.conditions)

        if len(pop) < 4:
            pop.append(genome)
            scores.append(passed)
        else:
            worst = min(range(4), key=lambda idx: scores[idx])
            if passed >= scores[worst]:
                pop[worst] = genome
                scores[worst] = passed

        if passed >= best_passed:
            best_genome = genome
            best_passed = passed

    return ArmResult("beam4_ga_v3", best_genome, best_passed / total, tuple())


def variant_arm_train_only(variant: str, budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    if variant == "current_hillclimb":
        result = ga_arm_train_only(budget, seed, frames)
        return ArmResult(variant, result.best_genome, result.best_fitness_train, result.generations)
    if variant == "restart_hillclimb_v3":
        return restart_hillclimb_arm_train_only(budget, seed, frames)
    if variant == "immigrant_hillclimb_v3":
        return immigrant_hillclimb_arm_train_only(budget, seed, frames)
    if variant == "beam4_ga_v3":
        return beam4_ga_arm_train_only(budget, seed, frames)
    if variant == "random":
        result = random_arm_train_only(budget, seed, frames)
        return ArmResult(variant, result.best_genome, result.best_fitness_train, result.generations)
    raise ValueError(f"unknown v2 search variant: {variant}")


def same_boot_ab_search(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ABResult:
    return ABResult(
        seed=seed,
        budget=budget,
        frames=frames,
        ga=ga_arm_train_only(budget, seed ^ 0x4A4A, frames),
        random=random_arm_train_only(budget, seed ^ 0xBEEF, frames),
    )


def condition_set_hash() -> str:
    return sha256(json.dumps([condition.__dict__ for condition in CONDITIONS], sort_keys=True).encode()).hexdigest()


def benchmark_manifest() -> dict[str, object]:
    return {
        "benchmark_id": BENCHMARK_ID,
        "schema_version": SCHEMA_VERSION,
        "genome_id": GENOME_ID,
        "genome_bits": GENOME_BITS,
        "default_frames": DEFAULT_FRAMES,
        "conditions": [condition.__dict__ for condition in CONDITIONS],
        "arms": ["ga", "random"],
        "holdout_firewall": "holdout evaluated after each arm champion is locked",
    }


def benchmark_manifest_hash() -> str:
    return sha256(json.dumps(benchmark_manifest(), sort_keys=True).encode()).hexdigest()


def build_run_log_fixture(result: ABResult) -> dict[str, object]:
    ga_train = score_set("train", result.ga.best_genome, result.frames)
    ga_holdout = score_set("holdout", result.ga.best_genome, result.frames)
    random_train = score_set("train", result.random.best_genome, result.frames)
    random_holdout = score_set("holdout", result.random.best_genome, result.frames)
    return {
        "schema": "run_log",
        "schema_version": "1.0.0",
        "header": {
            "run_id": "host_headroom_fixture",
            "board_id": "host",
            "benchmark_id": BENCHMARK_ID,
            "benchmark_version": SCHEMA_VERSION,
            "benchmark_manifest_hash": benchmark_manifest_hash(),
            "condition_set_hash": condition_set_hash(),
            "search_seed": f"0x{result.seed:08X}",
            "seed_source": "pc_supplied(test-mode)",
            "schema_versions": {
                "genome_contract": SCHEMA_VERSION,
                "phenotype_manifest": "1.0.0",
                "benchmark_package": SCHEMA_VERSION,
                "run_log": "1.0.0",
            },
            "ab_arms": {
                "ga": {"seed_rule": "search_seed ^ 0x4A4A", "selection": "train_only_mutation"},
                "random": {"seed_rule": "search_seed ^ 0xBEEF", "selection": "best_train_random"},
            },
        },
        "generations": [
            *result.ga.generations,
            *result.random.generations,
        ],
        "events": [],
        "final_evaluation": {
            "locked_gen": result.budget - 1,
            "ga": {
                "champion_genome_hash": genome_hash(result.ga.best_genome),
                "train_fitness": round(ga_train.fitness, 6),
                "holdout_fitness": round(ga_holdout.fitness, 6),
            },
            "random_equal_budget": {
                "champion_genome_hash": genome_hash(result.random.best_genome),
                "train_fitness": round(random_train.fitness, 6),
                "holdout_fitness": round(random_holdout.fitness, 6),
            },
            "beats_random_holdout": ga_holdout.fitness > random_holdout.fitness,
            "noise_band": 0.0,
        },
    }
