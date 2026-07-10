# Preregistered v3 search-screening plan

This document freezes the next search-side screening protocol before any v3
variant results are inspected. Its purpose is to avoid selecting a board
candidate from hidden trial-and-error.

## Fixed benchmark regime

- Benchmark: `uart_stream_v2_headroom`
- Genome contract: `uart_sampler_v2_headroom`, schema `2.0.0`
- Train frames per condition: `64`
- Final holdout frames per condition: `256`
- Train evals per candidate: `4 * 64 = 256`
- Final holdout evals per arm: `4 * 256 = 1024`
- Board-throughput reference for host screening: latest board-measured v2
  dense-train calibration, `evals_per_sec = 1592`
- Equal-budget arm count for v3 screening: `2`
- Per-arm candidate budget:

```text
floor(1592 * 7200 / (2 * 256)) = 22387
```

If a later candidate changes evals per candidate or the number of same-boot
arms, the budget must be recomputed with the same formula before any result is
read.

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

This seed is not used for variant selection. It is used only after a single
variant is frozen:

```text
0xB17D
```

The board firmware must use this seed instead of the historical
`AUTOEHW_BOARD_SEED=0xC0DE` for the confirmatory run. The drop must include the
host-predicted golden for the fixed `(variant, 0xB17D)` pair before the board
run starts.

## Candidate variants

All variants use the existing v2 genome, train/holdout firewall, and fake/MMIO
backend semantics. `random` remains the equal-budget baseline and is never
removed.

| id | Description | Notes |
|---|---|---|
| `current_hillclimb` | Existing `(1+1)` hill-climb: mutate current best, accept `candidate >= best`. | Control only; not eligible for board promotion unless it unexpectedly passes the same thresholds. |
| `restart_hillclimb_v3` | Divide the budget across 16 independent `(1+1)` restarts; return the best train champion across restarts. | Low-risk firmware change; same mutation operator as current GA. |
| `immigrant_hillclimb_v3` | Existing hill-climb, but every 64 candidates evaluate a fresh random immigrant instead of a mutation of current best. | Tests whether occasional global jumps are enough to beat best-of-stream random. |
| `beam4_ga_v3` | Keep a population of four elites; initialize with four random genomes, then mutate a pseudo-random elite and replace the current worst if the candidate is no worse. | Small-population diversity without new ABI or RTL. |

CMA-ES or other continuous-space optimizers are explicitly out of scope for
this screening round.

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
