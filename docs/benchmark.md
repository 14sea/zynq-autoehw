# zynq-autoehw — benchmark package `uart_stream_v1` (M0)

The **one committed benchmark** M0 requires before any board line expands
(`future_plan.md` §Benchmark Driver, §M0 PASS). It is deliberately a
**peripheral-style** task, not a compute-adaptation task — compute adaptation is
higher-ambiguity and easier to overfit, and the roadmap forbids it until a
peripheral-style benchmark has passed holdout.

`benchmark_id: uart_stream_v1` · `schema_version: "1.0.0"`

---

## 1. Why this benchmark

```
PL stimulus generator ─► noisy / drifting UART-like bitstream
                       ─► evolvable sampler / decoder / filter
                       ─► CRC / pass-rate fitness
```

- **No dead-Ethernet dependency, no new peripheral board.** The stimulus is
  generated inside PL, so the benchmark runs on the EBAZ as-is. (The board's RJ45
  is a known-dead copper fault; this benchmark sidesteps it entirely.)
- **Controlled, replayable drift/noise.** The noise source is a seeded PL LFSR,
  so a holdout condition is exactly reproducible.
- **Simple, observable fitness.** CRC pass rate, frame error rate, latency,
  timeout count — all directly measurable on-board and emittable as mailbox words.
- **Natural holdout axes.** Unseen baud offsets, jitter patterns, seeds, packet
  lengths, and clock/temperature points are all held-out conditions the training
  set never showed.
- **Exercises the real adaptation pattern** needed later for genuine peripherals
  (UART/SPI sampling margin, noisy GPIO decode) without their electrical risk.

The evolvable phenotype is a **sampler/slicer**: sub-bit sampling phase, slicer
threshold, a small majority-vote / debounce window, and (later) a tiny local
filter — all expressible as LUT-INIT + local-select fields inside a fixed-route
island, i.e. contention-safe. Evolution never touches IO banks, global clocks, or
static PS/AXI logic.

---

## 2. Stimulus model

A PL generator emits UART-like frames (start bit, 8 data bits, optional parity,
stop bit) at a nominal baud, then perturbs them with seeded, bounded distortions:

| Distortion | Parameter | Controlled by |
|---|---|---|
| baud offset | `baud_ppm` | fixed per condition |
| timing jitter | `jitter_frac` (fraction of a bit period) | seeded LFSR |
| additive bit noise | `flip_prob` | seeded LFSR |
| edge slew / metastable sampling window | `edge_uncertainty` | fixed per condition |
| inter-frame gap drift | `gap_jitter` | seeded LFSR |

Each **condition** is a fixed tuple `(baud_ppm, jitter_frac, flip_prob,
edge_uncertainty, gap_jitter, lfsr_seed, packet_len)`. A condition is fully
replayable from its tuple. Frame payloads carry a CRC so correctness is
self-checking on-board with no golden transmission needed.

---

## 3. The split

Three disjoint stimulus sets. The training set is the only thing evolution scores
against during search; **Claim C is tested on the holdout set only after the
search is locked**, and the adversarial set is a stress/anti-cheat probe.

### 3.1 Training set (`train`)

Conditions evolution is allowed to optimize against.

| # | baud_ppm | jitter_frac | flip_prob | edge_unc | packet_len | lfsr_seed |
|---|---|---|---|---|---|---|
| T0 | 0 | 0.05 | 0.005 | low | 16 | 0x1111 |
| T1 | +200 | 0.08 | 0.010 | low | 16 | 0x2222 |
| T2 | −200 | 0.08 | 0.010 | med | 32 | 0x3333 |
| T3 | +500 | 0.12 | 0.020 | med | 32 | 0x4444 |

### 3.2 Holdout set (`holdout`) — never seen during evolution

Different baud offsets, jitter patterns, seeds, and packet lengths. Used **only**
to score a frozen champion after evolution. No candidate selection, mutation-rate
tuning, early stopping, or human "one more run" decision may use `holdout`
results. A champion that improves `train` but not `holdout` **falsifies Claim C**.

| # | baud_ppm | jitter_frac | flip_prob | edge_unc | packet_len | lfsr_seed |
|---|---|---|---|---|---|---|
| H0 | +100 | 0.06 | 0.008 | low | 24 | 0xA001 |
| H1 | −350 | 0.10 | 0.015 | med | 48 | 0xB002 |
| H2 | +650 | 0.14 | 0.022 | high | 12 | 0xC003 |
| H3 | −500 | 0.09 | 0.012 | med | 64 | 0xD004 |

### 3.3 Adversarial / noise set (`adversarial`)

Deliberately near/over the edge of what a safe sampler can recover — used to
detect **reward hacking** (a phenotype that games the narrow fitness harness) and
to map the failure boundary. Not part of the headline PASS number; reported
separately.

| # | condition | intent |
|---|---|---|
| A0 | `flip_prob=0.10` | beyond correctable → champion must degrade *gracefully*, not exploit |
| A1 | `jitter_frac=0.30` | sampling-window collapse |
| A2 | all-zero / all-one payloads | detect a phenotype that "passes" by ignoring data |
| A3 | CRC-valid but semantically degenerate frames | anti-cheat: fitness must track real decode, not a shortcut |

---

## 4. Fitness and thresholds

Primary fitness on a set S:

```
fitness(S) = mean over conditions in S of  frame_pass_rate
             where a frame "passes" iff CRC(decoded) == CRC(sent)
```

Secondary reported metrics (not folded into the headline number, logged per
`run_log`): frame error rate, mean/95th-pct decode latency, timeout count.

### PASS thresholds (M1 uses these)

| Gate | Threshold | Falsifies |
|---|---|---|
| **Beats random search** | champion `fitness(holdout)` > best random-search-equal-budget `fitness(holdout)` by a margin > noise band | Claim A / M1 |
| **Beats static baseline** | champion `fitness(holdout)` > fixed mid-phase / mid-threshold sampler `fitness(holdout)` | Claim C |
| **Generalizes** | `fitness(holdout) ≥ fitness(train) − gap_max`, `gap_max = 0.10` | Claim C |
| **No reward hack** | champion does not "pass" A2/A3 by a data-ignoring shortcut (checked by payload-sensitivity probe) | Claim C |
| **Graceful degradation** | on A0/A1 the champion's pass rate falls but stays ≥ a no-op sampler's | Claim C |

Concrete numeric bands (e.g. the "noise band" and static-baseline value) are
**measured, then frozen** during M1 bring-up from the actual PL generator and
recorded here as `uart_stream_v1.1`; M0 commits the *structure* and the *split*,
which is what §M0 PASS requires.

---

## 5. Replay seeds and telemetry contract

**Replay seeds.** Every condition's `lfsr_seed` is fixed above; the *search* seed
is separate and recorded in the `run_log` header (`search_seed`, `seed_source`).
A PC-supplied search seed is test-mode only (Claim A).

**Expected telemetry (mailbox / log words).** M1 firmware must emit, per the
`run_log` schema:

| Word class | Meaning |
|---|---|
| `gen`, `best_fitness(train)` | live convergence on the training set |
| `evals`, `evals_per_sec` | measured throughput (M1 PASS needs this *before* the long run) |
| `write_counter` | cumulative NV writes vs `write_budget` |
| event words: `new_champion`, `candidate_rejected`, `recovery` | bounded out-of-band events |
| `final_holdout_fitness` | emitted only after search is locked and the champion is frozen |

A run whose telemetry cannot distinguish "slow progress" from "stuck" fails
Claim A regardless of final fitness.

**Holdout firewall.** During the autonomous search loop, the board may report
`best_fitness_train` and operational telemetry only. `holdout_fitness` belongs to
the final evaluation record after the champion genome and phenotype hash are
frozen. If a run uses holdout results to guide candidate choice, tune parameters,
or decide whether to continue, it is a training result, not a Claim C result.

---

## 6. Package manifest

```yaml
benchmark_id: uart_stream_v1
schema_version: "1.0.0"
substrate: uart_sampler_island_v1        # -> phenotype_manifest in schema.md
sets:
  train:       [T0, T1, T2, T3]
  holdout:     [H0, H1, H2, H3]
  adversarial: [A0, A1, A2, A3]
fitness: frame_pass_rate_crc
thresholds:
  generalization_gap_max: 0.10
  beats_random: margin_gt_noise_band
  beats_static: true
  reward_hack_probe: payload_sensitivity
telemetry_fields: [gen, best_fitness_train, evals, evals_per_sec,
                   write_counter, events, final_holdout_fitness]
frozen_numeric_bands: pending_M1_measurement   # -> uart_stream_v1.1
```

**M0 status:** structure + splits + fitness + thresholds committed. Numeric bands
that depend on the real PL generator are measured and frozen in M1. This satisfies
§M0 PASS ("the UART-like benchmark and holdout split are specified").
