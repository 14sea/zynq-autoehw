# Preregistered graded-fitness benchmark revision v1

This document freezes the next benchmark-revision protocol before any
graded-fitness search results are inspected. It follows the hard-fitness
screening ladder through v7: PBIL and multi-island search improved train and
median holdout behavior, but the hard CRC pass/fail signal repeatedly failed
the left-tail holdout gate. The remaining evidence points to the fitness signal
itself, not another hard-fitness search tweak.

## Scope

This drop is host-only:

- define graded-fitness semantics in the Python oracle;
- mirror the semantics in the portable C twin;
- add tests and small smoke fixtures.

This drop does **not** change RTL, MMIO, firmware mailbox ABI, DFX build
scripts, or board behavior. A later board-facing drop must explicitly
preregister the RTL/MMIO interface and run OOC/fit gates.

## Fixed benchmark regime

- Benchmark family: `uart_stream_v2_headroom`
- New graded benchmark id: `uart_stream_v2_graded`
- Genome contract: `uart_sampler_v2_headroom`, schema `2.0.0`
- Search train frames per condition: `64`
- Final holdout frames per condition: `256`
- Candidate genome space: 39-bit v2 genome, unchanged
- Train/holdout firewall: unchanged. Search and selection may use only train
  split scores. Holdout is evaluated only after the arm champion is frozen.
- Set B seed `0xB17D`: remains sealed until a future board-confirmatory run is
  authorized.

## Graded score definition

For a `(condition, genome, frame_idx)`:

1. Decode the v2 genome into the existing effective v1 sampler config for that
   condition.
2. Generate the deterministic payload and transmitted CRC byte exactly as the
   current hard-fitness oracle does.
3. Run the existing sampler/vote path to decode every transmitted payload bit
   and CRC bit.
4. Count bit matches between transmitted bytes and decoded bytes across
   payload plus CRC.

Per-frame graded score:

```text
bit_matches in [0, 8 * (packet_len + 1)]
```

Per-condition graded score:

```text
sum(frame bit_matches)
```

Per-split graded score:

```text
sum(condition graded scores)
```

This score is intentionally not CRC-gated. A frame can earn partial credit for
nearly-correct payload/CRC bits even when the hard CRC pass bit is zero.

Hard pass/fail remains available as a reference metric but is no longer the
optimization target for graded-fitness search variants.

## Host gates for this drop

The host-only graded drop must provide:

- Python oracle function for per-frame and per-split graded scores;
- C twin function and CLI output for the same scores;
- bit-exact Python/C tests on representative v2 genomes;
- a small host smoke that reports hard and graded train/holdout for historical
  champions and random genomes.

No full Set A search screening is authorized by this document. It only freezes
the score semantics and implementation contract.

## Future RTL/MMIO requirements

If the host graded score is accepted, the next board-facing prereg must define:

- RTL `eval_core` output width for graded score;
- MMIO register ABI for score readback;
- how hard pass and graded score coexist during transition;
- OOC/fit thresholds and resource-risk handling;
- regenerated golden vectors for Python, C, RTL sim, and board mailbox.

The RTL score must match the Python/C definition above bit-exactly for the
committed test vectors before any board search run is authorized.

## Decision boundary after host-only scoring

After this host-only drop lands, the next decision is:

1. If Python/C graded scores are bit-exact and show the expected locality on
   existing v4 diagnostic samples, preregister the RTL/MMIO graded-fitness
   implementation.
2. If Python/C graded scores cannot be made deterministic or expose no stronger
   locality than hard pass/fail on the existing diagnostic samples, stop the
   graded route and record the hard-fitness M1 search ladder as the scoped
   result.

Set B remains untouched in both cases.
