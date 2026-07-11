# Preregistered graded-fitness board smoke v1

This document freezes the first board-facing graded-fitness smoke before
firmware or mailbox code is changed. It follows the graded RTL OOC gate:
`UART_REG_GRADED_SCORE=0x38` is implemented, RTL sim hard+graded vectors pass,
and OOC fit risk is cleared.

## Scope

This is a board smoke, not a search run:

- firmware reads `UART_REG_GRADED_SCORE` after `STATUS.DONE`;
- firmware publishes a small paged mailbox report with hard pass and graded
  score for fixed oracle vectors;
- host checker compares the board carousel against Python/C goldens;
- no candidate search, Set A screening, Set B confirmation, or multi-hour run
  is authorized.

## MMIO contract

The board smoke uses the committed RTL/MMIO ABI:

```c
#define UART_REG_GRADED_SCORE 0x38u
```

Read sequence per frame:

1. program condition/config/frame registers;
2. clear done;
3. start;
4. poll `UART_REG_STATUS` until `DONE`;
5. read hard pass from `STATUS.PASS`;
6. read graded score from `UART_REG_GRADED_SCORE`.

The smoke must not infer graded score from hard pass or from software-side
oracle calculations on board. The reported graded value must come from MMIO.

## Test vector set

Use a fixed, small vector set to keep board runtime short while covering both
train and holdout behavior:

| vector | condition | frame | genome | reason |
|---|---|---:|---|---|
| 0 | `T0v2` | 0 | `0x60894268a2` | historical GA/board champion family |
| 1 | `T1v2` | 3 | `0x6a8ba845d4` | random champion family |
| 2 | `T2v2` | 5 | `0x09571273ce` | hard/graded ranking disagreement evidence |
| 3 | `T3v2` | 7 | `0x08d590f3ee` | v2 PBIL/GA search champion family |
| 4 | `H0v2` | 1 | `0x4e85cbc206` | holdout path, early v2 fixture |
| 5 | `H1v2` | 7 | `0x6cbfb15fd8` | holdout path, random baseline champion |
| 6 | `H2v2` | 2 | `0x60894268a2` | short-packet holdout edge |
| 7 | `H3v2` | 4 | `0x6a8ba845d4` | long-packet holdout edge |

For each vector, host goldens must include:

- raw genome;
- effective sampler config;
- hard pass bit;
- graded score;
- graded maximum bits for that frame.

## Mailbox ABI

Use paged mailbox page id `9` for this smoke. Page ids 4/5/6/7/8 are already
used by v2 final/progress/calibration pages.

Page 9 payload count:

```text
1 header payload + 8 vector payloads + 1 aggregate payload = 10
```

Payload layout:

| payload index | meaning |
|---:|---|
| 0 | version/summary: `(1 << 16) | vector_count` |
| 1..8 | one vector result each: `(vector_idx << 18) | (hard_pass << 17) | graded_score[9:0]` |
| 9 | aggregate: low 22 bits of `sum(graded_score)` |

The existing page framing, 2-bit sequence counter, and checksum rules apply.
Consecutive duplicate payloads are legal and must be handled positionally.

## Host checker

The host checker must:

- reconstruct page 9 positionally, not by global de-duplication;
- recompute all vector goldens from the Python oracle;
- verify vector count, hard pass bits, graded scores, aggregate sum, and page
  checksum;
- fail if extra page-9 payloads are present or if any expected vector is absent.

## Gates before board load

Before the smoke is loaded onto the board:

- `make host-gate` must pass;
- RTL smoke must pass with hard+graded vectors;
- OOC gates must remain 0 errors / 0 critical warnings;
- host-stub mailbox smoke must pass the page-9 checker.

## Board pass criteria

The board smoke passes only if:

- DFX build/load succeeds with the graded RTL;
- FCLK0=50 preflight passes;
- page 9 is captured from the board carousel;
- host checker reports exact match against Python/C goldens;
- legacy hard-pass behavior remains observable and unchanged.

Set B remains sealed. Passing this smoke authorizes a later prereg for
graded-fitness host screening and/or a graded board search scaffold; it does
not itself establish beats-random.
