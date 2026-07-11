# zynq-autoehw — Technical Report

Status: M0 claims contract plus M1 closure ledger. Board evidence is recorded in
`docs/board_results.md`; this report summarizes what that evidence does and does
not establish.

This report is the M0 seed required by `zynq-ehw/docs/future_plan.md`. Its job is
to make the *claims* defensible **before** any board-facing line opens, so that
the new work cannot be confused with the already-completed `zynq-ehw` ladder.

**M1 closure, 2026-07-11.** Commit `27bc3d1` closes the M1 beats-random gate on
silicon for `uart_stream_v2_headroom` with graded train scoring and the frozen
`pbil_island8_graded_v9` search arm. The confirmatory Set B run used the
pre-registered seed `0xB17D`, derived its own board budget
(`eps=1570`, `budget=22078` candidates), ran PC-free for about 124 minutes, and
matched the host golden bit-for-bit. The hard holdout delta was `+113/1024`
(`128/1024` vs random `15/1024`). This closes the M1 runtime/search gate, not
Claim B and not a broad cross-benchmark generalization claim.

---

## 0. One-paragraph thesis

`zynq-ehw` (v1.2.0) proved a ladder of *mechanisms* — VRC search, live ICAP
LUT-INIT edits, per-eval internal ICAPE2, spare-route islands, and a memetic
GA×HW-SGD loop — each board-verified on an EBAZ4205. Those are **per-evaluation
capabilities**. `zynq-autoehw` asks a **runtime** question that the old ladder
never answered: *can one board sustain a long, autonomous evolutionary-hardware
loop — no PC choosing candidates or scoring fitness — while persisting champions,
logging replayable evidence, recovering from bad candidates without a power
cycle, and beating a random-search baseline on a **held-out** stimulus
distribution?* That is a systems + generalization claim, not a mechanism claim.

---

## 1. Claims ledger

Each claim states what is asserted, what is explicitly **not** asserted, why it
is distinct from `zynq-ehw`, and its falsification test. These mirror
`future_plan.md` Claims M1/M2/M3 and are the contract M1+ milestones must honor.

### M1 claim status as of commit `27bc3d1`

| Claim | M1 status | Evidence | Scope boundary |
|---|---|---|---|
| **A — autonomous runtime** | **PASS for the M1 runtime core.** The board ran multi-hour autonomous search with PC out of candidate selection and fitness, board-derived budget, live heartbeat, bit-exact replay against host golden, rejection/recovery scaffolds, and no power-cycle dependency. | `docs/board_results.md` multi-hour, v2/v9, graded-smoke, and Set B confirmatory entries. | NV champion storage and board-side replay-bundle emission remain engineering remainders; existing persistence evidence is a static-shell RAM restore ABI plus host-side replay fixtures. |
| **B — map-guided evolution** | **NOT TESTED in M1.** | None claimed. | Reserved for M2/local-map work. Current M1 result is search over a constrained genome, not a learned device-local map. |
| **C — held-out improvement** | **PASS for the M1 beats-random holdout subclaim on one benchmark/regime.** The final pre-registered Set B board run beat equal-budget random on 1024-frame hard holdout by `+113/1024`. | `docs/prereg_search_v9_graded_islands.md`, `docs/screening_v9_results.md`, `docs/v9_setb_confirm_golden.md`, and `docs/board_results.md`. | The broad Claim C wording still requires careful scope: this is one UART-like benchmark family, one budget regime, and the winning condition was discovered as graded train signal + K=8 PBIL islands through v3-v9 screening. It is not a claim of cross-device, cross-task, or adversarial-set generalization. |

### Claim A — Autonomous runtime is new work

> A single EBAZ4205 board can run a multi-hour evolutionary-hardware loop with no
> PC in the decision loop, preserving persistent champions, replayable logs, and
> self-recovery from bad candidates without a power cycle.

**Distinct from zynq-ehw because** EHW-2 and EHW-3.4 already proved *per-eval*
on-chip ICAPE2 reconfiguration. They did **not** prove any of the runtime
properties: long-running operation, PC-free candidate selection *and* fitness,
persistent champion storage with a write budget, automatic recovery without
unplugging, or post-run replay. In `zynq-ehw` the PC still orchestrated loads,
sampled the mailbox, and the "runs" were seconds-to-minutes with fixed
pre-staged candidate sets.

**Non-claims.** Not a claim of new reconfiguration *mechanism* (mechanism is
inherited). Not a claim of open-routing evolution (that is M3/K7). Not a claim of
multi-board or distributed evolution.

**Falsification (any one fails the claim):**
- a bad-but-safe candidate can wedge configuration so only a Type-C unplug
  recovers;
- the PC is still selecting candidates or computing fitness;
- a reported champion cannot be replayed from saved artifacts alone;
- telemetry cannot distinguish slow progress from a stuck run;
- champion persistence depends on unbounded NAND/QSPI/SD writes.

**Replay modes (must be kept separate):**
- *deterministic replay* — same recorded search seed + artifacts → same
  trajectory;
- *autonomous discovery* — the board may derive its seed from a local entropy
  source, but the chosen seed is recorded at run start and enters the replay
  bundle. **A PC-supplied seed is a test mode, not the autonomy headline.**

### Claim B — Local maps can drive evolution more safely than raw mutation

> A device-local map (learned or inherited inside a constrained island) can guide
> later hardware evolution more safely than raw bit mutation.

**Distinct from zynq-ehw because** `zynq-ehw` used *fixed, pre-authored*
substrates (a fixed CGP grid, a fixed spare-route island). It never built a map
of "which local tokens/templates are safe, observable, useful, stable" from
on-board measurement, nor used such a map to gate selection.

**Non-claims.** Not a claim to reconstruct a full public 7-series bitstream
database (that is prjxray's job, not ours). The map is **device-local** and may
be **behavioral** (record `source_A reaches sink_B`, delay score, stability) not
necessarily symbolic.

**Falsification:**
- map-selected candidates do not beat random *safe* baselines;
- map entries are not replayable across cold boot or reload;
- compatibility records drift without detection;
- the map cannot reject a known-bad composition case.

### Claim C — Generalization is measured, not assumed

> Adaptation improves a **held-out** stimulus distribution, not only the exact
> evolution cases.

**Distinct from zynq-ehw because** every `zynq-ehw` fitness number is a
**same-set deployment metric** — EHW-0.4 explicitly scored the GA on the same 40
samples it optimized; EHW-4/5 are same-set adaptation metrics. `zynq-ehw` never
made a holdout claim, and honestly said so. This project's benchmark
(`docs/benchmark.md`) is built around an explicit train/holdout/adversarial
split precisely so this claim can be tested.

**Non-claims.** Not a claim of cross-device transfer (Whitley-style physics
exploitation is explicitly out of scope). Not a claim of arbitrary-scale EHW; the
task stays small and reproducible.

**Falsification:**
- the evolved phenotype improves only the training/evolution set;
- holdout performance regresses while training fitness improves;
- temperature/clock/seed/stimulus changes destroy the reported behavior;
- a reward-hacking phenotype passes the narrow fitness harness but fails the
  task on holdout.

---

## 2. Baselines and prior-art comparison

### 2.1 Mandatory experimental baselines

A claim of "evolution works" is meaningless without a control. Every M1+ result
must report against these baselines on the **same evaluation budget** and the
**same holdout split**:

| Baseline | Purpose | Where required |
|---|---|---|
| **Random search, equal budget** | proves selection ≠ luck; the headline autonomy number must beat it on holdout | Claim A, Claim C |
| **Static / hand-coded phenotype** | proves adaptation buys something over a fixed reasonable design | Claim C |
| **Same-set vs holdout gap** | quantifies overfit; a large gap falsifies Claim C even if training fitness is perfect | Claim C |
| **Map-guided vs random-safe** | isolates the *map's* contribution from mere safe mutation | Claim B |
| **Deterministic-replay bit-match** | proves the champion is reproducible from artifacts, not hidden state | Claim A |

### 2.2 Prior art

| Work | What it did | How zynq-autoehw differs |
|---|---|---|
| **Thompson 1996** (XC6200 tone discriminator) | intrinsic direct-bitstream evolution on a documented part; exploited analog/physical device quirks | we stay **digital + contention-safe** (LUT-INIT / local-select / VRC / whitelisted templates); no physics exploitation, no cross-chip-fragile phenotypes |
| **Whitley et al., ISAL'21** (*Resurrecting FPGA Intrinsic Analog EHW*) | intrinsic analog evolution; evolved circuits die on sibling chips | we explicitly reject the analog/physics path; determinism + replayability are core claims, the opposite trade |
| **CoBEA, Hoffmann et al., GECCO'22** | framework for direct iCE40 bitstream manipulation, ~130× faster reconfig; names "Xilinx 7-series + DPR" as *future work* | we run on the **7-series part they named but did not target**, via prjxray bit-location + on-chip ICAP under a running soft-core (self-reconfiguring, not host+MCU rig). Borrowed: non-zero seed search, plateau-aware fitness, one-resident-process/diff-frames, CSV/HDF5 logs |
| **prjxray / prjtrellis** | open bitstream *databases* built by exhaustive fuzzing | we do **not** aim to complete a family DB; we build a **device-local** map (behavioral where unsymbolized), and treat prjxray as an inherited bit-location layer only |
| **Cyclone_CRAM_Mapper** (sibling, silicon-validated) | non-prjxray symbolic CRAM/LUT/route map + FASM/RBF toolchain + per-pip validation gate on Cyclone IV | shares the **map/log/replay vocabulary** this report defines, but its RBF/EPCS transport and recovery mechanics stay in a *separate* repo (`cyclone-fabric-cartographer`); its key lesson — single routes are mined but **composition** is the hazard — is imported directly into our safety model |
| **zynq-ehw v1.2.0** (direct predecessor) | board-verified EHW-0..5.5 mechanism ladder; all same-set metrics; PC-orchestrated short runs | we inherit every mechanism and add the **runtime + holdout-generalization** layer that ladder deliberately did not claim |

### 2.3 The distinctness test (M0 KILL criterion)

`future_plan.md` §M0 says M0 must **KILL/HOLD** if "claims cannot be distinguished
from already completed EHW-2/3.4/5.x work." The table below is the explicit
distinctness ledger:

| Property | zynq-ehw (done) | zynq-autoehw (new) |
|---|---|---|
| Per-eval on-chip ICAPE2 reconfiguration | ✅ EHW-2/3.4 | inherited, not re-claimed |
| Live ICAP LUT-INIT edit, no reset | ✅ EHW-0.5/1.2/3.3/5.5 | inherited |
| GA×HW-SGD memetic loop on-chip | ✅ EHW-4/5 | inherited |
| PC out of candidate-selection loop | partial (board GA) | **required + fitness also on-board** |
| Multi-hour run | ❌ | **claimed (Claim A)** |
| Persistent champion + write budget | ❌ | **claimed (Claim A)** |
| Self-recovery without power cycle | ❌ (power-cycled once) | **claimed (Claim A)** |
| Post-run replay bundle | ❌ | **claimed (Claim A)** |
| Device-local map guiding selection | ❌ (fixed substrates) | **claimed (Claim B)** |
| Held-out generalization | ❌ (same-set, stated) | **claimed (Claim C)** |

If a proposed M1 experiment lands only in the top three rows, it is **not** a new
claim and must be reworked or the milestone HELD.

---

## 3. Milestones and kill criteria

Condensed from `future_plan.md`; every milestone yields **PASS / HOLD / KILL**,
never just a task list. M0 owns only the first row; the rest are recorded here so
the claims ledger and the milestone gates stay in one document.

### M0 — this report (docs only, no board)

**PASS:** claims ledger exists · baselines + prior-art written · non-claims
explicit · UART-like benchmark + holdout split specified (`docs/benchmark.md`) ·
replay/log/manifest schemas carry version numbers (`docs/schema.md`).

**HOLD/KILL:** no single benchmark can be committed · claims cannot be
distinguished from EHW-2/3.4/5.x (see §2.3) · recovery/safety claims cannot be
tested.

### M1 — Zynq autonomous runtime (first board line, gated on M0 clean)

**PASS (all):** PC selects no candidates and computes no fitness · evals/sec
measured on the *real* reconfig+stimulus path before the long run · run window
derived from measured evals/sec × a generation/candidate budget (not an arbitrary
wall-clock) · champion survives reset/reload and replays · champion store named,
write budget enforced · search seed is a first-class run-log field · champion
beats random-search-equal-budget on **holdout** · a deliberately bad-but-safe
candidate is rejected and logged · recovery avoids power-cycling and does not lean
on a wedged PS path.

**KILL/HOLD:** any candidate can wedge config so only a Type-C unplug recovers ·
logs insufficient to reproduce the champion · PC still in the decision loop ·
evals/sec too low for the convergence budget · evolution does not beat random
search at equal budget · persistence writes unbounded / no wear budget.

**Closure verdict at `27bc3d1`: PASS for the M1 runtime/search gate, with scoped
remainders.** The board evidence satisfies the PC-free runtime, measured budget,
long-run telemetry, equal-budget random baseline, hard-holdout win, deterministic
host replay, and bad-candidate/recovery scaffold requirements. Champion restore
across logic reset and host-side replay fixtures are demonstrated, but the
non-volatile champion store and board-side replay-bundle emitter remain
engineering items. Claim B is outside M1.

### M2 — cyclone-fabric-cartographer (separate repo)

**PASS:** inherited `Cyclone_CRAM_Mapper` artifacts carry provenance +
conformance checks · map/log/replay schema survives one real candidate lifecycle ·
flash-budget state enforced · known `DO_NOT_FLASH` composition failures blocked by
the wrapper. **KILL:** the new repo modifies the source repos · flash writes used
as the hot eval path · composition failures cannot be represented/blocked.

### M3 — XC7K70T open routing (separate repo, sacrificial boards)

**PASS:** experiments on sacrificial K7 hardware, never the only EBAZ ·
Vivado-legal variants extracted to route templates · pre-write validity checker
rejects incompatible template compositions · readback/attestation + golden reload
exercised before GA. **KILL:** raw routing mutation proposed before a
template/validity layer · no tested golden reload · a composition cannot be
checked before write.

### M4/M5 — peripheral & compute adaptation

**PASS:** improvement measured on holdout, not training-only · power/temp/clock
sensitivity reported · a static baseline included · reward-hacking cases tested.
**KILL:** only same-set fitness improves · no reproducible stimulus generator ·
fitness cannot separate useful adaptation from artifact exploitation.

---

## 4. Safety model (imported, not rediscovered)

The runtime inherits `zynq-ehw`'s structural safety and `Cyclone_CRAM_Mapper`'s
composition lesson. These are **design constraints**, not debug notes.

1. **Mutation surface stays contention-safe.** M1 uses only already-proven-safe
   phenotype mechanisms: LUT-INIT, local-select fields, VRC islands, HW-SGD
   adaptation, the parameter window, and ICAP writes already bounded by existing
   contracts. No raw switch-matrix routing on the only board.
2. **Single template valid ≠ template set composable.** The Cyclone IV evidence
   is explicit: individual routes can be mined and byte-identical while their
   *composition* fails because selection-mux values are global-routing-dependent.
   A pre-write validity checker — one driver per node, at most one selected input
   per mux group, all diffs inside the whitelist, unknown overlaps `HOLD` — is the
   first defense; readback only proves the expected bits landed, not electrical
   safety.
3. **Recovery ladder.** `logic reset → known-good partial/golden reload → full
   bitstream reload`. A logic reset clears a stuck FSM but cannot remove a bad
   config from SRAM.
4. **FCLK0 preflight is mandatory.** The miner FSBL leaves FCLK0 at 125 MHz while
   DFX designs sign off at 50 MHz; every board run pins FCLK0=50 MHz before
   `fpga loadb` (`zynq-ehw/scripts/board-set-fclk50.py` lineage). This root-caused
   the EHW-5.2 wrong-answer failures.
5. **Persistence is budgeted.** Per-generation telemetry lives in RAM during the
   hot loop; non-volatile writes happen only on bounded events (new champion,
   periodic checkpoint, final report, operator request); the physical store and a
   per-run write budget are recorded. "Persistent champion" must never depend on
   unbounded flash/NAND writes.

---

## 5. What M0 deliberately does NOT do

- No RTL, firmware, or board bring-up. M0 is docs only; the first board line is
  M1.
- No repo split into `ehw-tools` / `ehw-bench` / `ehw-islands`. Those are split
  out *after* the contracts stabilize, not now.
- No commitment to a compute-adaptation demo before a peripheral-style benchmark
  passes holdout (`future_plan.md`: compute adaptation is higher-ambiguity, easier
  to overfit).
- No modification of any sibling repo.

## 6. M1 closure evidence

The final result was not a single lucky board run. It was a pre-registered
sequence of host screens, landscape diagnostics, RTL/board validation, and one
sealed Set B confirmation run.

| Step | Documents | Result |
|---|---|---|
| v3 hard-fitness screen | `docs/prereg_search_v3.md`, `docs/screening_v3_results.md` | All search variants lost to random; no board run. |
| v4 landscape diagnosis | `docs/prereg_landscape_v4.md`, `docs/landscape_v4_results.md` | Hard local structure existed only in narrow regions; soft/graded signal was much stronger. |
| v4-v7 hard-fitness search | `docs/prereg_search_v4.md` through `docs/prereg_search_v7.md`, matching screening results | PBIL and island variants improved median behavior but failed the pre-registered p10/win gates; no Set B use. |
| Graded fitness path | `docs/prereg_graded_fitness_v1.md`, `docs/prereg_graded_rtl_v1.md`, `docs/graded_fitness_v1_gate.md`, `docs/ooc_results.md`, `docs/board_results.md` | Python, C, RTL simulation, OOC, and board MMIO readback all matched; graded output added only about 1% LUT. |
| v8 graded screen | `docs/prereg_search_v8_graded.md`, `docs/screening_v8_results.md` | Graded signal improved the hard-holdout delta about 4.6x but missed p10 by `2/1024`; no board run. |
| v9 graded K-islands | `docs/prereg_search_v9_graded_islands.md`, `docs/screening_v9_results.md` | `pbil_island8_graded_v9` passed all Set A gates and authorized Set B. |
| Set B confirmation | `docs/v9_setb_confirm_golden.md`, `docs/board_results.md` | Single pre-registered board run with seed `0xB17D` passed mailbox-vs-golden, board-derived budget, and hard holdout delta `+113/1024`. |

Honest scope:

- The result is for `uart_stream_v2_headroom` under the measured M1 budget regime,
  not for arbitrary EHW tasks.
- The winning condition is the graded-fitness, K=8 PBIL-island search arm found
  through the documented v3-v9 process; raw hard-fitness hill climbing and
  earlier PBIL variants are explicitly falsified in this repo.
- The Set B board run is a pre-registered single-seed confirmation of the
  16-seed Set A evidence, not an independent large-sample replication study.
- Claim B remains untested.

Engineering remainder:

- Implement true non-volatile champion storage with a named physical store and
  enforced write budget.
- Emit the replay bundle from the board side, not only from host fixtures.
- Optionally clean up confirm-firmware bookkeeping that evaluated island-local
  holdout data then discarded it for the frozen final-report ABI.

---

## 7. M0 exit checklist (historical)

M0 passed before the first board-facing line. The checklist is kept here as the
root contract M1 was measured against:

- [x] claims ledger present with per-claim non-claims + falsifiers (§1)
- [x] mandatory baselines enumerated (§2.1)
- [x] prior-art comparison covers Thompson, Whitley, CoBEA, prjxray, Cyclone,
      zynq-ehw (§2.2)
- [x] distinctness ledger separates new claims from EHW-2/3.4/5.x (§2.3)
- [x] milestone PASS/HOLD/KILL criteria recorded (§3)
- [x] `docs/benchmark.md` commits one benchmark with train/holdout/adversarial
      splits + thresholds + replay seeds + expected telemetry
- [x] `docs/schema.md` defines local-map / run-log / replay-bundle / whitelist /
      blacklist / write-budget records, **each with a `schema_version`**
- [x] `docs/workflow.md` carries forward the two-AI process contract
- [x] a short external review pass (human or second model) finds no claim that
      collapses into already-done work
