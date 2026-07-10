# v3 search screening — Set A results (gatekeeper record, 2026-07-10)

Executed exactly per `prereg_search_v3.md`: budget 22,387/arm, train_frames 64,
holdout_frames 256, all 16 Set A seeds, arms paired per seed
(variant `seed^0x4A4A` vs random `seed^0xBEEF`, the firmware derivation).
Harness: `host/screen_v3_search.py --jobs 20 --json` (C twin CLI, ~13 min
wall on 20 threads; 128 full-budget arms). Raw JSON preserved by the
gatekeeper; summary below is copied unedited.

## Verdict: **NO VARIANT IS BOARD-ELIGIBLE — no board run authorized.**

| variant | wins | losses | ties | mean Δ | median Δ | p10 | eligible |
|---|---|---|---|---|---|---|---|
| current_hillclimb | 3 | 13 | 0 | −14.12 | −21.0 | −55 | ✗ |
| restart_hillclimb_v3 | 5 | 11 | 0 | −18.62 | −11.5 | −73 | ✗ |
| immigrant_hillclimb_v3 | 5 | 11 | 0 | **−4.38** | −8.0 | −27 | ✗ |
| beam4_ga_v3 | 4 | 12 | 0 | −16.56 | −24.0 | −78 | ✗ |

(Δ = variant holdout − random holdout, out of 1024. Prereg gate required
wins ≥ 10, losses ≤ 4, mean ≥ +8, median ≥ +4, p10 ≥ −16.)

Per-seed deltas:

- current_hillclimb: −6 −20 −81 +49 −27 −7 −25 −25 +50 −26 −25 −17 −55 +20 −9 −22
- restart_hillclimb_v3: +9 +10 −14 +5 −42 −53 −60 −24 +85 −5 −73 +8 −9 −3 −59 −73
- immigrant_hillclimb_v3: −9 −82 −27 +47 +4 −7 −23 −24 +47 −7 +32 −21 −23 +49 −4 −22
- beam4_ga_v3: −9 −23 −82 +49 −25 +67 −23 −78 +29 −57 −22 −27 −26 +50 −63 −25

## Observations (gatekeeper, for the next iteration)

1. The dense-train board verdict is now reproduced across 16 independent
   seeds: equal-budget random best-of-stream beats every mutation-based local
   search tried, usually decisively. This is a property of the landscape at
   this budget, not a fluke of seed 0xC0DE.
2. Ranking by mean: immigrant (−4.4) ≫ current (−14) ≈ beam4 (−16.6) ≈
   restart (−18.6). The *more random sampling* a variant does, the better it
   fares — consistent with the hypothesis that mutation-local moves add ~no
   value here, and suggesting the natural next probes: much higher immigrant
   rates (e.g. 1-in-4, 1-in-2), stronger mutation kernels (multi-bit/field
   resample), or accepting that this benchmark's fitness landscape lacks
   exploitable local structure at ~6–8 % pass rates.
3. Per-seed variance is huge (Δ range −82…+85, σ ≈ 40): single-seed
   comparisons are nearly meaningless — the multi-seed prereg gate was the
   right instrument.
4. Landscape smoothness is now a benchmark-design question (M0 discipline):
   Claim B (map-guided > raw mutation) presupposes local structure that this
   task may not expose at this eval budget. Worth considering a benchmark
   revision (e.g. graded fitness instead of hard CRC pass/fail) alongside
   further search-side attempts.
