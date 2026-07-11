# v9 Set B confirmatory host golden

Generated before any board confirmatory run for the frozen v9 variant.

- Frozen variant: `pbil_island8_graded_v9`
- Confirmatory seed: `0xB17D`
- Variant arm seed: `0xB17D ^ 0x4A4A = 0xFB37`
- Random arm seed: `0xB17D ^ 0xBEEF = 0x0F92`
- Train frames per condition: `64`
- Final holdout frames per condition: `256`
- Nominal host-screening arm budget: `22387` candidates
- Primary confirmatory metric: hard holdout delta

## Golden at budget 22387

```text
pbil_island8_graded_v9 raw 0x7c009161b2 phase 18 threshold 13 majority_idx 3 taps 0xf80122 train 83489 83968 holdout 128 1024 evals 1879791616
graded_holdout 382336 385024

random raw 0x06c219610c phase 12 threshold 8 majority_idx 3 taps 0x0d8432 train 38 256 holdout 15 1024 evals 5731072
graded_holdout 332459 385024
```

Hard holdout delta:

```text
128 - 15 = +113 / 1024
```

This exceeds the preregistered Set B confirmatory threshold `+8 / 1024`.

## Evals-field note

The C twin's `variant-graded` CLI reports `evals` for graded-search variants as
the accumulated graded train bit-count (`1879791616` above). The board mailbox
uses the project-wide board convention: `evals` means fabric frame evaluations.
For the nominal Set B budget, the expected board frame-eval count per arm is:

```text
22387 candidates * 4 train conditions * 64 frames = 5731072 frame-evals
```

The board checker therefore validates the variant mailbox `evals` field against
`budget * 256`, while validating genome, train score, hard holdout, and graded
holdout against the C twin golden.

## Budget derivation

The board confirmatory firmware must run its graded-path speed probe and derive
the actual board budget from measured `evals/sec`. If the measured board budget
differs from `22387`, `host/check_v9_confirm_mailbox.py` recomputes the frozen
variant and random goldens for the observed budget before comparing mailbox
payloads. The variant and seed remain fixed; only the preregistered speed-derived
budget may vary.
