# v4 search screening — Set A results (gatekeeper record, 2026-07-10)

Executed exactly per `prereg_search_v4.md`: budget 22,387/arm (init pool
included in the ledger), train 64 frames, holdout 1024, all 16 Set A seeds,
`host/screen_v4_search.py --jobs 20 --json` (C twin engine, ~19 min).
Set B untouched.

## Verdict: **NO VARIANT BOARD-ELIGIBLE — no board run.** But PBIL is the first arm to beat random on mean holdout.

| variant | wins | losses | mean Δ | median Δ | p10 | eligible |
|---|---|---|---|---|---|---|
| bitflip1_topdecile_v4 | 3 | 13 | −17.94 | −24.5 | −63 | ✗ |
| current_hillclimb | 3 | 13 | −14.12 | −21.0 | −55 | ✗ |
| **pbil_eda_v4** | **7** | 9 | **+5.94** | −5.5 | −22 | ✗ |

(Gate: wins ≥ 10, mean ≥ +8, median ≥ +4, p10 ≥ −16.)

Train-side split (variant vs random, per-seed):

- bitflip1_topdecile_v4: train wins 2/16, mean train 33.3 vs random 41.0
- pbil_eda_v4: **train wins 12/16, mean train 45.8 vs random 41.0**

## Reading

1. **PBIL/EDA is a real signal.** First arm in two rounds to beat random on
   mean holdout (+5.94) and on train (12/16 wins). It fails the gate on
   consistency (7/16 wins, median −5.5): when it wins it wins big (+30…+58),
   but roughly half the seeds still land slightly negative, plus one crash
   (−84). Distribution learning over the 39 bits is the right family — the
   locality diagnostic's per-bit signal is being exploited.
2. **bitflip1_topdecile failed decisively — a useful falsification.** One-step
   locality (corr 0.60 at Hamming-1) does NOT compose into a good 22k-step
   trajectory: single-bit accept-if-≥ hill-climb walks into local traps early
   (train 33.3, *below* random's 41.0) and never escapes — worse than the old
   hot operator. The landscape supports *statistical* locality (PBIL-style
   aggregation) but not *greedy chains*.
3. Same-seed comparison of the ledger: all arms consumed exactly
   22,387 × 256 = 5,731,072 evals. Budget fairness verified in review.

## Suggested round-3 direction (for the next prereg; not frozen here)

Tune PBIL's consistency, not its peak: slower learning rate and/or larger
batch (variance of the model update), min-probability floor vs the observed
crash seed, possibly restart-on-stall of the probability vector. A hybrid
(PBIL sampling + occasional bitflip_1 refinement of the champion) is also
within the already-measured locality evidence.
