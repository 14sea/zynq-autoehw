# Preregistered v6 multi-island PBIL screening plan

This document freezes the round-4 search-side screening protocol before any v6
variant results are inspected. It follows the v5 screening verdict: single-run
PBIL parameter tuning did not stabilize performance, while seed-anticorrelated
wins/losses indicate that early basin lock-in variance is the likely failure
mode.

## Fixed benchmark regime

- Benchmark: `uart_stream_v2_headroom`
- Genome contract: `uart_sampler_v2_headroom`, schema `2.0.0`
- Train frames per condition: `64`
- Final holdout frames per condition: `256`
- Train evals per candidate: `4 * 64 = 256`
- Final holdout evals per arm: `4 * 256 = 1024`
- Board-throughput reference for host screening: latest board-measured v2
  dense-train calibration, `evals_per_sec = 1592`
- Equal-budget arm count for v6 screening: `2`
- Per-arm candidate budget:

```text
floor(1592 * 7200 / (2 * 256)) = 22387
```

All islands split this same per-arm budget. Initialization candidates, PBIL
samples, and any remainder candidates all count against the same ledger.

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

All multi-island variants use the original aggressive v4 PBIL inner loop:
160-candidate initialization pool, top-16 probability seeding, 32-candidate
batches, top-4 update, learning rate `1/8`, probability mutation toward 0.5
with rate `1/64`, and clamp `[2048, 30720]`.

For `K` islands, each island receives:

```text
floor(22387 / K) candidates, plus one extra candidate for the first
(22387 mod K) islands.
```

Island `i` uses seed `(arm_seed ^ 0x3000 ^ (i * 0x1F3D)) & 0xFFFF`, with zero
remapped to `0xACE1`. Each island returns its train champion. The arm returns
the island champion with highest train score; train ties are resolved by lower
island index, then first-seen order inside that island. Holdout is evaluated
only once on the selected arm champion after all islands finish.

| id | Description | Rationale |
|---|---|---|
| `pbil_island2_v6` | Two independent v4-PBIL islands split the same total arm budget. | Tests whether a small amount of independent basin sampling improves consistency without starving each island too much. |
| `pbil_island3_v6` | Three independent v4-PBIL islands split the same total arm budget. | Main variance-reduction candidate suggested by v5: crash probability falls if only one island needs to find a good basin. |
| `pbil_island4_v6` | Four independent v4-PBIL islands split the same total arm budget. | Tests whether further variance reduction beats the per-island budget loss. |
| `pbil_eda_v4` | Previous single-island PBIL arm. | Control only; not board-eligible unless it unexpectedly passes all thresholds under the same gate. |

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
highest 10th percentile. If all four tie, prefer fewer islands in this order:
`pbil_island2_v6`, `pbil_island3_v6`, `pbil_island4_v6`, `pbil_eda_v4`.

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
