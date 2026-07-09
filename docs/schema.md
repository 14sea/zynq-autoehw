# zynq-autoehw — contract schemas (M0)

Versioned artifact schemas so projects interact through **artifacts, not ad-hoc
source-tree references** (`future_plan.md` §Inter-Project Contracts). Every schema
here carries an explicit `schema_version`, a compatibility policy, and a note on
its standalone validator + conformance fixture (to be built in M1; specified now).

**Compatibility policy (all schemas):** MAJOR bump = incompatible field
change; MINOR bump = additive optional field. A consumer must reject a record
whose MAJOR differs from what it supports, and must ignore unknown MINOR fields.
Field encodings are little-endian unless a field says otherwise. All schemas are
shown as YAML for readability; the on-board/on-wire form may be a packed binary
whose layout is pinned by the `genome_contract` / `phenotype_manifest`.

**Freeze point:** this M0 document defines the initial `1.0.0` contracts. Review
edits made before the first M1 validators and conformance fixtures exist are part
of that initial freeze. After those fixtures land, the compatibility policy above
is mandatory for every schema change.

Each schema below is versioned **independently** (they evolve at different rates).

---

## 1. `genome_contract` — schema_version 1.0.0

Field layout, decode rules, valid ranges of the evolving genome. This is what a
replay consumer needs to interpret raw genome bytes.

```yaml
schema: genome_contract
schema_version: "1.0.0"
genome_id: uart_sampler_v1        # names the substrate this genome drives
byte_length: 32
endianness: little
fields:
  - name: sample_phase
    offset_bits: 0
    width_bits: 5
    type: uint
    range: [0, 31]
    decode: "sub-bit sampling phase, phase/32 of a bit period"
  - name: threshold
    offset_bits: 5
    width_bits: 8
    type: int
    range: [-128, 127]
    decode: "slicer threshold, Q0.8-ish, substrate-defined"
  # ... remaining fields defined alongside the substrate RTL in M1
invalid_select_policy: default_to_safe   # any out-of-range select decodes to a
                                          # legal single-driver default (the
                                          # zynq-ehw spare-route contract rule)
```

**Invariant:** every genome decodes to a *legal single-driver* phenotype — no
byte pattern can express contention. Inherited from the EHW-3 spare-route
contract (every mux is a fan-in selector; invalid select → safe default).

### `genome_contract` — schema_version 2.0.0 (`uart_sampler_v2_headroom`)

M1's two-hour board run proved the v1 genome is too small for a meaningful
equal-budget random-search comparison: the 24,576-point phenotype space is
covered hundreds of times. The headroom benchmark therefore introduces a new
incompatible genome contract. This does **not** rewrite v1 history or v1 replay
bundles.

```yaml
schema: genome_contract
schema_version: "2.0.0"
genome_id: uart_sampler_v2_headroom
byte_length: 5
endianness: little
raw_genome_bits: 39                 # 2^39 encodings; >> 2h measured budget
fields:
  - {name: sample_phase, offset_bits: 0,  width_bits: 5,  type: uint, range: [0, 31]}
  - {name: threshold,    offset_bits: 5,  width_bits: 8,  type: int,  range: [-128, 127]}
  - {name: majority_idx, offset_bits: 13, width_bits: 2,  type: uint,
     decode: "0->1 vote, 1->3 vote, 2->5 vote, 3->safe 5 vote"}
  - {name: filter_taps,  offset_bits: 15, width_bits: 24, type: packed_s8x3,
     decode: "condition-local phase/threshold equalizer taps"}
invalid_select_policy: default_to_safe
search_arms:
  ga: "train-only mutation/selection arm"
  random: "equal-budget random arm, same boot/image"
holdout_firewall: "holdout evaluated only after both arm champions are locked"
```

**Compatibility:** this is a MAJOR bump for `genome_contract`; consumers that
only support `1.x` must reject it. The packed 39-bit layout is intentionally
small enough for firmware and mailbox fingerprints but large enough that a
2-hour run (~7M candidates at the measured v1 speed) cannot exhaust it.

---

## 2. `phenotype_manifest` — schema_version 1.0.0

Binds a genome to the physical bits it is *allowed* to touch. This is the safety
envelope; anything outside it is rejected before write.

```yaml
schema: phenotype_manifest
schema_version: "1.0.0"
manifest_id: uart_sampler_island_v1
bitstream_sha256: <hex>            # the static/base bitstream this applies to
part: xc7z010clg400-1
pblock: island_0                    # spatial scope of all edits
allowed_far_set:                    # every writable configuration frame
  - {far: 0x0040149A, words: 101}
  - {far: 0x0040149B, words: 101}
allowed_bit_whitelist_ref: whitelist_uart_sampler_v1  # -> §5
route_template_ids: []              # empty for M1 (no routing evolution on EBAZ)
lut_select_contract:
  luts:  [g0, g1, g2, g3, g4, g7, g8]     # editable LUT-INIT cells
  select_fields: [node_mux, out_mux]      # editable local-select fields
fclk0_mhz_signoff: 50               # preflight must match before loadb
```

**Rule:** a candidate diff must be **fully contained** in `allowed_far_set` ∩
`allowed_bit_whitelist_ref`. Readback proves the expected bits landed; it does
**not** prove electrical safety of a composition (see §5).

---

## 3. `local_map` — schema_version 1.0.0

Device-local map of configuration tokens. **Sparse graph, never a dense
`O(N²)` compatibility matrix** (`future_plan.md` §Local-Map State Explosion).
May be **behavioral** (measured) where no symbolic model exists, or wrap an
inherited symbolic model (e.g. `Cyclone_CRAM_Mapper` FASM) for known tokens.

```yaml
schema: local_map
schema_version: "1.0.0"
map_id: uart_sampler_island_v1
backend: zynq7_icap
tokens:
  - token: token_017
    spatial_scope: {type: switchbox_window, ref: island_0/sbx_3}  # REQUIRED
    symbolic: null                  # null => behavioral-only token
    diff_hash: <sha256 of the frame diff that realizes it>
    observed_behavior: "source_A reaches sink_B"
    metrics:
      delay_score: 31
      stable_50mhz: true
      stable_100mhz: false
    # sparse edges: only OBSERVED relations are recorded
    observed_compatible_with: [token_003, token_011]
    observed_conflicts_with: [token_042]
    # unknown combinations remain UNKNOWN and are never treated as compatible
    evidence_runs: [run_2026_07_09_a]
unknown_combination_policy: hold    # unknown != compatible
```

**Invariants:**
- every token carries a `spatial_scope` (tile / switchbox window / pblock / CRAM
  byte range / backend island);
- only **observed** dependencies, conflicts, and metrics are stored;
- unknown combinations stay unknown → `HOLD`, never "best effort";
- maps must be replayable across cold boot / reload (a map that cannot be
  reloaded byte-consistently falsifies Claim B).

---

## 4. `run_log` — schema_version 1.0.0

The per-run evidence record. One header + a stream of generation records. Must
pin every artifact needed to reproduce a reported champion by id, version, and
hash (else Claim A fails).

```yaml
schema: run_log
schema_version: "1.0.0"
header:
  run_id: run_2026_07_09_a
  board_id: ebaz4205_unit0
  fclk0_mhz: 50
  temperature_c: 41.0               # if telemetry available, else null
  manifest_id: uart_sampler_island_v1
  benchmark_id: uart_stream_v1      # -> docs/benchmark.md
  benchmark_version: "1.0.0"
  benchmark_manifest_hash: <sha256 of the frozen benchmark manifest>
  condition_set_hash: <sha256 of train/holdout/adversarial tuples>
  whitelist_id: whitelist_uart_sampler_v1
  blacklist_id: bl_uart_sampler_v1
  local_map_id: null                # null until Claim B work enables a map
  write_budget_ref: write_budget_uart_sampler_v1
  search_seed: 0x0000C0DE           # FIRST-CLASS field (Claim A)
  seed_source: local_entropy        # local_entropy | pc_supplied(test-mode)
  persistent_store: {type: nand_partition, ref: mtdX, write_budget: 1000}
  schema_versions:                  # pin every consumed schema
    genome_contract: "1.0.0"
    phenotype_manifest: "1.0.0"
    benchmark_package: "1.0.0"
    safety_whitelist: "1.0.0"
    blacklist: "1.0.0"
    write_budget: "1.0.0"
    local_map: null
generations:
  - gen: 0
    best_genome_hash: <sha256>
    best_fitness_train: 0.71
    phenotype_hash: <sha256>        # frame-diff hash of the instantiated best
    mailbox_words: [0xF4F00028]
    frame_diff_hash: <sha256>
    write_counter: 3                # cumulative NV writes so far
    evals: 512
    evals_per_sec: 1840
events:                             # bounded, out-of-band
  - {gen: 7, kind: new_champion, write_counter: 4}
  - {gen: 22, kind: candidate_rejected, reason: safety_gate, blacklist_ref: bl_09}
  - {gen: 40, kind: recovery, method: golden_reload}
final_evaluation:                   # emitted only after search is locked
  locked_gen: 40
  champion_genome_hash: <sha256>
  champion_phenotype_hash: <sha256>
  train_fitness: 0.71
  holdout_fitness: 0.66
  adversarial_report_hash: <sha256>
  random_equal_budget_holdout: 0.52
  static_baseline_holdout: 0.58
  noise_band: 0.02
```

**Required fields (Claim A / M1 PASS):** `search_seed`, `seed_source`,
`persistent_store` + `write_budget`, `benchmark_version`,
`benchmark_manifest_hash`, `condition_set_hash`, per-gen `best_fitness_train`,
`evals_per_sec`, `phenotype_hash`, and a post-search `final_evaluation` with
`holdout_fitness`. A run log missing any of these cannot support the autonomy
claim.

**Holdout firewall:** `holdout_fitness` is forbidden in `generations`. It appears
only in `final_evaluation`, after the champion genome and phenotype hash are
locked. If holdout results influence selection, tuning, or run continuation, the
record cannot support Claim C.

---

## 5. `safety_whitelist` — schema_version 1.0.0

The bit whitelist a candidate diff must be contained in, plus the composition
gate. This is the **pre-write** validity layer, stronger than readback alone.

```yaml
schema: safety_whitelist
schema_version: "1.0.0"
whitelist_id: whitelist_uart_sampler_v1
manifest_ref: uart_sampler_island_v1
allowed_bits:                       # candidate diff MUST be a subset of this
  - {far: 0x0040149A, word: 12, bit_mask: 0x00FF0000}
composition_rules:
  one_driver_per_node: true
  one_selected_input_per_mux_group: true
  overlap_policy: identical_or_reject   # shared bits must be declared-identical
                                        # or the candidate is rejected
  unknown_overlap: hold                 # never a best-effort write
attestation:
  readback_required: true
  note: "readback proves bits landed, NOT electrical composition safety"
```

**Rule ordering (recovery on gate failure):** `logic reset → known-good
partial/golden reload → full bitstream reload`.

---

## 6. `blacklist` — schema_version 1.0.0

Permanent record of candidates proven bad. Uses compact fingerprints, not full
frames.

```yaml
schema: blacklist
schema_version: "1.0.0"
blacklist_id: bl_uart_sampler_v1
entries:
  - id: bl_09
    diff_fingerprint: <sha256 of the candidate frame diff>
    genome_hash: <sha256>
    reason: wedged_config            # wedged_config | contention_suspected |
                                     # holdout_regression | reward_hack
    first_seen_run: run_2026_07_09_a
    permanent: true                  # abnormal candidates are blacklisted forever
```

**Invariant:** a blacklisted fingerprint is never re-evaluated; recovery from a
wedge that produced it must re-check the blacklist before resuming.

---

## 7. `write_budget` — schema_version 1.0.0

Explicit non-volatile-write accounting. "Persistent champion" must never depend on
unbounded writes (Claim A falsifier).

```yaml
schema: write_budget
schema_version: "1.0.0"
budget_id: write_budget_uart_sampler_v1
store: {type: nand_partition, ref: mtdX}
endurance_estimate_cycles: 100000    # datasheet or conservative
per_run_budget: 1000                 # hard cap; run aborts persistence at cap
counters:
  champion_writes: 0
  checkpoint_writes: 0
  final_report_writes: 0
policy:
  write_only_on: [new_champion, periodic_checkpoint, final_report, operator_request]
  hot_loop_writes_nv: false          # per-gen telemetry stays in RAM
```

---

## 8. `replay_bundle` — schema_version 1.0.0

The portable package that reproduces a reported champion with **no hidden local
state** (the replay-conformance gate).

```yaml
schema: replay_bundle
schema_version: "1.0.0"
bundle_id: replay_run_2026_07_09_a_champion
contents:
  genome: <bytes or path>
  genome_contract_ref:
    id: uart_sampler_v1
    schema_version: "1.0.0"
    sha256: <sha256>
  phenotype_manifest_ref:
    id: uart_sampler_island_v1
    schema_version: "1.0.0"
    sha256: <sha256>
  safety_whitelist_ref:
    id: whitelist_uart_sampler_v1
    schema_version: "1.0.0"
    sha256: <sha256>
  benchmark_ref:
    id: uart_stream_v1
    schema_version: "1.0.0"
    manifest_sha256: <sha256>
    condition_set_sha256: <sha256>
  local_map_ref: null                # or {id, schema_version, sha256}
  blacklist_ref: {id: bl_uart_sampler_v1, schema_version: "1.0.0", sha256: <sha256>}
  write_budget_ref: {id: write_budget_uart_sampler_v1, schema_version: "1.0.0", sha256: <sha256>}
  run_log_ref: {id: run_2026_07_09_a, schema_version: "1.0.0", sha256: <sha256>}
  expected_mailbox_words: [0xF4F00028]
  framebank: <optional path>          # if ICAP instantiation is part of replay
  load_run_script: replay.sh
  search_seed: 0x0000C0DE
  artifact_hashes:
    base_bitstream_sha256: <sha256>
    champion_frame_diff_sha256: <sha256>
    replay_script_sha256: <sha256>
verification:
  mode: deterministic                 # deterministic | autonomous_discovery
  expected_train_fitness: 0.71
  expected_holdout_fitness: 0.66
  bit_match_required: true            # champion phenotype must reproduce bit-exact
```

**Replay-conformance gate:** a champion is only "reported" if this bundle
reproduces it from artifacts alone. All contract, benchmark, whitelist, optional
map, run-log, bitstream, frame-diff, and script inputs are pinned by version and
hash. If reproduction needs uncommitted local state, the champion does not count.

---

## Schema registry (versions at a glance)

| Schema | Version | Bumps when |
|---|---|---|
| `genome_contract` | 1.0.0, 2.0.0 | genome field layout / decode changes |
| `phenotype_manifest` | 1.0.0 | allowed FAR/whitelist/pblock/LUT contract changes |
| `local_map` | 1.0.0 | token record or edge semantics change |
| `run_log` | 1.0.0 | required run-evidence fields change |
| `safety_whitelist` | 1.0.0 | allowed-bit / composition-rule semantics change |
| `blacklist` | 1.0.0 | fingerprint or reason taxonomy changes |
| `write_budget` | 1.0.0 | store accounting / policy changes |
| `replay_bundle` | 1.0.0 | replay contents / verification changes |

Each gets a standalone validator + a conformance-test fixture in M1, shared by any
repo that consumes the schema (`cyclone-fabric-cartographer`, K7 line).
