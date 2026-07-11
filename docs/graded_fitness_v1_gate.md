# Graded-fitness v1 host drop — gate record (2026-07-11)

Gate reproduction for the host-only graded-fitness drop
(`prereg_graded_fitness_v1.md` + oracle/C-twin implementation).

## Gates reproduced

- `make all`: 38 tests OK, RTL smoke green (RTL untouched — OOC standing).
- Graded smoke fixture generated (`host/run_graded_smoke.py --frames 8`).
- Independent C-vs-Python cross-check (gatekeeper script, 6 historical
  champions × train+holdout at 8 frames): **all 12 comparisons bit-exact**.

## Evidence-linkage verification (the load-bearing check)

The prereg decision boundary requires the graded score to "show the expected
locality on existing v4 diagnostic samples". Verified **by construction and
by execution**:

- `sim/uart_stream_v2.py:frame_bit_matches` is line-identical to
  `host/landscape_v4_probe.py:frame_soft_matches` (same payload+CRC path,
  same LFSR state derivation, same popcount).
- Programmatic identity check on 5 genomes (3 historical champions + 2
  arbitrary): `train_soft_score(g,16) == graded_score_split('train',g,16)`
  exactly.

Therefore the v4 landscape soft-locality measurements (top-decile bitflip_1
corr 0.766 CI[0.747,0.786]; champion-stratum P(child≥parent) 0.51 vs hard
0.38) apply verbatim to this graded score. Decision-boundary branch 1 is
satisfied: **preregistering the RTL/MMIO graded implementation is authorized
by the frozen rules.**

## Sanity notes from the smoke

- Graded scores sit at ~77–92% of total bits (noise floor is high, as
  expected — random bit agreement is ~50%, sampler structure adds the rest);
  the dynamic range between champions (~8050–9700/10496 train) is wide
  relative to hard scores (2–5/32), consistent with the finer signal the
  locality data showed.
- Hard/graded orderings visibly disagree on some champions (e.g.
  0x09571273ce: hard-train 4 > 0x60894268a2's 2, but graded 8088 < 9253) —
  exactly the discriminating-power difference the graded route is betting on.

## Scope kept

No RTL/firmware/MMIO/DFX changes; Set B untouched; no search screening run
(none authorized by this prereg).
