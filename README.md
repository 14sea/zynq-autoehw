# zynq-autoehw

Autonomous evolvable-hardware runtime on a recycled Zynq-7010 EBAZ4205 board.
This is the successor line to
[`zynq-ehw`](https://github.com/14sea/zynq-ehw): `zynq-ehw` proved the FPGA
mechanisms; this repo tests whether one board can run the experiment loop
itself.

## Status

**M1 is closed at tag `m1-complete`.**

The final board run confirmed, on silicon, that the autonomous runtime can beat
an equal-budget random-search baseline on the held-out split of
`uart_stream_v2_headroom`.

| Result | Value |
|---|---|
| Tag | `m1-complete` |
| Final board commit | `27bc3d1` |
| Search arm | `pbil_island8_graded_v9` |
| Confirmation seed | `0xB17D` |
| Board-derived budget | `22078` candidates |
| Runtime | about 124 minutes, PC out of candidate selection and fitness |
| Random hard holdout | `15/1024` |
| Search hard holdout | `128/1024` |
| Delta | `+113/1024` |

The result is deliberately scoped: one UART-like benchmark family, one measured
budget regime, one pre-registered Set B confirmation after a 16-seed Set A
screen. It is not a claim of cross-benchmark transfer or a local-map result.

## Claim Status

| Claim | M1 status |
|---|---|
| **A: autonomous runtime** | **PASS for the runtime core.** Multi-hour PC-free search, board-derived budget, heartbeat telemetry, bit-exact host replay, rejection/recovery scaffolds, and no power-cycle dependency are board evidenced. NV champion storage and board-side replay-bundle emission remain engineering remainders. |
| **B: device-local map guidance** | **NOT TESTED.** This is reserved for M2. |
| **C: held-out improvement** | **PASS for the M1 beats-random-on-holdout subclaim.** Static-baseline, adversarial/no-reward-hack, and broader generalization-gap axes are not closed by M1. |

The full claims ledger is in [`docs/tech_report.md`](docs/tech_report.md).

## What This Repo Contains

The M1 stack is a complete, evidence-bearing path from oracle to board:

- Python oracle and C twins for `uart_stream_v1` and `uart_stream_v2`.
- NEORV32-oriented firmware search paths, including random, hillclimb, PBIL, and
  graded K-island variants.
- RTL evaluator and MMIO island for the UART-stream benchmark.
- Host gates, preregistered screening scripts, board mailbox checkers, and Vivado
  OOC/DFX scripts.
- Board-result logs and preregistration/results documents for every failed and
  successful search round.

## Evidence Map

| File | Purpose |
|---|---|
| [`docs/tech_report.md`](docs/tech_report.md) | Claims ledger, scope, milestone criteria, and M1 closure evidence. |
| [`docs/board_results.md`](docs/board_results.md) | Silicon results: smoke tests, long runs, graded MMIO proof, and final Set B confirmation. |
| [`docs/benchmark.md`](docs/benchmark.md) | Benchmark definitions, holdout firewall, v2 headroom package, and final M1 benchmark closure. |
| [`docs/schema.md`](docs/schema.md) | Versioned contracts for genome, manifest, run log, replay bundle, safety lists, and write budget. |
| [`docs/ooc_results.md`](docs/ooc_results.md) | Vivado OOC resource/fit gates and warnings. |
| [`docs/prereg_search_v3.md`](docs/prereg_search_v3.md) ... [`docs/prereg_search_v9_graded_islands.md`](docs/prereg_search_v9_graded_islands.md) | Pre-registered screening plans. |
| [`docs/screening_v3_results.md`](docs/screening_v3_results.md) ... [`docs/screening_v9_results.md`](docs/screening_v9_results.md) | Host screening results, including failed variants. |
| [`docs/v9_setb_confirm_golden.md`](docs/v9_setb_confirm_golden.md) | Frozen host golden for the final Set B board confirmation. |

The failed rounds are part of the result. The project intentionally records
near-misses, falsified search variants, and scope limits rather than only the
final winning run.

## Repository Layout

| Path | Contents |
|---|---|
| `sim/` | Python benchmark oracles. |
| `sw/` | C twins, firmware search logic, board mailbox firmware glue. |
| `rtl/` | UART-stream evaluator, island registers, and testbenches. |
| `host/` | Host gates, screening scripts, mailbox checkers, vector generators. |
| `scripts/` | Board monitor utilities and Vivado OOC/DFX scripts. |
| `docs/` | Claims, benchmark contracts, preregistration, screening, OOC, and board evidence. |
| `external/` | Copied board/tooling assets from sibling repos; source repos stay read-only. |

## Quick Gates

Host and RTL smoke:

```sh
make all
```

Host-only gate:

```sh
make host-gate
```

RTL smoke only:

```sh
make rtl-smoke
```

Vivado OOC gates:

```sh
make vivado-ooc
```

The board-facing DFX flow is documented by the scripts under `scripts/` and by
the executed evidence in `docs/board_results.md`; board runs should be treated as
confirmation runs, not exploratory tuning sessions.

## Boundaries

- Sibling repos (`zynq-ehw`, `zynq-xpart`, `zynq-agentctl`,
  `Cyclone_CRAM_Mapper`) are read-only sources. Reused assets are copied in.
- The PC may monitor, load firmware/bitstreams, and collect logs; it must not
  choose candidates or compute fitness for an autonomous board claim.
- Holdout results are final-evaluation data only. They must not guide search,
  tuning, early stopping, or rerun decisions.
- Claim B is intentionally open. The next research line is M2: device-local map
  construction and map-guided safe evolution.

## Roadmap

```text
zynq-ehw v1.2.0
  completed board-verified mechanism ladder
        |
        v
M0  claims contract, schemas, benchmark package
M1  autonomous Zynq runtime + held-out beats-random gate  [DONE: m1-complete]
M2  device-local map guidance and safe ICAP/LUT evolution [NEXT]
M3  open-routing work on sacrificial 7-series hardware
```
