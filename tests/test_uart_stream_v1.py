import subprocess
import unittest
from pathlib import Path

from sim.uart_stream_v1 import (
    DEFAULT_FRAMES,
    STATIC_BASELINE,
    SamplerConfig,
    benchmark_manifest_hash,
    build_replay_bundle_fixture,
    build_run_log_fixture,
    build_write_budget_fixture,
    champion_store_words,
    condition_set_hash,
    lfsr16_step,
    longrun_mailbox_page,
    random_baseline_best,
    random_search_train_only,
    round_nearest_away_from_zero,
    score_as_rows,
    score_set,
    summary_mailbox_page,
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

    def test_replay_and_write_budget_fixtures_are_schema_versioned(self):
        search = random_search_train_only(budget=16, seed=0xC0DE, frames=8)
        run_log = build_run_log_fixture(search, frames=8)
        write_budget = build_write_budget_fixture(write_counter=1)
        replay = build_replay_bundle_fixture(run_log, write_budget)
        self.assertEqual(write_budget["schema"], "write_budget")
        self.assertEqual(write_budget["schema_version"], "1.0.0")
        self.assertEqual(write_budget["counters"]["champion_writes"], 1)
        self.assertFalse(write_budget["policy"]["hot_loop_writes_nv"])
        self.assertEqual(replay["schema"], "replay_bundle")
        self.assertEqual(replay["schema_version"], "1.0.0")
        self.assertEqual(replay["expected_mailbox_words"][:6], [
            "0xA7000000",
            "0xA8001008",
            "0xA90F05B7",
            "0xAA013020",
            "0xAB011020",
            "0xAC000200",
        ])
        self.assertEqual(replay["expected_mailbox_words"][8], "0xAF011020")
        self.assertEqual(replay["expected_mailbox_words"][-16:-8], list(summary_mailbox_page()))
        self.assertEqual(replay["expected_mailbox_words"][-8:], list(longrun_mailbox_page()))
        self.assertIn("sha256", replay["artifacts"]["run_log_ref"])
        self.assertIn("sha256", replay["artifacts"]["write_budget_ref"])

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
        self.assertEqual(fields[13], "random_holdout")
        self.assertEqual(tuple(map(int, fields[14:16])), (17, 32))

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
        self.assertEqual(words[:6], [0xA7000000, 0xA8001008, 0xA90F05B7, 0xAA013020, 0xAB011020, 0xAC000200])
        self.assertEqual(words[6], 0xAD00C0DE)
        self.assertEqual(words[7], 0xAE006400)
        self.assertEqual(words[8], 0xAF011020)
        self.assertEqual(words[9], 0xB00013E8)
        self.assertEqual(words[10], 0xB10F05B7)
        self.assertEqual(words[11], 0xB2000001)
        self.assertEqual(words[12], 0xB3000000)
        self.assertEqual(words[13], 0xB4010101)
        self.assertEqual(words[14], 0xB5010101)
        self.assertEqual(words[15:], [
            0xC0010006,
            0xC101000F,
            0xC1406400,
            0xC1811020,
            0xC1C00001,
            0xC1010101,
            0xC1410101,
            0xC2A505CF,
            0xC0020006,
            0xC1020078,
            0xC1400020,
            0xC1BC8000,
            0xC1C0002B,
            0xC117E400,
            0xC1400001,
            0xC28C1693,
        ])
        self.assertEqual(len(words), 31)
        check = subprocess.run(
            ["python3", "host/check_m1_mailbox.py"],
            cwd=ROOT,
            input=proc.stdout,
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(check.stdout.strip(), "PASS")

    def test_board_mailbox_host_stub_restores_seeded_champion(self):
        if not BOARD.exists():
            self.skipTest(f"board host CLI not built: {BOARD}")
        proc = subprocess.run(
            [str(BOARD), "--seed-persisted"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        words = [int(line, 16) for line in proc.stdout.strip().splitlines()]
        self.assertEqual(words[:11], [
            0xA7000000,
            0xA8001008,
            0xA90F05B7,
            0xAA013020,
            0xAB011020,
            0xAC000200,
            0xAD00C0DE,
            0xAE006400,
            0xAF011020,
            0xB00013E8,
            0xB10F05B7,
        ])
        self.assertEqual(words[11], 0xB2010101)
        self.assertEqual(words[12], 0xB30F05B7)
        self.assertEqual(words[13], 0xB4010101)
        self.assertEqual(words[14], 0xB5010101)
        self.assertEqual(words[15:], [
            0xC0010006,
            0xC101000F,
            0xC1406400,
            0xC1811020,
            0xC1C10101,
            0xC1010101,
            0xC1410101,
            0xC2A404CF,
            0xC0020006,
            0xC1020078,
            0xC1400020,
            0xC1BC8000,
            0xC1C0002B,
            0xC117E400,
            0xC1400001,
            0xC28C1693,
        ])
        self.assertEqual(len(words), 31)
        check = subprocess.run(
            ["python3", "host/check_m1_mailbox.py"],
            cwd=ROOT,
            input=proc.stdout,
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(check.stdout.strip(), "PASS")

    def test_champion_store_words_match_uboot_seed_script(self):
        words = champion_store_words(SamplerConfig(sample_phase=15, threshold=-73, majority_window=5))
        self.assertEqual(words, (0x43484D50, 0x00010001, 0x000F05B7, 0x000003E8, 0xDD7132B7))
        proc = subprocess.run(
            ["python3", "host/m1_persist_framebuf_words.py"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.stdout.strip().splitlines(), [
            "mw.l 0x40000000 0x43484d50",
            "mw.l 0x40000004 0x00010001",
            "mw.l 0x40000008 0x000f05b7",
            "mw.l 0x4000000c 0x000003e8",
            "mw.l 0x40000010 0xdd7132b7",
        ])

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
