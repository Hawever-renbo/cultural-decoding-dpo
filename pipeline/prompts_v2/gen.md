You write preference pairs for training a model to do qualitative OPEN CODING of interview quotes. Each pair has a "chosen" code (faithful, deep reading of what the speaker says) and a "rejected" code (worse in exactly one labelled way). Both sides are written in the same format:

    <code label> — [n] «<span>»

where [n] is the quote number and <span> is ONE contiguous span copied exactly from quote n (the same span on both sides, a complete clause or sentence, 5–45 words, not cut mid-phrase). Only the label differs between chosen and rejected.

STANDARDS FOR CHOSEN (approved by the coding expert):
1. Anchored to the span. Keep the speaker's own words wherever possible. Keep every negation, condition, hedge, modal and time frame ("sometimes", "if needed", "I think", "never", "now than formerly").
2. A because/so/but/if/although in the label must attach to the antecedent the speaker herself attached it to. No inference beyond the quote; never the author's or interviewer's framing.
3. Use only words found in the quote (names of people, places and organisations from the background card are fine; other background-card words are not). Inflections are fine; "says/explains/describes/asks" are fine. No outside academic, emotion, stance or evaluative words.
4. A fluent phrase, not fragments glued together; no dangling "although ...".
5. Every claim in the label must be readable off the span itself; if you cannot point to the words, leave it out.
6. Code what the speaker stresses: her first-person stance, what follows "but", what she repeats. Setup and side details are not the point.
7. If the speaker gives her own reason, purpose or explanation, keep it in her terms.
8. Keep the speaker's own group words and quantifiers (women, white, kids, people; few, all, most, always, never). These are hers, not outside words.
9. Use the speaker's own words for feelings; no diagnostic, clinical or evaluative terms.
10. Keep who does and who says what exactly as in the span; never swap the actor, speaker or object.

PAIR TYPES — produce exactly 6 pairs for the unit: 2 D, 3 F, 1 C. Use different spans across the 6 pairs where the quotes allow.
- D (deep reading), two kinds; produce one of each:
  · d_kind "reason": chosen = a code that also carries ONE reason, condition, contrast or consequence the speaker actually states in the span; rejected = the same code without it (shallower), otherwise word-for-word identical. The added part is ≤20 words. Only add a reason if it is what the speaker is stressing; if her point is the main clause, do not make a reason-D pair from that span.
  · d_kind "emphasis": the span contains both setup/background and the point the speaker stresses. rejected = a code of the setup or side detail presented as the point; chosen = a code of what the speaker stresses. rejected must be the SAME LENGTH OR LONGER than chosen (in words). Both must be accurate to the words; only the emphasis differs.
- F (defect): rejected = chosen with exactly ONE defect, edit ≤6 words, every other word identical; rejected must still read fluently and look plausible (no broken grammar, no typos). Use exactly the defect types assigned below, one per F pair. Defect types:
  · overgeneralization — turns the speaker's specific/hedged claim into a general one (adds words like "always", "all", "in general"; rejected LONGER)
  · outside_word — adds an interpretive word or phrase not in the quote (emotion, stance, theory, motive), e.g. "bitterly", "as normal", "prompting her divorce" (rejected LONGER)
  · category_confusion — swaps who/what the code is about (speaker vs. others, cause vs. effect, actor vs. object) with similar length
  · lost_qualifier — drops or flips a negation, condition, hedge, modal or time frame the speaker used (similar length: replace rather than only delete where possible)
  · misattached_connective — keeps a connective but hangs it on the wrong antecedent, or reverses its direction
  · lost_in_vivo — replaces the speaker's own distinctive term with a bland generic word of similar length
- C (control): use the c_kind assigned below.
  · c_kind "flatten": rejected = chosen with the speaker's connective flattened into a parallel list (e.g. "A because B" → "A; B"), all content words kept, length within 10%. Chosen must contain a speaker-stated connective.
  · c_kind "impose": pick a span where the speaker states two things WITHOUT any causal link. chosen = a code that keeps them side by side as she does; rejected = the same code with "because" or "so" inserted to impose a causal link she never states, otherwise identical, length within 10%.

For every pair give "d_kind" (D only, else ""), "c_kind" (C only, else ""), and "note": one short Chinese sentence saying exactly what differs and why chosen is better.

Here are approved example pairs (from an earlier batch, some at category/relation level; your pairs are open codes):
{FEWSHOT}

Return JSON only.
