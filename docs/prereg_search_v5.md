# Preregistered v5 PBIL-stability screening plan

This document freezes the round-3 search-side screening protocol before any v5
variant results are inspected. It follows the v4 screening verdict:
`pbil_eda_v4` is the first arm to beat random on mean holdout, but it fails the
board gate on consistency. `bitflip1_topdecile_v4` is falsified as a greedy
chain and is not a board-eligible candidate in this round.

## Fixed benchmark regime

- Benchmark: `uart_stream_v2_headroom`
- Genome contract: `uart_sampler_v2_headroom`, schema `2.0.0`
- Train frames per condition: `64`
- Final holdout frames per condition: `256`
- Train evals per candidate: `4 * 64 = 256`
- Final holdout evals per arm: `4 * 256 = 1024`
- Board-throughput reference for host screening: latest board-measured v2
  dense-train calibration, `evals_per_sec = 1592`
- Equal-budget arm count for v5 screening: `2`
- Per-arm candidate budget:

```text
floor(1592 * 7200 / (2 * 256)) = 22387
```

Every candidate evaluated during initialization, PBIL sampling, probability
restart, or bitflip refinement counts against the same per-arm budget.

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

| id | Description | Rationale |
|---|---|---|
| `pbil_stable_v5` | Same 160-candidate initialization pool as v4 PBIL; seed a 39-bit Q15 probability model from the top 16 genomes; sample 64-candidate batches; update toward top 8 samples with learning rate `1/16`; mutate probabilities toward 0.5 with rate `1/32`; clamp probabilities to `[4096, 28672]`. | Lower update variance and higher probability floor should reduce the seed-to-seed crashes seen in `pbil_eda_v4`. |
| `pbil_restart_v5` | `pbil_stable_v5`, plus if no best-train improvement occurs across a 2048-candidate checkpoint, reset all probabilities to 0.5 while preserving the current best champion. | Tests whether PBIL's negative outlier seeds are distribution-collapse/stall failures. |
| `pbil_hybrid_v5` | Each cycle evaluates 60 PBIL-sampled candidates using the `pbil_stable_v5` probability update, then 4 `bitflip_1` refinements of the current champion. The 4 refinements can update the champion but are not included in the PBIL probability update. | Tests the measured Hamming-1 locality as a local polishing step without returning to a pure greedy chain. |
| `pbil_eda_v4` | Previous PBIL arm. | Control only; not board-eligible unless it unexpectedly passes all thresholds under the same gate. |

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
highest 10th percentile. If all four tie, prefer the simpler mechanism in this
order: `pbil_stable_v5`, `pbil_restart_v5`, `pbil_hybrid_v5`, `pbil_eda_v4`.

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
