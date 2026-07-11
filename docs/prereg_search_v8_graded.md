# Preregistered v8 graded-fitness screening plan

This document freezes the first graded-fitness search screening protocol before
any v8 Set A results are inspected. It follows the board-verified graded smoke:
Python, C, RTL simulation, and silicon MMIO register `0x38` now agree on
per-frame bit-match score. The search signal can therefore move from hard
CRC pass/fail to graded bit matches without changing the benchmark splits.

## Fixed benchmark regime

- Benchmark family: `uart_stream_v2_headroom` with graded train signal
- Genome contract: `uart_sampler_v2_headroom`, schema `2.0.0`
- Search train frames per condition: `64`
- Deep selection train frames per condition: `256`
- Final holdout frames per condition: `256`
- Search train frame-evals per candidate: `4 * 64 = 256`
- Final hard holdout evals per arm: `4 * 256 = 1024`
- Final graded holdout bit-count denominator: computed from condition packet
  lengths, reported as a secondary metric only
- Board-throughput reference for host screening: latest board-measured v2
  dense-train calibration, `evals_per_sec = 1592`
- Equal-budget arm count for v8 screening: `2`

The raw per-arm search budget remains:

```text
floor(1592 * 7200 / 2 / 256) = 22387 candidates
```

For the deep graded-selection variant, reserve `4 * 1024 = 4096` train
frame-evals for 256-frame re-scoring of the four island champions:

```text
floor((1592 * 7200 / 2 - 4096) / 256) = 22371 candidates
```

Host screening uses these fixed budgets. Board firmware must still run its own
speed probe before any confirmatory graded board run; if the measured graded
readback throughput differs, board-side candidate budget and heartbeat cadence
must be derived from that measurement, not from this host-screening constant.

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

## Primary and secondary metrics

Search and selection may use only train split graded bit-match score.
Holdout remains firewalled and is evaluated only after each arm champion is
locked.

Board eligibility is judged only on **hard holdout delta**:

```text
variant_hard_holdout_passes - random_hard_holdout_passes
```

This keeps the v8 gate on the same claim scale as v3-v7: "more decoded frames
on unseen holdout." Graded holdout delta is reported as a secondary diagnostic
metric and cannot by itself authorize a board run.

## Candidate variants

`random` remains the equal-budget baseline and is never removed. It is the
existing hard-fitness best-of-stream random arm from v3-v7. The hard-fitness
`pbil_island4_v6` arm is included as a control, so the screen can directly
measure the value of replacing the search signal with graded fitness.

| id | Description | Rationale |
|---|---|---|
| `pbil_graded_v8` | Single aggressive v4-PBIL arm using graded train score for elite selection and best tracking. | Minimal ML-in-GA test on the board-verified soft signal. |
| `pbil_island4_graded_v8` | Four independent aggressive graded-PBIL islands, same seed derivation as v6, selected by graded train score. | Carries forward the v6 result that islands reduce basin variance. |
| `pbil_island4_deep_graded_v8` | Same four graded islands, but choose the final island champion using 256-frame graded train re-score. | Tests whether deeper graded train evidence reduces left-tail basin selection without touching holdout. |
| `pbil_island4_v6` | Previous hard-fitness K=4 island arm. | Control only; not board-eligible unless it unexpectedly passes all thresholds under this same gate. |

No surrogate model, CMA-ES, benchmark-condition change, additional RTL change,
NV store work, or board-side replay bundle work is in scope for this screening
round.

## Screening gate on Set A

For each candidate variant, run same-seed comparisons against the random arm
over every Set A seed. Candidate budgets must match the ledger above:

- non-deep variants and random baseline: `22387` candidates;
- `pbil_island4_deep_graded_v8`: `22371` search candidates plus four
  256-frame train-only re-scores.

The selected board candidate must satisfy all of these criteria on final hard
holdout:

- wins on at least `10 / 16` Set A seeds;
- losses on at most `4 / 16` Set A seeds;
- mean hard holdout delta `(variant - random)` at least `+8 / 1024`;
- median hard holdout delta at least `+4 / 1024`;
- the 10th percentile of per-seed hard holdout delta is not below `-16 / 1024`;
- graded holdout wins, graded train wins, or median-only improvement are not
  sufficient if the hard holdout criteria fail.

If multiple variants pass, freeze exactly one by this preregistered tie-break:
highest mean hard holdout delta, then most hard holdout wins, then highest hard
holdout median delta, then highest hard holdout 10th percentile. If all four
tie, prefer the simpler rule in this order: `pbil_graded_v8`,
`pbil_island4_graded_v8`, `pbil_island4_deep_graded_v8`, `pbil_island4_v6`.

If no variant passes all criteria, no board run is authorized.

## Confirmatory board gate on Set B

After Set A screening, exactly one variant may be frozen for board confirmation.
The Set B board run is considered a confirmatory success only if:

- the board mailbox is bit-exact against the precomputed host golden;
- the selected variant beats random on final hard holdout for seed `0xB17D`;
- hard holdout delta is at least `+8 / 1024`;
- the board run reports its own graded-path speed probe and derives budget and
  heartbeat from that measurement.

Set B results must not influence variant selection. The gatekeeper may reproduce
and inspect Set A results for screening; Set B is used only once, after a single
variant is frozen.
