# agent/: a coding agent for interview and field material

An agent that does grounded-theory three-level coding (open → axial → selective) and can be asked about the result. It is the harness half of this repository; the model half is the post-trained open-coding model in [`../training/`](../training/).

**Authors:** sangji (GitHub: Hawever-renbo), M. Cen

```
                  transcript + research focus Y
                              │
   level 1   open codes ──────┤   post-trained open-coding model, one statement at a time
             label — [n] «verbatim quote»        ↳ program checks: format, verbatim, outside words
                              │
   level 2   concepts → categories (6C slots) + typed relations ┐
   level 3   core category + theory (storyline, propositions)   ├ general chat model
             decoding (thick description, quotes only evidence) ┘
                              │
             gates G1–G9 · five program-computed metrics · best round kept
                              │
        tools ── read any layer · trace a category down to its quotes · run a coding
                              │
                        the agent loop  ←→  you
```

Standard library only (Python 3.9+). Every model is reached through an OpenAI-compatible endpoint set in the environment, so the agent is not tied to a provider.

## Try it

```bash
cd agent
cp .env.example .env          # fill in REASONER_*; OPENCODER_* if you serve the post-trained model
python -m anthro_agent check
python -m anthro_agent code -f examples/synthetic_interview.txt \
  --focus "How night-market food vendors decide whether to accept mobile payments"
python -m anthro_agent chat    # then ask: "Why does Tomas keep the code in the drawer? Quote him."
```

Without `OPENCODER_BASE_URL`, the general model also writes the open codes; the run record says which model coded. With it, level 1 goes to the post-trained model in the format it was trained on, and `--compare` also codes every statement with the untrained base model so the two can be read side by side.

`examples/synthetic_interview.txt` is a synthetic interview written for this repository. No research data is included.

## What is in here

| Path | What |
|---|---|
| `anthro_agent/opencoder.py` | Level 1. Builds the context card and one request per statement; checks every answer by program |
| `anthro_agent/pipeline.py` | Levels 2–3, decoding, hooks (TF / IDF, node score), gates G1–G9, round scoring, the loop |
| `anthro_agent/prompts.py` | Prompts in Chinese (as developed) and English (translation) |
| `anthro_agent/checks.py` | Checks on an open code: verbatim quote, words the speaker never used, imposed connectives |
| `anthro_agent/tools.py` | The agent's 11 tools |
| `anthro_agent/agent.py` | The agent loop (native tool calls, or a text protocol for servers without a tool parser) |
| `anthro_agent/segment.py` | Transcript → turns → statements, deterministic |
| `docs/design.md` | Design rules, gates, metrics, what was tried and dropped |
| `tests/` | Offline tests with a rule-based mock model: `python -m unittest discover -s tests` |

## Tools

| Tool | Does |
|---|---|
| `gt_code(text, focus)` | Runs a coding; the result becomes the current coding |
| `gt_coding_overview` | Compression chain, core category, counts, gates, score |
| `gt_coding_labels` | Level 1: labels with quote, turn and program checks |
| `gt_coding_concepts`, `gt_coding_categories`, `gt_coding_relations` | Level 2 |
| `gt_coding_core` | Level 3: core category, storyline, propositions |
| `gt_coding_decode` | The decoding and the reflexive notes |
| `gt_coding_trace(name)` | A category or concept, down to its quotes and turn numbers |
| `gt_coding_rubric` | The program-computed metrics and gates |
| `gt_coding_summary` | The design notes |

## Three rules the code follows

1. **A floor, not a recipe.** Gates and blacklists say what a coding may not be. How to name and cluster is left to the model.
2. **The model that codes does not judge.** Rounds are ranked by five program-computed metrics. A model's ratings of its own output are logged under `telemetry` and decide nothing.
3. **The focus comes from the researcher.** It filters levels 1–2 and anchors the core category; the coding may not redefine it.

Details: [`docs/design.md`](docs/design.md).

## Limits

- The post-trained model covers open coding only. Concepts, categories, the core category and the theory are proposals from a general model, for the researcher to check against the data.
- The naming examples in `data/naming_examples.json` were written for this release; the ones used in development come from non-public studies. No evaluation figures are reported for this public version.
- Level 1 with the post-trained model is tested here against a mock that follows the served model's request and answer format. The model itself is not in this repository.
- TF / IDF and the open-code checks tokenise English.
- One interview is not a general rule. The agent is told to say so.
