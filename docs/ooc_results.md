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

---

## eval_core arithmetic-determinism fix (commit 8ba1413) — OOC **FIT FAIL** (pre-build gate)

The sim-vs-synth arithmetic rework (explicit `round_div_s32`, and the `%` operator
replaced by a hand-written 16-iteration restoring-division `mod_u16_by_u6`) is
functionally correct (host 384-vector gate PASS) and synthesizes 0 err/0 crit, but
the manual restoring-division is **much larger** than the Vivado-inferred divider
it replaced:

| module | before (smoke #2) | after 8ba1413 |
|---|---|---|
| `uart_stream_eval_core` | 3371 LUT | **4654 LUT** |
| `uart_stream_island_regs` | 3480 LUT | 4772 LUT |
| `tpu_rp` (the RM) | 3490 LUT | **4781 LUT** |

**Blocker:** the DFX RP pblock (`pblock_rp`, `SLICE_X22Y0:SLICE_X43Y49` = 1100
slices = **4400 LUT6**) cannot hold a 4781-LUT RM. The DFX build would fail
placement. **Caught by the OOC gate before the ~25-min DFX build** — its purpose.

**Recommendation to the RTL owner (avoids a golden re-baseline):** keep the modulo
numerically exact but drop the hand-rolled restoring division. The real sim-vs-synth
cause was the *mixed signed/unsigned* operands, not the `%` operator itself — so
keep Vivado's inferred `%` (which was compact, part of the original 3371 LUT) but
make its operands **explicitly unsigned with fixed width** (e.g.
`{16'd0,tmp_state1} % {26'd0, divisor6}` with both unsigned), matching the oracle's
unsigned remainder. That removes the ambiguity *and* fits the pblock. A 2^k-scaling
rework would also shrink it but would change the numbers and force a golden
re-baseline — not preferred. (If a bigger footprint is truly needed, the RP pblock
could be enlarged, but keeping the RM ≤4400 LUT is the clean path.)

---

## Graded-fitness RTL/MMIO plumbing (commit a46a429) — OOC PASS (gatekeeper run 2026-07-11)

All three OOC gates re-run with the graded score datapath
(`graded_score[9:0]` popcount+accumulator sharing the hard-compare XOR,
`UART_REG_GRADED_SCORE=0x38` readback): **0 errors / 0 critical warnings**
on `xc7z010clg400-1`.

| module | pre-graded (compact-modulo era) | with graded (a46a429) |
|---|---|---|
| `uart_stream_eval_core` | ~4100* | 4144 LUT / 758 FF / 4 DSP |
| `uart_stream_island_regs` | — | 4256 LUT / 886 FF / 4 DSP |
| `tpu_rp` (the RM) | 4223 LUT | **4266 LUT** / 929 FF / 4 DSP |

*eval_core standalone wasn't re-recorded in the compact-modulo entry; delta
derived from the RM: **graded costs ≈ +43 LUT (+1%)** — the datapath-sharing
approach worked as intended (the accumulator reuses the existing
decoded^source XOR; only the popcount tree and 10-bit register are new).

**Fit assessment:** RM 4266 LUT < 4400 LUT6 envelope of the *original*
quadrant pblock, and comfortably inside the current tracked pblock
(`rtl/dfx/pblock_rp.xdc`, full right half = 2200 slices = 8800 LUT6).
Slice-packing pressure is essentially unchanged from the board-proven
smoke-#3 build (FF count +~60). No DFX rebuild risk indicated. Board-facing
firmware/golden prereg may proceed.

---

## M1 addendum framebuf write port (commit 525ccaa) — **OOC HOLD / FAIL** (gatekeeper run 2026-08-01)

The delivered `external/shell/axil_framebuf.vhd` adds the NEORV32 write inside
the existing AXI write process. Behaviourally correct (GHDL smoke passes), but
**it does not synthesize**: Vivado cannot map two independent write sources onto
the RAM and dissolves the whole 2048×32 array into flip-flops.

```
WARNING: [Synth 8-4767]  Trying to implement RAM 'ram_reg' in registers.
                         Block RAM or DRAM implementation is not possible
WARNING: [Synth 8-13159] ... dissolved into (65536) registers bits
```

| variant | LUT | FF | BRAM | verdict |
|---|---|---|---|---|
| baseline (`zynq_ehw/rtl/axil_framebuf.vhd`) | 5 (0.03 %) | 4 | **4** | reference |
| **delivered 525ccaa** | **123 215 (700 %)** | 65 604 (186 %) | **0** | **unbuildable** |
| gate probe A: shared-variable TDP, 1 process/port | — | — | — | `ERROR [Synth 8-2914] Unsupported RAM template` |
| gate probe B: two half-size arrays, both read twice | 3 960 (22.5 %) | 101 | 0 | LUTRAM, still no BRAM |
| **gate probe C: param RAM untouched + separate store RAM** | **38** | 5 | **5** | **infers BRAM — viable direction** |

**Root cause.** A BRAM port carries one address bus, so a block RAM offers two
addresses total. The original topology is 1 write / 2 reads (AXI write, AXI
read, NEORV32 read) and Vivado satisfies it by replicating into 4 tiles. Adding
a second *write* source creates four independent addresses with two writers,
which no supported template covers. This is invisible to behavioural simulation
— the same class as the M1 smoke-#1 XBUS handshake and the smoke-#2 arithmetic
divergence.

**Viable direction (probe C, measured):** leave the PS param RAM byte-identical
— its topology and its board-verified PS path are then untouched by
construction — and add a *separate* store array for the board-origin record,
written by NEORV32 and read over AXI, muxed into the AXI read data by the
address MSB. Cost over baseline: **+1 BRAM tile, +33 LUT**.

Two constraints probe C must still satisfy, both found by reading the delivered
firmware rather than the RTL:

1. `champion_store_v2_current_write_count()` reads the record back, so the store
   array needs the **NEORV32 read port too** (1 write / 2 reads, i.e. the same
   topology the param RAM already proves) — not the write-only SDP of probe C.
   Expect one or two more tiles; there are 60.
2. The store and the restore paths are **different directions and must not share
   an address region**: restore is PS→board (PS writes over AXI, firmware reads)
   and stays in the param RAM; store is board→PS. The delivered firmware uses
   one `AUTOEHW_FRAMEBUF_BOARD_STORE_WORD` base for both, which the split
   topology cannot honour.

**Also flagged (not a blocker today):** the SoC registers the write, so the RAM
updates ~2 cycles after the XBUS write is acked. A read-back placed immediately
after a write would return stale data. Today's firmware appears to read the
write count *before* writing, which is safe — keep that order and state it as an
ABI rule.

No DFX build, no bitstream, no board: the gate stopped here. `525ccaa` stays
local and unpushed.

### Follow-up RTL fix submitted after HOLD (pending OOC)

The follow-up keeps the param/restore RAM and the board-store RAM as two
separate arrays:

- low half (`0..1023`): PS-written parameter/restore RAM, NEORV32-readable;
- high half (`1024..2047`): NEORV32-written board-store RAM, PS- and
  NEORV32-readable.

This removes the second writer from the original RAM template while preserving
the existing address convention (`0x40000000` low half for restore,
`0x40001000` high half for `fatwrite`). GHDL behavioural smoke covers
NEORV32-write/NEORV32-read, NEORV32-write/AXI-read, and AXI-write/NEORV32-read.
It is **not** an OOC PASS claim until Vivado confirms BRAM inference.

### Round 2 — split RAMs (commit 48b6f0a) — **still OOC FAIL**, cause isolated

Splitting into `param_ram` / `store_ram` removed the register explosion but the
array still does not reach block RAM:

| variant | LUT | LUT as Memory | FF | BRAM |
|---|---|---|---|---|
| baseline | 5 | 0 | 4 | **4** |
| 525ccaa (shared array, two writers) | 123 215 | 0 | 65 604 | 0 |
| **48b6f0a (split arrays)** | **3 958** | **3 456** | 68 | **0** |
| gate probe D: 48b6f0a + mux moved after the registers | **70** | **0** | 6 | **4** |

**Cause, isolated and verified by probe D:** both read processes select between
the two arrays *before* the output register —

```vhdl
if rd_addr(ADDR_BITS-1) = '1' then rd_data_r <= store_ram(ri);
else                              rd_data_r <= param_ram(ri); end if;
```

so one register is fed by two different memories and neither matches a RAM
template; Vivado falls back to distributed RAM (3 456 LUT of LUTRAM). Probe D
changes nothing else — same split, same address policy, same ports — and only
gives each array its **own** output register, muxing afterwards:

```vhdl
rd_param <= param_ram(ri);   rd_store <= store_ram(ri);
nrsel_r  <= rd_addr(ADDR_BITS-1);
...
rd_data  <= rd_store when nrsel_r = '1' else rd_param;
```

Result: **4 BRAM, 0 LUTRAM, 70 LUT** — back to the baseline tile count, +65 LUT
for the two post-register muxes. Same treatment is needed on the AXI read
(`rdata_param` / `rdata_store` + `rsel_r`).

**Rule for this file: each RAM read lands in its own dedicated register; the
half-select mux happens after the registers, never before.**

### Address directions — now correct

Re-audited against the firmware, both constraints from round 1 hold in 48b6f0a:

- board store base = word **1024** (high half) → NEORV32 write is permitted, and
  `champion_store_v2_current_write_count()` can read it back because the NEORV32
  read port now spans both halves.
- v1 restore reads words **0..4** (low half), which is where the PS can write —
  so store (board→PS) and restore (PS→board) no longer collide.

### Remaining functional gap (not an OOC matter)

Nothing converts a flushed v2 store back into low-half restore words:
`host/m1_persist_framebuf_words.py` still builds them from a hand-written
`SamplerConfig`. Until that exists the NV round trip
(store → `fatwrite` → power cycle → `fatload` → restore) cannot be closed on the
board, which is the whole point of the addendum.

### Round-3 follow-up submitted after OOC FAIL (pending OOC)

The RTL follow-up applies probe D's rule directly: each RAM now has its own read
output register (`param` and `store`), and the half-select mux is after those
registers for both AXI and NEORV32 read ports. This should preserve the split
topology while restoring the block-RAM inference template.

The host restore gap is also closed at the tool level:
`host/m1_persist_framebuf_words.py --from-store-hex <dump>` validates the v2
store record checksum and emits low-half `mw.l 0x40000000 ...` restore words.
That gives the board procedure a concrete bridge from the high-half
board-written store dump to the low-half post-power-cycle restore input.

GHDL behavioural smoke and `make all` pass locally. This remains **pending OOC**
until Vivado confirms BRAM inference and resource use.

### Round 3 (commit 222c51b) — **framebuf OOC PASS**

| variant | LUT | LUT as Memory | FF | BRAM | err / crit |
|---|---|---|---|---|---|
| baseline | 5 | 0 | 4 | 4 | 0 / 0 |
| **222c51b** | **72** | **0** | 6 | **4** | **0 / 0** |

Matches gate probe D (70 LUT) — read muxes now sit after the RAM output
registers, block RAM inference is restored, no distributed RAM. The framebuf
change is clear to go into a DFX build. Host gate independently reproduced:
44 tests OK.

### Round 3 blocker — the NV round trip does not close, and the new test hides it

`host/m1_persist_framebuf_words.py --from-store-hex` **byte-copies** the 16-word
v2 store record into low-half words 0..15. Verified by running it against a real
`--dump-store-window` dump: the emitted words are the v2 record verbatim,
starting `mw.l 0x40000000 0x43484d50` / `mw.l 0x40000004 0x00020000`.

The only firmware reader of the low half is `load_persisted_champion()`, which
reads words 0..4 and requires

```c
#define AUTOEHW_CHAMPION_STORE_VERSION 0x00010000u
...
(meta & 0xFFFF0000u) != AUTOEHW_CHAMPION_STORE_VERSION   ->  reject
```

The converted record presents `0x00020000` in that position, and the v1 layout
(word 1 = `meta`, word 2 = packed config, word 4 = checksum) does not match the
v2 layout at all. **The firmware will reject every restore produced by this
tool** — so `store → fatwrite → power cycle → fatload → restore`, the entire
point of the addendum, cannot close.

The new assertions do not catch it because they only check the emitted *text*
(16 lines, first two words, last address, and that `--from-store-hex` agrees
with the `md`-format parser). Nothing asserts that a restore actually happens.

**Recommended fix — firmware side, not converter side.** The v1 restore ABI
carries a `SamplerConfig` (phase / threshold / majority window) while a v2
champion is a 39-bit genome, so a v2→v1 conversion is lossy by construction and
must not be attempted. Instead give the firmware a **v2-aware restore reader at
low-half base 0** (validate magic + `0x00020000` + the 16-word checksum,
dispatch on the version word, keep v1 for the historical fixture). The
converter's byte-copy then becomes correct as delivered.

**Test requirement:** the round-trip test must drive the *restore*, not the text
— seed the host stub's low half with the converted words, run the restore path,
and assert the recovered champion equals the stored one. A green test over
formatting is what let this through.

**Gate decision:** no DFX build yet. The fix changes firmware, firmware is baked
into the bitstream's BRAM INIT, so a build now would be thrown away. Building
when the restore reader lands.

### Round-4 follow-up submitted after restore blocker (pending DFX)

The firmware follow-up keeps the converter's v2 byte-copy semantics and fixes
the actual consumer:

- `load_persisted_champion_v2()` reads low-half words 0..15, validates `CHMP`,
  schema `0x00020000`, the 16-word record checksum, and the 39-bit raw-genome
  range, then restores the v2 champion without converting it to the lossy v1
  `SamplerConfig` ABI.
- Page 15 keeps its original digest payloads in positions 0..7 and extends the
  page with restore status plus restored raw-genome chunks. A board observer can
  now require `restore_valid && restored_raw == stored_raw` after the
  power-cycle `fatload`.
- The host gate now drives the restore path: it generates a high-half store
  record, clears the fake framebuf to model reconfiguration, writes that record
  into low-half restore words, runs the firmware restore reader, and asserts the
  recovered v2 raw genome equals the stored one.

This resolves the false-green text-only test gap. RTL OOC remains the already
measured 222c51b result (72 LUT / 0 LUTRAM / 4 BRAM); the remaining gate is a
fresh firmware/DFX build and the physical NV round trip on the 4203.

### Round 4 (commit b78dfcc) — restore reader OK, **board firmware does not compile**

RTL untouched this round (`git diff 222c51b b78dfcc -- external/shell rtl/` is
empty), so the round-3 framebuf OOC PASS stands. Host gate reproduced: 44 tests
OK. The restore reader itself reviewed and correct — reads low-half words 0..15,
validates magic + `0x00020000` + the 16-word checksum, rejects a raw genome
wider than 39 bits, decodes losslessly.

**Blocker: `AUTOEHW_BOARD_STORE_DIGEST_MODE` fails to build for the board.**

```
autoehw_board_mbox.c:1379: error: 'board_eval_frame_graded' undeclared
autoehw_board_mbox.c:1399: error: 'publish_v9_confirm_progress' undeclared
```

The new board block at line 1376 uses two helpers whose *definitions* are still
guarded for V9-confirm only:

| line | guard | needs |
|---|---|---|
| 602 | `#if defined(AUTOEHW_HOST_STUB) \|\| defined(AUTOEHW_BOARD_V9_CONFIRM_MODE)` | `\|\| defined(AUTOEHW_BOARD_STORE_DIGEST_MODE)` |
| 934 | `#if defined(AUTOEHW_HOST_STUB) \|\| defined(AUTOEHW_BOARD_V9_CONFIRM_MODE)` | same |
| 956 | already includes `AUTOEHW_BOARD_STORE_DIGEST_MODE` | — |

One of the three guards was updated and two were not. **No host-side gate can
see this**: the stub build defines `AUTOEHW_HOST_STUB`, which pulls both helpers
in regardless. Only the cross-compiled board firmware exposes it.

**Second finding — the board mode would cost 2 h per iteration.** The
`STORE_DIGEST` block derives a full budget from measured throughput
(`v9_confirm_arm_budget(measure_v9_graded_evals_per_sec(...))`), i.e. it re-runs
the whole ~2 h Set B confirm before it writes the store. The existing smoke
paths use `AUTOEHW_V9_CONFIRM_SMOKE_BUDGET = 8`. The NV claim does not depend on
run length, and the round trip needs `store → fatwrite → power cycle → fatload →
restore` iterated in minutes. Recommend the store-digest board mode use the
smoke budget (or a build-time switch), keeping a long variant for later if
wanted.

**Third finding (host-only, no rebuild needed) — the checker still trusts a
board-computed flag.** Negative controls run against
`check_store_digest_mailbox.py`:

| control (page checksum recomputed each time, so the page is internally valid) | expected | actual |
|---|---|---|
| restore status cleared, `--require-restore` | FAIL | **FAIL** ✓ `restore status mismatch` |
| restore status cleared, no flag | PASS reporting `restore=no` | **PASS, restore=no** ✓ |
| **restored genome word flipped, status still claims restored+matches** | FAIL | **PASS** ✗ |

So the checker verifies that the board *claims* a matching restore, but never
compares the reported restored genome against the stored one. Given the standing
rule in this repo — recompute host-side, never fixed-compare a host fake — the
checker should cross-check payloads 9/10 against the stored raw genome rather
than trusting the match bit.

**Gate decision:** no DFX build. Firmware does not compile for the board, and
firmware is baked into the bitstream.

### Round-5 follow-up submitted after board-compile/checker blocker (pending DFX)

The firmware/checker follow-up addresses all three round-4 findings:

- The two V9 helper guards now also include `AUTOEHW_BOARD_STORE_DIGEST_MODE`,
  so `board_eval_frame_graded()` and the progress helper are visible in the
  board STORE_DIGEST build.
- The board STORE_DIGEST mode uses `AUTOEHW_V9_CONFIRM_SMOKE_BUDGET` and no
  progress callback. The NV round trip tests store/flush/power-cycle/restore;
  it must not re-run the full two-hour Set B confirm on every iteration.
- `host/check_store_digest_mailbox.py --require-restore --expect-raw-from-store
  <dump>` validates the v2 record checksum from the dumped store window and
  compares mailbox payloads 9/10 against the stored raw genome. A recomputed
  page checksum plus a forged `restored+matches` bit is no longer enough to
  pass.

The host unit test now includes that forged-payload negative control. The next
gate should include a board-mode compile-only check for
`AUTOEHW_BOARD_STORE_DIGEST_MODE`, then DFX and the physical 4203 NV round trip.

Local follow-up gates:

- `make all` PASS (44 tests plus RTL smoke).
- `make framebuf-vhdl-smoke` PASS.
- `cc -fsyntax-only -DNEORV32_H -DAUTOEHW_BOARD_STORE_DIGEST_MODE
  -DAUTOEHW_NO_MAIN ... sw/autoehw_board_mbox.c` PASS, covering the board-only
  STORE_DIGEST preprocessor path that host stub builds cannot see.
- A full `riscv64-unknown-elf-gcc` compile was attempted but the installed
  toolchain is missing standard newlib headers (`inttypes.h`), so that exact
  cross-compile remains for Claude's board toolchain.

### Round 5 (commit 966643c) — guards fixed, **firmware now overflows IMEM**

The three round-4 items are addressed: the mode guards compile, the board mode
uses the smoke budget, and `--expect-raw-from-store` makes the checker recompute
instead of trusting the board's match bit. Compilation gets past the guards.

**New blocker — link fails:**

```
ld: main.elf section `.text' will not fit in region `rom'
ld: region `rom' overflowed by 1884 bytes
```

`neorv32_soc_dfx.vhd` sets `IMEM_SIZE => 32*1024` and the fw Makefile pins
`__neorv32_rom_size=32k`, so the image must fit 32 768 B. The store-digest image
needs **34 652 B — 5.4 % over**, not a magnitude, but the linker is exact.

`--gc-sections` and `-ffunction-sections/-fdata-sections` are already on
(`common.mk:147-148`), so this is post-collection: the code is genuinely linked.
Per-object `.text*` totals (sum every `.text*` section — plain `size -A` hides
them under function sections):

| object | text | rodata |
|---|---|---|
| `uart_stream_v2.c.o` | 9 742 | 987 |
| `neorv32_aux.c.o` | 4 432 | 3 350 |
| `autoehw_firmware_v2.c.o` | 3 962 | 52 |
| `autoehw_board_mbox.c.o` | 2 670 | 8 |
| `uart_stream_v1.c.o` | 1 668 | 475 |

**Recommended fix — drop the search from this mode entirely.** The store-digest
mode still links the full graded v9 confirm search
(`autoehw_v2_firmware_confirm_island8_graded_v9`, ~4 KB, plus the graded
evaluation paths it keeps alive in `uart_stream_v2.c`), only with a smaller
budget. But the addendum claims persistence, not search: it needs *a* champion,
not an *earned* one. Seeding the frozen v9 champion as a constant and going
straight to store → digest → restore removes far more than 1 884 B, makes the
expected values fixed and host-checkable, and removes the last reason for this
mode to be slow. A separate minimal `main()` for the store test would have the
same effect.

Enlarging `IMEM_SIZE` to 64 KB is the alternative, but it perturbs a static
shell that just passed OOC and spends ~8 more BRAM tiles for a testability
problem. Not recommended while a trim is available.

**Gate decision:** still no DFX build — there is no linkable board image.

### Round-6 follow-up submitted after IMEM overflow (pending link/DFX)

The STORE_DIGEST board mode now tests persistence as a persistence path, not as
a fresh search:

- The board mode no longer calls `measure_v9_graded_evals_per_sec()`,
  `autoehw_v2_firmware_confirm_island8_graded_v9()`, graded MMIO evaluation, or
  progress publication.
- It emits the record/blob from the already board-verified Set B constants:
  eps `1570`, budget `22078`, variant raw `0x7c009161b2`, random raw
  `0x06c219610c`, hard holdouts `128/1024` and `15/1024`, graded holdouts
  `382336` and `332459`, and board-convention frame evals `5651968`.
- The STORE_DIGEST block now owns its carousel and does not fall through into
  the legacy M1 main loop.
- Unused page helpers are guarded by their actual modes, so the STORE_DIGEST
  board translation unit only references `uart_v2_encode_genome()` and
  `uart_v2_decode_genome()` from the v2 library.

Local compile-only evidence:

```text
riscv64-unknown-elf-gcc ... -DAUTOEHW_BOARD_STORE_DIGEST_MODE -c sw/autoehw_board_mbox.c
PASS

size -A /tmp/autoehw_board_store_digest.o
.text 1320
.rodata 88
Total 1490

nm -u /tmp/autoehw_board_store_digest.o
U uart_v2_decode_genome
U uart_v2_encode_genome
```

This does not replace Claude's full NEORV32 link, but it shows the overflow
cause has been removed from this translation unit: no PBIL/search/evaluator
symbols remain live in STORE_DIGEST mode.

### Round 6 (commit 93e0505) — **firmware links, DFX build PASS**

Store-only mode fixed the overflow decisively: image **1 640 B** (was 34 652 B
against a 32 768 B IMEM), `verify-image` OK, `image_size_c = 1640`.

Full DFX build: **0 errors, 101 critical warnings** (the known-good count),
routing completed with **0 failed nets**, `dfx_top.bit` 2 083 859 B
md5 `2e6d7f0d5e0330729b71f17312ecd643`. Utilization 8 080 LUT (45.9 %),
4 962 FF, **10.5 BRAM tiles**, LUT-as-Memory only 148 — the framebuf split kept
its block RAM, as the OOC probe predicted.

**Timing, and a correction to this repo's own lore.** WNS = **−19.394 ns**
against the previously recorded −17 baseline. The worst path is

```
Source:      u_soc/wb_tpu_inst/u_island/eval_core/noise_state_reg[4]/C
Destination: u_soc/wb_tpu_inst/u_island/eval_core/graded_score_reg[9]/D
Logic Levels: 61 (CARRY4=36 LUT2=6 LUT3=7 LUT4=2 LUT5=1 LUT6=9)
```

i.e. entirely inside the pre-existing RM evaluation datapath — **none of the
addendum's logic appears on it**, and the −17 → −19.4 delta is placement noise
on that same old path. Recorded for the record: the note carried in project
memory that this negative WNS comes from "the BD declaring FCLK high while we
sign off at 50" is **wrong**. The clock summary shows `clk_fpga_0` constrained
at exactly 20.000 ns / 50 MHz, and the path's data delay is 39.093 ns, so the
violation is real against the constraint. What is genuinely established is
empirical: this same path has produced bit-exact results for hours, across two
different dice, at 50 MHz. Why it does is *not* explained anywhere in this repo
— the likely reason is that the path is functionally multi-cycle (the island
runs a start/busy/done handshake, ~31 µs per frame evaluation) with no
multicycle constraint declared, but that has not been demonstrated. It should be
investigated and constrained properly, separately from this drop.
