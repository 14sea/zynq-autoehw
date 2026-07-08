# OOC synthesis gate results

Claude-side Vivado out-of-context (OOC) synthesis gate results. This is the gate
ChatGPT cannot run (no Vivado in its environment); it is mandatory before any
board build per `docs/workflow.md`. Not a board result — no silicon behavior is
claimed here. Raw reports live under `build/ooc/` (gitignored); this file is the
persisted summary.

Tool: Vivado 2025.2 · `make vivado-ooc` (`scripts/vivado_ooc_uart_stream.tcl`).

---

## uart_stream_eval_core (commit f9722aa)

- **Part:** `xc7z010clg400-1`, `synth_design -mode out_of_context`
- **Verdict:** **PASS** — `Synth Design complete`, **0 errors, 0 critical
  warnings**, 12 benign warnings.
- **Date:** 2026-07-07

### Utilization (flat OOC synth)

| Resource | Used | Avail | % |
|---|---|---|---|
| Slice LUTs (all Logic) | 3371 | 17600 | 19.15 |
| Slice Registers (FF) | 738 | 35200 | 2.10 |
| DSP48E1 | 3 | 80 | 3.75 |
| Block RAM Tile | 0 | 60 | 0.00 |
| LUT as Memory | 0 | 6000 | 0.00 |

`payload_mem[0:63]` maps to logic/distributed, not BRAM (0 BRAM). The 3 DSPs come
from the integer multiplies (`frame_idx*0x1F3D`, `jitter_milli*32`,
`flip_ppm*65535`).

### Warnings (all benign, non-blocking)

- 10× `[Synth 8-6014] Unused sequential element tmp_*_reg removed` — the `tmp_*`
  regs are blocking-assignment temporaries inside the clocked `always`; Vivado
  classifies them as sequential then trims them because they hold no cross-cycle
  state. Cosmetic only; iverilog's 144-vector gate already proves functional
  equivalence to the Python oracle. **Style cleanup suggestion:** declare them as
  `automatic`/local or split combinational vs sequential logic to silence.
- 1× `[Synth 8-3936] flip_threshold_reg trimmed 29→16 bits` — correct: only
  `flip_threshold[15:0]` is used, and the value (`flip_ppm*65535/1e6`, max
  `flip_ppm=1e6` → 65535) fits in 16 bits. No functional impact.
- `[Netlist 29-101] not ideal for floorplanning (large number of primitives)` —
  flat OOC synth of a module with dividers/modulo; enable hierarchy for the real
  island build.
- `[Timing 38-493]/[38-242]` — no clock buffer / `HD.CLK_SRC` unset in OOC mode →
  `report_timing_summary` has **no meaningful number here**. Real timing must be
  taken at the island build with a proper clock constraint at **FCLK0 = 50 MHz**.

### Resource note for the island budget (non-blocking)

3371 LUTs for a single-frame evaluator is dominated by two non-power-of-2
operations that synthesize to large combinational dividers:

- `tmp_state1 % ((2*noise_span)+1)` (variable modulo), and
- `round_div(x, 1000)` (divide-by-1000).

Comfortable at 19% of the whole device now, but when this core becomes a DFX RP
inside a pblock it is the first shrink target. Options: make the noise span /
scaling factors powers of two so the modulo/divide become shifts (the same class
of rework as EHW-4.2's 48-DSP → 18-DSP fix in `zynq-ehw`). Any such change must
re-pass the 144-vector RTL gate and be re-synthesized here.

---

## uart_stream_island_regs (commit 8f38bdd)

MMIO register wrapper (`rtl/uart_stream_island_regs.v`) around
`uart_stream_eval_core`; the register map matches `sw/uart_stream_regs.h` byte-for-byte.

- **Part:** `xc7z010clg400-1`, `synth_design -mode out_of_context`, top =
  `uart_stream_island_regs`
- **Verdict:** **PASS** — **0 errors, 0 critical warnings**, 12 warnings (same
  benign classes as the core: trimmed `tmp_*` temporaries + OOC no-BUFG/no-XDC
  clock notes).
- **Date:** 2026-07-07

### Utilization

| Resource | Used | Avail | % | Δ vs bare core |
|---|---|---|---|---|
| Slice LUTs | 3480 | 17600 | 19.77 | +109 (MMIO decode) |
| Slice Registers (FF) | 866 | 35200 | 2.46 | +128 (register file) |
| DSP48E1 | 3 | 80 | 3.75 | +0 |
| Block RAM Tile | 0 | 60 | 0.00 | +0 |

The wrapper adds only the register file + address decode over the evaluator core;
the 3371-LUT core still dominates, so the shrink note above applies unchanged.
Timing again not meaningful in OOC-no-XDC mode (real timing at island build,
FCLK0=50 MHz).

### Register/backend contract cross-check (host-side)

`sw/uart_stream_regs.h` offsets and `CTRL`/`STATUS` bit definitions match the RTL
decode in `uart_stream_island_regs.v` (CTRL bit0=start / bit1=clear-done; STATUS
bit0=busy / bit1=done / bit2=pass). The `tb_uart_stream_island_regs` smoke drives
this path and returns `status=0x6` (done+pass) on a known-passing vector. The
`autoehw_mmio_backend` write/poll sequence (clear-done → start → poll STATUS.DONE
with timeout) is consistent with the RTL; it is **compiled and host-consistent
only — not yet board-verified** (no real base address bound, no silicon).

---

## tpu_rp_rm_uart_stream — XBUS RM wrapper (commit 45a8ce3, synth-fixed)

DFX reconfigurable-module wrapper (`rtl/dfx/tpu_rp_rm_uart_stream.v`, module
`tpu_rp`) that keeps the zynq-ehw NEORV32 XBUS port contract and wraps
`uart_stream_island_regs` (island base 0xF0000000).

- **Part:** `xc7z010clg400-1`, `synth_design -mode out_of_context`, top = `tpu_rp`
- **Verdict:** **PASS after a Claude synth-fix** — see below. Post-fix: **0 errors,
  0 critical warnings**, 61 warnings (benign: wide unused XBUS bits — `xbus_sel`
  fanin, tied handshake nets — plus the inherited eval-core temporaries and OOC
  no-BUFG/no-XDC clock notes).
- **Date:** 2026-07-08

### Utilization

| Resource | Used | Avail | % |
|---|---|---|---|
| Slice LUTs | 3487 | 17600 | 19.81 |
| Slice Registers (FF) | 867 | 35200 | 2.46 |
| DSP48E1 | 3 | 80 | 3.75 |
| Block RAM Tile | 0 | 60 | 0.00 |

Essentially the island_regs wrapper cost (3480 LUT) plus the XBUS ack handshake.

### Synth-fix applied by the OOC gate (iverilog-passed, Vivado-rejected)

As delivered, the module declared `` `default_nettype none `` (line 1) but wrote
its ports in bare Verilog-2001 style (`input clk`, `output [31:0] xbus_dat_r`,
…). Icarus accepts this and the RTL smoke passed, but Vivado synth **failed with
21 errors** (`[Synth 8-6735] net type must be explicitly specified … when
default_nettype is none` / `[Synth 8-9844] non-net port cannot be of mode
input`). The two older RTL files avoided this by using explicit `input wire` /
`output reg`; only this new wrapper regressed.

**Fix (Claude, mechanical):** made every port explicit `input wire` / `output
wire`. Behavior unchanged — the RTL smoke still returns `status=0x6`. This is the
same class as the EHW-1.1-fabric lesson in `zynq-ehw`: *iverilog accepts what
Vivado synth rejects; the OOC gate is the real gate for board-bound RTL.*

**Note for ChatGPT:** when a module sets `` `default_nettype none ``, all module
ports need an explicit `wire`/`reg` net type, not bare `input`/`output`. Keep the
`input wire` / `output wire` style already used in `uart_stream_eval_core.v` and
`uart_stream_island_regs.v`.

---

## Not yet gated

- No pblock/resource-bound assertion in either OOC tcl yet — they report, they do
  not fail on a budget. Add a pblock + `report_utilization` threshold check when
  the DFX island is defined.
- No place/route, no timing signoff, no board result.
- `autoehw_mmio_backend` base address / timeout not yet bound to a real island.
