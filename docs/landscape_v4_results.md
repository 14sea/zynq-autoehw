# v4 landscape diagnostics — Set A results (gatekeeper record, 2026-07-10)

Executed exactly per `prereg_landscape_v4.md`: 3 strata × 4 kernels × 256
parents × 16 children = 49,152 pairs, 64-frame hard + soft scoring, bootstrap
CIs (1000 rounds, seed 0x51A7). `host/landscape_v4_probe.py --jobs 20 --json`,
~6.5 h wall on 20 processes. Set B untouched. Full JSON preserved by the
gatekeeper (14 KB summary; raw per-pair rows not retained by the tool).

## Verdict: **prereg Decision Rule 1 FIRES — hard-fitness locality EXISTS.**

Exactly one (kernel, stratum) pair passes all three Rule-1 criteria:

**`bitflip_1` @ `random_stream_top_decile`**
- corr CI [0.577, 0.622] — lower bound 0.577 > 0.15 ✓
- P(child ≥ parent) CI [0.564, 0.596] — lower bound > 0.30 ✓
- E[child−parent] CI [−3.48, −3.03] — upper bound > −4 ✓

Near misses (each fails exactly one criterion):
- `field_resample` @ top_decile: corr [0.360,0.411] ✓, Pge [0.358,0.386] ✓,
  ΔE upper −5.75 ✗ (too destructive on average)
- `bitflip_1` @ historical_champion: corr [0.377,0.442] ✓, Pge [0.363,0.393] ✓,
  ΔE upper −7.65 ✗ (champions sit higher; single flips fall further)
- `bitflip_4` everywhere: Pge lower ≤ 0.25 ✗ (4 flips already ≈ teleport)

`full_random` behaves as the reference: corr ≈ 0 in every stratum.
(`uniform_random` stratum shows inflated corr/Pge for all kernels — the
zero-inflation artifact anticipated at prereg time; the decision rules
correctly exclude it.)

## Why the v3 variants lost despite locality existing

The production mutation operator `uart_v2_mutate_genome` flips **1–4 bits
uniformly** (mean 2.5). This diagnostic shows the locality signal lives
almost entirely at Hamming distance 1 and is largely destroyed by 4 flips
(corr 0.60 → 0.27 at top-decile). Every v3 variant inherited this operator;
none could exploit the distance-1 structure. The landscape was never the
whole story — the operator was too hot.

## Soft score (recorded, not acted on — Rule 1 pre-empts Rule 2)

The graded score shows uniformly stronger locality than hard pass/fail
(top-decile bitflip_1: corr 0.766 vs 0.599; champion stratum: 0.663 vs
0.411) and P(child≥parent) ≈ 0.51 at champions (vs 0.38 hard). Per prereg,
Rule 1 firing means **no benchmark revision now**, but this measurement
stands as strong evidence for a graded-fitness RTL path if round-2 stalls
near champion-level scores, where hard-fitness locality visibly thins.

## Preregistered next action (Rule 1)

Preregister a round-2 search built on:
- mutation kernel = `bitflip_1` (exactly one bit per candidate);
- initialization = top-decile-style seeding (random pool → keep best), the
  stratum where the passing signal was measured;
- same equal-budget random baseline, same Set A screening gate as v3
  (`prereg_search_v3.md` thresholds), Set B still reserved.

Mean drift is negative even for bitflip_1 (−3.2 frames/step), so plain
accept-if-better hill-climbing remains rational (selection filters the
drift); the corrected operator is the change under test. EDA/PBIL-style
distribution learning over the 39 bits is a natural second arm under the
same prereg.

## Tooling notes for the next probe drop

- `evaluate_pair` re-scores the parent for all 16 children (~2× total work);
  cache parent scores.
- Soft score exists only in the Python oracle (~3.5 s/genome); port to the
  C twin before any screening that uses it.
