# M1 handoff — uart_stream_v1 firmware/island handoff

Status: host + RTL vector gates are ready, with a firmware backend seam and a
simple evaluator-island register wrapper. No Vivado OOC result for the new
wrapper and no board result are claimed here.

## What is included

- `sim/uart_stream_v1.py` — deterministic Python oracle for the committed
  `uart_stream_v1` train/holdout/adversarial splits.
- `sw/uart_stream_v1.c` + `sw/uart_stream_cli.c` — portable-C twin used by the
  host gate.
- `sw/autoehw_runtime.c` + `sw/autoehw_runtime_cli.c` — portable-C train-only
  autonomous search seed; holdout is evaluated only after the champion config is
  locked.
- `sw/autoehw_firmware.c` + `sw/autoehw_firmware_cli.c` — firmware-facing
  train-only loop over a hardware `eval_frame` backend.
- `sw/autoehw_mmio_backend.c` + `sw/uart_stream_regs.h` — board backend seam and
  register contract for the RTL island.
- `rtl/uart_stream_lfsr.v` + `rtl/tb_uart_stream_lfsr.v` — RTL smoke fixture for
  the LFSR sequence shared by the oracle and C twin.
- `rtl/uart_stream_eval_core.v` + `rtl/tb_uart_stream_eval_core.v` —
  synthesizable single-frame evaluator and RTL-vs-oracle vector gate.
- `rtl/uart_stream_island_regs.v` + `rtl/tb_uart_stream_island_regs.v` — simple
  memory-mapped register wrapper around the evaluator core.
- `rtl/dfx/tpu_rp_rm_uart_stream.v` + `rtl/tb_tpu_rp_uart_stream.v` — XBUS
  reconfigurable-module wrapper compatible with the zynq-ehw NEORV32 DFX shell.
- `host/gen_rtl_eval_vectors.py` — generates Python-oracle vectors for the RTL
  evaluator gate.
- `tests/test_uart_stream_v1.py` — Python standard-library tests; no pytest
  dependency.
- `host/run_m1_smoke.py` — emits a deterministic host `run_log` fixture under
  `build/host/`.
- `scripts/vivado_ooc_uart_stream*.tcl` — Claude-side OOC synth/resource entries
  for `uart_stream_eval_core`, `uart_stream_island_regs`, and the XBUS `tpu_rp`
  wrapper.
- `docs/m1_board_handoff.md` — board-side integration notes and mailbox golden.

## Gate command

```sh
make all
```

This builds the C twin, checks Python/C condition scores bit-exactly, enforces
the holdout firewall in the generated `run_log` fixture, checks the firmware fake
backend against the Python oracle, runs the iverilog LFSR smoke test, checks
`uart_stream_eval_core` against 144 Python-oracle vectors, and exercises the
island register wrapper plus the XBUS `tpu_rp` RM wrapper on a known passing
vector.

Claude-side OOC entry:

```sh
make vivado-ooc
```

This is not run or claimed by this handoff; it is the next gate before board
integration.

## Holdout discipline

The search helper is named `random_search_train_only` on purpose. Its generation
records include `best_fitness_train`, `evals`, and hashes only. `holdout_fitness`
is emitted only in `final_evaluation` after the champion config is locked.

## Not claimed yet

- No board-integrated firmware loop yet; the portable-C firmware loop and MMIO
  backend seam compile and are host-verified with a fake backend.
- No ICAP write path yet.
- No Vivado OOC/resource gate yet for the new `uart_stream_island_regs` wrapper,
  only the Tcl entry for Claude to run. `docs/ooc_results.md` records the earlier
  `uart_stream_eval_core` OOC result.
- No board verification or `docs/board_results.md` entry yet.
- No numeric PASS bands for `uart_stream_v1.1`; those must be measured from the
  real PL generator during board bring-up.

## Next Claude-side checks

1. Run `make all` from a clean checkout.
2. Run `make vivado-ooc` and inspect utilization/timing under
   `build/ooc/uart_stream_eval_core/` and `build/ooc/uart_stream_island_regs/`.
3. Bind `autoehw_mmio_backend` to the real island base address and timeout.
4. Before any board run, create `docs/hw_notes.md` and record the FCLK0=50 MHz
   preflight result.
