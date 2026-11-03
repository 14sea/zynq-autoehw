# Prior art — what in this project was already done by others

Added 2026-11-03 after a full-text literature review (≈75 papers, 8 external code
bases). This repo's own distinctness test (`docs/tech_report.md` §2.3) was written
against `zynq-ehw` only; this file checks the same claims against the published
literature.

**Bottom line:** the mechanisms are inherited (as the tech report already says), and
several runtime properties also have precedents: PC-free on-chip evolution with
on-board fitness, multi-hour on-chip runs, held-out evaluation and hypothesis tests on
silicon. What has not been found is the *evidence package*: pre-registration, an
equal-budget random-**sampling** baseline, bit-identical reproduction on a second die,
and persistent champion + write budget + full-trajectory replay.

"Not found" means *not found in the 2026-11 search*; three such verdicts were
overturned during that same search, so treat them as provisional.

## 1. Claim-by-claim

| Property (tech report §2.3) | Literature status | Closest prior work |
|---|---|---|
| PC out of candidate selection **and** fitness on-board | **Precedent** | Upegui & Sanchez 2006 (MicroBlaze, Virtex-II); Cancare et al. 2010–12 (PowerPC 405, Virtex-4); Dobai & Sekanina, ZyEHW 2013–15 (ARM PS + PL fitness, Zynq-7020); Garnica et al. 2018 (Zynq-7020, EA in hardware, ARM or MicroBlaze) |
| Multi-hour run | **Precedent** | Cancare et al., TRETS 2012: on-chip PPC405, 26-bit parity averaged 79.2 h. (Thompson & Layzell 2000 ran ≈15 days by evaluation count, but with a PC in the loop and stopped by hand.) |
| Persistent champion + write budget | **Not found** | — |
| Self-recovery from bad candidates without a power cycle | **Partial** | Thompson & Layzell 2000: the PC periodically resets and fully reconfigures the FPGA; Garvie & Thompson 2004: rollback (simulation). Neither recovers from a configuration wedge. Our own evidence is at scaffold level. |
| Post-run replay bundle | **Partial** | ZyEHW host tools record the seed and recompute the champion's fitness (source code only). Full search-trajectory replay: not found. |
| Held-out generalization | **Precedent** | Cancare 2012 (75/25 classification split); Salvador et al., IEEE TC 2013 (36 unseen images); Kawai et al., FPT 2008 (hardware test set). Garnica 2018 splits train/test but reports no test results. What is new here is only the *quantified, pre-registered* holdout against an equal-budget random baseline. |
| Equal-budget random baseline | **Partial** | Vašíček & Sekanina 2007 compare GA/HC/RS at equal budget, but their RS is mutation-based search, not random sampling. Equal-budget random **sampling**: not found. |
| Hypothesis tests | **Precedent** | Garnica et al. 2018 (silicon, 20 runs per setting, t-test / ANOVA); Hodaň et al. 2021 (simulation, Mann-Whitney U). |
| Pre-registration | **Not found** | — |
| Cross-die bit-identical reproduction (Set B on 4203 `17A6`) | **Not found** as such | Multi-chip *evaluation* exists: Thompson & Layzell 2000 (4 chips in the loop, two foundries, −27…60 °C, 4.75–5.25 V, 6 more chips afterwards). We have 2 dies at room temperature. |
| Device-local map guiding selection (Claim B, now in zynq-fabricmap) | **Partial** | Guided / semantic mutation beats standard mutation in CGP circuit evolution, but all in simulation: Hodaň, Mrázek, Vašíček (SOMO, GECCO 2020 / GPEM 2021), Češka et al. (SagTree 2022), Möller et al. 2020, Galeta & Sekanina 2026. A map built on silicon by the device itself: not found. |

## 2. Where prior work is ahead of this repo

- **Static baseline.** UPM's image-filter line always compares against a median filter;
  our beats-static axis was not closed in M1.
- **Robustness range.** Thompson & Layzell tested several chips, temperatures and
  supply voltages; we have two dies at room temperature.
- **Task size.** Precedents evolve image filters, 26-bit parity and 7-bit multipliers;
  our benchmark is a UART-like sampler with 1024 holdout cases.
- **Throughput.** ZyEHW reports 8,700–30,000 candidates/s; this repo reports a
  board-derived budget (22,078 candidates in ≈124 min) but not a per-evaluation
  reconfiguration-time breakdown.

## 3. References

- Upegui, Sanchez. IPDPS 2006 (RAW); AHS 2006.
- Cancare, Bartolini, Carminati, Sciuto, Santambrogio. On the evolution of hardware circuits via reconfigurable architectures. ACM TRETS 5(4):22, 2012.
- Dobai, Sekanina. ICES 2013 (doi:10.1109/ICES.2013.6613287); AHS 2013 (doi:10.1109/AHS.2013.6604241); TRETS 8(3):20, 2015 (doi:10.1145/2700414). Dobai et al. ICES 2014 (doi:10.1109/ICES.2014.7008726); Dobai, FPL 2014 (doi:10.1109/FPL.2014.6927455).
- Garnica, Glette, Torresen. Comparing three online evolvable hardware implementations of a classification system. GPEM 19:211–234, 2018, doi:10.1007/s10710-017-9312-1.
- Thompson, Layzell. Evolution of robustness in an electronics design. ICES 2000.
- Garvie, Thompson. IOLTS 2004.
- Salvador et al. Self-reconfigurable evolvable hardware system for adaptive image processing. IEEE Trans. Computers 62(8), 2013.
- Kawai et al. FPT 2008.
- Vašíček, Sekanina. An evolvable hardware system in Xilinx Virtex II Pro FPGA. IJICA 2007.
- Hodaň, Mrázek, Vašíček. GECCO 2020 (doi:10.1145/3377930.3390188); GPEM 22:539–572, 2021 (doi:10.1007/s10710-021-09416-6).
- Češka, Matyáš, Mrázek et al. SagTree. Swarm and Evolutionary Computation 69:100986, 2022.
- Möller et al. RL-based adaptive mutation for CGP. LNCS 2020 (doi:10.1007/978-3-030-61380-8_2).
- Galeta, Sekanina. Transformer-based mutation for approximate circuit design. CEC 2026 (doi:10.1109/cec69861.2026.11727165).
