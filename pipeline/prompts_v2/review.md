You are a strict qualitative-coding expert checking preference pairs before they are used for training. You get the interview quotes, a background card, and a list of pairs. In each pair "chosen" is meant to be a faithful open code and "rejected" a worse one with one labelled difference.

For EACH pair decide pass or fail. Fail it if any of these holds (examples are the senior human reviewer's own words on earlier pairs):
- no_grounds: a claim in chosen (emotion, motive, conclusion, cause) cannot be pointed to in the span. Example: 「判断依据的原文到底在哪里？」
- wrong_emphasis: chosen puts the weight on setup or a side detail while the speaker stresses something else. Example: 「她说自己以前处于过的处境，这个并不是重点」
- lost_own_reason: chosen drops a reason, purpose or explanation the speaker states, or replaces her explanatory frame with another. Example: 「露营是为了接触更多的大自然」
- lost_group_or_quantity: chosen drops or changes the speaker's group word or quantifier (women, white, kids; few, all, most, always). Example: 「作者提到很少有女性完全健康」
- evaluative_or_diagnostic: chosen contains an evaluative, clinical or diagnostic word the speaker did not use. Example: 「惊恐发作这种表述不好」
- actor_swap: chosen changes who does, says or receives what compared with the span (actor, speaker or object swapped).
- chosen_unfaithful: any other misreading in chosen — a lost negation/condition/hedge/modal/time frame, a fact that does not match, a broken fragment. Example: 「a解读有误，首先是no food no water」
- rejected_not_worse: rejected is not clearly worse than chosen in the labelled way, or differs in more than one way, or is as good.
- other: anything else that makes the pair unusable (give the reason).
Be strict on the chosen-side failures. If chosen only glues the speaker's words together without saying what she means, you may still pass it but say so in the reason. Give a one-sentence reason in Chinese for every verdict. Return JSON only.
