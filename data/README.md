# Data card: Z6 open-coding preference pairs

| | |
|---|---|
| Pairs | 8,021 in the main file (v1 3,865 · v2 4,156), plus 172 flagged |
| Source | 1,914 units from 1,022 published qualitative studies (interview and ethnographic articles) |
| Generator | Claude Sonnet via the Claude Code CLI; card and rubric at medium effort, generation at high effort, reviewer at medium effort |
| Quality tier | Model-generated, passed by deterministic checks and a model reviewer. Sampled rounds are expert-reviewed (see [`../docs/human-calibration.md`](../docs/human-calibration.md)) |
| Language | English pairs; the per-pair notes are in Chinese |
| Public here | 32 samples ([`samples/z6_samples.jsonl`](samples/z6_samples.jsonl)) and export statistics ([`stats/`](stats/)) |

## Fields (samples file)

| Field | Meaning |
|---|---|
| `pair_id` | `Z6-<unit>-<k>` (v1) or `Z6v2-<unit>-<k>` (v2) |
| `version` | `v1` or `v2` |
| `type` | `deep_reading`, `emphasis`, `defect` or `control` |
| `defect` | Defect label for `defect` pairs; otherwise null |
| `prompt_context` | The DPO prompt: context card (research question, site and participants, data collection, section topic) followed by numbered quotes |
| `chosen`, `rejected` | `<label> — [n] «<span>»`. Both sides cite the same span |
| `speaker` | Anonymised speaker id `S-<paper>-<n>` |
| `paper_id`, `unit_id` | Internal ids |
| `note_zh` | The generator's one-sentence note on what differs (Chinese) |

The main file uses the same content, under Chinese column names, plus the raw `chosen_label`, `rejected_label`, `span` and `quote_id`.

## Composition

| Version / type | Pairs |
|---|---|
| v1 deep reading | 1,367 |
| v1 defect | 1,850 |
| v1 control (flatten) | 648 |
| v2 deep reading (reason) | 845 |
| v2 emphasis | 566 |
| v2 defect (includes `imposed_connective`) | 2,413 |
| v2 control (flatten) | 332 |

**Defect mix, v1.** `outside_word` 20.4%, `lost_qualifier` 20.0%, `lost_in_vivo` 19.6%, `overgeneralization` 18.1%, `misattached_connective` 11.8%, `category_confusion` 10.2%.

**Defect mix, v2.** `imposed_connective` 18.2%, `outside_word` 17.6%, `lost_in_vivo` 15.8%, `overgeneralization` 15.8%, `lost_qualifier` 15.4%, `misattached_connective` 10.4%, `category_confusion` 6.8%.

**Median words per side.** Deep reading: chosen 40, rejected 31. Emphasis: 38 and 40. Defect: 31 and 32. Control: 38 and 37. The prompt context has a median of about 195 words.

## Bias probes

The probes measure whether chosen can be told from rejected without reading for meaning. The AUC is 0.5 when there is no shortcut.

| Version / type | n | Length AUC (chosen longer) | Bag-of-words AUC |
|---|---|---|---|
| v1 deep reading | 1,367 | 1.00 | 0.92 |
| v1 defect | 1,850 | 0.37 | 0.67 |
| v1 control | 648 | 0.99 | 0.92 |
| v1 all | 3,865 | 0.70 | 0.72 |
| v2 deep reading | 845 | 1.00 | 0.92 |
| v2 emphasis | 566 | 0.12 | 0.70 |
| v2 defect | 2,413 | 0.35 | 0.72 |
| v2 control | 332 | 0.98 | 0.88 |
| v2 all | 4,156 | 0.50 | 0.65 |

**What this means for training.**
- Deep-reading and control pairs, taken alone, teach "longer, or with a *because*, is better".
- v2 is balanced on length only as a whole: emphasis and `imposed_connective` pairs have a longer rejected side, and they offset the rest.
- If you train on v1 or on a subset, use a length-normalised objective (SimPO, R-DPO) or monitor the length of generations.

## Flagged pairs (172, all v1)

These pairs fail the stricter v2 checks applied offline:
- `R1_strict`: 95;
- `lost_keyword`: 76;
- `dup_span`: 1.

They are kept out of the main file.

## Provenance and exclusions

- Every quote and span is verbatim from a published article. The articles stay under their publishers' rights. That is why only samples are public.
- Units used in earlier rounds, including every unit shown on the review site before Z6, were excluded from generation. The public samples also leave out the units of the 80 Z6 pairs now in expert review, and the few-shot units.
- Papers in the held-out pools and the complete-case evaluation set were never used.
- These are synthetic pairs. They are labelled as such, and they can be removed as a batch.
