# v8 graded search screening — Set A results (gatekeeper record, 2026-07-11)

Executed exactly per `prereg_search_v8_graded.md`: primary gate = hard holdout
delta (v3–v7 thresholds), graded holdout secondary, budget 22,387/arm
(deep 22,371), 16 Set A seeds, C twin engine. v4/v6 regressions bit-exact.
Set B untouched.

## Verdict: **NO VARIANT BOARD-ELIGIBLE — the graded island arms pass 4 of 5 criteria and miss the fifth (p10) by 2/1024. Per prereg, no board run is authorized.**

| variant | wins | losses | mean Δ | median Δ | p10 | eligible |
|---|---|---|---|---|---|---|
| pbil_graded_v8 | 12 ✓ | 4 ✓ | +22.62 ✓ | +29.5 ✓ | −60 ✗ | ✗ |
| pbil_island4_graded_v8 | 12 ✓ | 4 ✓ | **+30.75** ✓ | +25.0 ✓ | **−18** ✗ | ✗ |
| pbil_island4_deep_graded_v8 | 12 ✓ | 4 ✓ | +30.75 ✓ | +25.0 ✓ | −18 ✗ | ✗ |
| pbil_island4_v6 (hard control) | 10 | 6 | +6.69 | +10.0 | −47 | ✗ |

(Gate: wins ≥ 10, losses ≤ 4, mean ≥ +8, median ≥ +4, p10 ≥ −16.)

Secondary metric: every graded arm beats random on graded holdout **16/16
seeds** (mean +49,687/24,6016 bits ≈ +20%); even the hard-fitness control
wins 15/16 on graded — the two metrics are aligned in direction but hard
pass/fail keeps its heavier left tail.

## What the graded signal bought (control-based attribution)

Same search (K=4 islands, aggressive PBIL), same seeds, same budget — only
the train signal changed:

- hard holdout mean: **+6.69 → +30.75** (4.6×)
- p10: **−47 → −18**
- losses: 6 → 4
- the four deepest v6/v7 left-tail seeds all repaired or halved

Deep graded re-selection is again a no-op (identical 16 deltas to plain
graded islands) — consistent with v7's finding, now on the graded signal.

## The honest miss

p10 = second-lowest delta = −18 (seed 0xCF25), threshold −16. One seed
(0x2468, −42) and that near-threshold seed keep the tail. The gate exists
precisely to prevent "close enough" promotions; −18 < −16 is a fail, and
Set B stays sealed.

## Options for the next (prereg'd) round

1. More islands (K=6/8) on the graded signal — the K-trend (v6) and the
   graded tail-repair (this round) both point that way; cost is per-island
   budget dilution (K=8 → ~2800 candidates/island).
2. Graded + within-island restart or immigrant hybrids re-tested on the
   graded signal (v5's falsifications were on the hard signal; the graded
   landscape may reward them differently).
3. Accept threshold-adjacent evidence and stop: NOT available under the
   frozen rules — listed only to be explicit that it was considered and
   rejected.

Multiplicity note: iterating Set A rounds is within the discipline (Set A is
the exploration set), but every extra round raises the look-elsewhere burden
on the eventual Set B confirmation — one more reason the Set B run stays a
single-shot, fixed-variant, fresh-seed test.
