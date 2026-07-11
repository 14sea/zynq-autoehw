# v9 graded island sweep — Set A results (gatekeeper record, 2026-07-11)

Executed exactly per `prereg_search_v9_graded_islands.md`: K ∈ {6, 8} graded
islands vs the K=4 v8 control, same seed derivation (K the only variable),
budget 22,387/arm, 16 Set A seeds, C twin engine. K4 control reproduced v8
bit-exact. Set B untouched during screening.

## Verdict: **`pbil_island8_graded_v9` PASSES ALL FIVE CRITERIA — first board-eligible variant in seven screening rounds. Set B confirmatory board run is authorized per the frozen rules.**

| variant | wins | losses | mean Δ | median Δ | p10 | dilution vs K4 | eligible |
|---|---|---|---|---|---|---|---|
| pbil_island4_graded_v8 (control) | 12 | 4 | +30.75 | +25.0 | −18 | — | ✗ (control) |
| pbil_island6_graded_v9 | 11 | 5 | +27.94 | +14.0 | −18 | **FAILED** | ✗ |
| **pbil_island8_graded_v9** | **12 ✓** | **4 ✓** | **+32.94 ✓** | **+26.0 ✓** | **−9 ✓** | ok | **✓** |

(Gate: wins ≥ 10, losses ≤ 4, mean ≥ +8, median ≥ +4, p10 ≥ −16.)

- K=8 repaired the v8 tail: 0x2468 −42 → **+38**; worst remaining seed −18
  (0xCF25), second-worst −9 → p10 = −9, inside the −16 bar with margin.
- Mean/median both *above* the K4 control (+32.94/+26.0 vs +30.75/+25.0):
  no dilution penalty at ~2,798 candidates/island — the aggressive PBIL
  kernel still sharpens within that budget.
- K=6 is eliminated by the preregistered dilution criterion (median +14 <
  K4's +25) — the K-trend is not monotone seed-for-seed (island seed sets
  differ per K), which is exactly why the sweep tested both.

## Frozen board candidate

Per the prereg tie-break (single passer), the frozen variant is:

```
pbil_island8_graded_v9
```

## Set B confirmatory requirements (from the prereg, now in force)

1. Board firmware: frozen variant, seed **0xB17D** (Set B), graded-path
   speed probe on board, budget/heartbeat derived from that measurement.
2. Host-predicted golden for `(pbil_island8_graded_v9, 0xB17D)` committed
   **before** the board run.
3. Success = mailbox bit-exact vs golden AND hard holdout delta vs random
   ≥ +8/1024 for seed 0xB17D.
4. Set B is used exactly once. No re-rolls; a failure is a recorded failure.
