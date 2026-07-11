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
    _payload,
    _vote_bit,
    crc8,
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
V4_INIT_POOL = 160
V4_INIT_ELITES = 16
V4_PBIL_BATCH = 32
V4_PBIL_ELITES = 4
V4_PBIL_Q15 = 32768
V4_PBIL_MIN_Q15 = 2048
V4_PBIL_MAX_Q15 = 30720
V4_PBIL_HALF_Q15 = V4_PBIL_Q15 // 2
V4_PBIL_LEARNING_SHIFT = 3
V4_PBIL_MUTATION_SHIFT = 6
V5_PBIL_BATCH = 64
V5_PBIL_SAMPLE_COUNT = 60
V5_PBIL_REFINEMENTS = 4
V5_PBIL_ELITES = 8
V5_PBIL_MIN_Q15 = 4096
V5_PBIL_MAX_Q15 = 28672
V5_PBIL_LEARNING_SHIFT = 4
V5_PBIL_MUTATION_SHIFT = 5
V5_PBIL_RESTART_CHECKPOINT = 2048
V6_ISLAND_SEED_SALT = 0x3000
V6_ISLAND_SEED_STEP = 0x1F3D
V7_DEEP_SELECTION_FRAMES = 256
V7_MARGIN_PASSED = 8


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


def train_passed(genome: SamplerGenomeV2, frames: int = DEFAULT_FRAMES) -> int:
    return sum(score.passed for score in score_set("train", genome, frames).conditions)


def frame_bit_matches(condition: Condition, genome: SamplerGenomeV2, frame_idx: int) -> int:
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


def graded_score_condition(condition: Condition, genome: SamplerGenomeV2, frames: int = DEFAULT_FRAMES) -> int:
    return sum(frame_bit_matches(condition, genome, frame_idx) for frame_idx in range(frames))


def graded_score_split(split: str, genome: SamplerGenomeV2, frames: int = DEFAULT_FRAMES) -> int:
    return sum(graded_score_condition(condition, genome, frames) for condition in conditions_for(split))


def graded_score_split_total(split: str, frames: int = DEFAULT_FRAMES) -> int:
    return sum((condition.packet_len + 1) * 8 * frames for condition in conditions_for(split))


def graded_train_score(genome: SamplerGenomeV2, frames: int = DEFAULT_FRAMES) -> int:
    return graded_score_split("train", genome, frames)


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


def _sorted_scored(scored: list[tuple[int, int, SamplerGenomeV2]]) -> list[tuple[int, int, SamplerGenomeV2]]:
    return sorted(scored, key=lambda item: (-item[0], item[1]))


def _v4_initial_pool(
    state: int,
    budget: int,
    frames: int,
    score_fn=train_passed,
) -> tuple[int, int, SamplerGenomeV2, int, list[tuple[int, int, SamplerGenomeV2]]]:
    pool_count = min(V4_INIT_POOL, budget)
    scored: list[tuple[int, int, SamplerGenomeV2]] = []
    best_genome = STATIC_BASELINE
    best_passed = -1
    for order in range(pool_count):
        state, genome = random_genome(state)
        passed = score_fn(genome, frames)
        scored.append((passed, order, genome))
        if passed > best_passed:
            best_genome = genome
            best_passed = passed
    return state, pool_count, best_genome, best_passed, _sorted_scored(scored)


def bitflip1_topdecile_v4_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    if budget <= 0:
        raise ValueError("budget must be positive")
    state = seed & 0xFFFF
    total = len(conditions_for("train")) * frames
    state, used, best_genome, best_passed, _scored = _v4_initial_pool(state, budget, frames)

    for _gen in range(used, budget):
        state, candidate = landscape_child("bitflip_1", state, best_genome)
        passed = train_passed(candidate, frames)
        if passed >= best_passed:
            best_genome = candidate
            best_passed = passed

    return ArmResult("bitflip1_topdecile_v4", best_genome, best_passed / total, tuple())


def _q15_step_toward(value: int, target: int, shift: int) -> int:
    if target >= value:
        return value + ((target - value) >> shift)
    return value - ((value - target) >> shift)


def _clamp_q15(value: int, min_q15: int = V4_PBIL_MIN_Q15, max_q15: int = V4_PBIL_MAX_Q15) -> int:
    return max(min_q15, min(max_q15, value))


def _pbil_probabilities_from_elites(
    scored: list[tuple[int, int, SamplerGenomeV2]],
    elite_count: int = V4_INIT_ELITES,
    min_q15: int = V4_PBIL_MIN_Q15,
    max_q15: int = V4_PBIL_MAX_Q15,
) -> list[int]:
    elites = scored[:min(V4_INIT_ELITES, len(scored))]
    if not elites:
        return [V4_PBIL_HALF_Q15] * GENOME_BITS
    probs: list[int] = []
    elites = scored[:min(elite_count, len(scored))]
    for bit in range(GENOME_BITS):
        ones = sum(1 for _passed, _order, genome in elites if encode_genome(genome) & (1 << bit))
        probs.append(_clamp_q15((ones * V4_PBIL_Q15 + (len(elites) // 2)) // len(elites), min_q15, max_q15))
    return probs


def _pbil_sample(state: int, probabilities: list[int]) -> tuple[int, SamplerGenomeV2]:
    raw = 0
    for bit, probability in enumerate(probabilities):
        state, rnd = _rand16(state)
        if (rnd & 0x7FFF) < probability:
            raw |= 1 << bit
    return state, decode_genome(raw)


def _pbil_update(
    probabilities: list[int],
    batch: list[tuple[int, int, SamplerGenomeV2]],
    elite_count: int = V4_PBIL_ELITES,
    learning_shift: int = V4_PBIL_LEARNING_SHIFT,
    mutation_shift: int = V4_PBIL_MUTATION_SHIFT,
    min_q15: int = V4_PBIL_MIN_Q15,
    max_q15: int = V4_PBIL_MAX_Q15,
) -> list[int]:
    elites = _sorted_scored(batch)[:min(elite_count, len(batch))]
    if not elites:
        return probabilities
    updated: list[int] = []
    for bit, probability in enumerate(probabilities):
        ones = sum(1 for _passed, _order, genome in elites if encode_genome(genome) & (1 << bit))
        target = (ones * V4_PBIL_Q15 + (len(elites) // 2)) // len(elites)
        value = _q15_step_toward(probability, target, learning_shift)
        value = _q15_step_toward(value, V4_PBIL_HALF_Q15, mutation_shift)
        updated.append(_clamp_q15(value, min_q15, max_q15))
    return updated


def _pbil_arm_train_only(
    arm: str,
    budget: int,
    seed: int,
    frames: int,
    batch_size: int,
    sample_count: int,
    refinement_count: int,
    elite_count: int,
    learning_shift: int,
    mutation_shift: int,
    min_q15: int,
    max_q15: int,
    restart_checkpoint: int = 0,
    score_fn=train_passed,
    score_total_fn=lambda frames: len(conditions_for("train")) * frames,
) -> ArmResult:
    if budget <= 0:
        raise ValueError("budget must be positive")
    state = seed & 0xFFFF
    total = score_total_fn(frames)
    state, used, best_genome, best_passed, scored = _v4_initial_pool(state, budget, frames, score_fn)
    probabilities = _pbil_probabilities_from_elites(scored, V4_INIT_ELITES, min_q15, max_q15)
    order = used
    checkpoint_best = best_passed
    since_checkpoint = 0

    while used < budget:
        batch_count = min(batch_size, budget - used)
        pbil_count = min(sample_count, batch_count)
        batch: list[tuple[int, int, SamplerGenomeV2]] = []
        for _idx in range(pbil_count):
            state, genome = _pbil_sample(state, probabilities)
            passed = score_fn(genome, frames)
            batch.append((passed, order, genome))
            if passed > best_passed:
                best_genome = genome
                best_passed = passed
            order += 1
            used += 1
            since_checkpoint += 1
        probabilities = _pbil_update(batch=batch, probabilities=probabilities, elite_count=elite_count,
                                     learning_shift=learning_shift, mutation_shift=mutation_shift,
                                     min_q15=min_q15, max_q15=max_q15)

        refinements = min(refinement_count, budget - used)
        for _idx in range(refinements):
            state, genome = landscape_child("bitflip_1", state, best_genome)
            passed = score_fn(genome, frames)
            if passed >= best_passed:
                best_genome = genome
                best_passed = passed
            order += 1
            used += 1
            since_checkpoint += 1

        if restart_checkpoint > 0 and since_checkpoint >= restart_checkpoint:
            if best_passed <= checkpoint_best:
                probabilities = [V4_PBIL_HALF_Q15] * GENOME_BITS
            checkpoint_best = best_passed
            since_checkpoint = 0

    return ArmResult(arm, best_genome, best_passed / total, tuple())


def pbil_eda_v4_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    return _pbil_arm_train_only(
        "pbil_eda_v4",
        budget,
        seed,
        frames,
        V4_PBIL_BATCH,
        V4_PBIL_BATCH,
        0,
        V4_PBIL_ELITES,
        V4_PBIL_LEARNING_SHIFT,
        V4_PBIL_MUTATION_SHIFT,
        V4_PBIL_MIN_Q15,
        V4_PBIL_MAX_Q15,
    )


def pbil_graded_v8_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    return _pbil_arm_train_only(
        "pbil_graded_v8",
        budget,
        seed,
        frames,
        V4_PBIL_BATCH,
        V4_PBIL_BATCH,
        0,
        V4_PBIL_ELITES,
        V4_PBIL_LEARNING_SHIFT,
        V4_PBIL_MUTATION_SHIFT,
        V4_PBIL_MIN_Q15,
        V4_PBIL_MAX_Q15,
        score_fn=graded_train_score,
        score_total_fn=lambda local_frames: graded_score_split_total("train", local_frames),
    )


def pbil_stable_v5_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    return _pbil_arm_train_only(
        "pbil_stable_v5",
        budget,
        seed,
        frames,
        V5_PBIL_BATCH,
        V5_PBIL_BATCH,
        0,
        V5_PBIL_ELITES,
        V5_PBIL_LEARNING_SHIFT,
        V5_PBIL_MUTATION_SHIFT,
        V5_PBIL_MIN_Q15,
        V5_PBIL_MAX_Q15,
    )


def pbil_restart_v5_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    return _pbil_arm_train_only(
        "pbil_restart_v5",
        budget,
        seed,
        frames,
        V5_PBIL_BATCH,
        V5_PBIL_BATCH,
        0,
        V5_PBIL_ELITES,
        V5_PBIL_LEARNING_SHIFT,
        V5_PBIL_MUTATION_SHIFT,
        V5_PBIL_MIN_Q15,
        V5_PBIL_MAX_Q15,
        V5_PBIL_RESTART_CHECKPOINT,
    )


def pbil_hybrid_v5_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    return _pbil_arm_train_only(
        "pbil_hybrid_v5",
        budget,
        seed,
        frames,
        V5_PBIL_BATCH,
        V5_PBIL_SAMPLE_COUNT,
        V5_PBIL_REFINEMENTS,
        V5_PBIL_ELITES,
        V5_PBIL_LEARNING_SHIFT,
        V5_PBIL_MUTATION_SHIFT,
        V5_PBIL_MIN_Q15,
        V5_PBIL_MAX_Q15,
    )


def _island_seed(seed: int, island: int) -> int:
    derived = (seed ^ V6_ISLAND_SEED_SALT ^ (island * V6_ISLAND_SEED_STEP)) & 0xFFFF
    return derived if derived else 0xACE1


def pbil_island_v6_arm_train_only(
    arm: str,
    islands: int,
    budget: int,
    seed: int,
    frames: int = DEFAULT_FRAMES,
    island_fn=pbil_eda_v4_arm_train_only,
) -> ArmResult:
    if budget <= 0:
        raise ValueError("budget must be positive")
    if islands <= 0:
        raise ValueError("islands must be positive")

    best_genome = STATIC_BASELINE
    best_fitness = -1.0
    for island in range(islands):
        island_budget = budget // islands + (1 if island < (budget % islands) else 0)
        if island_budget <= 0:
            continue
        result = island_fn(island_budget, _island_seed(seed, island), frames)
        if result.best_fitness_train > best_fitness:
            best_genome = result.best_genome
            best_fitness = result.best_fitness_train

    return ArmResult(arm, best_genome, best_fitness, tuple())


def _pbil_island_results(
    islands: int,
    budget: int,
    seed: int,
    frames: int,
    island_fn=pbil_eda_v4_arm_train_only,
) -> list[tuple[int, ArmResult]]:
    results: list[tuple[int, ArmResult]] = []
    for island in range(islands):
        island_budget = budget // islands + (1 if island < (budget % islands) else 0)
        if island_budget <= 0:
            continue
        results.append((island, island_fn(island_budget, _island_seed(seed, island), frames)))
    return results


def pbil_island4_deep_v7_arm_train_only(
    budget: int,
    seed: int,
    frames: int = DEFAULT_FRAMES,
    deep_frames: int = V7_DEEP_SELECTION_FRAMES,
) -> ArmResult:
    if budget <= 0:
        raise ValueError("budget must be positive")
    results = _pbil_island_results(4, budget, seed, frames)
    best_genome = STATIC_BASELINE
    best_deep = -1
    total = len(conditions_for("train")) * deep_frames
    for island, result in results:
        deep_passed = train_passed(result.best_genome, deep_frames)
        if deep_passed > best_deep:
            best_genome = result.best_genome
            best_deep = deep_passed
    return ArmResult("pbil_island4_deep_v7", best_genome, best_deep / total, tuple())


def pbil_island4_margin_v7_arm_train_only(
    budget: int,
    seed: int,
    frames: int = DEFAULT_FRAMES,
    deep_frames: int = V7_DEEP_SELECTION_FRAMES,
) -> ArmResult:
    if budget <= 0:
        raise ValueError("budget must be positive")
    results = _pbil_island_results(4, budget, seed, frames)
    if not results:
        return ArmResult("pbil_island4_margin_v7", STATIC_BASELINE, 0.0, tuple())

    incumbent_island, incumbent = max(results, key=lambda item: (item[1].best_fitness_train, -item[0]))
    best_genome = incumbent.best_genome
    incumbent_deep = train_passed(best_genome, deep_frames)
    best_deep = incumbent_deep
    total = len(conditions_for("train")) * deep_frames

    for island, result in results:
        if island == incumbent_island:
            continue
        deep_passed = train_passed(result.best_genome, deep_frames)
        if deep_passed >= incumbent_deep + V7_MARGIN_PASSED and (
            deep_passed > best_deep or (deep_passed == best_deep and island < incumbent_island)
        ):
            best_genome = result.best_genome
            best_deep = deep_passed
            incumbent_island = island

    return ArmResult("pbil_island4_margin_v7", best_genome, best_deep / total, tuple())


def pbil_island2_v6_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    return pbil_island_v6_arm_train_only("pbil_island2_v6", 2, budget, seed, frames)


def pbil_island3_v6_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    return pbil_island_v6_arm_train_only("pbil_island3_v6", 3, budget, seed, frames)


def pbil_island4_v6_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    return pbil_island_v6_arm_train_only("pbil_island4_v6", 4, budget, seed, frames)


def pbil_island4_graded_v8_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    return pbil_island_v6_arm_train_only(
        "pbil_island4_graded_v8",
        4,
        budget,
        seed,
        frames,
        island_fn=pbil_graded_v8_arm_train_only,
    )


def pbil_island6_graded_v9_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    return pbil_island_v6_arm_train_only(
        "pbil_island6_graded_v9",
        6,
        budget,
        seed,
        frames,
        island_fn=pbil_graded_v8_arm_train_only,
    )


def pbil_island8_graded_v9_arm_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> ArmResult:
    return pbil_island_v6_arm_train_only(
        "pbil_island8_graded_v9",
        8,
        budget,
        seed,
        frames,
        island_fn=pbil_graded_v8_arm_train_only,
    )


def pbil_island4_deep_graded_v8_arm_train_only(
    budget: int,
    seed: int,
    frames: int = DEFAULT_FRAMES,
    deep_frames: int = V7_DEEP_SELECTION_FRAMES,
) -> ArmResult:
    if budget <= 0:
        raise ValueError("budget must be positive")
    results = _pbil_island_results(4, budget, seed, frames, island_fn=pbil_graded_v8_arm_train_only)
    best_genome = STATIC_BASELINE
    best_deep = -1
    total = graded_score_split_total("train", deep_frames)
    for island, result in results:
        deep_score = graded_train_score(result.best_genome, deep_frames)
        if deep_score > best_deep:
            best_genome = result.best_genome
            best_deep = deep_score
    return ArmResult("pbil_island4_deep_graded_v8", best_genome, best_deep / total, tuple())


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
    if variant == "bitflip1_topdecile_v4":
        return bitflip1_topdecile_v4_arm_train_only(budget, seed, frames)
    if variant == "pbil_eda_v4":
        return pbil_eda_v4_arm_train_only(budget, seed, frames)
    if variant == "pbil_stable_v5":
        return pbil_stable_v5_arm_train_only(budget, seed, frames)
    if variant == "pbil_restart_v5":
        return pbil_restart_v5_arm_train_only(budget, seed, frames)
    if variant == "pbil_hybrid_v5":
        return pbil_hybrid_v5_arm_train_only(budget, seed, frames)
    if variant == "pbil_island2_v6":
        return pbil_island2_v6_arm_train_only(budget, seed, frames)
    if variant == "pbil_island3_v6":
        return pbil_island3_v6_arm_train_only(budget, seed, frames)
    if variant == "pbil_island4_v6":
        return pbil_island4_v6_arm_train_only(budget, seed, frames)
    if variant == "pbil_island4_deep_v7":
        return pbil_island4_deep_v7_arm_train_only(budget, seed, frames)
    if variant == "pbil_island4_margin_v7":
        return pbil_island4_margin_v7_arm_train_only(budget, seed, frames)
    if variant == "pbil_graded_v8":
        return pbil_graded_v8_arm_train_only(budget, seed, frames)
    if variant == "pbil_island4_graded_v8":
        return pbil_island4_graded_v8_arm_train_only(budget, seed, frames)
    if variant == "pbil_island6_graded_v9":
        return pbil_island6_graded_v9_arm_train_only(budget, seed, frames)
    if variant == "pbil_island8_graded_v9":
        return pbil_island8_graded_v9_arm_train_only(budget, seed, frames)
    if variant == "pbil_island4_deep_graded_v8":
        return pbil_island4_deep_graded_v8_arm_train_only(budget, seed, frames)
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
