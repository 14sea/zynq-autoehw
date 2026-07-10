# v7 deep-train island selection — Set A results (gatekeeper record, 2026-07-11)

Executed exactly per `prereg_search_v7.md`: K=4 v4-PBIL islands, deep variants
22,371 search candidates + 4×1024 deep train re-score (ledger-equal to the
22,387 control/random), 16 Set A seeds, C twin engine. Set B untouched.

## Verdict: **NO VARIANT BOARD-ELIGIBLE — no board run. Deep/margin selection is a holdout NO-OP: selection-side refinement of the train signal is now exhausted.**

All three arms produced *identical* 16-seed holdout deltas
(wins 10, losses 6, mean +6.69, median +10.0, p10 −47 — same as v6 K=4).

## Gatekeeper implementation audit (the important part)

Identical outputs triggered a bug audit before this verdict. Result: the
implementation is CORRECT and the identity is a real property of the
landscape:

- Independent re-computation of all 64 island champions (16 seeds × 4
  islands) shows the 256-frame train re-score *does* flip the island ranking
  on exactly 2/16 seeds (0x47AD: island 0→2; 0xD036: island 2→0).
- The screener JSON confirms both flips executed: on 0x47AD the deep arm
  returns a different champion genome (0x0810035f70 vs 0x6ee2254433); the
  margin arm correctly *rejected* that challenger (+1 < +8 margin) and kept
  the incumbent; on 0xD036 both deep and margin accepted the challenger
  (+10 ≥ +8).
- **In both flips, the new champion has exactly the same 1024-frame holdout
  score as the old one.** Champions' 256-frame train scores cluster tightly
  (155–198) and their holdout outcomes are indistinguishable.

## Reading

v6's "winner's curse" diagnosis is now sharpened into something stronger:
the selected island is not train-*lucky* — it is genuinely the best on 4×
deeper train evidence, and *still* its holdout is what it is. Within-arm
champion selection barely influences holdout at all. The left-tail seeds
(0x1357 −52, 0x69CF −47, 0x0ACE −39) are not selection errors; they are
basins where train quality genuinely fails to transfer. **No amount of
train-eval depth or selection conservatism will move the p10/losses gate.**

## Where this leaves the ladder

Search side: island4 remains the best arm (wins 10 ✓, median +10 ✓,
mean +6.69 ✗, losses 6 ✗, p10 −47 ✗). Three selection-side fixes and three
stability fixes are now all falsified with clean data.

The strongest remaining lever, per the v4 landscape evidence bank, is the
**graded (soft) fitness signal**: it showed uniformly stronger locality than
hard pass/fail (corr 0.766 vs 0.599 at top-decile; P(child≥parent) 0.51 vs
0.38 at champions) and would change the *signal* that both search and
selection consume — the axis every falsification so far points at. That
path requires the planned RTL/MMIO change (eval_core currently exposes
pass/fail only) plus a re-baseline of goldens, i.e. a deliberate
benchmark-revision drop per prereg_landscape_v4's Rule-2-style pathway —
a decision for the user + RTL owner, not this gate record.
