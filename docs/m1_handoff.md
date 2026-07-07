# M1 handoff — uart_stream_v1 host gate seed

Status: first M1 code drop, host/smoke only. No board result is claimed here.

## What is included

- `sim/uart_stream_v1.py` — deterministic Python oracle for the committed
  `uart_stream_v1` train/holdout/adversarial splits.
- `sw/uart_stream_v1.c` + `sw/uart_stream_cli.c` — portable-C twin used by the
  host gate.
- `rtl/uart_stream_lfsr.v` + `rtl/tb_uart_stream_lfsr.v` — RTL smoke fixture for
  the LFSR sequence shared by the oracle and C twin.
- `tests/test_uart_stream_v1.py` — Python standard-library tests; no pytest
  dependency.
- `host/run_m1_smoke.py` — emits a deterministic host `run_log` fixture under
  `build/host/`.

## Gate command

```sh
make all
```

This builds the C twin, checks Python/C condition scores bit-exactly, enforces
the holdout firewall in the generated `run_log` fixture, and runs the iverilog
LFSR smoke test.

## Holdout discipline

The search helper is named `random_search_train_only` on purpose. Its generation
records include `best_fitness_train`, `evals`, and hashes only. `holdout_fitness`
is emitted only in `final_evaluation` after the champion config is locked.

## Not claimed yet

- No autonomous firmware loop yet.
- No ICAP write path yet.
- No Vivado OOC/resource gate yet.
- No board verification or `docs/board_results.md` entry yet.
- No numeric PASS bands for `uart_stream_v1.1`; those must be measured from the
  real PL generator during board bring-up.

## Next Claude-side checks

1. Run `make all` from a clean checkout.
2. Run Vivado OOC/resource checks once the generator/sampler RTL expands beyond
   this smoke fixture.
3. Before any board run, create `docs/hw_notes.md` and record the FCLK0=50 MHz
   preflight result.
