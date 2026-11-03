# pipeline/: the Z6 pair generator

The design is described in [`../docs/pipeline.md`](../docs/pipeline.md). Code comments are in Chinese.

| File | Role |
|---|---|
| `z6.py` | v1: select units, card + rubric, generate, check, review, export, report |
| `z6v2.py` | v2 full run: imports v1, with the v2 prompts and checks and three type changes |
| `z6v2_ab.py` | v1 vs. v2 A/B on the same units; v2 local checks (`R1_strict`, `lost_keyword`) |
| `lib/prefilter.py` | quote prefilter, no model calls |
| `lib/checks.py` | tokenising, lemmas, content words, R1 closed-class rule, single-diff and verbatim checks |
| `lib/units.py` | reads units from the earlier rounds' frozen order; applies exclusions |
| `lib/claude_cli.py` | `claude -p` wrapper: JSON schema, disk cache, cost ledger, quota exit code 75, call lock |
| `prompts/`, `prompts_v2/` | card, generation and reviewer prompts. `prompts_v2/常见坑_草案.md` is a draft list of pitfalls collected from the expert's comments |
| `fewshot/pilot_x1.jsonl` | Z5 pilot pairs with the expert's verdicts; those judged *correct* serve as few-shot examples |
| `tools/strict_checks.py` | offline re-check of v1 pairs with the v2 rules → flagged file |
| `tools/final_export.py` | merges v1 and v2, writes stats and bias probes |
| `tools/sample_x1.py` | draws the stratified 80-pair sample for expert review |
| `tests/` | self-tests, no model calls |

The scripts read their inputs (units, cards, earlier-round files) from the private working tree, which is not published. They document the method; they will not run from this repo alone.
