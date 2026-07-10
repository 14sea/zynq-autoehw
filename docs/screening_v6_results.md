# v6 multi-island PBIL screening — Set A results (gatekeeper record, 2026-07-10)

Executed exactly per `prereg_search_v6.md`: budget 22,387/arm split across K
islands, v4 aggressive PBIL kernel per island (verbatim reuse), train-only
island-champion selection, 16 Set A seeds, C twin engine, ~25 min. v4 control
reproduced exactly again. Set B untouched.

## Verdict: **NO VARIANT BOARD-ELIGIBLE — no board run. But the island mechanism WORKS, and the remaining failure mode is now isolated: winner's curse at island selection.**

| variant | wins | losses | mean Δ | median Δ | p10 | eligible |
|---|---|---|---|---|---|---|
| pbil_eda_v4 (K=1 control) | 7 | 9 | +5.94 | −5.5 | −22 | ✗ |
| pbil_island2_v6 | 8 | 8 | **+8.75** | +1.0 | −39 | ✗ |
| pbil_island3_v6 | 9 | 7 | +1.31 | +9.5 | −52 | ✗ |
| pbil_island4_v6 | **10** | 6 | +6.69 | **+10.0** | −47 | ✗ |

(Gate: wins ≥ 10, losses ≤ 4, mean ≥ +8, median ≥ +4, p10 ≥ −16.)

## What worked

Monotonic improvement with K on the consistency axes: wins 7→8→9→10,
median −5.5→+1.0→+9.5→+10.0. K=4 passes the wins and median criteria —
the variance-reduction hypothesis from v5 is confirmed. The v4 crash seed
0x2468 (−84) is fully repaired by K=4 (+10).

## What now fails: train-selection winner's curse

Every island variant still fails p10/losses, and per-seed data shows the
new deep losses are *created by the selection step*: on seeds where v4 was
mildly negative (0x69CF −7, 0x1357 −5, 0x0ACE −22), K-island arms pick an
island whose champion has *higher train* (e.g. 0x69CF: train 53 vs v4's 43)
but *worse holdout* (−47). More islands = more chances to select a
train-lucky/holdout-poor champion. The 16-deltas of K=3 and K=4 are nearly
identical — selection, not search, is the bottleneck now.

## Suggested round-5 direction (not frozen here)

Attack selection noise, keep K=4 search: re-score the K island champions on
a deeper train evaluation before choosing (e.g. 256 frames/condition instead
of 64, still train split only — no holdout access; cost 4×1024 evals ≈ 0.02%
of budget, ledger-compatible). Optionally require a challenger to beat the
incumbent by a margin on the deeper re-score. This directly reduces the
selection variance that p10 is catching, without touching the proven island
search. (Board-port note: the per-island discarded holdout evals inside the
reused v4 arm should be dropped in firmware.)
