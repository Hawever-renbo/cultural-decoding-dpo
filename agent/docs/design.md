# Design notes: three-level coding as a constrained pipeline

These notes explain why the agent is built the way it is: its rules, its layers, what is checked by program, and what was tried and dropped. The agent's `gt_coding_summary` tool returns this file.

## 0. Design rules

**Within a frame of constraints, let the model do as much as it can.** Three consequences:

1. **Constrain what the model may not do (a floor); do not prescribe how it does the work (the ceiling).**
   - Floor = deterministic hooks and gates: a blacklist of bare-noun names, names must land on a concrete action, names must be bound to the phenomenon, the core category must stay on Y, propositions must be falsifiable, the structure must be connected, counts must stay inside bounds that scale with the input.
   - The ceiling is left open: no naming grammar, no clustering axis, no fixed field structure. Those are the model's to choose.
2. **The model that produces a coding does not judge it.** Rounds are ranked by program-computed metrics only (fidelity, structural reach, paradigm completeness, specificity, label absorption). A model's ratings of its own output are recorded as telemetry and decide nothing.
3. **Y is the focus. It is not the theory and not the core category.** Y is the research focus, given from outside by the researcher.
   - For levels 1–2 it is a relevance filter: keep what bears on it, drop the rest.
   - For level 3 it is an anchor: the core category must converge on Y and name what Y refers to.
   - The core category is the overall line about Y. The theory is the explanatory frame raised from it: a storyline plus falsifiable propositions.

## 1. Layers

```
raw text X
  -> A   open codes: in-vivo label + verbatim quote          (level 1)
  -> T1  concepts: researcher-side abstractions + attributes
  -> T2  categories with a 6C slot, and typed relations      (level 2)
  -> T3  core category + mapping; theory = storyline + propositions   (level 3)
  -> E   decoding: thick description in eight fields
  -> M   reflexive notes: boundary, position, uncertainty
```

| Layer | Voice | Output |
|---|---|---|
| A open codes | the participant's own words (emic) | `label`, `evidence` (verbatim quote), `turn_id`, program checks |
| T1 concepts | the researcher's (etic) | `concept`, `attributes`, `label_ids` |
| T2 categories | etic | `name`, `c6_slot`, `concepts` |
| T3 core category | etic | `name`, `mapping` |
| theory | etic | `storyline`, `propositions` |
| E decoding | interpretive | surface, functional, emotional, social, cultural, cultural logic, symbolic meaning, counter-example |
| M reflexive | the program | boundary, position, uncertainty |

**Traceability.** The result is a graph: labels `supports` concepts, concepts `abstracts_to` categories, categories carry typed relations with a confidence, and the core category is linked back to the categories it subsumes. Every label keeps its quote and turn number, so any abstraction can be followed down to what someone said (`gt_coding_trace`).

**Who writes what.** Level 1 can run on the post-trained open-coding model: one statement at a time, in the format it was trained on (`label — [n] «verbatim quote»`), greedy, thinking off. Levels 2–3, the decoding and the conversation run on a general chat model. The training data cover open coding only, so nothing above level 1 is attributed to the post-trained model.

## 2. The loop

```
encode(text, focus)
  parse turns -> participant excerpts -> TF / IDF hooks
  for each round:
     open codes -> concepts -> categories + relations -> core + theory -> decoding
     -> metrics -> gates -> score
  return the round with the highest score
```

- All `max_rounds` rounds are run. The round returned is the best-scoring one, which need not be the first that passes the gates.
- Failed gates and low metrics become feedback for the next round.
- With the post-trained model, level 1 is coded once (decoding is greedy, so repeating it changes nothing) and the feedback goes to levels 2–3.

**Temperatures by stage.** Freedom where the work diverges, stability where structure is set.

| Stage | Temperature | Reason |
|---|---|---|
| open coding (post-trained model) | 0 | as trained and evaluated |
| concepts | 0.7 | abstraction, moderate |
| categories and relations | 0.3 | the frame must be stable; this stage is the main source of run-to-run variation |
| core category and theory | 0.4 | a stable anchor, still rich propositions |
| decoding | 0.8 | interpretive, expansive |

## 3. Constraints

### 3.1 Naming floors (what a name may not be)

1. Not a bare noun. Names may not end on: background, strategy, preference, outcome / result, culture, environment (gate G8).
2. It must land on a concrete action (a concrete verb, e.g. a gerund), not stop at an action-less generality such as "practice", "negotiation", "needs".
3. It must be bound to the phenomenon: a constitutive dimension of what the focus is about.
4. No joining of unrelated themes with "and".

Removed on purpose, because they prescribe *how*: a whitelist of head words, a fixed format (modifier + gerund), clustering by mechanism. They produced empty shells or pulled the coding away from Y.

### 3.2 Gates

| Gate | Floor |
|---|---|
| G1 | The structure is complete: labels, concepts, categories, relations and a core category all exist |
| G2 | No duplicate concepts |
| G3 | Relation types are legal |
| G4 | All six 6C slots are covered |
| G5 | The core category subsumes: its degree is at most 1 below the highest degree |
| G6 | T1→T2 fidelity is above the compression ratio |
| G7 | Layered fidelity holds |
| G8 | No category or core name ends on a bare noun |
| G9 | The number of categories and of concepts is inside bounds that scale with the input |

G7 compares fidelity with a model's own estimate of category contribution when telemetry is on; like every gate it only produces feedback. It never ranks rounds.

### 3.3 The 6C paradigm (Strauss and Corbin)

P phenomenon, CC causal conditions, Ctx context, IC intervening conditions, S action strategies, Csq consequences. All six must be covered; a category that fits none is not forced into one.

### 3.4 Theory in two layers

- `core_category = {name, mapping}`: the hub. It carries only the dominant condition. It does not try to cover everything, because that forces it up into super-class words.
- `theory = {storyline, propositions}`: the propositions cover all the specific conditions, and each can fail ("the stronger X, the more …; if …, the proposition is refuted").

### 3.5 The decoding may quote only what was said

The decoding step receives the quotes behind each category and may quote only from them. A program check lists every quotation in the decoding that is not verbatim in the source text (`decode_unsupported_quotes`).

## 4. Computation (deterministic hooks)

**TF and IDF.** `TF[w]` is the word's frequency in the excerpts. `IDF[w] = log((N + 1) / (df[w] + 1)) + 1` with `df` the number of excerpts containing the word. IDF measures rarity, not importance: a theme that runs through the whole interview has a high TF and a low IDF.

**Node score.** `S(v) = D · log(1 + TF) · (IDF + 0.1) · R`, computed on a concept's evidence words. `D = log(1 + attribute richness)` keeps short names from winning by default. `R` is 1 with evidence and 0.5 without.

**Information-bottleneck proxies.**
- `I(X;T)`: information density `rho = (labels + concepts + relations) / characters`.
- `I(T;Y)`: structural reach, the share of categories connected to the core category.
- `I(T1;T2)`: fidelity, the share of concepts absorbed by a category.

**Round score.** `0.25·fidelity + 0.20·reach + 0.20·paradigm completeness + 0.20·specificity + 0.15·label absorption`, with `specificity = min(1, mean node score / 50)`. Everything in it is computed by program.

**G9 bounds.** Categories: 5 to 15. Concepts: at most 90, at least `max(2, min(20, labels // 5))`, so that small inputs are not blocked and over-compression is still caught.

**Truncated output.** If a JSON array is cut off by the token limit, it is closed after the last complete object and parsed; only the trailing half-object is lost.

**Open-code checks.** For every `label — [n] «quote»`: is the format right, is the quote verbatim in excerpt n, does the label contain content words found nowhere in the excerpts, does it contain a causal or contrast connective the quote does not, is there text after the answer.

## 5. Directions tried and dropped

| Direction | Why it was dropped |
|---|---|
| Set-theoretic classification into a finite list of types | Grounded types emerge from the data; they are not a closed set |
| QCA (necessity / sufficiency) | It needs a truth table and a binary outcome; the output here is a narrative structure |
| Weight of evidence | Evidence spans are short, so content words rarely repeat |
| Category extraction by co-occurrence graph clustering | Co-occurrence edges between concepts were far too sparse |
| A whitelist or a fixed naming grammar | It prescribes how; it yields empty shells or names detached from Y |
| A model's semantic mutual-information estimate as the verdict | A single self-rating varies by about ±0.1 between calls |

## 6. Metric pitfalls

1. Information density `rho` is not name density; it is dominated by the number of labels.
2. Hyphen counts cannot compare naming density across languages.
3. A single model self-rating is not a stable verdict.
4. IDF as a specificity signal is questionable: it rewards rarity and penalises the main thread.
5. An open coder that over-produces labels raises the G9 floor and lowers the compression ratio.
6. Some texts support two competing framings. Voting over several runs stabilises the categories but cannot settle the frame.

## 7. What this public version leaves out or changes

- **No project data.** The interview material and the naming examples the pipeline was developed with come from non-public studies and are not here. `data/naming_examples.json` holds illustrative examples written for this release, so outputs will differ from internal runs. No evaluation figures are reported for this version.
- **No held-out cases.** Case-based evaluation against published gold codings exists, but those cases belong to the held-out evaluation set and stay private.
- **English output.** Prompts exist in Chinese (the working language of development) and in English translation. The specificity constant (50) was calibrated on Chinese output.
- **Open coding per statement.** In round 1 of training, coding a whole unit at once regressed, so the agent sends one statement at a time.
- **English tokenisation** for TF / IDF and for the open-code checks.
- An LDA topic hook existed in development but fed no decision; it is omitted.
