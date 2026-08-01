# M1 engineering addendum — closing the two remainders

Two items were left open when M1 closed at tag `m1-complete`:

1. **NV champion store** — the champion currently survives a *logic* reset
   (`FPGA_RST_CTRL` pulse, static-BRAM restore ABI, board-verified `1ab3fe9`),
   but not a power cycle. Nothing is ever written to non-volatile media.
2. **Board-side replay bundle emission** — replay bundles exist only as
   host-authored JSON fixtures; the board does not emit the material itself.

This addendum closes both, **in this repo**. They are this repo's own debt —
its firmware, its framebuf, its host checkers — and the M1 record must not end
up pointing at remainders that were closed somewhere else. `m1-complete` stays
frozen: an addendum is not a re-opening of M1.

They were briefly labelled "M2 drop 0" (2026-08-01). That label was wrong and is
withdrawn: M2's research line — self-cartography, fuzz×evolve, `local_map`,
prjxray subset extraction + certification — tests **Claim B**, carries a
different board-risk envelope, and gets its **own repo**. Only the finished
engineering debt stays here.

Scope discipline up front: neither item touches the search, the benchmark, or
any seed. No claim in the M1 ledger changes. Set B stays spent.

---

## 1. Facts established on hardware before specifying anything

Measured 2026-08-01 on EBAZ4203 `17A6` and read out of the current RTL:

| fact | value | consequence |
|---|---|---|
| `axil_framebuf` NEORV32-side port | **read-only** (`rd_addr` → `rd_data`, 1-cycle registered) | the firmware **cannot** deposit a record today — this is the one real blocker |
| framebuf geometry | `ADDR_BITS=11` = 2048 words / 8 KB; PS window assigned at `0x40000000` range 8K; NEORV32 sees `0xF5000xxx` | 8 KB is plenty for a record + a replay blob |
| 4203 U-Boot | **`fatwrite` and `fatload` both present** | the S2 one-shot flush needs **no U-Boot rebuild** |
| mailbox page ids | 1–14 used | **15 is the next free id** |
| existing champion record | 5 words at framebuf word 0: magic `CHMP`, meta, config, budget, checksum; PS-seeded, firmware-validated | record ABI already exists; it needs a v2 and a *writer* |

**The single design consequence:** one small static-shell RTL change (a write
port into the framebuf from XBUS) unlocks *both* remainders. Everything else is
firmware + host.

---

## 2. Architecture

```
  run ends
     │
     │ firmware writes record + replay blob   ← NEW write path (RTL)
     ▼
  axil_framebuf  (PL BRAM, 2048 words)
     │  low  1024 words : PS → board (existing param window, unchanged)
     │  high 1024 words : board → PS (NEW, board-written store window)
     ▼
  U-Boot one-shot flush (S2):  fatwrite mmc 0:1 0x40001000 champ.bin <len>
     ▼
  TF card FAT partition  ← the NV medium
```

Restore after a power cycle — **order matters**, the framebuf lives inside the
PL, so it does not exist until the bitstream is loaded:

```
1. fpga loadb 0 <addr> <size>          # framebuf now exists, zeroed; firmware
                                       # boots, finds no valid record, runs default
2. fatload mmc 0:1 0x40000000 champ.bin
3. SLCR unlock; mw 0xF8000240 0xF; mw 0xF8000240 0   # logic reset, BRAM preserved
4. firmware re-boots, validates magic+checksum, restores champion
```

Steps 3–4 are exactly the EHW-5.4b / `1ab3fe9` sequence already board-verified;
only `mw.l`-by-hand is replaced by `fatload`. Do **not** reorder 1 and 2.

### Address split (why disjoint, not arbitrated)

Two writers on one RAM invites a conflict policy nobody wants to reason about.
Split the window by address instead: PS writes only words `0..1023`, NEORV32
writes only words `1024..2047`. Both ports are already in the single FCLK0
domain, so Vivado infers a true-dual-port BRAM cleanly and there is no
arbitration logic at all. The split is a *convention* enforced by construction
(the XBUS write decode ignores addresses below 1024).

---

## 3. What ChatGPT owns (authorship)

### 3.1 RTL — the write port (the only RTL in this addendum)

- `axil_framebuf.vhd`: add a second **write** port (`wr_addr`, `wr_data`,
  `wr_en`) alongside the existing read port. Same clock. Keep the AXI side
  byte-for-byte as it is — the PS param window must not change behaviour.
- `neorv32_soc_dfx.vhd`: decode XBUS **writes** into the framebuf region and
  drive the new port; ignore writes with `xbus_adr` word index < 1024. Keep the
  **1-cycle registered ack** pattern (`fb_ack`) — NEORV32 XBUS deasserts `stb`
  on acceptance, so a multi-cycle ack never fires. This exact trap already cost
  one board smoke (M1 smoke #1, XBUS DONE handshake).
- Do not touch the RM (`rm_uart_stream`) or the pblock. The RM is unchanged, so
  its OOC and placement results stand; only the static shell rebuilds.
- Ship an iverilog/GHDL testbench for the new port, but note the standing
  lesson: **a passing tb is not a passing synthesis** — the OOC gate is mine and
  it is not optional.

### 3.2 Firmware

- **Champion record v2** in the store window (word 1024 onward), little-endian
  u32, all fields explicit:
  `magic 'CHMP' | schema_version | build_id_lo | build_id_hi | seed | budget |
   genome_lo | genome_hi | train_score | train_total | hard_holdout_packed |
   graded_holdout | evals_lo | evals_hi | write_count | checksum`
  Keep the existing 5-word v1 record readable so the proven restore path does
  not regress; version-dispatch on `schema_version`.
- **Writer**: `champion_store_write()` — called once when the run completes,
  after the final carousel material is computed. Must be a no-op on the host
  stub except into the existing `host_framebuf_words[]` fake, so the host gate
  can assert the exact bytes.
- **Write-budget counter**: `write_count` lives in the record; the firmware
  refuses to arm a flush past the ceiling and publishes the refusal instead of
  silently continuing. Be explicit in the docs that the ceiling is enforced by
  firmware + flush script, **not** by hardware.
- **Replay blob**: a self-describing binary block in the store window carrying
  everything the `replay_bundle` schema needs from the board side — schema
  version, genome contract version, build id, benchmark id + params
  (train/holdout frames, conditions), seed, derived budget, measured eps,
  champion genome and all scores, eval counts. Host converts blob → JSON.
- **Mailbox page 15 (digest)**: schema version, build id (3 × 22-bit chunks),
  record checksum, blob length, blob CRC, write_count. This lets a UART-only
  observer verify that the blob they later pull matches what the board computed,
  without needing the blob itself over the mailbox.
- Reminder from EHW-5.5: mailbox payloads are 22-bit under the tag; keep every
  field inside 22 bits or chunk it explicitly, and never publish two
  consecutive byte-identical words without the seq counter.

### 3.3 Build id — read this before implementing it

The firmware **cannot** hash its own image (the hash would have to be inside the
image it hashes). Do not attempt a self-hash slot.

Instead: `build_id` = a 64-bit digest computed **on the host at build time** over
the inputs that actually determine reproducibility — genome contract version,
variant name, benchmark id + numeric band version, train/holdout frame counts,
conditions, seed — emitted into a generated header (`sw/autoehw_build_id.h`,
generated by a script, not hand-edited) and baked into the firmware. The board
publishes it; the host bundle separately records the artifact hashes (bitstream
md5, IMEM image md5) that it holds anyway. State this split in `schema.md` so
nobody later reads `build_id` as an artifact hash.

### 3.4 Host

- `host/assemble_replay_bundle.py`: framebuf blob (binary) → `replay_bundle`
  JSON, schema bumped to **1.1.0** (MINOR: added fields, old bundles still
  valid) — not 2.0.0, nothing is removed or reinterpreted.
- `host/verify_replay_bundle.py`: take a bundle, re-run the C twin from it
  alone, and assert it reproduces the champion **bit-exactly**. A bundle that
  cannot be independently replayed is not a replay bundle.
- `host/check_store_digest_mailbox.py`: page-15 checker, same style as the
  existing checkers (recompute over board-observed values, never fixed-compare
  a host fake).
- Unit tests: record v1/v2 dispatch, checksum, write-budget refusal, blob
  round-trip (write → parse → JSON → verify), page-15 encoding. The host stub
  must produce the **same bytes** the board will.
- `docs/schema.md`: `replay_bundle` → 1.1.0, `write_budget` given a real
  `write_count` field, plus the `build_id` note from §3.3.

---

## 4. What I own (gate + board)

- OOC gate on the changed static shell (and confirmation that the RM is
  untouched, so its placement result stands).
- Full DFX rebuild; 101 critical warnings incl. `WNS=-17` is the known-good
  baseline, not a regression.
- FCLK0 preflight with `scripts/board_set_fclk50.py` (PLL-decoding version — the
  4205's `0x00200a00` magic is board-specific, see the 4203 note in
  `board_results.md`).
- Board run on the **4203** (it owns the TF card, which is the NV medium):
  load → run → framebuf readback via `md 0x40001000` → `fatwrite` →
  **physical power cycle** → `fpga loadb` → `fatload` → logic-reset pulse →
  confirm the restored champion is bit-identical to what was stored.
- The power-cycle test is the whole point: a restore that only survives a logic
  reset is what we already had.
- `docs/board_results.md`, commit, push (push after user review, as always).

---

## 5. Honest scope when this lands

**Closes:** champion persistence across power loss on real NV media; a replay
bundle whose *content originates on the board*; a write budget with a real
counter.

**Does not close:** NV write-endurance claims (one file, one write per run, no
wear study); autonomous re-flush without U-Boot (S2 is deliberately a one-shot
from the boot loader — S1, a resident PS servant, was rejected); the 4205 has no
SD, so its NV path would be `nand write` with the same record ABI and is out of
scope here.

**Explicitly not claimed:** nothing about search quality, generalization, or
beats-random. This addendum is plumbing.
