"""The agent's tools: read a finished coding layer by layer, trace any abstraction down to the words someone
said, and run a new coding. Read tools are side-effect free; gt_code is the only tool that calls models."""
import json
from dataclasses import dataclass, field

from .config import ROOT_DIR
from .pipeline import encode
from .store import Session


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: object
    required: list = field(default_factory=list)
    concurrency_safe: bool = True

    def spec(self):
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                "parameters": {"type": "object", "properties": self.parameters, "required": self.required}}}


@dataclass
class ToolContext:
    settings: object
    store: object
    session: Session = field(default_factory=Session)
    on_event: object = None
    limits: dict = field(default_factory=dict)      # host-imposed caps, e.g. {"max_words": 1500, "max_rounds": 1}


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, tool):
        if tool.name in self.tools:
            raise ValueError("tool already registered: " + tool.name)
        self.tools[tool.name] = tool

    def specs(self):
        return [t.spec() for t in self.tools.values()]

    def call(self, name, args, ctx):
        """Run a tool. Failures come back as a JSON error for the model to read; they never raise into the loop."""
        tool = self.tools.get(name)
        if not tool:
            return json.dumps({"error": "unknown tool: %s" % name})
        missing = [k for k in tool.required if args.get(k) in (None, "")]
        if missing:
            return json.dumps({"error": "missing required argument(s): " + ", ".join(missing)})
        try:
            return tool.fn(args, ctx)
        except Exception as e:                      # noqa: BLE001 - a tool error is data for the model
            return json.dumps({"error": "%s failed: %s" % (name, e)}, ensure_ascii=False)


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _cut(s, n):
    return s if not isinstance(s, str) or len(s) <= n else s[:n] + "…"


def _limit(args, default, cap):
    try:
        return min(max(1, int(args.get("limit") or default)), cap)
    except (TypeError, ValueError):
        return default


def _run(ctx):
    run_id = ctx.session.active_run or ctx.store.latest_id()
    if not run_id:
        raise LookupError("no coding exists yet; run gt_code first")
    data = ctx.store.load(run_id)
    if not data["graph"]:
        raise LookupError("the last run produced no coding")
    return data


def overview(args, ctx):
    data = _run(ctx)
    g, r = data["graph"], data["rubric"]
    labels, concepts, cats = g.get("labels") or [], g.get("concepts") or [], g.get("categories") or []
    theory = g.get("theory") or {}
    return _dump({
        "run_id": data["meta"].get("run_id"), "focus": g.get("focus"), "models": g.get("models"),
        "compression": "%d:%d:%d:1" % (len(labels), len(concepts), len(cats)),
        "core_category": (g.get("core_category") or {}).get("name"),
        "theory_propositions": len(theory.get("propositions") or []),
        "storyline_sentences": len(theory.get("storyline") or []),
        "counts": {"excerpts": len(g.get("excerpts") or []), "labels": len(labels), "concepts": len(concepts),
                   "categories": len(cats), "relations": len(g.get("relations") or [])},
        "orphan_labels": r.get("orphan_labels"), "decode_lenses_covered": r.get("decode_lenses_covered"),
        "decode_counter_example": (g.get("decode") or {}).get("counter_example") or None,
        "open_coding_scorecard": (g.get("open_coding") or {}).get("scorecard"),
        "gates_passed": r.get("gates_passed"), "score": r.get("score"),
    })


def core(args, ctx):
    g = _run(ctx)["graph"]
    c, t = g.get("core_category") or {}, g.get("theory") or {}
    out = {"core_category": c.get("name"), "mapping": c.get("mapping"), "theory_storyline": t.get("storyline")}
    if args.get("include_propositions") is not False:
        out["theory_propositions"] = t.get("propositions")
    return _dump(out)


def categories(args, ctx):
    cats = _run(ctx)["graph"].get("categories") or []
    return _dump({"count": len(cats), "categories": [{"name": c.get("name"), "c6_slot": c.get("c6_slot"),
                                                       "concepts": c.get("concepts")} for c in cats]})


def concepts(args, ctx):
    g = _run(ctx)["graph"]
    q, limit, out = str(args.get("query") or "").lower(), _limit(args, 30, 100), []
    for c in g.get("concepts") or []:
        hay = (str(c.get("concept", "")) + " " + json.dumps(c.get("attributes") or {}, ensure_ascii=False)).lower()
        if q and q not in hay:
            continue
        out.append({"concept": c.get("concept"), "attributes": c.get("attributes"), "labels": len(c.get("label_ids") or []),
                    "evidence": _cut(c.get("evidence"), 200)})
        if len(out) >= limit:
            break
    return _dump({"query": args.get("query") or None, "count": len(out), "concepts": out})


def labels(args, ctx):
    g = _run(ctx)["graph"]
    q, limit, out = str(args.get("query") or "").lower(), _limit(args, 30, 100), []
    for l in g.get("labels") or []:
        if q and q not in (str(l.get("label", "")) + " " + str(l.get("evidence", ""))).lower():
            continue
        chk = l.get("checks") or {}
        out.append({"label": l.get("label"), "evidence": _cut(l.get("evidence"), 240), "turn": l.get("turn_id"),
                    "speaker": l.get("role") or None, "concept": l.get("concept") or "",
                    "outside_words": chk.get("outside_words") or [], "quote_verbatim": chk.get("verbatim_ok")})
        if len(out) >= limit:
            break
    return _dump({"query": args.get("query") or None, "count": len(out), "labels": out})


def relations(args, ctx):
    g = _run(ctx)["graph"]
    limit, want, out = _limit(args, 50, 200), args.get("rel"), []
    for r in g.get("relations") or []:
        if want and r.get("type") != want:
            continue
        out.append({k: r.get(k) for k in ("from", "to", "type", "evidence", "confidence")})
        if len(out) >= limit:
            break
    return _dump({"rel": want or None, "count": len(out), "relations": out})


def decode(args, ctx):
    g = _run(ctx)["graph"]
    return _dump({"core_category": (g.get("core_category") or {}).get("name"), "lens": g.get("lens"),
                  "decode": g.get("decode") or {}, "reflexive": g.get("reflexive") or {}})


def rubric(args, ctx):
    return _dump(_run(ctx)["rubric"])


def trace(args, ctx):
    """Category or concept -> concepts -> labels -> verbatim quotes with their turn."""
    g = _run(ctx)["graph"]
    name = str(args.get("name") or "").strip().lower()
    per = _limit(args, 4, 12)
    all_labels = g.get("labels") or []
    by_concept = {c.get("concept"): c for c in g.get("concepts") or []}

    def quotes(concept_name):
        c = by_concept.get(concept_name) or {}
        rows = [all_labels[i] for i in c.get("label_ids") or [] if 0 <= i < len(all_labels)]
        return {"concept": concept_name, "labels_total": len(rows),
                "labels": [{"label": l.get("label"), "quote": _cut(l.get("evidence"), 300), "turn": l.get("turn_id"),
                            "speaker": l.get("role") or None} for l in rows[:per]]}
    cats = [c for c in g.get("categories") or [] if name and name in str(c.get("name", "")).lower()]
    if cats:
        return _dump({"matched": "category", "trace": [{"category": c.get("name"), "c6_slot": c.get("c6_slot"),
                      "concepts": [quotes(cn) for cn in c.get("concepts") or []]} for c in cats[:3]]})
    hits = [cn for cn in by_concept if name and name in str(cn).lower()]
    if hits:
        return _dump({"matched": "concept", "trace": [quotes(cn) for cn in hits[:5]]})
    return _dump({"error": "no category or concept matches %r" % args.get("name"),
                  "categories": [c.get("name") for c in g.get("categories") or []]})


def summary(args, ctx):
    path = ROOT_DIR / "docs" / "design.md"
    try:
        return _cut(path.read_text(encoding="utf-8"), 12000)
    except OSError as e:
        return _dump({"error": "design notes not found: %s" % e})


def gt_code(args, ctx):
    text, focus = str(args["text"]), str(args["focus"])
    lim = ctx.limits or {}
    if lim.get("max_words") and len(text.split()) > lim["max_words"]:
        return _dump({"error": "text too long for this host: %d words, limit %d" % (len(text.split()), lim["max_words"])})
    try:
        rounds = int(args.get("max_rounds") or 1)
    except (TypeError, ValueError):
        rounds = 1
    rounds = max(1, min(rounds, lim.get("max_rounds", 3)))
    units = [s.strip() for s in text.split("\n") if s.strip()] if args.get("units_mode") else text
    res = encode(units, focus, settings=ctx.settings, max_rounds=rounds, max_targets=lim.get("max_targets"),
                 on_event=ctx.on_event)
    if not res.get("graph"):
        return _dump({"status": "failed", "reason": res.get("reason")})
    run_id = ctx.store.new_id()
    ctx.store.save(run_id, res)
    ctx.session.active_run = run_id
    g, r = res["graph"], res["rubric"]
    return _dump({"run_id": run_id, "status": res["status"], "round": res["round"], "score": res["score"],
                  "core_category": (g.get("core_category") or {}).get("name"), "theory": g.get("theory"),
                  "categories": [c.get("name") for c in g.get("categories") or []],
                  "counts": {"labels": len(g.get("labels") or []), "concepts": len(g.get("concepts") or []),
                             "categories": len(g.get("categories") or [])},
                  "gates_failed": r.get("gates_failed"), "models": g.get("models")})


def build_registry():
    reg = ToolRegistry()
    q = {"query": {"type": "string", "description": "Keyword filter (omit to list everything)"},
         "limit": {"type": "integer", "description": "Maximum number of results (default 30, at most 100)"}}
    for tool in (
        Tool("gt_coding_overview", "Overview of the current coding: compression chain (labels:concepts:categories:1), core category, "
             "number of theory propositions, counts per layer, orphan labels, open-coding scorecard, gates and score.", {}, overview),
        Tool("gt_coding_core", "Level 3: the core category (the overall line about the research focus Y), the categories it subsumes, "
             "and the theory: storyline plus falsifiable propositions.",
             {"include_propositions": {"type": "boolean", "description": "Include the propositions (default true)"}}, core),
        Tool("gt_coding_categories", "Level 2: the categories with their 6C slot (P/CC/Ctx/IC/S/Csq) and the concepts each one absorbs.", {}, categories),
        Tool("gt_coding_concepts", "Level 1.5: list or search the concepts (researcher-side abstractions) with attributes and evidence.", q, concepts),
        Tool("gt_coding_labels", "Level 1: list or search the open codes, i.e. in-vivo labels with their verbatim quote, turn, "
             "the concept that absorbed them, and program checks (words outside the excerpt, quote verbatim).", q, labels),
        Tool("gt_coding_relations", "Typed relations between categories (causal, conditional, contextual, intervening, action, consequence, "
             "temporal, includes, opposes, abstracts_to) with evidence and confidence.",
             {"rel": {"type": "string", "description": "Filter by relation type"},
              "limit": {"type": "integer", "description": "Maximum number of results (default 50, at most 200)"}}, relations),
        Tool("gt_coding_decode", "The thick-description decoding of the core category (surface, functional, emotional, social, cultural, "
             "cultural logic, symbolic meaning, counter-example) and the reflexive notes (boundary, position, uncertainty).", {}, decode),
        Tool("gt_coding_rubric", "Program-computed metrics of the current coding: compression, paradigm completeness, structural reachability, "
             "T1->T2 fidelity, node scores, orphan labels, failure modes, gates passed or failed, and the five-metric score. "
             "The `telemetry` block holds model self-ratings; they are not evidence of quality.", {}, rubric),
        Tool("gt_coding_trace", "Trace a category or a concept down to what was said: its concepts, their labels and the verbatim quotes "
             "with turn numbers. Use this before quoting a participant.",
             {"name": {"type": "string", "description": "Category or concept name (a distinctive part of it is enough)"},
              "limit": {"type": "integer", "description": "Quotes per concept (default 4, at most 12)"}}, trace, required=["name"]),
        Tool("gt_coding_summary", "The design notes of this coding method: design rules, what Y is, naming floors, gates, metrics and known pitfalls.", {}, summary),
        Tool("gt_code", "Run three-level coding on a text: open coding -> concepts -> categories with relations -> core category and theory -> decoding. "
             "Needs the text and a research focus Y. Takes a while (several model calls). The result becomes the current coding.",
             {"text": {"type": "string", "description": "Interview transcript with speaker marks (e.g. `Name: ...`), or one quote per line with units_mode"},
              "focus": {"type": "string", "description": "The research focus Y, as the researcher states it"},
              "units_mode": {"type": "boolean", "description": "true = treat each line as one quote; false = treat as a transcript (default)"},
              "max_rounds": {"type": "integer", "description": "Coding rounds: 1 = quick (default), 3 = full; the best-scoring round is kept"}},
             gt_code, required=["text", "focus"], concurrency_safe=False),
    ):
        reg.register(tool)
    return reg
