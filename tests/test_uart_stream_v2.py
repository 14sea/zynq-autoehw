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
)


ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
