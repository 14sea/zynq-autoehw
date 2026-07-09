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
    same_boot_ab_search,
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
        self.assertEqual(words[:3], [0xA7000000, 0xA8000804, 0xAD00C0DE])
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
