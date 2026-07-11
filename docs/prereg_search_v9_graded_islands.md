# Preregistered v9 graded-island K sweep

This document freezes the v9 Set A screening protocol before any v9 results are
inspected. It follows the v8 graded-screen verdict: graded PBIL islands improved
the hard-holdout mean from `+6.69` to `+30.75` and repaired most left-tail
behavior, but the best graded island arm missed the p10 gate by `2 / 1024`
(`-18` vs required `>= -16`).

## Fixed benchmark regime

- Benchmark family: `uart_stream_v2_headroom` with graded train signal
- Genome contract: `uart_sampler_v2_headroom`, schema `2.0.0`
- Search train frames per condition: `64`
- Final holdout frames per condition: `256`
- Search train frame-evals per candidate: `4 * 64 = 256`
- Board-throughput reference for host screening: latest board-measured v2
  dense-train calibration, `evals_per_sec = 1592`
- Equal-budget arm count for screening: `2`
- Per-arm candidate budget: `floor(1592 * 7200 / 2 / 256) = 22387`

All K values use the same total per-arm budget. Increasing K therefore dilutes
the per-island budget:

| K | island budgets |
|---|---|
| 4 | `5597, 5597, 5597, 5596` |
| 6 | `3732, 3731, 3731, 3731, 3731, 3731` |
| 8 | `2799, 2799, 2799, 2798, 2798, 2798, 2798, 2798` |

K=8 is only a little over one order of magnitude above the 160-candidate PBIL
initial pool per island, so distribution sharpening may fail. This is the
explicit dilution risk being tested.

## Seed sets

### Set A — screening only

The host gate may inspect only these seeds while selecting a variant:

```text
0x1357 0x2468 0x369C 0x47AD
0x58BE 0x69CF 0x7AD0 0x8BE1
0x9CF2 0xAD03 0xBE14 0xCF25
0xD036 0xE147 0xF258 0x0ACE
```

### Set B — confirmatory board seed

This seed remains sealed until exactly one non-control variant passes Set A:

```text
0xB17D
```

The board firmware must use Set B instead of `AUTOEHW_BOARD_SEED=0xC0DE` for
the confirmatory run. The drop must include the host-predicted golden for the
fixed `(variant, 0xB17D)` pair before any board run starts.

## Fixed island seed derivation

All K values use the exact v6/v8 island seed derivation. No new salt is allowed:

```text
island_seed(i) = (arm_seed ^ 0x3000 ^ (i * 0x1F3D)) & 0xFFFF
if island_seed(i) == 0: island_seed(i) = 0xACE1
```

For K=6, `i = 0..5`. For K=8, `i = 0..7`. K is the only island-mechanism
variable under test.

## Candidate variants

`random` remains the equal-budget baseline and is never removed.

| id | K | Role |
|---|---:|---|
| `pbil_island6_graded_v9` | 6 | Candidate: tests whether more independent graded PBIL basins reduce the p10 tail. |
| `pbil_island8_graded_v9` | 8 | Candidate: stronger tail-coverage test, with explicit per-island dilution risk. |
| `pbil_island4_graded_v8` | 4 | Control only, reproduced under the same screener to keep v8 comparison bit-exact. |

No deep re-selection, restart/immigrant variants, surrogate model, additional
RTL change, NV store work, or board-side replay bundle work is in scope.

## Primary and secondary metrics

Search and selection may use only train split graded bit-match score. Holdout
remains firewalled and is evaluated only after each arm champion is locked.

Board eligibility is judged only on hard holdout delta:

```text
variant_hard_holdout_passes - random_hard_holdout_passes
```

Graded holdout delta is reported as a secondary diagnostic metric and cannot by
itself authorize a board run.

## Screening gate on Set A

For each candidate variant, run same-seed comparisons against the random arm
over every Set A seed. Candidate budgets must match the ledger above.

The selected board candidate must satisfy all of these criteria on final hard
holdout:

- wins on at least `10 / 16` Set A seeds;
- losses on at most `4 / 16` Set A seeds;
- mean hard holdout delta `(variant - random)` at least `+8 / 1024`;
- median hard holdout delta at least `+4 / 1024`;
- the 10th percentile of per-seed hard holdout delta is not below `-16 / 1024`.

Additionally, K=6 and K=8 have a preregistered dilution-failure rule:

- if a K candidate's mean hard holdout delta is below the K4 control's mean, the
  K candidate is eliminated as dilution backfire;
- if a K candidate's median hard holdout delta is below the K4 control's median,
  the K candidate is eliminated as dilution backfire.

The K4 control is not board-eligible in v9 by itself. It is present only to
measure whether increasing K helped or diluted the v8 graded-island result.

If both K=6 and K=8 pass all hard-holdout and dilution criteria, freeze exactly
one by this preregistered tie-break: highest mean hard holdout delta, then most
hard holdout wins, then highest hard holdout median delta, then highest hard
holdout 10th percentile. If all four tie, prefer `pbil_island6_graded_v9` over
`pbil_island8_graded_v9` because it is the smaller mechanism.

If no non-control variant passes all criteria, no board run is authorized.

## Confirmatory board gate on Set B

After Set A screening, exactly one non-control variant may be frozen for board
confirmation. The Set B board run is considered a confirmatory success only if:

- the board mailbox is bit-exact against the precomputed host golden;
- the selected variant beats random on final hard holdout for seed `0xB17D`;
- hard holdout delta is at least `+8 / 1024`;
- the board run reports its own graded-path speed probe and derives budget and
  heartbeat from that measurement.

Set B results must not influence variant selection. The gatekeeper may reproduce
and inspect Set A results for screening; Set B is used only once, after a single
variant is frozen.
