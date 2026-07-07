# zynq-autoehw — division of labour & workflow

This project is built by **two AIs with a human relay**, carried forward from
`zynq-ehw/docs/workflow.md`. This doc is the contract both sides follow. Read it
before contributing. Deltas from the `zynq-ehw` contract are marked **[Δ]**.

## Roles

| Who | Owns | Cannot do |
|---|---|---|
| **ChatGPT** (codegen) | writes `sim/`, `sw/`, `host/`, `tests/`, `rtl/` — oracles, portable-C twins, firmware, RTL, host gates | cannot touch the board; has no access to Claude's persistent memory |
| **Claude** (board + gatekeeper) | board bring-up, review, the **mandatory OOC synth/resource gate**, `git` commit/push, repo hygiene, `docs/board_results.md`, `docs/hw_notes.md` | should not author large new *features* (reviews/fixes/board, not primary author) — **[Δ]** except docs/reports (M0 is Claude-authored) |
| **Human** | the relay: carries files between the AIs, makes scope/decision calls | — |

**[Δ] Vivado access (2026-07-04 policy, supersedes the earlier ChatGPT-no-Vivado
rule):** ChatGPT may run Vivado for its own iteration, but **Claude's OOC
synth/resource gate and board verification remain mandatory and are the final
gate** — a ChatGPT "builds clean" is not accepted until Claude reproduces the OOC
gate and the board result. Writer-verifier separation is preserved by the gate,
not by denying the writer a tool.

## Hard rules

1. **Every hardware-bound deliverable ships with a host gate.** No board-targeted
   code is accepted without a host-side self-proof: deterministic host oracle +
   portable-C twin + bit-exact test + a golden cross-check against the relevant
   HW-verified oracle. ChatGPT can't see the board, so its code must be verifiable
   on the host first; Claude's board step then only confirms **board == host
   model**.

2. **Claude runs a fixed pre-commit checklist every time** (below). Nothing is
   committed until it passes.

3. **Neither side's "done" is trusted; each is the other's gate.** No conclusion
   from memory or assumption — only from a command actually run this session. (In
   `zynq-ehw` a Claude review once shipped a wrong blocker by misreading an
   arithmetic line; ChatGPT correctly rebutted it. The rule stands.)

4. **Hardware truth lives in the repo, not in one AI's head.** All board gotchas,
   mailbox addresses, and numeric conventions go in `docs/hw_notes.md` (created
   when M1 board work starts). Code is written against that file, not guesses.

5. **Isolation is absolute.** `external/` holds **read-only** copies of
   `zynq-ehw`, `zynq-xpart`, `zynq-agentctl`, and `Cyclone_CRAM_Mapper` for
   offline reference. Edit only the copies here; **never modify the source
   projects.** `external/` and `runs/` are gitignored — never commit them.

6. **[Δ] Contracts are versioned artifacts, not source references.** Cross-project
   interaction goes through the schemas in `docs/schema.md` (each with a
   `schema_version`), never through ad-hoc paths into a sibling repo. A champion
   is only "reported" if its `replay_bundle` reproduces it from artifacts alone.

7. **[Δ] Claims discipline (M0-derived).** Every board-facing milestone must map to
   a claim in `docs/tech_report.md` §1, honor that claim's non-claims, and be
   testable by its falsifier. A milestone that only re-demonstrates an
   already-completed `zynq-ehw` mechanism (see the distinctness ledger,
   tech_report §2.3) is **HELD**, not merged.

## Handoffs (both directions are files; the human carries them)

- **ChatGPT → Claude:** code + README updates + `docs/*_handoff.md` (what was
  built, what's incomplete, what board step is next).
- **Claude → ChatGPT:**
  - `review.vN.txt` — review with **file:line + evidence + a decisive test**.
    Deleted once resolved; stays local-untracked (the v1–vN convention).
  - `docs/board_results.md` — structured board observations: exact mailbox hex,
    pass/fail per vector, where/how it diverged.

## Claude's pre-commit checklist

Run before every commit; all must pass:

1. **Host gate green** — Py↔C bit-exact + golden cross-check. For any board-bound
   RTL, also the **Vivado OOC synth/resource gate** run by Claude (iverilog proves
   protocol behavior, not synthesizability or pblock fit).
2. **Board-verified** (hardware milestones only) — on-board result matches the
   host model; logged in `docs/board_results.md`.
3. **[Δ] FCLK0 preflight** (board runs only) — FCLK0 pinned to 50 MHz before
   `fpga loadb` (miner FSBL default is 125 MHz; mismatch caused EHW-5.2 wrong
   answers).
4. **Isolation** — `git -C <each sibling repo> status -s` empty (sources
   untouched).
5. **gitignore sanity** — no `external/`, `runs/`, `__pycache__/`, no staged file
   > ~500 KB.
6. **[Δ] Schema conformance** — any new/changed artifact validates against its
   `docs/schema.md` schema and bumps `schema_version` per the compatibility policy.
7. **Claims source-validated** — every assertion in the review/commit message is
   backed by a command actually run this session.
8. **Root-cause discipline for build-dependent bugs** — before blaming P&R / DFX /
   timing / settle / silicon: build a flat/non-DFX control when feasible; compare
   against an independent source of truth (ELF/objcopy, Python oracle, model),
   never the artifact under test; prefer same-firmware cross-build comparisons.

## Git policy

- Branch `main`. **Commit locally without asking; always ask the human before
  push** (human reviews first).
- Commit attribution is honest: state who authored vs who board-tested in the
  body. `Co-Authored-By: Claude` trailer.
- Remote: none yet. Before adding one, confirm branch is `main` (not `master`),
  and confirm the `.gitignore` excludes `external/`, `ref/`, `runs/`.

## Milestone ladder

See `docs/tech_report.md` §3 for M0→M5 PASS/HOLD/KILL criteria and §1 for the
claims each milestone must honor. M0 (this documentation set) is owned by Claude;
M1 board work resumes the two-AI flow above.
