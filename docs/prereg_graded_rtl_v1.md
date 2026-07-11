# Preregistered graded-fitness RTL/MMIO implementation v1

This document freezes the first board-facing graded-fitness implementation
contract before RTL is changed. It follows the authorized host-only graded
drop (`graded_fitness_v1_gate.md`): Python and C twins are bit-exact, and the
graded score is identical to the soft score whose locality advantage was
measured in v4.

## Scope

This is an RTL/MMIO plumbing drop, not a search drop:

- extend `uart_stream_eval_core` to produce the committed graded bit-match
  score for one frame;
- extend `uart_stream_island_regs` and the software register header to expose
  that score;
- regenerate RTL vectors from the Python oracle and verify RTL simulation
  against them;
- run OOC/fit gates before any board build.

No Set A screening, Set B confirmation, multi-hour run, or board search is
authorized by this document.

## Score semantics

The RTL graded score must match `docs/prereg_graded_fitness_v1.md` exactly:

```text
score = number of bit matches between transmitted payload+CRC bytes and
        decoded payload+CRC bytes for one frame
```

The score is not CRC-gated. Hard pass/fail remains available and unchanged.

Maximum per-frame score:

```text
packet_len <= 64
max_bits = 8 * (64 + 1) = 520
```

Therefore the RTL output width is:

```text
graded_score[9:0]
```

The MMIO readback still uses a 32-bit word with zero extension.

## RTL interface

`uart_stream_eval_core` adds one output:

```verilog
output wire [9:0] graded_score
```

The score must be valid when `done` is asserted and remain stable until the
next `start`. Existing outputs keep their current semantics:

- `busy`: unchanged;
- `done`: unchanged;
- `pass`: hard CRC pass/fail, unchanged;
- `cycles`: unchanged.

## MMIO ABI

Extend `sw/uart_stream_regs.h` and `rtl/uart_stream_island_regs.v` with:

```c
#define UART_REG_GRADED_SCORE 0x38u
```

Readback:

```text
UART_REG_GRADED_SCORE -> {22'd0, graded_score[9:0]}
```

`UART_REG_STATUS` remains unchanged:

```text
bit0 busy
bit1 done
bit2 hard pass
```

This keeps hard/graded transition explicit: old software can keep reading
`STATUS.PASS`; graded-aware software reads `GRADED_SCORE` after `STATUS.DONE`.

## Golden vectors

Regenerate `build/rtl/eval_vectors.txt` or an equivalent committed test vector
fixture from the Python oracle with both hard pass and graded score included.
The vector set must cover at least:

- historical champions:
  - `0x60894268a2`
  - `0x6a8ba845d4`
  - `0x09571273ce`
  - `0x08d590f3ee`
  - `0x4e85cbc206`
  - `0x6cbfb15fd8`
- train and holdout conditions;
- at least 8 frames per condition;
- edge cases with short and long packet lengths.

The RTL smoke test must fail on either hard pass mismatch or graded score
mismatch.

## OOC and fit gates

Before board build:

- `make host-gate` must pass;
- RTL simulation for `uart_stream_eval_core`, `uart_stream_island_regs`, and
  XBUS wrapper must pass with graded vectors;
- Vivado OOC for `uart_stream_eval_core`, `uart_stream_island_regs`, and
  `tpu_rp` must report 0 errors and 0 critical warnings;
- RM utilization must fit the current tracked pblock envelope.

Resource watchpoints:

- graded score adds a per-bit popcount/accumulator path, so LUT growth is
  expected;
- if OOC or DFX fit fails, first reduce control-set pressure or share existing
  decode datapath; do not shrink the score definition or change the benchmark
  semantics to fit.

## Board-facing follow-up boundary

Only after the RTL/MMIO drop passes host, RTL sim, and OOC gates may a later
prereg define:

- firmware use of `UART_REG_GRADED_SCORE`;
- mailbox page ids for graded train/holdout telemetry;
- regenerated board golden words;
- a board smoke that checks hard pass and graded score against the Python/C
  oracle.

Set B remains sealed until a future prereg explicitly authorizes a
confirmatory search run.
