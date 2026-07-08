import subprocess
import unittest
from pathlib import Path

from sim.uart_stream_v1 import (
    DEFAULT_FRAMES,
    STATIC_BASELINE,
    SamplerConfig,
    benchmark_manifest_hash,
    build_run_log_fixture,
    condition_set_hash,
    lfsr16_step,
    random_baseline_best,
    random_search_train_only,
    round_nearest_away_from_zero,
    score_as_rows,
    score_set,
)


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "host" / "uart_stream_cli"
RUNTIME = ROOT / "build" / "host" / "autoehw_runtime_cli"
FIRMWARE = ROOT / "build" / "host" / "autoehw_firmware_cli"
BOARD = ROOT / "build" / "host" / "autoehw_board_host_cli"


class UartStreamV1Test(unittest.TestCase):
    def test_lfsr_sequence_matches_rtl_fixture(self):
        state = 0x1111
        expected = [0x8888, 0xC444, 0xE222, 0xF111, 0xF888]
        for want in expected:
            state = lfsr16_step(state)
            self.assertEqual(state, want)

    def test_rounding_semantics_match_c_twin(self):
        self.assertEqual(round_nearest_away_from_zero(1.5), 2)
        self.assertEqual(round_nearest_away_from_zero(2.5), 3)
        self.assertEqual(round_nearest_away_from_zero(-1.5), -2)
        self.assertEqual(round_nearest_away_from_zero(-2.5), -3)
        self.assertEqual(round_nearest_away_from_zero(-0.5), -1)

    def test_static_baseline_is_deterministic(self):
        train_a = score_set("train", STATIC_BASELINE, DEFAULT_FRAMES)
        train_b = score_set("train", STATIC_BASELINE, DEFAULT_FRAMES)
        self.assertEqual(train_a, train_b)
        self.assertEqual(len(train_a.conditions), 4)

    def test_holdout_is_final_evaluation_only(self):
        search = random_search_train_only(budget=8, seed=0xC0DE, frames=8)
        fixture = build_run_log_fixture(search, frames=8)
        for generation in fixture["generations"]:
            self.assertNotIn("holdout_fitness", generation)
            self.assertIn("best_fitness_train", generation)
        self.assertIn("holdout_fitness", fixture["final_evaluation"])
        self.assertIn("random_equal_budget_holdout", fixture["final_evaluation"])
        self.assertEqual(fixture["header"]["condition_set_hash"], condition_set_hash())
        self.assertEqual(fixture["header"]["benchmark_manifest_hash"], benchmark_manifest_hash())

    def test_random_baseline_is_post_search_deterministic(self):
        first = random_baseline_best("holdout", budget=8, seed=0xBEEF, frames=8)
        second = random_baseline_best("holdout", budget=8, seed=0xBEEF, frames=8)
        self.assertEqual(first, second)

    def test_c_runtime_matches_python_train_only_search(self):
        if not RUNTIME.exists():
            self.skipTest(f"C runtime not built: {RUNTIME}")
        budget = 16
        frames = 8
        seed = 0xC0DE
        search = random_search_train_only(budget=budget, seed=seed, frames=frames)
        train = score_set("train", search.best_config, frames)
        holdout = score_set("holdout", search.best_config, frames)
        proc = subprocess.run(
            [str(RUNTIME), str(budget), hex(seed), str(frames)],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        fields = proc.stdout.strip().split()
        self.assertEqual(fields[0], "best")
        self.assertEqual(
            tuple(map(int, fields[1:4])),
            (search.best_config.sample_phase, search.best_config.threshold, search.best_config.majority_window),
        )
        self.assertEqual(fields[4], "train")
        self.assertEqual(tuple(map(int, fields[5:7])), (sum(s.passed for s in train.conditions), 4 * frames))
        self.assertEqual(fields[7], "holdout")
        self.assertEqual(tuple(map(int, fields[8:10])), (sum(s.passed for s in holdout.conditions), 4 * frames))
        self.assertEqual(fields[10], "evals")
        self.assertEqual(int(fields[11]), budget * 4 * frames)

    def test_firmware_fake_backend_matches_python_train_only_search(self):
        if not FIRMWARE.exists():
            self.skipTest(f"firmware CLI not built: {FIRMWARE}")
        budget = 16
        frames = 8
        seed = 0xC0DE
        search = random_search_train_only(budget=budget, seed=seed, frames=frames)
        train = score_set("train", search.best_config, frames)
        holdout = score_set("holdout", search.best_config, frames)
        proc = subprocess.run(
            [str(FIRMWARE), str(budget), hex(seed), str(frames)],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        fields = proc.stdout.strip().split()
        self.assertEqual(fields[0], "firmware")
        self.assertEqual(fields[1], "best")
        self.assertEqual(
            tuple(map(int, fields[2:5])),
            (search.best_config.sample_phase, search.best_config.threshold, search.best_config.majority_window),
        )
        self.assertEqual(fields[5], "train")
        self.assertEqual(tuple(map(int, fields[6:8])), (sum(s.passed for s in train.conditions), 4 * frames))
        self.assertEqual(fields[8], "holdout")
        self.assertEqual(tuple(map(int, fields[9:11])), (sum(s.passed for s in holdout.conditions), 4 * frames))
        self.assertEqual(fields[11], "evals")
        self.assertEqual(int(fields[12]), budget * 4 * frames)

    def test_board_mailbox_host_stub_matches_oracle(self):
        if not BOARD.exists():
            self.skipTest(f"board host CLI not built: {BOARD}")
        proc = subprocess.run(
            [str(BOARD)],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        words = [int(line, 16) for line in proc.stdout.strip().splitlines()]
        self.assertEqual(
            words,
            [0xA7000000, 0xA8001008, 0xA90F05B7, 0xAA013020, 0xAB011020, 0xAC000200],
        )

    def test_board_smoke2_champion_oracle_counts(self):
        config = SamplerConfig(sample_phase=30, threshold=111, majority_window=5)
        train = score_set("train", config, frames=8)
        holdout = score_set("holdout", config, frames=8)
        self.assertEqual(sum(score.passed for score in train.conditions), 10)
        self.assertEqual(sum(score.frames for score in train.conditions), 32)
        self.assertEqual(sum(score.passed for score in holdout.conditions), 6)
        self.assertEqual(sum(score.frames for score in holdout.conditions), 32)

    def test_c_twin_matches_python_oracle(self):
        if not BUILD.exists():
            self.skipTest(f"C twin not built: {BUILD}")
        configs = [
            STATIC_BASELINE,
            SamplerConfig(sample_phase=18, threshold=-12, majority_window=3),
            SamplerConfig(sample_phase=13, threshold=21, majority_window=5),
        ]
        for config in configs:
            proc = subprocess.run(
                [
                    str(BUILD),
                    str(config.sample_phase),
                    str(config.threshold),
                    str(config.majority_window),
                    str(DEFAULT_FRAMES),
                ],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )
            c_rows = []
            for line in proc.stdout.strip().splitlines():
                name, split, passed, frames = line.split()
                c_rows.append((name, split, int(passed), int(frames)))
            self.assertEqual(c_rows, score_as_rows(config, DEFAULT_FRAMES))


if __name__ == "__main__":
    unittest.main()
