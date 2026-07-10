import json
import subprocess
import unittest
from pathlib import Path

from sim.uart_stream_v2 import (
    BENCHMARK_ID,
    GENOME_BITS,
    SCHEMA_VERSION,
    decode_genome,
    encode_genome,
    genome_space_size,
    landscape_child,
    same_boot_ab_search,
    variant_arm_train_only,
    build_run_log_fixture,
    score_set,
)


ROOT = Path(__file__).resolve().parents[1]
V2_C_TWIN = ROOT / "build" / "host" / "uart_stream_v2_cli"
V2_FIRMWARE = ROOT / "build" / "host" / "autoehw_firmware_v2_cli"
BOARD = ROOT / "build" / "host" / "autoehw_board_host_cli"


class UartStreamV2HeadroomTest(unittest.TestCase):
    def test_genome_contract_has_headroom_over_two_hour_budget(self):
        self.assertEqual(GENOME_BITS, 39)
        self.assertGreaterEqual(genome_space_size(), 1 << 32)
        # M1 measured about 7M candidates in two hours; v2 leaves >600x headroom.
        self.assertGreater(genome_space_size() // 7_000_000, 600)

    def test_genome_encoding_round_trips(self):
        for raw in (0, 1, 0x123456789, (1 << GENOME_BITS) - 1):
            genome = decode_genome(raw)
            self.assertEqual(encode_genome(genome), raw & ((1 << GENOME_BITS) - 1))

    def test_same_boot_ab_fixture_preserves_holdout_firewall(self):
        result = same_boot_ab_search(budget=8, seed=0xC0DE, frames=2)
        fixture = build_run_log_fixture(result)
        self.assertEqual(fixture["header"]["benchmark_id"], BENCHMARK_ID)
        self.assertEqual(fixture["header"]["benchmark_version"], SCHEMA_VERSION)
        self.assertEqual(fixture["header"]["schema_versions"]["genome_contract"], "2.0.0")
        self.assertEqual(set(fixture["header"]["ab_arms"].keys()), {"ga", "random"})
        self.assertIn("ga", fixture["final_evaluation"])
        self.assertIn("random_equal_budget", fixture["final_evaluation"])
        self.assertIn("holdout_fitness", fixture["final_evaluation"]["ga"])
        self.assertIn("holdout_fitness", fixture["final_evaluation"]["random_equal_budget"])
        for generation in fixture["generations"]:
            self.assertIn(generation["arm"], ("ga", "random"))
            self.assertIn("best_fitness_train", generation)
            self.assertNotIn("holdout_fitness", generation)

    def test_headroom_smoke_script_writes_fixture(self):
        out = ROOT / "build" / "host" / "headroom_test_fixture.json"
        proc = subprocess.run(
            [
                "python3",
                "host/run_headroom_smoke.py",
                "--budget",
                "8",
                "--frames",
                "2",
                "--out",
                str(out),
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn("genome_bits=39", proc.stdout)
        fixture = json.loads(out.read_text())
        self.assertEqual(fixture["header"]["benchmark_id"], BENCHMARK_ID)
        self.assertEqual(fixture["header"]["schema_versions"]["genome_contract"], "2.0.0")

    def test_c_twin_matches_python_score_rows(self):
        if not V2_C_TWIN.exists():
            self.skipTest(f"v2 C twin not built: {V2_C_TWIN}")
        raw = 0x123456789
        genome = decode_genome(raw)
        frames = 4
        proc = subprocess.run(
            [str(V2_C_TWIN), "score", hex(raw), str(frames)],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        observed = []
        for line in proc.stdout.strip().splitlines():
            fields = line.split()
            observed.append((fields[0], fields[1], int(fields[2]), int(fields[3])))
        expected = []
        for split in ("train", "holdout", "adversarial"):
            for score in score_set(split, genome, frames).conditions:
                expected.append((score.condition, score.split, score.passed, score.frames))
        self.assertEqual(observed, expected)

    def test_c_twin_matches_python_same_boot_ab_search(self):
        if not V2_C_TWIN.exists():
            self.skipTest(f"v2 C twin not built: {V2_C_TWIN}")
        budget = 16
        frames = 4
        seed = 0xC0DE
        result = same_boot_ab_search(budget, seed, frames)
        fixture = build_run_log_fixture(result)
        proc = subprocess.run(
            [str(V2_C_TWIN), "ab", str(budget), hex(seed), str(frames)],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        lines = proc.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        parsed = {}
        for line in lines:
            fields = line.split()
            parsed[fields[0]] = {
                "raw": int(fields[2], 16),
                "train": (int(fields[12]), int(fields[13])),
                "holdout": (int(fields[15]), int(fields[16])),
                "evals": int(fields[18]),
            }
        self.assertEqual(parsed["ga"]["raw"], encode_genome(result.ga.best_genome))
        self.assertEqual(parsed["random"]["raw"], encode_genome(result.random.best_genome))
        self.assertEqual(
            parsed["ga"]["train"],
            (
                round(fixture["final_evaluation"]["ga"]["train_fitness"] * 4 * frames),
                4 * frames,
            ),
        )
        self.assertEqual(
            parsed["random"]["holdout"],
            (
                round(fixture["final_evaluation"]["random_equal_budget"]["holdout_fitness"] * 4 * frames),
                4 * frames,
            ),
        )
        self.assertEqual(parsed["ga"]["evals"], budget * 4 * frames)
        self.assertEqual(parsed["random"]["evals"], budget * 4 * frames)

    def test_c_twin_matches_python_v3_variants(self):
        if not V2_C_TWIN.exists():
            self.skipTest(f"v2 C twin not built: {V2_C_TWIN}")
        budget = 48
        train_frames = 4
        holdout_frames = 8
        seed = 0x1357
        for variant in (
            "current_hillclimb",
            "restart_hillclimb_v3",
            "immigrant_hillclimb_v3",
            "beam4_ga_v3",
        ):
            result = variant_arm_train_only(variant, budget, seed, train_frames)
            train = score_set("train", result.best_genome, train_frames)
            holdout = score_set("holdout", result.best_genome, holdout_frames)
            proc = subprocess.run(
                [str(V2_C_TWIN), "variant", variant, str(budget), hex(seed), str(train_frames), str(holdout_frames)],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )
            fields = proc.stdout.strip().split()
            self.assertEqual(int(fields[2], 16), encode_genome(result.best_genome), variant)
            self.assertEqual((int(fields[12]), int(fields[13])), (
                sum(score.passed for score in train.conditions),
                sum(score.frames for score in train.conditions),
            ), variant)
            self.assertEqual((int(fields[15]), int(fields[16])), (
                sum(score.passed for score in holdout.conditions),
                sum(score.frames for score in holdout.conditions),
            ), variant)

    def test_c_twin_matches_python_v4_search_variants(self):
        if not V2_C_TWIN.exists():
            self.skipTest(f"v2 C twin not built: {V2_C_TWIN}")
        budget = 196
        train_frames = 2
        holdout_frames = 4
        seed = 0x1357
        for variant in ("bitflip1_topdecile_v4", "pbil_eda_v4"):
            result = variant_arm_train_only(variant, budget, seed, train_frames)
            train = score_set("train", result.best_genome, train_frames)
            holdout = score_set("holdout", result.best_genome, holdout_frames)
            proc = subprocess.run(
                [str(V2_C_TWIN), "variant", variant, str(budget), hex(seed), str(train_frames), str(holdout_frames)],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )
            fields = proc.stdout.strip().split()
            self.assertEqual(int(fields[2], 16), encode_genome(result.best_genome), variant)
            self.assertEqual((int(fields[12]), int(fields[13])), (
                sum(score.passed for score in train.conditions),
                sum(score.frames for score in train.conditions),
            ), variant)
            self.assertEqual((int(fields[15]), int(fields[16])), (
                sum(score.passed for score in holdout.conditions),
                sum(score.frames for score in holdout.conditions),
            ), variant)

    def test_c_twin_matches_python_v5_pbil_variants(self):
        if not V2_C_TWIN.exists():
            self.skipTest(f"v2 C twin not built: {V2_C_TWIN}")
        budget = 260
        train_frames = 2
        holdout_frames = 4
        seed = 0x2468
        for variant in ("pbil_stable_v5", "pbil_restart_v5", "pbil_hybrid_v5"):
            result = variant_arm_train_only(variant, budget, seed, train_frames)
            train = score_set("train", result.best_genome, train_frames)
            holdout = score_set("holdout", result.best_genome, holdout_frames)
            proc = subprocess.run(
                [str(V2_C_TWIN), "variant", variant, str(budget), hex(seed), str(train_frames), str(holdout_frames)],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )
            fields = proc.stdout.strip().split()
            self.assertEqual(int(fields[2], 16), encode_genome(result.best_genome), variant)
            self.assertEqual((int(fields[12]), int(fields[13])), (
                sum(score.passed for score in train.conditions),
                sum(score.frames for score in train.conditions),
            ), variant)
            self.assertEqual((int(fields[15]), int(fields[16])), (
                sum(score.passed for score in holdout.conditions),
                sum(score.frames for score in holdout.conditions),
            ), variant)

    def test_c_twin_matches_python_v6_island_variants(self):
        if not V2_C_TWIN.exists():
            self.skipTest(f"v2 C twin not built: {V2_C_TWIN}")
        budget = 360
        train_frames = 2
        holdout_frames = 4
        seed = 0x369C
        for variant in ("pbil_island2_v6", "pbil_island3_v6", "pbil_island4_v6"):
            result = variant_arm_train_only(variant, budget, seed, train_frames)
            train = score_set("train", result.best_genome, train_frames)
            holdout = score_set("holdout", result.best_genome, holdout_frames)
            proc = subprocess.run(
                [str(V2_C_TWIN), "variant", variant, str(budget), hex(seed), str(train_frames), str(holdout_frames)],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )
            fields = proc.stdout.strip().split()
            self.assertEqual(int(fields[2], 16), encode_genome(result.best_genome), variant)
            self.assertEqual((int(fields[12]), int(fields[13])), (
                sum(score.passed for score in train.conditions),
                sum(score.frames for score in train.conditions),
            ), variant)
            self.assertEqual((int(fields[15]), int(fields[16])), (
                sum(score.passed for score in holdout.conditions),
                sum(score.frames for score in holdout.conditions),
            ), variant)

    def test_c_twin_matches_python_v7_deep_selection_variants(self):
        if not V2_C_TWIN.exists():
            self.skipTest(f"v2 C twin not built: {V2_C_TWIN}")
        budget = 360
        train_frames = 2
        deep_frames = 256
        holdout_frames = 4
        seed = 0x47AD
        for variant in ("pbil_island4_deep_v7", "pbil_island4_margin_v7"):
            result = variant_arm_train_only(variant, budget, seed, train_frames)
            deep_train = score_set("train", result.best_genome, deep_frames)
            holdout = score_set("holdout", result.best_genome, holdout_frames)
            proc = subprocess.run(
                [str(V2_C_TWIN), "variant", variant, str(budget), hex(seed), str(train_frames), str(holdout_frames)],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )
            fields = proc.stdout.strip().split()
            self.assertEqual(int(fields[2], 16), encode_genome(result.best_genome), variant)
            self.assertEqual((int(fields[12]), int(fields[13])), (
                sum(score.passed for score in deep_train.conditions),
                sum(score.frames for score in deep_train.conditions),
            ), variant)
            self.assertEqual((int(fields[15]), int(fields[16])), (
                sum(score.passed for score in holdout.conditions),
                sum(score.frames for score in holdout.conditions),
            ), variant)

    def test_c_twin_matches_python_v4_landscape_kernels(self):
        if not V2_C_TWIN.exists():
            self.skipTest(f"v2 C twin not built: {V2_C_TWIN}")
        raw = 0x123456789
        seed = 0x5A5A
        frames = 4
        parent = decode_genome(raw)
        parent_train = score_set("train", parent, frames)
        for kernel in ("bitflip_1", "bitflip_4", "field_resample", "full_random"):
            _state, child = landscape_child(kernel, seed, parent)
            child_train = score_set("train", child, frames)
            proc = subprocess.run(
                [str(V2_C_TWIN), "landscape", kernel, hex(raw), hex(seed), str(frames)],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )
            fields = proc.stdout.strip().split()
            self.assertEqual(fields[2], kernel)
            self.assertEqual(int(fields[4], 16), encode_genome(parent), kernel)
            self.assertEqual(int(fields[6], 16), encode_genome(child), kernel)
            self.assertEqual((int(fields[8]), int(fields[9])), (
                sum(score.passed for score in parent_train.conditions),
                sum(score.frames for score in parent_train.conditions),
            ), kernel)
            self.assertEqual((int(fields[11]), int(fields[12])), (
                sum(score.passed for score in child_train.conditions),
                sum(score.frames for score in child_train.conditions),
            ), kernel)

    def test_v3_screening_script_smoke(self):
        if not V2_C_TWIN.exists():
            self.skipTest(f"v2 C twin not built: {V2_C_TWIN}")
        proc = subprocess.run(
            [
                "python3",
                "host/screen_v3_search.py",
                "--cli",
                str(V2_C_TWIN),
                "--budget",
                "16",
                "--train-frames",
                "4",
                "--holdout-frames",
                "8",
                "--seeds",
                "0x1357,0x2468",
                "--variants",
                "current_hillclimb,restart_hillclimb_v3",
                "--jobs",
                "2",
                "--json",
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        self.assertEqual(report["budget"], 16)
        self.assertEqual(set(report["variants"].keys()), {"current_hillclimb", "restart_hillclimb_v3"})

    def test_v4_screening_script_smoke(self):
        if not V2_C_TWIN.exists():
            self.skipTest(f"v2 C twin not built: {V2_C_TWIN}")
        proc = subprocess.run(
            [
                "python3",
                "host/screen_v4_search.py",
                "--cli",
                str(V2_C_TWIN),
                "--budget",
                "40",
                "--train-frames",
                "2",
                "--holdout-frames",
                "4",
                "--seeds",
                "0x1357,0x2468",
                "--variants",
                "bitflip1_topdecile_v4,pbil_eda_v4",
                "--jobs",
                "2",
                "--json",
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        self.assertEqual(report["protocol"], "prereg_search_v4")
        self.assertEqual(report["budget"], 40)
        self.assertEqual(set(report["variants"].keys()), {"bitflip1_topdecile_v4", "pbil_eda_v4"})

    def test_v5_screening_script_smoke(self):
        if not V2_C_TWIN.exists():
            self.skipTest(f"v2 C twin not built: {V2_C_TWIN}")
        proc = subprocess.run(
            [
                "python3",
                "host/screen_v5_search.py",
                "--cli",
                str(V2_C_TWIN),
                "--budget",
                "180",
                "--train-frames",
                "2",
                "--holdout-frames",
                "4",
                "--seeds",
                "0x1357,0x2468",
                "--variants",
                "pbil_stable_v5,pbil_restart_v5,pbil_hybrid_v5",
                "--jobs",
                "2",
                "--json",
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        self.assertEqual(report["protocol"], "prereg_search_v5")
        self.assertEqual(report["budget"], 180)
        self.assertEqual(set(report["variants"].keys()), {"pbil_stable_v5", "pbil_restart_v5", "pbil_hybrid_v5"})

    def test_v6_screening_script_smoke(self):
        if not V2_C_TWIN.exists():
            self.skipTest(f"v2 C twin not built: {V2_C_TWIN}")
        proc = subprocess.run(
            [
                "python3",
                "host/screen_v6_search.py",
                "--cli",
                str(V2_C_TWIN),
                "--budget",
                "240",
                "--train-frames",
                "2",
                "--holdout-frames",
                "4",
                "--seeds",
                "0x1357,0x2468",
                "--variants",
                "pbil_island2_v6,pbil_island3_v6,pbil_island4_v6",
                "--jobs",
                "2",
                "--json",
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        self.assertEqual(report["protocol"], "prereg_search_v6")
        self.assertEqual(report["budget"], 240)
        self.assertEqual(set(report["variants"].keys()), {"pbil_island2_v6", "pbil_island3_v6", "pbil_island4_v6"})

    def test_v7_screening_script_smoke(self):
        if not V2_C_TWIN.exists():
            self.skipTest(f"v2 C twin not built: {V2_C_TWIN}")
        proc = subprocess.run(
            [
                "python3",
                "host/screen_v7_search.py",
                "--cli",
                str(V2_C_TWIN),
                "--budget",
                "240",
                "--deep-budget",
                "224",
                "--train-frames",
                "2",
                "--holdout-frames",
                "4",
                "--seeds",
                "0x1357,0x2468",
                "--variants",
                "pbil_island4_deep_v7,pbil_island4_margin_v7,pbil_island4_v6",
                "--jobs",
                "2",
                "--json",
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        self.assertEqual(report["protocol"], "prereg_search_v7")
        self.assertEqual(report["budget"], 240)
        self.assertEqual(report["deep_budget"], 224)
        self.assertEqual(set(report["variants"].keys()), {
            "pbil_island4_deep_v7",
            "pbil_island4_margin_v7",
            "pbil_island4_v6",
        })
        for row in report["variants"]["pbil_island4_deep_v7"]["rows"]:
            self.assertEqual(row["variant_budget"], 224)
            self.assertEqual(row["random_budget"], 240)

    def test_v4_landscape_probe_smoke(self):
        proc = subprocess.run(
            [
                "python3",
                "host/landscape_v4_probe.py",
                "--frames",
                "1",
                "--parents-per-stratum",
                "4",
                "--top-pool-per-seed",
                "4",
                "--children-per-parent",
                "1",
                "--bootstrap-rounds",
                "4",
                "--seeds",
                "0x1357,0x2468",
                "--json",
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        self.assertEqual(report["protocol"], "prereg_landscape_v4")
        self.assertEqual(report["frames"], 1)
        self.assertEqual(set(report["results"].keys()), {
            "uniform_random",
            "random_stream_top_decile",
            "historical_champion",
        })
        for by_kernel in report["results"].values():
            self.assertEqual(set(by_kernel.keys()), {"bitflip_1", "bitflip_4", "field_resample", "full_random"})
            for stats in by_kernel.values():
                self.assertEqual(stats["n_pairs"], 4)
                self.assertIn("hard", stats)
                self.assertIn("soft", stats)
                self.assertIn("hard_soft_child_corr", stats)

    def test_firmware_fake_backend_matches_python_same_boot_ab_search(self):
        if not V2_FIRMWARE.exists():
            self.skipTest(f"v2 firmware CLI not built: {V2_FIRMWARE}")
        budget = 16
        frames = 4
        seed = 0xC0DE
        result = same_boot_ab_search(budget, seed, frames)
        proc = subprocess.run(
            [str(V2_FIRMWARE), str(budget), hex(seed), str(frames)],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        lines = proc.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        parsed = {}
        for line in lines:
            fields = line.split()
            parsed[fields[0]] = {
                "raw": int(fields[2], 16),
                "train": (int(fields[4]), int(fields[5])),
                "holdout": (int(fields[7]), int(fields[8])),
                "evals": int(fields[10]),
            }
        self.assertEqual(parsed["ga"]["raw"], encode_genome(result.ga.best_genome))
        self.assertEqual(parsed["random"]["raw"], encode_genome(result.random.best_genome))
        self.assertEqual(parsed["ga"]["evals"], budget * 4 * frames)
        self.assertEqual(parsed["random"]["evals"], budget * 4 * frames)

    def test_board_host_v2_ab_mailbox_matches_oracle(self):
        if not BOARD.exists():
            self.skipTest(f"board host CLI not built: {BOARD}")
        proc = subprocess.run(
            [str(BOARD), "--v2-ab-mailbox-smoke"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        words = [int(line, 16) for line in proc.stdout.strip().splitlines()]
        self.assertEqual(words[:3], [0xA7000000, 0xA8001004, 0xAD00C0DE])
        self.assertEqual(len(words), 21)
        check = subprocess.run(
            ["python3", "host/check_v2_ab_mailbox.py"],
            cwd=ROOT,
            input=proc.stdout,
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(check.stdout.strip(), "PASS")

    def test_board_host_v2_ab_longrun_smoke_has_progress_pages(self):
        if not BOARD.exists():
            self.skipTest(f"board host CLI not built: {BOARD}")
        proc = subprocess.run(
            [str(BOARD), "--v2-ab-longrun-smoke"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        words = [int(line, 16) for line in proc.stdout.strip().splitlines()]
        self.assertEqual(words[:3], [0xA7000000, 0xA8000840, 0xAD00C0DE])
        self.assertEqual(len(words), 111)
        check = subprocess.run(
            ["python3", "host/check_v2_ab_longrun_mailbox.py"],
            cwd=ROOT,
            input=proc.stdout,
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(check.stdout.strip(), "PASS")


if __name__ == "__main__":
    unittest.main()
