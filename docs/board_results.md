# Board results — EBAZ4205 (XC7Z010)

Structured board observations for the two-AI handoff. Exact mailbox hex, pass/fail
per word, and where/how it diverged from the host golden. Board truth lives here.

Board: EBAZ4205, XC7Z010-1CLG400I. JTAG Digilent HS3; UART CH340 `/dev/ebaz-uart`.
Loader: U-Boot `fpga loadb` over ymodem. Mailbox observed at PS AXI-GPIO
`0x41200000` via U-Boot `md`.

---

## M1 board smoke #1 — uart_stream autonomous loop (2026-07-08) — **PARTIAL / FAIL**

Bitstream: `build/dfx/dfx.runs/impl_1/dfx_top.bit` (full, static NEORV32 shell +
`rm_uart_stream`), DFX build `scripts/vivado_dfx_uart_stream_build.tcl`. Firmware
`sw/autoehw_board_mbox.c` (budget=16, frames=8, seed=0xC0DE), baked IMEM
(text=1880 B, verify-image OK). OOC gate: all three modules 0 err/0 crit.

**FCLK0=50 preflight (mandatory):** `board-set-fclk50.py` → before
`FPGA0_CLK_CTRL=0x00200400`, after `0x00200a00`, **PASS (50 MHz pinned)**.

Load: `fpga loadb` OK (2 083 740 bytes, part 7z010clg400). NEORV32 booted and
published the mailbox lifecycle; the board-only republish loop cycles the six
evidence words steadily (~4.5 s/word, stable over >180 s of polling).

### Observed vs golden (word by word)

| # | Observed (steady) | Golden | Verdict |
|---|---|---|---|
| 1 | `0xA7000000` | `0xA7000000` | ✅ reached `main` |
| 2 | `0xA8001008` | `0xA8001008` | ✅ budget=16, frames=8 |
| 3 | `0xA90F05B7` | `0xA90F05B7` | ⚠️ champion phase=15/maj=5/thr=−73 — **matches, but see note** |
| 4 | `0xAA000020` | `0xAA013020` | ❌ train **0/32** (golden 19/32) |
| 5 | `0xAB000020` | `0xAB011020` | ❌ holdout **0/32** (golden 17/32) |
| 6 | `0xAC000200` | `0xAC000200` | ✅ evals=512 |

### Diagnosis (decisive)

**The autonomous control plane works on silicon; the fabric evaluator does not
complete.** NEORV32 ran the full train-only search loop (512 evals), published the
lifecycle, and the PS reads the mailbox — control plane, XBUS→mailbox, and
FCLK0=50 signoff are all good. But **every hardware `eval_frame` returned 0**:
train and holdout both collapse to `0/32`.

- The word-3 champion match is **not** independent evidence the evaluator worked.
  With all evals scoring 0, the search keeps the first candidate (nothing beats an
  initial best of 0). For seed `0xC0DE` the first `random_config` is exactly
  phase=15/thr=−73/maj=5, which also happens to be the host's true champion
  (verified host-side). So the champion degenerated to the first config and
  coincides with golden; the real evaluator evidence is the **pass counts**, which
  are 0.
- The run took ~2.5 min (mailbox stuck at word 2 `0xA8001008` for ~155 s before
  the lifecycle completed). That is the signature of the MMIO backend hitting its
  full `timeout=1,000,000` poll on **every** frame: the island's `STATUS.DONE`
  bit is never observed, so each `autoehw_mmio_eval_frame` times out and returns 0.

**Root-cause locus:** the `tpu_rp` ↔ `uart_stream_island_regs` ↔
`uart_stream_eval_core` completion handshake over the **real** `neorv32_soc_dfx`
XBUS. It passes the iverilog testbench (`tb_tpu_rp_uart_stream`, `status=0x6` =
done+pass) but not against the actual soc_dfx XBUS arbiter (registered
per-transaction ack `ack_q <= cyc & tpu_stb & !ack_q`; `wr_en` gated by
`!ack_q` and `xbus_sel != 0`; `start_pulse`/`busy` edge trigger). This is a
**board-only, sim-invisible** bug — the same class as the OOC lesson (the iverilog
tb is not the real bus master), and it belongs to the RTL author.

### Hypotheses for the fix (for the RTL owner)

1. The soc_dfx XBUS holds `xbus_cyc` high across accesses and pulses `tpu_stb`
   per transfer; the ad-hoc `ack_q <= cyc & tpu_stb & !ack_q` may not present a
   clean Wishbone ack/handshake to the master the way the proven base RM
   (`wb_tpu_accel`, a real Wishbone slave) does — leading to writes (START) not
   landing or the STATUS read not returning `done_latched`.
2. Prefer mirroring the base RM's known-good Wishbone-slave handshake rather than
   the bespoke `ack_q`/`wr_en && !ack_q` gating.
3. Confirm `xbus_sel` is non-zero on NEORV32 word writes (the island gates writes
   on `xbus_sel != 0`; the base RM ignores `sel`).

### What this run *does* establish on silicon

- Full DFX build + `fpga loadb` of a fresh single-RM design works.
- NEORV32 static shell (reused from zynq-ehw, copied read-only) + `rm_uart_stream`
  RM elaborate, place, route (DRC 0 err) and run.
- The autonomous train-only loop, mailbox publish, and PS observability all work.
- FCLK0=50 preflight is correct.

Not established: the fabric evaluator's per-frame result (blocked by the handshake
bug above). Full golden match is pending that RTL fix + rebuild + re-verify.

---

## M1 board smoke #2 — after XBUS handshake fix (2026-07-08) — **PROGRESS / still FAIL**

Bitstream rebuilt with ChatGPT's `tpu_rp` handshake fix (commit `cbde38d`:
pending-transaction + registered `xbus_ack`/`xbus_dat_r`, writes no longer gated
on `xbus_sel != 0`). Same firmware/IMEM (unchanged). New `dfx_top.bit`
md5 `bd8b55b5…`. OOC re-verified 0 err/0 crit (3490 LUT / 909 FF). FCLK0=50
preflight PASS (`0x00200a00`). `fpga loadb` OK. No reset/power-cycle needed
(board was already at the U-Boot prompt).

### Observed vs golden

| # | Observed (steady) | Golden | Verdict |
|---|---|---|---|
| 1 | `0xA7000000` | `0xA7000000` | ✅ |
| 2 | `0xA8001008` | `0xA8001008` | ✅ |
| 3 | `0xA91E056F` (phase=30, maj=5, thr=+111) | `0xA90F05B7` (phase=15, maj=5, thr=−73) | ❌ different champion |
| 4 | `0xAA008020` (train **8/32**) | `0xAA013020` (19/32) | ❌ |
| 5 | `0xAB006020` (holdout **6/32**) | `0xAB011020` (17/32) | ❌ |
| 6 | `0xAC000200` (evals=512) | `0xAC000200` | ✅ |

### Diagnosis — handshake FIXED, new functional (sim-vs-synth) discrepancy

**The handshake fix worked:** the island now completes every eval (search runs
fast, non-zero results, steady republish) — the timeout/`DONE`-never-asserts
failure from smoke #1 is gone. **New problem:** the on-chip evaluator's per-frame
results differ slightly from the oracle, deterministically.

Decisive cross-check (host oracle vs island, for the island's own champion
phase=30/thr=111/maj=5, frames=8):

| metric | island (on silicon) | host oracle | |
|---|---|---|---|
| train | 8/32 | 10/32 | **off by 2 frames** |
| holdout | 6/32 | 6/32 | **exact match** |

So the hardware eval ≈ oracle but flips a few frames on some inputs (holdout for
this config matches exactly; train is off by 2). That small per-frame error
shifts the search argmax, so the on-chip search selects phase=30 instead of the
golden phase=15. The champion, train, and holdout all differ **because the
evaluator is slightly wrong per-frame**, not because the search or handshake is
broken.

**Root cause locus:** `rtl/uart_stream_eval_core.v` — a **simulation-vs-synthesis
arithmetic discrepancy**. The iverilog 144-vector gate (`tb_uart_stream_eval_core`)
matches the Python oracle bit-exactly, but Vivado-synthesized hardware diverges on
some frames. Prime suspects (the same non-power-of-2 ops flagged in the OOC
resource note): the variable modulo `tmp_state1 % ((2*noise_span)+1)` and the
`round_div(_, 1000)` divides, and mixed signed/unsigned width handling in the
signal/noise/threshold arithmetic. Behavioral iverilog and Vivado can differ on
these.

**Suggested fixes (RTL owner):**
1. Rework the eval arithmetic to be synthesis-deterministic: explicit signedness
   and widths; avoid mixed signed/unsigned `%` and `/`; consider power-of-two
   scaling so modulo/divide become masks/shifts (also shrinks the 3.5k-LUT core).
2. Strengthen the gate beyond behavioral iverilog: add a **post-synthesis
   (gate-level) simulation** of `eval_core` against the oracle vectors, or a wider
   randomized vector sweep, so this class of sim-vs-synth divergence is caught on
   the host before the board.

### What smoke #2 establishes on silicon

- The XBUS handshake fix is confirmed good: island evals complete, search is fast,
  results are non-zero and deterministic; full DFX reload from an existing U-Boot
  prompt (no reset) works.
- Remaining gap is purely the eval_core arithmetic's sim-vs-synth fidelity.

---

## M1 board smoke #3 — after arithmetic-fit fix + pblock enlarge (2026-07-08) — **PASS ✅**

Bitstream rebuilt with ChatGPT's compact deterministic modulo (commit `4b9bb0b`:
Vivado-inferred `%` with explicit unsigned fixed-width operands, keeping the
signed/width fixes) + a Claude pblock enlargement (RP extended into clock region
X1Y1 → full right half, 2200 slices; the RM did not pack into the single-region
1100-slice pblock — 1885 LUT fit but needed ~1170 slices). New `dfx_top.bit`
md5 `2df5de81…`, DRC 0 err. Reset to U-Boot from a Buildroot-Linux state (board
had auto-booted during the long builds), FCLK0=50 preflight PASS
(`0x00200400`→`0x00200a00`), `fpga loadb` OK.

### Observed vs golden — FULL MATCH

| # | Observed (steady) | Golden | Verdict |
|---|---|---|---|
| 1 | `0xA7000000` | `0xA7000000` | ✅ reached `main` |
| 2 | `0xA8001008` | `0xA8001008` | ✅ budget=16, frames=8 |
| 3 | `0xA90F05B7` | `0xA90F05B7` | ✅ champion phase=15/maj=5/thr=−73 |
| 4 | `0xAA013020` | `0xAA013020` | ✅ train **19/32** |
| 5 | `0xAB011020` | `0xAB011020` | ✅ holdout **17/32** |
| 6 | `0xAC000200` | `0xAC000200` | ✅ evals=512 |

Steady republish, 2+ full cycles, **all six words match the host golden, no
extras.** RESULT: **ALL 6 GOLDEN MATCHED**.

### What M1 now establishes on silicon

The uart_stream autonomous train-only loop runs end-to-end on the EBAZ4205 and
its result is **bit-exact to the host oracle**: NEORV32 (no PC in the
candidate-selection or fitness loop) drives the fabric evaluator island over XBUS,
runs 512 evals, selects the golden champion (phase=15), and reports train 19/32 /
holdout 17/32 — matching `sim/uart_stream_v1.py` exactly. Control plane, fabric
evaluator, XBUS handshake, mailbox, FCLK0=50 signoff, and the reused NEORV32 DFX
shell are all confirmed on hardware.

Lineage of the three fixes it took: smoke #1 (XBUS DONE handshake never asserted)
→ smoke #2 (handshake fixed; eval arithmetic sim-vs-synth mismatch) → OOC fit-fail
(deterministic modulo blew the pblock) → smoke #3 (compact modulo + enlarged
pblock → full golden). No hardware damage; no power-cycle required across all
attempts.
