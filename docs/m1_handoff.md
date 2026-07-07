# M1 handoff — uart_stream_v1 RTL/OOC handoff

Status: host + RTL vector gates are ready for Claude's OOC/resource check. No
Vivado OOC result or board result is claimed here.

## What is included

- `sim/uart_stream_v1.py` — deterministic Python oracle for the committed
  `uart_stream_v1` train/holdout/adversarial splits.
- `sw/uart_stream_v1.c` + `sw/uart_stream_cli.c` — portable-C twin used by the
  host gate.
- `rtl/uart_stream_lfsr.v` + `rtl/tb_uart_stream_lfsr.v` — RTL smoke fixture for
  the LFSR sequence shared by the oracle and C twin.
- `rtl/uart_stream_eval_core.v` + `rtl/tb_uart_stream_eval_core.v` —
  synthesizable single-frame evaluator and RTL-vs-oracle vector gate.
- `host/gen_rtl_eval_vectors.py` — generates Python-oracle vectors for the RTL
  evaluator gate.
- `tests/test_uart_stream_v1.py` — Python standard-library tests; no pytest
  dependency.
- `host/run_m1_smoke.py` — emits a deterministic host `run_log` fixture under
  `build/host/`.
- `scripts/vivado_ooc_uart_stream.tcl` — Claude-side OOC synth/resource entry for
  `uart_stream_eval_core`.

## Gate command

```sh
make all
```

This builds the C twin, checks Python/C condition scores bit-exactly, enforces
the holdout firewall in the generated `run_log` fixture, runs the iverilog LFSR
smoke test, and checks `uart_stream_eval_core` against 144 Python-oracle vectors.

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

- No autonomous firmware loop yet.
- No ICAP write path yet.
- No Vivado OOC/resource gate yet, only the Tcl entry for Claude to run.
- No board verification or `docs/board_results.md` entry yet.
- No numeric PASS bands for `uart_stream_v1.1`; those must be measured from the
  real PL generator during board bring-up.

## Next Claude-side checks

1. Run `make all` from a clean checkout.
2. Run `make vivado-ooc` and inspect utilization/timing under
   `build/ooc/uart_stream_eval_core/`.
3. Before any board run, create `docs/hw_notes.md` and record the FCLK0=50 MHz
   preflight result.
