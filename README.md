# zynq-autoehw

Single-board **autonomous** evolvable-hardware runtime on a recycled Zynq-7010
(EBAZ4205). Successor to [`zynq-ehw`](https://github.com/14sea/zynq-ehw) (complete
at `v1.2.0`), following the research-first roadmap in `zynq-ehw`'s
`docs/future_plan.md`.

`zynq-ehw` proved the *mechanisms* (VRC → ICAP → internal-ICAPE2 → memetic
GA×HW-SGD, all board-verified). This project makes a **different** claim: that a
board can run a **multi-hour evolutionary hardware loop with no PC in the
decision loop**, preserving persistent champions, replay logs, and self-recovery
from bad candidates — measured on a committed benchmark with a real holdout split.

## Status: M0 (technical report), pre-hardware

Per the roadmap, no board-facing line starts until the M0 report is review-clean.
M0 is **documentation only** — zero board-wedge risk. Deliverables:

| Doc | Purpose |
|---|---|
| [`docs/tech_report.md`](docs/tech_report.md) | claims ledger, non-claims, baselines, prior-art comparison, milestone kill criteria |
| [`docs/schema.md`](docs/schema.md) | versioned schemas: local-map, run log, replay bundle, safety whitelist, blacklist, write-budget |
| [`docs/benchmark.md`](docs/benchmark.md) | the committed benchmark: PL-generated UART-like stream + train/holdout/adversarial split |
| [`docs/workflow.md`](docs/workflow.md) | two-AI + human-relay process contract, inherited from `zynq-ehw` |

M0 **PASS** = claims ledger + non-claims explicit + baselines/prior-art written +
benchmark & holdout split specified + every schema carries a `schema_version`.

## Boundaries (inherited discipline)

- **Do not modify sibling repos.** `zynq-ehw`, `zynq-xpart`, `zynq-agentctl`,
  `Cyclone_CRAM_Mapper` are read-only sources; reusable assets are *copied* into
  `external/` (gitignored).
- **Neither AI's "done" is trusted** without a command or board result.
- **Board truth lives in the repo** (`docs/hw_notes.md` once hardware starts),
  not in one agent's head.

## Roadmap position

```
zynq-ehw (v1.2.0, DONE) ── reference ladder EHW-0..5.5
        │
        ▼
M0  technical report + contract schemas   ← THIS repo, now
M1  zynq-autoehw autonomous runtime + UART-like benchmark
M2  cyclone-fabric-cartographer (separate repo)
M3  XC7K70T open-routing (separate repo, sacrificial boards)
```
