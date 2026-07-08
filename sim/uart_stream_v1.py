"""Deterministic host oracle for the M1 `uart_stream_v1` benchmark.

The model is intentionally small enough to mirror in portable C and RTL test
fixtures. It is not a silicon-performance claim; it pins benchmark semantics,
stimulus splits, search bookkeeping, and the holdout firewall before board work.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Iterable


SCHEMA_VERSION = "1.0.0"
BENCHMARK_ID = "uart_stream_v1"
DEFAULT_FRAMES = 32
CHAMPION_STORE_MAGIC = 0x43484D50
CHAMPION_STORE_VERSION = 0x00010000
CHAMPION_STORE_SALT = 0x9E3779B9
SUMMARY_PAGE_ID = 1
LEGACY_MAILBOX_WORD_COUNT = 15


@dataclass(frozen=True)
class Condition:
    name: str
    split: str
    baud_ppm: int
    jitter_frac: float
    flip_prob: float
    edge_unc: str
    packet_len: int
    lfsr_seed: int
    gap_jitter: float = 0.0


@dataclass(frozen=True)
class SamplerConfig:
    sample_phase: int
    threshold: int
    majority_window: int

    def __post_init__(self) -> None:
        if not 0 <= self.sample_phase <= 31:
            raise ValueError("sample_phase must be in [0, 31]")
        if not -128 <= self.threshold <= 127:
            raise ValueError("threshold must be in [-128, 127]")
        if self.majority_window not in (1, 3, 5):
            raise ValueError("majority_window must be 1, 3, or 5")


@dataclass(frozen=True)
class ConditionScore:
    condition: str
    split: str
    passed: int
    frames: int

    @property
    def fitness(self) -> float:
        return self.passed / self.frames if self.frames else 0.0


@dataclass(frozen=True)
class SetScore:
    split: str
    conditions: tuple[ConditionScore, ...]

    @property
    def fitness(self) -> float:
        if not self.conditions:
            return 0.0
        return sum(score.fitness for score in self.conditions) / len(self.conditions)


@dataclass(frozen=True)
class SearchResult:
    best_config: SamplerConfig
    best_fitness_train: float
    generations: tuple[dict[str, int | float | str], ...]


CONDITIONS: tuple[Condition, ...] = (
    Condition("T0", "train", 0, 0.05, 0.005, "low", 16, 0x1111),
    Condition("T1", "train", +200, 0.08, 0.010, "low", 16, 0x2222),
    Condition("T2", "train", -200, 0.08, 0.010, "med", 32, 0x3333),
    Condition("T3", "train", +500, 0.12, 0.020, "med", 32, 0x4444),
    Condition("H0", "holdout", +100, 0.06, 0.008, "low", 24, 0xA001),
    Condition("H1", "holdout", -350, 0.10, 0.015, "med", 48, 0xB002),
    Condition("H2", "holdout", +650, 0.14, 0.022, "high", 12, 0xC003),
    Condition("H3", "holdout", -500, 0.09, 0.012, "med", 64, 0xD004),
    Condition("A0", "adversarial", 0, 0.05, 0.100, "med", 24, 0xA0A0),
    Condition("A1", "adversarial", 0, 0.30, 0.010, "high", 24, 0xA1A1),
    Condition("A2", "adversarial", 0, 0.05, 0.005, "low", 24, 0xA2A2),
    Condition("A3", "adversarial", +250, 0.08, 0.010, "med", 24, 0xA3A3),
)


EDGE_UNC_SCORE = {"low": 2, "med": 5, "high": 8}
MAJORITY_OPTIONS = (1, 3, 5)
STATIC_BASELINE = SamplerConfig(sample_phase=16, threshold=0, majority_window=1)


def round_nearest_away_from_zero(value: float) -> int:
    """Match the C twin's `round_div`: nearest integer, half away from zero."""
    if value >= 0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


def lfsr16_step(state: int) -> int:
    """Xorshift-like 16-bit LFSR used by the Python, C, and RTL smoke paths."""
    state &= 0xFFFF
    if state == 0:
        state = 0xACE1
    bit = ((state >> 0) ^ (state >> 2) ^ (state >> 3) ^ (state >> 5)) & 1
    return ((state >> 1) | (bit << 15)) & 0xFFFF


def crc8(data: Iterable[int]) -> int:
    crc = 0
    for value in data:
        crc ^= value & 0xFF
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def _rand16(state: int) -> tuple[int, int]:
    state = lfsr16_step(state)
    return state, state


def _rand_byte(state: int) -> tuple[int, int]:
    state, hi = _rand16(state)
    state, lo = _rand16(state)
    return state, ((hi >> 8) ^ lo) & 0xFF


def _payload(condition: Condition, frame_idx: int) -> list[int]:
    state = (condition.lfsr_seed ^ ((frame_idx + 1) * 0x1F3D)) & 0xFFFF
    payload: list[int] = []
    for byte_idx in range(condition.packet_len):
        state, value = _rand_byte(state)
        if condition.name == "A2":
            value = 0x00 if frame_idx % 2 == 0 else 0xFF
        elif condition.name == "A3":
            value = (byte_idx + frame_idx) & 0x03
        payload.append(value)
    return payload


def _ideal_phase(condition: Condition) -> int:
    # Keep the shift small and deterministic: +/-650 ppm moves only a few Q5 taps.
    return max(0, min(31, 16 + round_nearest_away_from_zero(condition.baud_ppm / 250)))


def _vote_bit(bit: int, condition: Condition, config: SamplerConfig, state: int) -> tuple[int, int]:
    ideal_phase = _ideal_phase(condition)
    phase_error = abs(config.sample_phase - ideal_phase)
    edge_penalty = EDGE_UNC_SCORE[condition.edge_unc]
    jitter_penalty = round_nearest_away_from_zero(condition.jitter_frac * 24)
    signal = max(6, 34 - (phase_error * 3) - edge_penalty - jitter_penalty)
    threshold_bias = round_nearest_away_from_zero(config.threshold / 8)
    noise_span = 4 + edge_penalty + round_nearest_away_from_zero(condition.jitter_frac * 32)

    ones = 0
    for _ in range(config.majority_window):
        state, rnd = _rand16(state)
        noise = (rnd % (2 * noise_span + 1)) - noise_span
        signed = signal if bit else -signal
        decoded = 1 if (signed + noise - threshold_bias) >= 0 else 0
        state, flip_rnd = _rand16(state)
        if flip_rnd < round_nearest_away_from_zero(condition.flip_prob * 65535):
            decoded ^= 1
        ones += decoded

    return state, 1 if ones > (config.majority_window // 2) else 0


def frame_passes(condition: Condition, config: SamplerConfig, frame_idx: int) -> bool:
    payload = _payload(condition, frame_idx)
    sent = payload + [crc8(payload)]
    decoded_bytes: list[int] = []
    state = (condition.lfsr_seed ^ 0xC0DE ^ (frame_idx * 0x1021)) & 0xFFFF

    for byte in sent:
        decoded = 0
        for bit_idx in range(8):
            state, bit = _vote_bit((byte >> bit_idx) & 1, condition, config, state)
            decoded |= bit << bit_idx
        decoded_bytes.append(decoded)

    decoded_payload = decoded_bytes[:-1]
    decoded_crc = decoded_bytes[-1]
    return crc8(decoded_payload) == decoded_crc


def score_condition(condition: Condition, config: SamplerConfig, frames: int = DEFAULT_FRAMES) -> ConditionScore:
    passed = sum(1 for frame_idx in range(frames) if frame_passes(condition, config, frame_idx))
    return ConditionScore(condition.name, condition.split, passed, frames)


def conditions_for(split: str) -> tuple[Condition, ...]:
    selected = tuple(condition for condition in CONDITIONS if condition.split == split)
    if not selected:
        raise ValueError(f"unknown split: {split}")
    return selected


def score_set(split: str, config: SamplerConfig, frames: int = DEFAULT_FRAMES) -> SetScore:
    return SetScore(split, tuple(score_condition(condition, config, frames) for condition in conditions_for(split)))


def random_config(state: int) -> tuple[int, SamplerConfig]:
    state, phase = _rand16(state)
    state, threshold = _rand16(state)
    state, majority = _rand16(state)
    return state, SamplerConfig(
        sample_phase=phase % 32,
        threshold=(threshold % 256) - 128,
        majority_window=MAJORITY_OPTIONS[majority % len(MAJORITY_OPTIONS)],
    )


def random_search_train_only(budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> SearchResult:
    if budget <= 0:
        raise ValueError("budget must be positive")
    state = seed & 0xFFFF
    best_config = STATIC_BASELINE
    best_fitness = -1.0
    generations: list[dict[str, int | float | str]] = []

    for gen in range(budget):
        state, config = random_config(state)
        train_score = score_set("train", config, frames)
        if train_score.fitness > best_fitness:
            best_fitness = train_score.fitness
            best_config = config
        generations.append(
            {
                "gen": gen,
                "best_fitness_train": round(best_fitness, 6),
                "evals": (gen + 1) * len(conditions_for("train")) * frames,
                "phenotype_hash": config_hash(best_config),
            }
        )

    return SearchResult(best_config, best_fitness, tuple(generations))


def random_baseline_best(split: str, budget: int, seed: int, frames: int = DEFAULT_FRAMES) -> float:
    """Post-search random baseline for reporting, never for candidate selection."""
    if budget <= 0:
        raise ValueError("budget must be positive")
    state = seed & 0xFFFF
    best = 0.0
    for _ in range(budget):
        state, config = random_config(state)
        best = max(best, score_set(split, config, frames).fitness)
    return best


def config_hash(config: SamplerConfig) -> str:
    payload = f"{config.sample_phase},{config.threshold},{config.majority_window}".encode()
    return sha256(payload).hexdigest()


def pack_config_payload(config: SamplerConfig) -> int:
    return ((config.sample_phase & 0x1F) << 16) | ((config.majority_window & 0x7) << 8) | (config.threshold & 0xFF)


def champion_store_checksum(magic: int, meta: int, config: int, budget: int) -> int:
    return (magic ^ meta ^ config ^ budget ^ CHAMPION_STORE_SALT) & 0xFFFFFFFF


def champion_store_words(config: SamplerConfig, write_counter: int = 1, write_budget: int = 1000) -> tuple[int, ...]:
    magic = CHAMPION_STORE_MAGIC
    meta = CHAMPION_STORE_VERSION | (write_counter & 0x0FFF)
    config_word = pack_config_payload(config)
    budget_word = write_budget & 0x0FFF
    return (
        magic,
        meta,
        config_word,
        budget_word,
        champion_store_checksum(magic, meta, config_word, budget_word),
    )


def mailbox_page_checksum(page_id: int, payloads: tuple[int, ...]) -> int:
    acc = (0xA50000 ^ ((page_id & 0xFF) << 8) ^ (len(payloads) & 0xFF)) & 0xFFFFFF
    for idx, payload in enumerate(payloads):
        acc ^= (payload & 0xFFFFFF) ^ (((idx + 1) * 0x1021) & 0xFFFFFF)
    return acc & 0xFFFFFF


def summary_mailbox_page(
    evals_per_sec_payload: int = 0x006400,
    restore_status_payload: int = 0x000001,
) -> tuple[str, ...]:
    payloads = (
        (0x01 << 16) | LEGACY_MAILBOX_WORD_COUNT,
        evals_per_sec_payload & 0xFFFFFF,
        0x011020,
        restore_status_payload & 0xFFFFFF,
        0x010101,
        0x010101,
    )
    words = [0xC0000000 | ((SUMMARY_PAGE_ID & 0xFF) << 16) | len(payloads)]
    words.extend(0xC1000000 | payload for payload in payloads)
    words.append(0xC2000000 | mailbox_page_checksum(SUMMARY_PAGE_ID, payloads))
    return tuple(f"0x{word:08X}" for word in words)


def condition_set_hash() -> str:
    return sha256(
        json.dumps([condition.__dict__ for condition in CONDITIONS], sort_keys=True).encode()
    ).hexdigest()


def benchmark_manifest() -> dict[str, object]:
    return {
        "benchmark_id": BENCHMARK_ID,
        "schema_version": SCHEMA_VERSION,
        "default_frames": DEFAULT_FRAMES,
        "conditions": [condition.__dict__ for condition in CONDITIONS],
    }


def benchmark_manifest_hash() -> str:
    return sha256(json.dumps(benchmark_manifest(), sort_keys=True).encode()).hexdigest()


def _sha256_json(payload: dict[str, object]) -> str:
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def build_run_log_fixture(search: SearchResult, frames: int = DEFAULT_FRAMES) -> dict[str, object]:
    train = score_set("train", search.best_config, frames)
    holdout = score_set("holdout", search.best_config, frames)
    adversarial = score_set("adversarial", search.best_config, frames)
    static_holdout = score_set("holdout", STATIC_BASELINE, frames)
    random_holdout = random_baseline_best("holdout", len(search.generations), seed=0xBEEF, frames=frames)
    phenotype_hash = config_hash(search.best_config)
    generations = []
    for generation in search.generations:
        record = dict(generation)
        record.update(
            {
                "best_genome_hash": record["phenotype_hash"],
                "mailbox_words": ["0xF4F00028"],
                "frame_diff_hash": record["phenotype_hash"],
                "write_counter": 0,
                "evals_per_sec": 0,
            }
        )
        generations.append(record)

    return {
        "schema": "run_log",
        "schema_version": SCHEMA_VERSION,
        "header": {
            "run_id": "host_m1_fixture",
            "board_id": "host",
            "fclk0_mhz": 50,
            "temperature_c": None,
            "manifest_id": "uart_sampler_island_v1",
            "benchmark_id": BENCHMARK_ID,
            "benchmark_version": SCHEMA_VERSION,
            "benchmark_manifest_hash": benchmark_manifest_hash(),
            "condition_set_hash": condition_set_hash(),
            "whitelist_id": "whitelist_uart_sampler_v1",
            "blacklist_id": "bl_uart_sampler_v1",
            "local_map_id": None,
            "write_budget_ref": "write_budget_uart_sampler_v1",
            "search_seed": "0x0000C0DE",
            "seed_source": "pc_supplied(test-mode)",
            "persistent_store": {"type": "host_file", "ref": "build/host_m1_fixture.json", "write_budget": 1},
            "schema_versions": {
                "genome_contract": SCHEMA_VERSION,
                "phenotype_manifest": SCHEMA_VERSION,
                "benchmark_package": SCHEMA_VERSION,
                "safety_whitelist": SCHEMA_VERSION,
                "blacklist": SCHEMA_VERSION,
                "write_budget": SCHEMA_VERSION,
                "local_map": None,
            },
        },
        "generations": generations,
        "events": [],
        "final_evaluation": {
            "locked_gen": len(search.generations) - 1,
            "champion_genome_hash": phenotype_hash,
            "champion_phenotype_hash": phenotype_hash,
            "train_fitness": round(train.fitness, 6),
            "holdout_fitness": round(holdout.fitness, 6),
            "adversarial_report_hash": sha256(
                json.dumps([score.__dict__ for score in adversarial.conditions], sort_keys=True).encode()
            ).hexdigest(),
            "random_equal_budget_holdout": round(random_holdout, 6),
            "static_baseline_holdout": round(static_holdout.fitness, 6),
            "noise_band": 0.0,
        },
    }


def build_write_budget_fixture(write_counter: int = 1) -> dict[str, object]:
    return {
        "schema": "write_budget",
        "schema_version": SCHEMA_VERSION,
        "budget_id": "write_budget_uart_sampler_v1",
        "store": "champion_store_uart_sampler_v1_stub",
        "per_run_budget": 1000,
        "counters": {
            "champion_writes": write_counter,
            "checkpoint_writes": 0,
            "final_report_writes": 0,
        },
        "policy": {
            "write_only_on": ["new_champion", "periodic_checkpoint", "final_report", "operator_request"],
            "hot_loop_writes_nv": False,
        },
    }


def build_replay_bundle_fixture(
    run_log: dict[str, object],
    write_budget: dict[str, object],
) -> dict[str, object]:
    champion_hash = str(run_log["final_evaluation"]["champion_phenotype_hash"])  # type: ignore[index]
    return {
        "schema": "replay_bundle",
        "schema_version": SCHEMA_VERSION,
        "bundle_id": "replay_host_m1_fixture_champion",
        "benchmark_id": BENCHMARK_ID,
        "expected_mailbox_words": [
            "0xA7000000",
            "0xA8001008",
            "0xA90F05B7",
            "0xAA013020",
            "0xAB011020",
            "0xAC000200",
            "0xAD00C0DE",
            "0xAE006400",
            "0xAF011020",
            "0xB00013E8",
            "0xB10F05B7",
            "0xB2000001",
            "0xB3000000",
            "0xB4010101",
            "0xB5010101",
            *summary_mailbox_page(),
        ],
        "artifacts": {
            "benchmark_manifest_hash": benchmark_manifest_hash(),
            "condition_set_hash": condition_set_hash(),
            "write_budget_ref": {
                "id": "write_budget_uart_sampler_v1",
                "schema_version": SCHEMA_VERSION,
                "sha256": _sha256_json(write_budget),
            },
            "run_log_ref": {
                "id": run_log["header"]["run_id"],  # type: ignore[index]
                "schema_version": SCHEMA_VERSION,
                "sha256": _sha256_json(run_log),
            },
            "load_run_script": "host/run_m1_smoke.py",
        },
        "determinism": {
            "champion_genome_hash": champion_hash,
            "champion_phenotype_hash": champion_hash,
            "bit_match_required": True,
        },
    }


def score_as_rows(config: SamplerConfig, frames: int = DEFAULT_FRAMES) -> list[tuple[str, str, int, int]]:
    rows = []
    for split in ("train", "holdout", "adversarial"):
        for score in score_set(split, config, frames).conditions:
            rows.append((score.condition, score.split, score.passed, score.frames))
    return rows
