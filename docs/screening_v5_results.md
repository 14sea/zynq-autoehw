# v5 PBIL stability screening — Set A results (gatekeeper record, 2026-07-10)

Executed exactly per `prereg_search_v5.md`: budget 22,387/arm, 16 Set A seeds,
`host/screen_v5_search.py --jobs 20 --json` (C twin, ~25 min). The v4 PBIL
control reproduced its round-2 numbers exactly (determinism verified). The
shared-PBIL refactor was regression-checked bit-exact against the pre-refactor
CLI before screening. Set B untouched.

## Verdict: **NO VARIANT BOARD-ELIGIBLE — no board run. All three stabilization hypotheses FALSIFIED; v4 PBIL remains the best arm.**

| variant | wins | losses | mean Δ | median Δ | p10 | eligible |
|---|---|---|---|---|---|---|
| pbil_eda_v4 (control) | 7 | 9 | **+5.94** | −5.5 | −22 | ✗ |
| pbil_stable_v5 | 5 | 11 | −12.50 | −12.5 | −64 | ✗ |
| pbil_restart_v5 | 4 | 12 | −20.25 | −18.0 | −80 | ✗ |
| pbil_hybrid_v5 | 5 | 11 | +2.50 | −4.5 | −26 | ✗ |

## Per-seed reading (the informative part)

- **Slower learning is strictly worse** (stable −12.5): at 22k budget, halving
  the learning rate and doubling the batch keeps the distribution too flat to
  exploit within the budget — it loses v4's big-win seeds (0x7AD0 +49→−23,
  0xD036 +38→−70) without eliminating deep losses (0x1357 −5→−62).
- **Restarts are destructive** (−20.25): resets discard learned structure and
  re-pay the burn-in cost; three additional −80s appear. The stall detector
  fires on the *normal* rarity of improvements at this pass rate, not on
  actual distribution collapse.
- **Hybrid is v4-lite** (+2.50): the 4/64 refinement slots mostly divert
  budget from sampling (bitflip chains already falsified in round-2); it
  does mitigate the v4 crash seed (0x2468 −84→−26) but trades away several
  v4 win seeds.
- **The crash-vs-win structure is seed-anticorrelated across arms**: v4's
  win seeds and hybrid/stable's win seeds barely overlap (e.g. 0x9CF2:
  v4 −8, stable +50, restart +52, hybrid +41). The instability is not a
  parameter defect — it is high run-to-run variance intrinsic to which basin
  the early distribution locks onto.

## Suggested round-4 direction (not frozen here)

The seed-anticorrelation points away from single-run tuning and toward
**variance reduction across independent runs within one arm's budget**:
K independent PBIL populations (islands) splitting the same 22,387 budget,
returning the best final champion by train score (an internal decision, no
extra holdout use). v4's aggressive parameters stay (they are the only ones
that produce big wins); K≈3–4 turns "half the seeds crash" into "crash only
if all K crash". Bigger init pool per island and best-of-K selection both
stay inside the existing prereg ledger rules.
