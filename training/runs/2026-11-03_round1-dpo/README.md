# Run: 2026-11-03_round1-dpo

**Authors:** sangji (GitHub: Hawever-renbo), M. Cen

Round 1 of DPO on the Z6 pairs. Training finished 2026-11-04; the selected checkpoint was evaluated once on a locked test split.

**Verdict:** every gated engineering check passed on the locked test split. The pre-registered 30-item human blind review is **not done yet**. It will be run on the round-2 model, with base and round 1 on the same blind sheet.

**Round 2 is in progress** (on-policy DPO from this checkpoint; see [Next](#next-round-2)). Results will be added here as a new run folder.

## Setup

| | |
|---|---|
| Base model | Qwen3.8-27B (bf16), thinking mode off for training and inference |
| Objective | DPO (sigmoid loss) + RPO term (NLL on the chosen side), `rpo_alpha` 1.0 |
| β | 0.1 |
| Learning rate, schedule | 5e-6, cosine, 10% warmup |
| Epochs, effective batch | 1 epoch, 250 steps, effective batch 32 |
| Adapter | LoRA r 32, α 64, dropout 0.05, all linear layers, vision tower frozen (0.85% of parameters trainable) |
| Max length | 3,072 tokens |
| Data | Z6 main file (8,021 pairs) → 7,933 after content cleaning (54 quotes not verbatim in the excerpt, 34 targets that were author text, not a participant) → 7,008 train pairs after the dev split → 6,360 after the locked test split → 6,310 after a quality filter (50 pairs dropped) → 7,972 training rows after oversampling four read-required groups ×2 |
| Split | by article: train / dev (checkpoint selection) / locked test (82 articles, 648 pairs, 300 excerpts, 80 whole units; evaluated once) |
| Hardware, wall time | 2 × RTX 4090 48 GB, model split across both GPUs; about 12.5 h |
| Framework | ms-swift 4.5.2, trl 1.10.0, transformers 5.6.2, peft 0.20.0, torch 2.10; inference with vLLM 0.19.1 |

## Why this run

The first DPO round on the Z6 data. Before training, the protocol, gate thresholds, a frozen showcase set and the data split were committed, and the base model was measured on dev and test. Every later change to a rule is logged with its timing relative to the results.

What the run should show: on held-out articles, the model prefers the more faithful code more often, especially in groups that require reading the quote, and writes clean in-vivo codes without losing general capability.

## Process

1. **Shortcut probe first.** Many pairs can be solved from word differences alone, without reading the quote (76.2% overall; 91.4% for depth). So the gate tests each group separately, and the groups that need the quote (focus, lost in-vivo words, category confusion, imposed connective) were oversampled ×2.
2. **First attempt stopped at step ~74.** The monitor flagged likelihood displacement: the chosen side's reward turned negative after the learning-rate peak while the chosen NLL rose. The run was restarted from scratch with a heavier NLL term on the chosen side (`rpo_alpha` 0.5 → 1.0). In the restarted run the chosen reward stays positive and the margin grows by pushing the rejected side down.
3. **Checkpoint selection on dev only.** 11 candidates (all 9 checkpoints of the restarted run, plus checkpoints 30 and 60 of the first attempt). From step 90 on, checkpoints sometimes append self-critique after the code ("Wait, I should not add …"; up to 19% of dev outputs at step 120), so they failed the "no extra text" rule. Among eligible candidates, **checkpoint 60** was closest to the reviewed reference codes and was selected.
4. **Judge calibration changed the gate.** On dev, the holistic LLM judge preferred base outputs over the reviewed reference codes 61:26, so it was demoted to a diagnostic before the test run. A metric bug (markup such as `<code>` counted as outside words) was fixed and base was re-scored; both versions are kept.
5. **One test run.** The test-evaluation script refuses a second run.

## Results (locked test split, checkpoint 60)

**L1: preference accuracy** (policy log-probabilities, 648 pairs). Group names follow the training data: depth = deep reading, focus = emphasis, relation = control, the rest are the defect labels.

| Group | Base | Trained |
|---|---|---|
| All pairs | 0.806 | **0.940** |
| Depth (n = 185) | 0.443 | **0.854** |
| Focus (n = 47) | 0.702 | **0.872** |
| Lost qualifier (n = 62) | 0.919 | 0.968 |
| Other 7 groups | 0.90–1.00 | equal |

Focus is the cleanest evidence that the model reads the quote: on the 300 dev pairs, a word-difference probe gets only 0.486 there and always picking the longer label gets 0.229. Depth is weaker evidence: its chosen side is almost always longer and the word-difference probe gets 0.914, above the trained 0.854, so part of that gain may be a length effect.

**L2: generated codes** (300 excerpts, greedy)

| Check | Base | Trained |
|---|---|---|
| Format compliance | 95.7% | **100%** |
| Quote copied verbatim | 95.7% | **100%** |
| Label adds words not in the quote | 10.0% | **4.7%** (McNemar p = 0.0026) |
| Label adds a causal / contrast connective | 3.0% | 2.0% |
| Extra text after the answer | 3.0% | 0% |
| Token F1 vs. reviewed reference code | 0.721 | **0.836** (166 closer, 52 further; sign test p ≈ 2e-15) |
| Holistic judge, trained vs. base (diagnostic) | | win rate 0.61, 95% CI [0.53, 0.69] |
| Human blind review (30 items) | | **pending** |

**L3: general capability**

| Check | Base | Trained |
|---|---|---|
| MMLU (1,000) | 0.829 | 0.829 |
| CMMLU (1,000) | 0.814 | 0.815 |
| Coding format leaking into non-coding prompts | 0 | 0 |

Training curves: [`metrics.csv`](metrics.csv) (train every step, dev every 30 steps). Dev loss 0.809 → 0.264; dev reward accuracy settles near 0.97 after step 120.

## Limitations

1. **Whole-unit coding regressed.** When the model codes a whole unit at once (observe-only, 80 units), labels with outside words rose from 13.8% to 22.5%. Training data were per excerpt; this is a round-2 target.
2. **No human or expert review of model outputs yet.** All test numbers above are automatic metrics, policy log-probabilities or an LLM judge.
3. **One selection rule was written after seeing dev results.** The test split was untouched until the single final run, and the full dev table is kept so the choice can be checked.
4. Checkpoints trained longer append reasoning text after the answer. The selected checkpoint does not (0/300 on test), but the cause is not fixed in training yet.
5. Single training run, single judge provider; the judge's position consistency is about 0.6.

## Next: round 2

On-policy DPO from checkpoint 60: sample the model's own codes, build pairs from its own errors (imposed connectives, outside words, extra text, whole-unit errors), and train a new adapter with checkpoint 60 as reference. Then a human blind review and an anthropology expert review, covering base, round 1 and round 2 on the same blind sheet.

## Evidence

The full run record is in a separate evidence repository: **[Hawever-renbo/cdm-open-coding-dpo](https://github.com/Hawever-renbo/cdm-open-coding-dpo)** (private).

- **What is in it:** pre-registration, gate thresholds, the deviation register (D-001 to D-011), frozen-hash manifests, training and monitor logs, dev screening of all 11 candidates, the test gate output, and the scripts behind them. Round 2 is being added as it runs.
- **Why it is private:** some files contain material that should not be public, such as excerpts from the copyrighted interview studies.
- **Access on request:** open an issue with the [evidence access form](https://github.com/Hawever-renbo/cultural-decoding-dpo/issues/new?template=evidence-access.yml) and your GitHub username, and you will be added to the repository. The link above shows a 404 until then.

Every commit there is SSH-signed. The milestone tags below are listed here so their commits can be checked once you have access:

| Tag | Commit | Time (UTC+8) | Milestone |
|---|---|---|---|
| `v0-preregistered` | `ace8c328a29b` | 2026-11-03 16:19 | Protocol, gates, showcase set and data split frozen |
| `v1-preflight` | `9e01ffe8695c` | 2026-11-03 17:01 | Training-machine preflight passed |
| `v3-smoke` | `81d3b7afa8c4` | 2026-11-03 18:03 | Smoke run passed |
| `v2-baseline` | `c78a7daf94d2` | 2026-11-03 19:22 | Base model measured on dev and the locked test split, before training |
| `v4-trained` | `9b3ac3cf4672` | 2026-11-04 11:41 | Training finished (250 steps) |
| `v5-gate` | `8c03adc1356b` | 2026-11-04 15:26 | Round-1 verdict on the locked test split |
