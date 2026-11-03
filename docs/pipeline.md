# Z6 pipeline

Code: [`pipeline/`](../pipeline/). `z6.py` is v1. `z6v2.py` is v2: it imports v1 and replaces the prompts and the checks. All model calls go through the Claude Code CLI (`claude -p`) with Claude Sonnet.

## 0. Units

A **unit** is one analytic section of one published qualitative study. It consists of:
- the study's front matter;
- the author's text for that section;
- the numbered interview or field quotes in it.

Units are drawn in a frozen order from the earlier rounds' candidate pool. Three things are excluded:
- units used in any earlier round, and units on the review site;
- papers in the held-out pools;
- the complete-case evaluation set. No step ever reads it.

## 1. Quote prefilter (no model calls)

[`lib/prefilter.py`](../pipeline/lib/prefilter.py) keeps quotes that have all of these properties:
- 15–200 words;
- complete sentences;
- one speaker, with no interviewer turns;
- no internal ellipses;
- few brackets.

Attribution tags such as "(Respondent #21)" are split off and kept as speaker hints.

## 2. Card and rubric: one call per paper

Prompt: [`prompts_v2/card.md`](../pipeline/prompts_v2/card.md). The input is the front matter (≤ 1,500 words), plus, for each unit, its section text (≤ 500 words) and its quotes. The model returns two things.

**A context card**, shared by all units of the paper:
- research question;
- site and population;
- how data were collected;
- a neutral section topic, with no findings.

**For each unit:**
- who speaks each quote;
- a 3–5 item rubric of what a faithful open coding must capture. Each item is pinned to an exact span of 3–30 words.

The rubric describes what the speaker says, never what the author concludes. Fields the paper does not state are written as "无" (none); the model is told not to guess them.

## 3. Generation: one call per unit, 6 pairs

Prompt: [`prompts_v2/gen.md`](../pipeline/prompts_v2/gen.md); Sonnet at high effort.

Both sides use the same format and cite the same span; only the label differs:

```
<code label> — [n] «<one contiguous span copied from quote n, 5–45 words>»
```

**Ten standards for the chosen side.** These are distilled from the expert's comments:
1. stay anchored to the span;
2. keep every negation, hedge, modal and time frame;
3. attach connectives where the speaker attached them;
4. use only words from the quote (names from the card are allowed);
5. write a fluent phrase;
6. make every claim readable off the span;
7. code what the speaker stresses;
8. keep her own reasons;
9. keep her group words and quantifiers;
10. use no diagnostic or evaluative words, and do not swap actors.

**The mix per unit, in v2.** v1 asked for 2 D pairs of a single kind (added reason) and used `flatten` as the only control.

| Kind | Count | How the rejected side differs |
|---|---|---|
| D, reason | 1 | Drops one reason, condition, contrast or consequence the speaker states (added part ≤ 20 words). |
| D, emphasis (exported as type K, *emphasis*) | 1 | Codes the setup instead of the point, and is the same length or longer. |
| F, defect | 3 | One assigned defect, edit ≤ 6 words, otherwise word-for-word identical. The three defect types rotate per unit by a hash of the unit id, so the mix stays balanced. |
| C, control | 1 | Assigned per unit. `flatten`: the speaker's connective becomes a list, with content words kept. `impose`: the speaker states two things side by side, and the rejected side inserts a *because* or *so* she never states. v2 exports `impose` pairs as the defect `imposed_connective`. |

**Few-shot examples.** These are pairs from the Z5 pilot that the expert judged *correct*. Each pair also carries a one-line note, in Chinese, on what differs.

## 4. Deterministic checks (no model calls)

The v1 checks are `z6.local_checks`; the v2 checks are `z6v2_ab.local_checks_v2`. A pair is dropped if any check fails:

| Check | Rule |
|---|---|
| format | type, both labels and a span are present |
| evidence_not_verbatim | the span is not found character-for-character in the quote |
| identical | chosen = rejected |
| not_single_diff | the two labels differ in more than one contiguous place |
| edit_or_length | F: edit > 6 words or length gap > 15%. D: added part > 20 words. C: length gap > 10% |
| R1 (v1) / R1_strict (v2) | the chosen label uses a content word that is not in the quote. Function words, reporting verbs and inflections are allowed. In v2 the card contributes proper nouns only |
| lost_keyword (v2) | a group noun or quantifier in the span is missing from the chosen label |
| dup_span (v2) | a label re-quotes the span, or the span repeats itself |
| dedup | within a unit, content-word overlap ≥ 0.8 with an already kept pair of the same type |

In v2, these checks dropped the following numbers of pairs:

| Check | Pairs dropped |
|---|---|
| not_single_diff | 605 |
| R1_strict | 278 |
| dedup | 204 |
| edit_or_length | 115 |
| lost_keyword | 115 |
| evidence_not_verbatim | 22 |
| dup_span | 12 |
| format | 6 |

v1 pairs were re-checked offline with the v2 rules ([`tools/strict_checks.py`](../pipeline/tools/strict_checks.py)). The 172 that fail are exported separately as *flagged*.

## 5. Model reviewer: one call per unit

Prompt: [`prompts_v2/review.md`](../pipeline/prompts_v2/review.md). The reviewer sees the quotes, the card and the surviving pairs, and returns pass or fail for each pair with a reason. Only passing pairs are kept.

The failure categories follow the expert's own feedback, and the prompt quotes the expert verbatim as examples:

| Category | Example from the expert |
|---|---|
| `no_grounds` | "where in the text is the basis for this judgment?" |
| `wrong_emphasis` | "the situation she says she used to be in is not the point" |
| `lost_own_reason` | — |
| `lost_group_or_quantity` | — |
| `evaluative_or_diagnostic` | "'panic attack' is not a good way to put it" |
| `actor_swap` | — |
| `chosen_unfaithful` | — |
| `rejected_not_worse` | — |
| `other` | — |

On average, v2 kept 4.26 of the 6 generated pairs per unit.

## 6. Export

[`tools/final_export.py`](../pipeline/tools/final_export.py) does the following:
- merges v1 and v2;
- anonymises speakers to `S-<paper>-<n>`;
- writes the main and flagged files;
- reports counts, the defect mix and two bias probes. The probes are the AUC of the chosen side being longer, and a bag-of-words logistic AUC. The results are in [`data/README.md`](../data/README.md).

## Engineering notes

- **CLI wrapper** ([`lib/claude_cli.py`](../pipeline/lib/claude_cli.py)):
  - tools are disabled, and output follows a JSON schema;
  - the fixed instructions go in the system prompt, so they stay cached across calls;
  - every response is cached on disk under a hash of the full request;
  - every call is logged with tokens and cost.
- **Quota handling.** On a subscription-limit message the run exits with code 75. A shell loop then retries every 30 minutes and resumes from the per-unit checkpoints, so nothing is generated twice.
- **Call lock.** No real model call can happen until a lock file is removed and an environment flag is set.
- **Self-tests.** [`tests/selftest.py`](../pipeline/tests/selftest.py) and [`tests/selftest_v2.py`](../pipeline/tests/selftest_v2.py) test the checks and the prefilter on hand-written cases, with no model calls.
