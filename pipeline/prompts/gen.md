You write preference pairs for training a model to do qualitative OPEN CODING of interview quotes. Each pair has a "chosen" code (faithful, deep reading of what the speaker says) and a "rejected" code (worse in exactly one labelled way). Both sides are written in the same format:

    <code label> — [n] «<span>»

where [n] is the quote number and <span> is ONE contiguous span copied exactly from quote n (the same span on both sides, a complete clause or sentence, 5–45 words, not cut mid-phrase). Only the label differs between chosen and rejected.

STANDARDS FOR CHOSEN (approved by the coding expert):
1. Anchored to the span. Keep the speaker's own words wherever possible. Keep every negation, condition, hedge, modal and time frame ("sometimes", "if needed", "I think", "never", "now than formerly").
2. A because/so/but/if/although in the label must attach to the antecedent the speaker herself attached it to. No inference beyond the quote and background; never the author's or interviewer's framing.
3. Use only words found in the quote or the background card (inflections are fine; "says/explains/describes" are fine). No outside academic, emotion, stance or evaluative words.
4. A fluent phrase, not fragments glued together; no dangling "although ...".

PAIR TYPES — produce exactly 6 pairs for the unit: 2 D, 3 F, 1 C. Use different spans across the 6 pairs where the quotes allow.
- D (deep reading): chosen = a code that also carries ONE reason, condition, contrast or consequence the speaker actually states in the span (verifiable from the quote alone, not from background). rejected = the same code without it (shallower), otherwise word-for-word identical. The added part is ≤20 words.
- F (defect): rejected = chosen with exactly ONE defect, edit ≤6 words, every other word identical; rejected must still read fluently and look plausible (no broken grammar, no typos). Use exactly the defect types assigned below, one per F pair. Defect types:
  · overgeneralization — turns the speaker's specific/hedged claim into a general one (adds words like "always", "all", "in general"; rejected LONGER)
  · outside_word — adds an interpretive word or phrase not in the quote (emotion, stance, theory, motive), e.g. "bitterly", "as normal", "prompting her divorce" (rejected LONGER)
  · category_confusion — swaps who/what the code is about (speaker vs. others, cause vs. effect, actor vs. object) with similar length
  · lost_qualifier — drops or flips a negation, condition, hedge, modal or time frame the speaker used (similar length: replace rather than only delete where possible)
  · misattached_connective — keeps a connective but hangs it on the wrong antecedent, or reverses its direction
  · lost_in_vivo — replaces the speaker's own distinctive term with a bland generic word of similar length
- C (control): rejected = chosen with the speaker's connective flattened into a parallel list (e.g. "A because B" → "A; B", "A if B" → "A, B"), all content words kept, length within 10%. Chosen must contain a speaker-stated connective.

For every pair also give "note": one short Chinese sentence saying exactly what differs and why chosen is better.

Here are approved example pairs (from an earlier batch, some at category/relation level; your pairs are open codes):
{FEWSHOT}

Return JSON only.
