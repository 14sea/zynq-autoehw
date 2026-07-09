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

### What M1-foundation now establishes on silicon

The uart_stream autonomous train-only loop runs end-to-end on the EBAZ4205 and
its result is **bit-exact to the host oracle**: NEORV32 (no PC in the
candidate-selection or fitness loop) drives the fabric evaluator island over XBUS,
runs 512 evals, selects the golden champion (phase=15), and reports train 19/32 /
holdout 17/32 — matching `sim/uart_stream_v1.py` exactly. Control plane, fabric
evaluator, XBUS handshake, mailbox, FCLK0=50 signoff, and the reused NEORV32 DFX
shell are all confirmed on hardware.

This is a **foundation/smoke PASS**, not the full M1 Claim A/C PASS. Still pending
for full M1: measured evals/sec-derived long-run budget, equal-budget random
baseline evidence, replay bundle, champion persistence with write-budget
accounting, bad-candidate rejection/recovery, and the eventual multi-hour run.

Lineage of the three fixes it took: smoke #1 (XBUS DONE handshake never asserted)
→ smoke #2 (handshake fixed; eval arithmetic sim-vs-synth mismatch) → OOC fit-fail
(deterministic modulo blew the pblock) → smoke #3 (compact modulo + enlarged
pblock → full golden). No hardware damage; no power-cycle required across all
attempts.

---

## M1-full scaffold smoke — telemetry + replay words (2026-07-08) — **PASS ✅ (scaffold scope)**

Bitstream rebuilt with ChatGPT's M1-full scaffold firmware (commit `7d7c911`; RTL
untouched, so the smoke-#3 OOC/fit results stand). Firmware text=3560 B,
verify-image OK. New `dfx_top.bit` md5 `8fa3184d…`. Board was still at the U-Boot
prompt (no reset needed), FCLK0=50 preflight PASS (`0x00200a00` persisted),
`fpga loadb` OK.

### Observed vs expected — ALL 11 WORDS, first roll

| # | Observed (steady) | Expected | Verdict |
|---|---|---|---|
| 1–6 | `A7000000 A8001008 A90F05B7 AA013020 AB011020 AC000200` | foundation golden, unchanged | ✅ exact |
| 7 | `0xAD00C0DE` | seed=0xC0DE | ✅ exact |
| 8 | `0xAE007C7F` | tag 0xAE + plausible nonzero (board-measured, not host fake) | ✅ **31 871 evals/sec measured on the real fabric path** |
| 9 | `0xAF011020` | random equal-budget holdout 17/32 | ✅ exact |
| 10 | `0xB00013E8` | write_counter=1 / budget=1000 | ✅ exact |
| 11 | `0xB10F05B7` | persisted champion stub = phase15/maj5/thr-73 | ✅ exact |

Steady republish (11-word carousel, ~4.5 s/word), 2+ full cycles, no extras.

### Scope (explicit, per the consolidation decision)

This is the **M1-full scaffold**, not full M1 PASS:

- `AE` gives the first **real measured evals/sec = 31 871** (512 evals ≈ 16 ms on
  the fabric evaluator incl. MMIO overhead) — the number the M1 long-run window
  must be derived from.
- The random equal-budget baseline **ties** the champion on holdout (17/32 vs
  17/32) — so **no beats-random claim**; the benchmark/search needs headroom
  before Claim A/C can be tested (expected: this scaffold run uses the tiny
  budget-16 smoke configuration).
- Champion persistence is an in-RAM stub with a write-budget counter; it does not
  yet survive reset/reload.
- Host-side `run_log` / `write_budget` / `replay_bundle` JSON fixtures exist and
  are schema-versioned; the board does not emit them itself yet.

Still pending for full M1 (tech_report §3): multi-hour run with derived budget,
persistence across reset/reload, board-side replay bundle, beats-random on
holdout, bad-candidate rejection + recovery.

---

## M1-full persistence-restore scaffold — framebuf champion restore (2026-07-08) — **PASS ✅ (scaffold scope)**

Bitstream rebuilt with ChatGPT's framebuf restore scaffold (commit `92ac6b4`; RTL
untouched — OOC/fit stands). Firmware verify-image OK. `dfx_top.bit` md5
`b088a2d0…`. FCLK0=50 preflight PASS (persisted `0x00200a00`), `fpga loadb` OK
from the existing U-Boot prompt.

### Two-phase board sequence, both first roll

**Phase 1 — default (no external store):** all 13 words matched, tail
`0xB2000001 0xB3000000` (no store found, no restore). Measured evals/sec this
image: `0xAE007CEE` = **31 982** (consistent with the previous 31 871).

**Phase 2 — seeded restore across a logic reset:**
1. Seeded the champion-store record from the PS via U-Boot into the static
   `axil_framebuf` (`mw.l 0x40000000…` ×5: magic `CHMP`, meta, config
   `0x000F05B7`, budget 1000, checksum; `md` readback verified).
2. Pulsed `FPGA_RST_CTRL` (SLCR unlock → `0xF8000240`=0xF → 0x0) — the proven
   zynq-ehw EHW-5.4b logic-restart that reboots NEORV32 **without a bitstream
   reload** and preserves BRAM contents.
3. NEORV32 rebooted, re-ran the search, validated magic+checksum on the store at
   `0xF5000000`, and restored the champion: all 13 words matched with tail
   **`0xB2010101 0xB30F05B7`** (restore-success status + restored champion
   phase=15/maj=5/thr=−73). No extras, steady carousel.

### Scope (explicit)

This proves the **restore ABI across a logic reset**: a champion record written
by the PS into the static-shell framebuf survives `FPGA_RST_CTRL` and is
validated (magic + checksum + config-validity) and restored by firmware on
reboot. It is **not** non-volatile persistence — the record lives in static-shell
RAM and would not survive a full reconfiguration or power cycle. NV champion
storage (QSPI/SD/NAND) with a real write budget remains open for full M1, along
with: multi-hour run with derived budget, board-side replay bundle emission,
beats-random headroom, and bad-candidate rejection + recovery.

---

## M1-full bad-candidate rejection + recovery scaffold (2026-07-08) — **PASS ✅ (scaffold scope)**

Bitstream rebuilt with ChatGPT's rejection/recovery scaffold (commit `e8ad35c`;
RTL untouched — OOC/fit stands). verify-image OK, `dfx_top.bit` md5 `5598d4dc…`.
FCLK0=50 preflight PASS, `fpga loadb` from the existing U-Boot prompt.

### Observed — ALL 15 WORDS, first roll

First 13 words unchanged (default-mode tail `B2000001/B3000000`; measured
`0xAE0076E4` = 30 436 evals/sec, consistent with the 30–32k band). New tail:

| # | Observed | Meaning | Verdict |
|---|---|---|---|
| 14 | `0xB4010101` | injected illegal-but-safe config (phase=99/thr=0/maj=4) **rejected by the safety gate before eval** | ✅ exact |
| 15 | `0xB5010101` | post-rejection recovery probe: golden champion re-run through the **real fabric backend** (T0 frame 2) passes — known-good path intact | ✅ exact |

Steady 15-word carousel, 2+ cycles, no extras.

### Scope (explicit)

This is the **event/recovery scaffold**: a config-level safety gate rejects an
invalid candidate pre-eval, and a known-good probe confirms the evaluator path
is undamaged afterwards. It is **not** the full M1 recovery claim (raw-bitstream
bad candidate + ICAP/golden reload without power-cycle). Full-M1 remainder:
NV champion store + real write budget, multi-hour run with derived budget,
board-side replay bundle emission, beats-random headroom.

---

## M1-full paged mailbox extension (2026-07-08) — **PASS ✅ (scaffold scope)**

Bitstream rebuilt with ChatGPT's paged-mailbox scaffold (commit `388d7c7`; RTL
untouched — OOC/fit stands). verify-image OK, `dfx_top.bit` md5 `4e259022…`.
FCLK0=50 preflight PASS, `fpga loadb` from the existing U-Boot prompt.

### Observed — full 23-word carousel, checker PASS

Legacy 15-word prefix identical to the previous round (this image's
`0xAE007B48` = **31 560 evals/sec**, in the stable 30–32k band). Typed summary
page follows:

```
C0010006                          page header: page_id=1, count=6
C101000F C1007B48 C1011020        data: champion, evals/sec, holdout
C1000001 C1010101 C1010101        data: restore-status, reject, recovery
C2A51A87                          checksum (recomputed over board payloads: OK)
```

`python3 host/check_m1_mailbox.py < observed_words.txt` → **PASS** (handles the
board-varying AE payload and recomputes the page checksum — the C2 word differs
from the host fixture exactly because the board's measured evals/sec differs).

### Measurement-method note (for future paged extensions)

The soc_dfx mailbox is a latched register, so **two consecutive identical words
are invisible as a transition** — the summary page legitimately publishes
`C1010101` twice (reject + recovery payloads are equal), and a distinct-value
poller collapses them to one. Resolution: dwell-time analysis — every word dwells
~4.8 s, while `C1010101` dwelt 8.5 s / 9.8 s across two independent cycles
(≈2× single dwell), proving the duplicate publish. The full 23-word sequence
reconstructed with that duplicate passes the checker. Recommendation for the
next page revision: fold a 1–2-bit sequence counter into each C1 word (payload
is 24 bits; top bits are free) so consecutive words are never byte-identical and
a plain latched-register poll suffices.

### Scope

Paged, checksummed telemetry ABI board-verified (legacy prefix + typed page).
This closes the mailbox tag-space concern. Full-M1 remainder unchanged: NV
champion store + real write budget, multi-hour run with derived budget,
board-side replay bundle emission, beats-random headroom.

---

## M1-full page sequence counters (2026-07-08) — **PASS ✅**

Bitstream rebuilt with ChatGPT's sequence-counter fix (commit `babfd66`; RTL
untouched). verify-image OK, `dfx_top.bit` md5 `a74086d9…`. FCLK0=50 preflight
PASS, `fpga loadb` from the existing U-Boot prompt.

### Observed — full 23 words captured by a PLAIN latched poll, checker PASS

```
legacy 15 unchanged (AE007CEE = 31 982 evals/sec)
C0010006                                   header
C101000F C1407CEE C1811020 C1C00001        C1 data, seq 0,1,2,3
C1010101 C1410101                          C1 data, seq 0,1
C2A51D21                                   checksum (recomputed over decoded payloads: OK)
```

`host/check_m1_mailbox.py` → **PASS** (seq pattern 0,1,2,3,0,1 verified, payloads
decoded, checksum recomputed against the board's measured AE).

The previous round's measurement problem is confirmed fixed on silicon: the
formerly byte-identical consecutive pair (`C1010101 C1010101`) is now
`C1010101 C1410101` — **no adjacent identical words**, so a plain
distinct-value poll of the latched mailbox captures the complete carousel with
no dwell-time analysis needed. Telemetry ABI is now robust for future pages.

---

## M1-full derived long-run budget page (2026-07-08) — **PASS ✅**

Bitstream rebuilt with ChatGPT's budget-page scaffold (commit `354022e`; RTL
untouched). verify-image OK, `dfx_top.bit` md5 `61d20b9c…`. FCLK0=50 preflight
PASS, `fpga loadb` from the existing U-Boot prompt.

### Observed — full 31-word carousel, plain poll, checker PASS

Legacy 15 + page 1 unchanged in structure (this image `0xAE00788E` =
**30 862 evals/sec**). New page 2 (id=2, 6 payloads + checksum):

```
C0020006                       header: page_id=2, count=6
C1020078                       version=2, target=120 min
C1400020                       32 train frame-evals per candidate
C1BE99C0 C1C00034              target_evals  low/high 22-bit chunks
C129F4CE C1400001              cand_budget   low/high 22-bit chunks
C2B01F82                       checksum (recomputed: OK)
```

**Derivation verified exactly against the board's own measurement** (decoded by
hand, independently of the checker):

- `target_evals` = (0x34 << 22) | 0x3E99C0 = **222 206 400** = 30 862 × 7200 ✅
- `candidate_budget` = (1 << 22) | 0x29F4CE = **6 943 950** = 222 206 400 / 32 ✅

`host/check_m1_mailbox.py` → **PASS** (recomputes page 2 from the observed AE).
Sequence counters held (plain distinct-value poll captured all 31 words).

### Meaning

The board now derives its 2-hour long-run window from its **own measured
throughput** — the M1 PASS requirement "run window derived from measured
evals/sec × a budget, not an arbitrary wall-clock" has its on-silicon
arithmetic verified. The actual multi-hour run itself remains the open item,
along with NV champion store, board-side replay bundle emission, and
beats-random headroom.

---

## M1-full MULTI-HOUR autonomous run (2026-07-08→09) — **PASS ✅ (the run itself)**

Long-run image built with `-DAUTOEHW_BOARD_LONGRUN_MODE`. verify-image OK,
`dfx_top.bit` md5 `3f757815…`. Board auto-booted to Linux between builds →
recovered to U-Boot via JTAG SLCR reset; FCLK0=50 preflight PASS; `fpga loadb`.
Monitored by `scratchpad/longrun_monitor.py` (stuck-alert 90 s, CH340-tolerant,
final-carousel autodetect).

### The run

The board first emitted the normal 31-word smoke, derived its own 2-hour
candidate budget from its measured throughput (page 2), then ran a train-only
search of that size against the fabric evaluator, publishing page-3 heartbeats
live (~every 10 s). **PC was pure observer — no candidate selection, no fitness.**

- Duration: **~116 min** (T+6950 s), 845 mailbox transitions logged.
- Heartbeat cadence: steady 8–10 s throughout; **0 stuck alerts, 0 serial errors**.
- Completed: **generation = 6,968,250 candidates**, **evals = 222,984,000**
  frame-evals (= 6,968,250 × 32 exactly; monotonic; final marker `0x0300F1`
  present). Both `check_m1_mailbox.py` and
  `check_longrun_live_mailbox.py --require-final` → **PASS**.

### Result — the long run found a better train champion, bit-exact to the oracle

| | phase | thr | maj | train | holdout |
|---|---|---|---|---|---|
| longrun champion (final page-3 + tail) | 16 | 56 | 5 | **22/32** | 17/32 |
| smoke champion (budget-16) | 15 | −73 | 5 | 19/32 | 17/32 |

Host oracle cross-check of the longrun champion: train **22/32**, holdout
**17/32** — bit-exact to the board's `aa016020` / `ab011020`. The 2-hour search
genuinely improved train fitness (19→22) with far more budget.

### Scope (explicit, honest)

- ✅ **The multi-hour autonomous run is silicon-verified**: long-running,
  PC-free candidate selection *and* fitness, budget derived from measured
  throughput (not arbitrary wall-clock), live telemetry that distinguishes
  progress from stuck (the 845-heartbeat monotonic log with 0 alerts *is* that
  evidence), champion bit-exact to the oracle.
- ❌ **Not beats-random on holdout.** Train improved 19→22 but holdout stayed
  17→17 (same as the random baseline). This is expected and now quantified: the
  config space is only 32×256×3 = **24,576 points**, and 6.97 M candidates
  covers it ~280×, so both the search and random find the holdout optimum; train
  optimization does not transfer to holdout. This is a clean train/holdout-gap
  demonstration, and the **evals/sec-driven quantification is itself the key
  input for designing a harder benchmark** where beats-random becomes testable.
- Persistence remains the framebuf/logic-reset restore ABI (not NV); replay
  bundles remain host-side. Those + a headroom benchmark are the remaining
  full-M1 (Claim A/C) items.

---

## M1-full v2 headroom A/B on-board (MMIO decode path) (2026-07-09) — **PASS ✅ (plumbing smoke, not the verdict)**

Board image built with `-DAUTOEHW_BOARD_V2_AB_MODE` (firmware sources +
`sw/uart_stream_v2.c` + `sw/autoehw_firmware_v2.c`). **No RTL change** — the v2
39-bit genome is decoded in firmware to a per-condition effective sampler config
that drives the already-board-verified uart_stream MMIO island. `dfx_top.bit`
md5 `4c35407f…`, verify-image OK. FCLK0=50 preflight PASS, `fpga loadb`.

### Result

- v1 31-word prefix: `check_m1_mailbox.py` **PASS**.
- v2 A/B pages 4 (GA arm) and 5 (random arm), reconstructed positionally from the
  carousel, are **byte-for-byte identical to the host oracle's pages**:

| arm | genome (board) | genome (host) | train | holdout |
|---|---|---|---|---|
| GA (page 4) | `0x4e85cbc206` | `0x4e85cbc206` | 1/16 | 2/16 |
| random (page 5) | `0x6cbfb15fd8` | `0x6cbfb15fd8` | 2/16 | 2/16 |

So the whole v2 chain — 39-bit genome → firmware decode → **real fabric MMIO
evaluator** → same-boot A/B telemetry — runs on silicon bit-exact to the model.
The low-risk (no-RTL) path works.

### Scope (explicit)

This is the **v2 plumbing smoke, not the beats-random verdict.** The A/B ran at
the trivial smoke budget (16 candidates, 4 frames); GA 1/16 vs random 2/16 is
pure noise at that budget and carries no comparative meaning. The actual
beats-random judgment needs the large-budget (multi-hour) same-boot A/B on the
39-bit space, which is the next run.

### Two measurement-tooling notes (board was correct in both)

1. `check_v2_ab_mailbox.py` validates the host-stub's standalone 21-word
   `--v2-ab-mailbox-smoke` format (prefix `a7000000 a8001004 …`), which the board
   carousel does not emit — the board appends pages 4/5 after its normal 31-word
   v1 smoke (frames=8). The correct board gate is the v1 prefix checker plus a
   byte-match of pages 4/5 against the host golden.
2. My one-shot collector's global first-seen dedup dropped page 5's data words
   that are byte-identical to page 4's (both arms share holdout 2/16 → equal
   payloads across pages). Fixed by reconstructing one positional cycle from the
   timestamped transition trace (no dedup). Not a board or firmware issue.
