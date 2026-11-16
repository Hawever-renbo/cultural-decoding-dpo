# cultural-decoding-dpo

Preference data for teaching an LLM to read interview material the way a qualitative researcher does, and the DPO training that uses it.

This is a post-training work sample. It covers the full data loop: task design, a synthetic pair generator, programmatic and model-based filters, a blind expert-review site, and six design rounds driven by what the expert said. Training runs are added to [`training/`](training/) as they progress; round 1 is done and round 2 is running.

**Status (2026-11-04)**

| | |
|---|---|
| Dataset | **8,021 DPO pairs** (Z6), from 1,914 units in 1,022 published qualitative studies. 172 more pairs are flagged by stricter checks and kept apart. |
| Expert check | In the last expert-reviewed round before Z6 (Z5, 39 pairs), the expert picked the intended *chosen* side blind in 33/39 and agreed with it after reveal in 36/39. An 80-pair blind review of Z6 is in progress. |
| Training | **Round 1 done (2026-11-04).** Qwen3.8-27B, DPO + LoRA. On a locked test split of held-out articles: pair accuracy 0.806 → 0.940 (emphasis pairs, which word-level shortcuts cannot solve, 0.702 → 0.872); labels adding words not in the quote 10.0% → 4.7%; token F1 vs. reviewed reference codes 0.721 → 0.836; MMLU unchanged. Human blind review pending. **Round 2 (on-policy DPO) in progress.** See [`training/runs/2026-11-03_round1-dpo/`](training/runs/2026-11-03_round1-dpo/). |
| Cost | 5,017 model calls for Z6, about $203 at API-equivalent prices (run through the Claude Code CLI subscription). |

## Two parts: a model and a harness

| | What | Where |
|---|---|---|
| **Model** | A post-trained open-coding model: Qwen3.8-27B with the round-1 DPO adapter. Given interview excerpts, it writes an in-vivo code that stays inside the quote. | The data and method are described below; results are in [`training/`](training/) |
| **Harness** | A coding agent built around that model. Level 1 (open codes) goes to the post-trained model, one statement at a time. Levels 2–3 (concepts, categories, a core category and a theory) and the conversation go to a general model, under gates and metrics computed by program. Any abstraction can be traced back to the quote it came from. | [`agent/`](agent/) |

The agent does not let the model that codes judge its own coding: rounds are ranked by program-computed metrics, and model self-ratings are logged but decide nothing. The same rule shaped the training (see step 4 of the [round-1 run](training/runs/2026-11-03_round1-dpo/)).

### Demo

[`demo/`](demo/) is a small web app that puts the two parts together. Paste interview text and a research focus, watch the three levels come in, read the post-trained model next to the untrained base model on your own text, see the finished coding as a map, and ask the agent about the result.

The demo is **open by invitation**. It is not a public site: it needs the project's own GPU machine, which serves the post-trained model, and is started for invited people. To use it, [request access](https://github.com/Hawever-renbo/cultural-decoding-dpo/issues/new?template=demo-access.yml) with your GitHub username, or contact the repository owner. You will get a link and a way to sign in (GitHub, or a code sent to your email). The machine is not on around the clock; when the post-trained model is off, the page says so.

## The task

Grounded-theory coding runs open → axial → selective. This dataset targets the first step, **open coding**: given one section of a study (a short research-context card plus numbered interview quotes), write a code label for what a speaker says and anchor it to a verbatim span.

```
<code label> — [n] «<span copied exactly from quote n>»
```

A good open code stays inside the quote. It keeps the speaker's own reasons, hedges, negations, group words and distinctive terms, and puts the weight where the speaker puts it. It adds no interpretation the quote cannot support. The pairs teach exactly these distinctions.

## What a pair looks like

Both sides cite the same span; only the label differs.

**Deep reading.** The chosen side keeps the reason the speaker states:

```
chosen:   we mostly rely on my evening milk money because cooperative payment often delays, sometimes up to two months — [3] «Payment from the cooperative often delays—sometimes up to two months—so we mostly rely on my evening milk money.»
rejected: we mostly rely on my evening milk money — [3] «…same span…»
```

**Defect: `outside_word`.** The rejected side adds an evaluative word the speaker never used:

```
chosen:   I think they would have great problems thinking their genetic material is making sperm for other people — [3] «…»
rejected: I think they would have great ethical problems thinking their genetic material is making sperm for other people — [3] «…»
```

**Emphasis.** The rejected side codes the setup instead of the point:

```
chosen:   come legally, won't have this problem — [2] «I know this sounds heartless, but if you come here legally, you won't have this problem.»
rejected: I know this sounds heartless to say — [2] «…»
```

[`data/samples/z6_samples.jsonl`](data/samples/z6_samples.jsonl) has 32 pairs across every type, each with its full prompt context.

| Type | Pairs | Chosen vs. rejected |
|---|---|---|
| Deep reading | 2,212 | Chosen also carries one reason, condition, contrast or consequence the speaker states. |
| Emphasis (v2) | 566 | Chosen codes what the speaker stresses; rejected codes the setup, and is the same length or longer. |
| Defect | 4,263 | Rejected = chosen plus one labelled defect, edit ≤ 6 words: `overgeneralization`, `outside_word`, `category_confusion`, `lost_qualifier`, `misattached_connective`, `lost_in_vivo`, `imposed_connective`. |
| Control | 980 | Rejected flattens the speaker's own connective into a list ("A because B" → "A; B"), with every content word kept. |

## How the generator works (Z6)

```
quotes ──► zero-call prefilter ──► card + unit rubric      ──► generate 6 pairs/unit  ──► deterministic checks ──► model reviewer ──► export
           (single speaker,        (1 call per paper:          (1 call per unit:          (verbatim span, one       (1 call per unit,
            whole sentences,        context, speakers,          2 deep, 3 defect,           diff only, edit size,     fails pairs on the
            no interviewer)         what a faithful code        1 control; few-shot =       no words outside the      expert's own failure
                                    must keep)                  expert-approved pairs)      quote, dedup)             categories)
```

The generator and reviewer prompts are written from the expert's feedback. The reviewer's failure categories quote the expert's own comments, e.g. "where in the text is the basis for this judgment?" Details: [`docs/pipeline.md`](docs/pipeline.md).

## Six rounds, one lesson

Each round was blind-reviewed by the same domain expert (X1), whom the project treats as the gold standard. The expert sees A and B in random order, picks the better one blind, then sees which side was intended and answers whether that side really is better.

| Round | How "chosen" was defined | Blind pick = chosen | After reveal: chosen is better |
|---|---|---|---|
| Z3 (levels 1–3) | Model draft plus the paper author's own interpretation at one slot; rejected = same slot read shallowly | 35/60 | 39/60 |
| Z4 (levels 1–2) | As Z3, plus a per-unit rubric for both sides, best-of-4 selection and an LLM judge | 9/26 | 11/26 |
| Z5 pilot (level 1) | Shared base code with one edit: a deeper reading grounded in the speaker's words, or one verifiable defect | 10/15 | 14/15 |
| Z5 second round (level 1) | Same, production settings | 33/39 | 36/39 |
| Z6 (level 1) | Direct generation from the quotes, under the standards above | 80 pairs in review | — |

**The lesson:** a published author's interpretation is not automatically the better code. In Z3 the expert's most frequent comment was that the *rejected* side was more accurate or clearer. In Z4 it was over-interpretation: "where on the page is the basis for this?" Agreement was much higher after *better* was redefined as a faithful reading anchored in the speaker's own words, and *worse* as one specific, checkable defect.

The rounds changed several things at once (method, units, papers and coding level), so this table shows a trajectory, not a controlled comparison. Full record: [`docs/human-calibration.md`](docs/human-calibration.md).

## Known issues in the data

- **Length bias in two types.** In deep-reading and control pairs the chosen side is almost always longer (length AUC ≈ 1.0). Across all of v2 the bias cancels out (AUC 0.50), because emphasis and `imposed_connective` pairs run the other way. Training on a subset needs a length-normalised objective (SimPO, R-DPO) or a length check. See [`data/README.md`](data/README.md).
- **Model-judged, not expert-judged.** All 8,021 pairs passed the programmatic checks and the model reviewer. Only the sampled rounds above were seen by a human expert.
- **Open coding only.** Axial and selective coding (levels 2–3) are not in this dataset.

## Repository map

| Path | What |
|---|---|
| [`pipeline/`](pipeline/) | Z6 generator: `z6.py` (v1), `z6v2.py` (v2), prompts, deterministic checks, word lists, few-shot pairs, self-tests |
| [`review_site/`](review_site/) | Blind A/B review web app (Vercel functions and Blob storage, token links, no model judgments shown before the blind pick) |
| [`data/`](data/) | Data card, schema, export statistics, 32 sample pairs |
| [`docs/`](docs/) | Pipeline design, the human-calibration record, and the Chinese originals in [`docs/zh/`](docs/zh/) |
| [`training/`](training/) | DPO runs: round 1 results and training curves; round 2 added when done |
| [`agent/`](agent/) | The coding agent: level-1 open coding on the post-trained model, levels 2–3 on a general model, gates, metrics, tools, offline tests |
| [`demo/`](demo/) | Access-restricted web demo of the agent with the post-trained model (sign-in by emailed code or GitHub, per-person limits) |

## What is not here

- **The full 8,021 pairs.** Every pair quotes interview material from published, copyrighted articles, so only samples are public.
- **The source corpus and the paper full texts.**
- **The held-out evaluation set.** Complete cases are reserved for final evaluation and are never read by any generation step. Papers in the held-out pools are excluded from generation.
- **Reviewer access tokens, raw answer sheets and the site's answer key.**
- **Model weights.** The base model and the adapter are not in this repository.
- **The interview material the agent was developed on.** It comes from non-public studies. The agent ships with a synthetic example instead, and its naming examples were rewritten for this release.
- **The training evidence repository.** Pre-registration, logs and gate outputs for the DPO runs are in [Hawever-renbo/cdm-open-coding-dpo](https://github.com/Hawever-renbo/cdm-open-coding-dpo) (private; access on request, see [`training/runs/2026-11-03_round1-dpo/`](training/runs/2026-11-03_round1-dpo/#evidence)).

The data pipeline in `pipeline/` reads inputs from the private working tree, so it shows how the data was made but does not run on its own. The agent in `agent/` does run on its own, given a model endpoint.

## License

Code: MIT (see [`LICENSE`](LICENSE)). The sample pairs and quoted excerpts come from published articles and stay under their original rights; they are included only to illustrate the format.
