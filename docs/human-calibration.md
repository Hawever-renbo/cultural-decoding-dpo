# Human calibration record

Every design change in this project came from a blind review by a domain expert. This page records what was reviewed, the scores, and what the expert said. The originals, in Chinese, are in [`zh/`](zh/).

## Reviewers and protocol

- **X1, the gold standard.** A qualitative-research expert. When X1 prefers the rejected side, the pair counts as wrongly built; the pair is not evidence about X1's taste. X1 does not take part in the final evaluation of the trained model.
- **X2, a reference reviewer.** X2 reviewed only Z3, and X2's scores are reported for that round only.
- **The PI's own reviews.** Earlier rounds (R2–R5) of card, rubric and pair review were done by the PI. They are not counted as expert review.

Each pair is reviewed on the [blind review site](../review_site/) in three steps:
1. **Blind pick.** The expert sees A and B in random order, with the context and quotes, and picks A, B, or "about the same". No model-side information is shown at this stage: no intended side, no judge scores, no generation notes.
2. **Reveal.** The site shows which side was intended as better. The expert answers *correct / partly correct / not correct* and may write a reason.
3. **Calibration pairs.** In Z3 and Z4 a few pairs had a deliberately reversed reveal, to check that the expert reads before agreeing.

Below, **blind** means the blind pick equals the intended chosen side ("about the same" counts as a miss). **After reveal** means the answer was *correct*. The pre-registered Z5 acceptance rule counts "about the same" as disagreement.

## Results by round

| Round | Dates | Pairs (X1) | Blind | After reveal: correct / partly / not |
|---|---|---|---|---|
| Z3 | 10-27 → 10-28 | 60 (+6 calibration) | 35/60 (0.58) | 39 / 7 / 14 |
| Z4, formal group | 10-30 → 10-31 | 26 | 9/26 (0.35) | 11 / 11 / 4 |
| Z5 pilot | 11-01 | 15 | 10/15 | 14 / 0 / 1 |
| Z5 second round | 11-02 | 39 | 33/39 | 36 / 1 / 2 |
| Z6, round 1 | 11-03 → | 80 | in review | — |

In Z3, X2 scored 45/60 blind on the same pairs.

The rounds differ in more than the construction method: they also differ in coding level, units and papers. Read the table as the path the project took, not as an ablation.

## Z3: chosen = the published author's reading

**Construction.** A model writes a full three-level coding of a unit without seeing the author's analysis. At one slot (an open code, a category or relation, or the core category), the chosen side adds the paper author's own interpretation. The rejected side rewrites the same slot as a shallower reading of similar length.

**Scores.** Blind 35/60. By level: open codes 13/20, axial 15/25, selective 7/15.

**What X1 said.** X1 wrote 24 comments. 21 of them fall into these groups:

| Group | Comments |
|---|---|
| The rejected side is more accurate, fluent, concise or clear | 9 |
| The chosen side misses the author's point or loses information | 4 |
| The chosen side is obscure, fragmented or unreadable | 4 |
| The chosen side reads only the surface | 2 |
| Confirms the chosen side is deeper | 2 |

Over-interpretation did not come up from X1 in Z3. It came only from X2, e.g. "you can't see the relaxation in the quote".

The pre-registration set no pass threshold for this round, so it was treated as not passed.

## Z4: rubric for both sides, best-of-4, LLM judge

**Construction.** Same idea as Z3, with four changes:
- both sides see the target rubric item and the restraint items;
- the chosen side is the best of 4 candidates;
- an LLM judge scores both sides on the per-unit rubric plus quality items (accurate and lossless, clear and fluent; for the core category, supported by the coding);
- only "clean" pairs are kept.

**Judge calibration first.** On Z3's pairs, split by unit into development and held-out sets, the judge's accepted pairs matched X1 on 12/21 held-out pairs, against a baseline of 0.58. The judge could not predict X1. The PI chose to continue and let a small X1 batch decide.

**Scores.**
- Formal group: blind 9/26, against a pass line of 19/26, so the method was not put into production.
- Of the 17 formal pairs X1 missed blind, X1 still answered *correct* for 2 after reveal, *partly* for 11 and *not correct* for 4. Knowing the author's original reading mostly did not change X1's view.
- Selective-level probe: 2/6.

**What X1 said** (15 comments on the formal group):

| Group | Comments | Examples (X1's words, translated) |
|---|---|---|
| Over-interpretation; no basis on the page | 5 | "the second half of A is an inference, not direct"; "the author's text doesn't show this here"; "over-interpretation" |
| Disagrees with the author's reading itself | 3 | "A's reading is wrong — first of all it's *no food, no water*"; "I feel the stress is on the frustration itself" |
| Concedes the chosen side is deeper, but it is unclear | 3 | "A means something deeper, but the wording isn't clear" |
| Both about the same, or both incomplete | 2 | "both sides feel about the same" |
| Points at a construction artifact | 1 | "B's last conclusion is extra information" |

The probe and judge-rejected groups added: "what is B's judgment based on?", "where exactly is the source text for this judgment?", "A has a value judgment, and it isn't accurate".

**Takeaway.** Pairs built as "chosen = the author's reading" did not hold up for X1. The cause was either over-reading beyond the quote, or X1 disagreeing with the reading itself. The selective level failed too: the author's core category rests on the whole study, and one unit's coding cannot support it.

## Z5: shared base, one edit, open codes only

**Construction.** Both sides share one base open code, and each pair makes exactly one edit:
- **D (deep).** The chosen side adds a deeper reading that the page itself grounds, usually the speaker's own stated link. The rejected side is the base.
- **F (defect).** The chosen side is the base. The rejected side adds one verifiable defect.
- **Control.** The chosen side keeps a connective; the rejected side flattens it into a list.

**Pre-registration.** The release rule was 72 of 80 fresh pairs with X1 agreeing blind. Z5 had not reached that test when the project moved to Z6.

**Scores.** Pilot: blind 10/15, *correct* after reveal 14/15. Second round: blind 33/39, *correct* after reveal 36/39.

**What X1 said.** X1 wrote few comments, and each named a precise miss:
- "the situation she says she used to be in is not the point" (emphasis);
- "the author mentions that very few women are completely healthy" (a lost quantifier);
- "because of her own bad experience, she doesn't want to discriminate against others";
- "it means she got used to it; it has nothing to do with coming and going".

The pilot's misses on defect pairs were added inferences that read naturally, such as *bitterly*, *as normal*, *prompting her divorce*. They became the `outside_word` examples in Z6.

**Cost problem.** In its production round Z5 used 887 model calls for 18 accepted pairs.

## Z6: direct generation under the expert's standards

**Construction.** One generation call per unit produces 6 pairs (2 deep, 3 defect, 1 control) directly from the quotes. Z6 builds on the earlier rounds in four ways:
- **The standards for "chosen"** are the ten rules in [`pipeline/prompts_v2/gen.md`](../pipeline/prompts_v2/gen.md). They are distilled from X1's comments: keep the speaker's group words and quantifiers, keep her own reasons, code what she stresses, use no outside or diagnostic words, and so on.
- **The few-shot examples** are the Z5 pilot pairs X1 judged *correct*.
- **The reviewer's failure categories** quote X1's comments verbatim (see [`pipeline/prompts_v2/review.md`](../pipeline/prompts_v2/review.md)).
- **The deterministic checks** enforce what can be checked by program: a verbatim span, a single difference, edit size, no content words from outside the quote, and a kept group word.

**v1 → v2.** v2 revised the prompts, after testing them in a small A/B run, and made three structural changes:
- emphasis pairs became their own type;
- the "imposed causal link" pairs moved from control to defect (`imposed_connective`);
- a check for duplicated spans was added.

**Cost.** Z6 used 5,017 calls for 8,021 pairs in total.

**Expert check.** Round 1 is an 80-pair stratified sample covering v1 and v2 and every type; it is on the review site now. Its result will be added here.
