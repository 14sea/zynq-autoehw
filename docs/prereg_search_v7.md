# Preregistered v7 deep-train island selection screening plan

This document freezes the round-5 search-side screening protocol before any v7
variant results are inspected. It follows the v6 screening verdict: K-island
PBIL reduces crash variance, but selecting the island champion by the noisy
64-frame train score creates a winner's-curse failure mode.

## Fixed benchmark regime

- Benchmark: `uart_stream_v2_headroom`
- Genome contract: `uart_sampler_v2_headroom`, schema `2.0.0`
- Search train frames per condition: `64`
- Deep selection train frames per condition: `256`
- Final holdout frames per condition: `256`
- Search train evals per candidate: `4 * 64 = 256`
- Deep selection evals per island champion: `4 * 256 = 1024`
- Final holdout evals per arm: `4 * 256 = 1024`
- Board-throughput reference for host screening: latest board-measured v2
  dense-train calibration, `evals_per_sec = 1592`
- Equal-budget arm count for v7 screening: `2`
- Raw per-arm eval budget:

```text
floor(1592 * 7200 / 2) = 5731200 train evals
```

For K=4 deep-selection variants, reserve `4 * 1024 = 4096` train evals for
deep re-scoring. The PBIL search candidate budget is therefore:

```text
floor((5731200 - 4096) / 256) = 22371 candidates
```

For the K=4 control without deep re-score, the candidate budget remains:

```text
floor(5731200 / 256) = 22387 candidates
```

No holdout is used during search or island selection. Holdout is evaluated only
once after the arm champion is selected.

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

This seed remains sealed until exactly one variant passes Set A:

```text
0xB17D
```

The board firmware must use Set B instead of `AUTOEHW_BOARD_SEED=0xC0DE` for
the confirmatory run. The drop must include the host-predicted golden for the
fixed `(variant, 0xB17D)` pair before any board run starts.

## Candidate variants

`random` remains the equal-budget baseline and is never removed.

All variants use K=4 independent aggressive v4-PBIL islands with the same seed
derivation as v6:

```text
(arm_seed ^ 0x3000 ^ (island_index * 0x1F3D)) & 0xFFFF
```

Zero is remapped to `0xACE1`. Each island returns its 64-frame train champion.
Deep selection variants then evaluate all four island champions on 256
train-only frames per condition before choosing the arm champion.

| id | Description | Rationale |
|---|---|---|
| `pbil_island4_deep_v7` | K=4 PBIL islands, 22,371 total search candidates split across islands, then choose the island champion with highest 256-frame train re-score. Ties use lower island index. | Directly attacks v6's train-selection winner's curse with deeper train-only evidence. |
| `pbil_island4_margin_v7` | Same as `pbil_island4_deep_v7`, but keep the original 64-frame selected incumbent unless a challenger's 256-frame score exceeds it by at least `+8 / 1024`. | Tests whether a conservative margin reduces over-selection of train-lucky challengers. |
| `pbil_island4_v6` | Previous K=4 island arm with 22,387 candidates and 64-frame train selection. | Control only; not board-eligible unless it unexpectedly passes all thresholds under the same gate. |

No surrogate model, graded-fitness benchmark, RTL change, or soft-score
selection is in scope for this screening round.

## Screening gate on Set A

For each candidate variant, run same-seed comparisons against the random arm
over every Set A seed. Candidate budgets must match the ledger above:

- deep-selection variants: 22,371 search candidates plus 4 deep train re-scores;
- K=4 control and random baseline: 22,387 search candidates.

The selected board candidate must satisfy all of these criteria on final
holdout:

- wins on at least `10 / 16` Set A seeds;
- losses on at most `4 / 16` Set A seeds;
- mean holdout delta `(variant - random)` at least `+8 / 1024`;
- median holdout delta at least `+4 / 1024`;
- the 10th percentile of per-seed holdout delta is not below `-16 / 1024`;
- train-only wins are not sufficient; a variant that fails the holdout criteria
  is not board-eligible.

If multiple variants pass, freeze exactly one by this preregistered tie-break:
highest mean holdout delta, then most wins, then highest median delta, then
highest 10th percentile. If all three tie, prefer the simpler rule in this
order: `pbil_island4_deep_v7`, `pbil_island4_margin_v7`, `pbil_island4_v6`.

If no variant passes all criteria, no board run is authorized.

## Confirmatory board gate on Set B

After Set A screening, exactly one variant may be frozen for board confirmation.
The Set B board run is considered a confirmatory success only if:

- the board mailbox is bit-exact against the precomputed host golden;
- the selected variant beats random on final holdout for seed `0xB17D`;
- holdout delta is at least `+8 / 1024`.

If a three-arm board image is later used instead, the budget denominator must be
changed from `/2` to `/3`, each non-random arm must receive distinct final and
progress page ids, and host screening must be repeated under that three-arm
budget before any board run.

## Gatekeeper information boundary

The gatekeeper may reproduce and inspect Set A results for screening. Set B is
used only to generate the fixed host golden immediately before the board run,
after the variant is frozen. Set B results must not influence variant selection.
