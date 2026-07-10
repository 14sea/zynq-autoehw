# Preregistered v4 search-screening plan

This document freezes the round-2 search-side screening protocol before any v4
search variant results are inspected. It follows the v4 landscape verdict:
hard-fitness locality exists only for `bitflip_1` at the
`random_stream_top_decile` parent stratum.

## Fixed benchmark regime

- Benchmark: `uart_stream_v2_headroom`
- Genome contract: `uart_sampler_v2_headroom`, schema `2.0.0`
- Train frames per condition: `64`
- Final holdout frames per condition: `256`
- Train evals per candidate: `4 * 64 = 256`
- Final holdout evals per arm: `4 * 256 = 1024`
- Board-throughput reference for host screening: latest board-measured v2
  dense-train calibration, `evals_per_sec = 1592`
- Equal-budget arm count for v4 screening: `2`
- Per-arm candidate budget:

```text
floor(1592 * 7200 / (2 * 256)) = 22387
```

Every candidate evaluated during initialization, learning, or local search
counts against the same per-arm budget.

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

This seed is not used for variant selection:

```text
0xB17D
```

After exactly one variant is frozen, the board firmware must use Set B instead
of the historical `AUTOEHW_BOARD_SEED=0xC0DE`. The drop must include the
host-predicted golden for the fixed `(variant, 0xB17D)` pair before any board
run starts.

## Candidate variants

`random` remains the equal-budget baseline and is never removed.

| id | Description | Rationale |
|---|---|---|
| `bitflip1_topdecile_v4` | Evaluate a 160-candidate random initialization pool, keep the best train-scoring genome, then spend the remaining budget on `(1+1)` hill-climb steps that flip exactly one bit and accept `candidate >= best`. | Directly tests the v4 landscape finding: locality exists for one-bit neighbors around top-decile random parents. |
| `pbil_eda_v4` | Evaluate the same 160-candidate random initialization pool, seed a 39-bit Q15 probability model from the top 16 genomes, then sample 32-candidate batches. Each batch updates the probability model toward its top 4 train-scoring samples with learning rate `1/8`, applies probability mutation toward 0.5 with rate `1/64`, and tracks the best train champion. | ML-integrated GA arm: online distribution estimation over the 39-bit genome. It is board-eligible because all state is small fixed-point integer state and candidate evaluation still uses the existing fabric evaluator. |
| `current_hillclimb` | Existing `(1+1)` control with the old 1-to-4-bit mutation operator. | Control only; not board-eligible unless it unexpectedly passes all thresholds. |

No surrogate model, graded-fitness benchmark, RTL change, or soft-score
selection is in scope for this screening round.

## Screening gate on Set A

For each candidate variant, run same-seed, same-budget comparisons against the
random arm over every Set A seed. The selected board candidate must satisfy all
of these criteria on final holdout:

- wins on at least `10 / 16` Set A seeds;
- losses on at most `4 / 16` Set A seeds;
- mean holdout delta `(variant - random)` at least `+8 / 1024`;
- median holdout delta at least `+4 / 1024`;
- the 10th percentile of per-seed holdout delta is not below `-16 / 1024`;
- train-only wins are not sufficient; a variant that fails the holdout criteria
  is not board-eligible.

If multiple variants pass, freeze exactly one by this preregistered tie-break:
highest mean holdout delta, then most wins, then highest median delta, then
highest 10th percentile. If all four tie, choose `bitflip1_topdecile_v4` over
`pbil_eda_v4` because it is the simpler mechanism directly implied by the
landscape diagnostic.

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
