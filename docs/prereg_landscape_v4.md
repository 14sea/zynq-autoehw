# Preregistered v4 landscape diagnostics

This document freezes the landscape-diagnostic protocol before any v4 probe
results are inspected. The goal is to decide whether the current
`uart_stream_v2_headroom` hard pass/fail fitness has exploitable locality, or
whether Claim B needs a benchmark/fitness revision before more GA work.

## Fixed regime

- Benchmark: `uart_stream_v2_headroom`
- Genome contract: `uart_sampler_v2_headroom`, schema `2.0.0`
- Train scoring frames per condition: `64` (`train_total = 256`)
- Holdout scoring frames per condition: not used by these locality probes
- Visible seed set: Set A from `docs/prereg_search_v3.md`
- Confirmatory Set B seed `0xB17D`: **not used**

All hard-fitness probes use the existing oracle/C twin semantics. Host-only
graded probes may compute extra oracle-derived scores, but any graded metric
that becomes board-eligible later will require RTL/MMIO work because the current
fabric evaluator exposes only a pass/fail bit.

## Parent strata

Each locality probe is reported separately for three parent strata:

| stratum | Parent source | Count |
|---|---|---|
| `uniform_random` | Fresh random genomes from Set A-derived streams | 256 |
| `random_stream_top_decile` | Top decile by 64-frame train score from random streams | 256 |
| `historical_champion` | Repeated historical board/search champions | 256 |

Historical champions are cycled in this fixed order:

```text
0x60894268a2
0x6a8ba845d4
0x09571273ce
0x08d590f3ee
0x4e85cbc206
0x6cbfb15fd8
```

For `random_stream_top_decile`, each Set A seed contributes a deterministic
stream of `160` random genomes, scored by 64-frame train score. The top `16`
genomes from each seed stream become the 256-parent stratum. Ties are kept in
first-seen stream order. No holdout or Set B information is used.

## Kernels

For each parent, generate `k = 16` children for each mutation kernel:

| kernel | Definition |
|---|---|
| `bitflip_1` | Flip exactly one raw genome bit |
| `bitflip_4` | Flip exactly four raw genome bits |
| `field_resample` | Resample one whole field: phase, threshold, majority index, or one tap byte |
| `full_random` | Ignore parent and draw a fresh random genome |

All child generation is deterministic from Set A-derived RNG streams. Each
parent/child is scored with the same 64-frame train score.

## Reported statistics

For each `(stratum, kernel)` pair, report:

- Pearson correlation between parent train score and child train score;
- bootstrap 95% CI for the correlation (`1000` resamples, fixed seed
  `0x51A7`);
- `E[child - parent]` in passed-frame counts out of 256;
- bootstrap 95% CI for `E[child - parent]`;
- `P(child >= parent)`;
- bootstrap 95% CI for `P(child >= parent)`.

Correlations must not be interpreted from point estimates alone; CI bounds are
part of the decision rule.

## Graded-fitness probe

The host oracle also computes a provisional soft score for each parent and child
using decoded CRC/payload mismatch distance rather than only frame pass/fail.
The preregistered question is whether this soft score has stronger locality than
hard pass/fail:

- report the same `(stratum, kernel)` statistics for the soft score;
- report hard-score/soft-score correlation on the same samples;
- do not change board firmware or RTL in this drop.

If the soft metric is selected by the decision rules below, a later drop must
explicitly plan the RTL/MMIO change needed to expose graded fitness on board.

## Decision rules

Use these rules after all statistics are generated:

1. **Hard-fitness locality exists** if any non-`full_random` kernel in
   `random_stream_top_decile` or `historical_champion` has:
   - correlation CI lower bound `> 0.15`; and
   - `P(child >= parent)` CI lower bound `> 0.30`; and
   - mean delta CI upper bound `> -4`.

   Next action: preregister a round-2 search using the best hard-fitness kernel
   and matching initialization stratum. Do not revise the benchmark yet.

2. **Hard-fitness locality does not exist, but soft locality exists** if no hard
   kernel passes rule 1, and any soft-score non-`full_random` kernel in
   `random_stream_top_decile` or `historical_champion` has:
   - correlation CI lower bound at least `0.20` higher than the matching hard
     correlation CI lower bound; and
   - `P(child >= parent)` CI lower bound `> 0.35`.

   Next action: stop GA tuning on the hard pass/fail benchmark and draft a
   graded-fitness benchmark/RTL plan.

3. **No exploitable locality found** if neither rule 1 nor rule 2 fires.

   Next action: mark v2 hard-fitness Claim B as unsupported for this benchmark
   and move to benchmark revision rather than additional local-search variants.

`full_random` is a reference distribution only. It cannot by itself establish
map-guided locality.

## Gatekeeper boundary

The gatekeeper may reproduce and inspect all Set A diagnostic outputs. Set B
remains untouched. These diagnostics do not authorize a board run.
