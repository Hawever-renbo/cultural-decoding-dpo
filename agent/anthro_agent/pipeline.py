"""Three-level grounded-theory coding as a constrained pipeline.

  raw text X -> open codes A (in-vivo labels, level 1) -> concepts T1 -> categories T2 with 6C slots and typed
  relations (level 2) -> core category T3 + theory (level 3) -> E thick-description decoding -> M reflexive notes

Three rules shape the code:
  1. Constrain what the model may not do (a floor: gates, blacklists, bounds). Do not prescribe how it names
     or clusters (no whitelists, no fixed naming grammar).
  2. The model that produces a coding never judges it. Rounds are ranked by five program-computed metrics;
     model self-ratings are recorded as telemetry and select nothing.
  3. Y is the research focus, given from outside. It filters levels 1-2 and anchors level 3; it is neither the
     theory nor something the coding may redefine.
"""
import json
import math
import re
from collections import Counter

from . import checks, opencoder, segment
from . import prompts as P
from .config import PKG_DIR
from .llm import chat, parse_json, parse_list_json

NL = "\n"
# Bounds set by hand; the model adapts inside them (gate G9).
HYPER = {"categories": (5, 15), "concepts": (20, 90), "core_degree_gap": 1}
SCORE_WEIGHTS = {"fidelity": 0.25, "reach": 0.20, "paradigm": 0.20, "specificity": 0.20, "absorption": 0.15}
STOP = set(("the a an and or of to in for is are was were be been i you he she it we they that this these those "
            "my your his her our their not no yes so just like really very but if then because about with from as at on by "
            "do does did have has had can could will would should speaker yeah think okay also other there here don now want "
            "know since use more lot guess well already usually um uh oh ah hey hm hmm actually basically literally kinda "
            "thing things going gonna went come came get got put said say says asked people person something").split())
QUOTED_RE = re.compile(r"[\"“«「『]([^\"”»」』]{12,})[\"”»」』]")


def tok(text):
    return [w.lower() for w in re.findall(r"[A-Za-z]+", text or "") if len(w) > 2 and w.lower() not in STOP]


def _toks(text):
    return set(re.findall(r"[A-Za-z]+", (text or "").lower()))


def naming_examples(lang):
    try:
        data = json.loads((PKG_DIR / "data" / "naming_examples.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], []
    return (data.get("categories") or {}).get(lang) or [], (data.get("core") or {}).get(lang) or []


# ---------------------------------------------------------------- deterministic hooks
def precompute_hooks(texts):
    """TF and IDF over the excerpts, computed once on the source text. IDF measures how rare a word is across
    excerpts, not how important it is: a theme that runs through the whole interview has a low IDF."""
    docs = [d for d in (tok(t) for t in texts) if d]
    n = len(docs)
    tf, df = Counter(), Counter()
    for d in docs:
        tf.update(d)
        df.update(set(d))
    idf = {w: math.log((n + 1) / (df[w] + 1)) + 1 for w in df}
    return {"tf": tf, "idf": idf, "n_docs": n}


def node_score(concepts, hooks):
    """S(v) = D * log(1 + TF) * (IDF + 0.1) * R, computed on the concept's evidence words.
    D = log(1 + attribute richness) keeps short names from winning by default; R = 1 with evidence, else 0.5."""
    tf, idf = hooks["tf"], hooks["idf"]
    scores = []
    for c in concepts:
        ws = tok(c.get("evidence", ""))
        tf_v = c.get("freq", 0) or max((tf.get(w, 0) for w in ws), default=0)
        idf_v = sum(idf.get(w, 0) for w in ws) / len(ws) if ws else 0.0
        attrs = c.get("attributes") or {}
        d = math.log(1 + len(attrs) + sum(len(str(v)) for v in attrs.values()))
        r = 1.0 if c.get("evidence") else 0.5
        scores.append({"concept": c.get("concept", ""), "S": round(d * math.log(1 + tf_v) * (idf_v + 0.1) * r, 3),
                       "TF": tf_v, "IDF": round(idf_v, 3), "D": round(d, 3), "R": r})
    scores.sort(key=lambda x: -x["S"])
    return scores


def _name_map(cats):
    m = {}
    for i, c in enumerate(cats):
        m["C%d" % (i + 1)] = c.get("name", "")
        m[c.get("name", "")] = c.get("name", "")
    return m


def ib_metrics(graph, n_char, semantic=None):
    """Proxies for the two information-bottleneck terms, all computable by program.
    I(X;T): information density rho. I(T;Y): share of categories structurally connected to the core category.
    I(T1;T2): share of concepts absorbed by some category. `semantic` (a model's own estimate) is telemetry."""
    labels, concepts = graph.get("labels") or [], graph.get("concepts") or []
    cats, rels = graph.get("categories") or [], graph.get("relations") or []
    core = (graph.get("core_category") or {}).get("name", "")
    rho = (len(labels) + len(concepts) + len(rels)) / n_char if n_char else 0
    nm = _name_map(cats)
    parent = {c.get("name", ""): c.get("name", "") for c in cats}
    if core:
        parent[core] = core

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x
    for r in rels:
        a, b = nm.get(r.get("from", ""), r.get("from", "")), nm.get(r.get("to", ""), r.get("to", ""))
        if a and b:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra
    core_comp = find(nm.get(core, core))
    reach = sum(1 for c in cats if find(c.get("name", "")) == core_comp) / max(1, len(cats))
    member = set()
    for c in cats:
        member.update(c.get("concepts") or [])
    fid = round(sum(1 for c in concepts if c.get("concept") in member) / max(1, len(concepts)), 3)
    comp = round(len(cats) / max(1, len(concepts)), 3)
    return {"info_density_rho": round(rho, 5), "reachability": round(reach, 3), "semantic_contribution": semantic,
            "fidelity_T1T2": fid, "compression_T1T2": comp, "fidelity_gt_compression": fid > comp,
            "layered_fidelity_holds": semantic is None or fid >= semantic,
            "compression": "%d:%d:%d:1" % (len(labels), len(concepts), len(cats))}


def _bare_noun_end(name):
    nm = (name or "").strip()
    if any(nm.endswith(n) for n in P.BLACKLIST["zh"]):
        return True
    last = re.sub(r"[^a-z]", "", nm.split()[-1].lower()) if nm.split() else ""
    return last in P.BLACKLIST["en"]


def gates(graph, ib=None):
    """G1-G9: floors a coding must clear. Failing gates become feedback for the next round."""
    failed = []
    labels, concepts = graph.get("labels") or [], graph.get("concepts") or []
    cats, rels = graph.get("categories") or [], graph.get("relations") or []
    core = (graph.get("core_category") or {}).get("name", "")
    if not (labels and concepts and cats and rels and core):
        failed.append("G1 structure incomplete (labels, concepts, categories, relations and a core category are all required)")
    names = [c.get("concept", "") for c in concepts]
    if len(set(names)) != len(names):
        failed.append("G2 duplicate concepts")
    bad = sorted({str(r.get("type", "")) for r in rels if r.get("type", "") not in P.REL_TYPES})
    if bad:
        failed.append("G3 illegal relation type: " + ", ".join(bad[:3]))
    slots = {c.get("c6_slot", "") for c in cats} & set(P.C6_SLOTS)
    if len(slots) < 6:
        failed.append("G4 paradigm incomplete, missing: " + "/".join(s for s in P.C6_SLOTS if s not in slots))
    nm = _name_map(cats)
    deg = Counter()
    for r in rels:
        deg[nm.get(r.get("from", ""), r.get("from", ""))] += 1
        deg[nm.get(r.get("to", ""), r.get("to", ""))] += 1
    max_deg = max(deg.values()) if deg else 0
    if max_deg and deg.get(nm.get(core, core), 0) < max_deg - HYPER["core_degree_gap"]:
        failed.append("G5 the core category does not subsume enough (its degree is more than %d below the maximum)" % HYPER["core_degree_gap"])
    if ib:
        if not ib.get("fidelity_gt_compression"):
            failed.append("G6 fidelity not above compression (concept coverage T1->T2 <= compression ratio)")
        if not ib.get("layered_fidelity_holds"):
            failed.append("G7 layered fidelity does not hold")
    for c in cats:
        if _bare_noun_end(c.get("name", "")):
            failed.append("G8 category name ends on a bare noun: " + c.get("name", "")[:40])
            break
    if core and _bare_noun_end(core):
        failed.append("G8 core category name ends on a bare noun")
    lo, hi = HYPER["categories"]
    if not lo <= len(cats) <= hi:
        failed.append("G9 number of categories out of bounds: %d not in [%d, %d]" % (len(cats), lo, hi))
    lo_k, hi_k = HYPER["concepts"]
    lo_k = max(2, min(lo_k, len(labels) // 5))     # the floor scales with input size; small inputs are not blocked
    if not lo_k <= len(concepts) <= hi_k:
        failed.append("G9 number of concepts out of bounds: %d not in [%d, %d]" % (len(concepts), lo_k, hi_k))
    return not failed, failed


LENS_FIELDS = {"thick_description": ["surface"], "chain_of_meaning": ["functional", "cultural_logic", "symbolic_meaning"],
               "emic_etic": ["emotional"], "contextualisation": ["social", "cultural"], "reflexivity": []}


def decode_lens_hook(decode, reflexive):
    """Which of the five lenses left a trace in the decoding (observation only; blocks nothing)."""
    d, r = decode or {}, reflexive or {}
    cov = {}
    for lens, fields in LENS_FIELDS.items():
        if lens == "reflexivity":
            cov[lens] = bool(r.get("boundary")) and bool(r.get("uncertainty"))
        else:
            cov[lens] = all(bool((d.get(f) or "").strip()) for f in fields)
    return {"coverage": cov, "covered": "%d/5" % sum(cov.values())}


def unsupported_quotes(decode, source_text):
    """Quotations in the decoding that are not verbatim in the source text (the decoder may quote only evidence)."""
    out = []
    for val in (decode or {}).values():
        for q in QUOTED_RE.findall(val if isinstance(val, str) else ""):
            if len(q.split()) >= 4 and not checks.is_verbatim(q, source_text):
                out.append(q[:120])
    return out


def rubric(graph, hooks, ib, source_text, self_score=None, referents=None):
    cats, rels = graph.get("categories") or [], graph.get("relations") or []
    concepts, labels = graph.get("concepts") or [], graph.get("labels") or []
    slots = {c.get("c6_slot", "") for c in cats} & set(P.C6_SLOTS)
    n = len(cats)
    edges = {tuple(sorted([r.get("from", ""), r.get("to", "")])) for r in rels
             if r.get("from") and r.get("to") and r.get("from") != r.get("to")}
    ns = node_score(concepts, hooks)
    core_name = (graph.get("core_category") or {}).get("name", "")
    flags = []
    if len(concepts) <= len(cats):
        flags.append("stage_collapse")
    no_ev = sum(1 for c in concepts if not c.get("evidence"))
    if no_ev:
        flags.append("no_evidence:%d" % no_ev)
    bad_quotes = unsupported_quotes(graph.get("decode"), source_text)
    if bad_quotes:
        flags.append("decode_unsupported_quotes:%d" % len(bad_quotes))
    lens = decode_lens_hook(graph.get("decode"), graph.get("reflexive"))
    return {
        "compression": ib["compression"],
        "paradigm_completeness": round(len(slots) / 6, 2),
        "concepts_per_category": round(len(concepts) / n, 2) if n else 0,
        "network_density": round(2 * len(edges) / (n * (n - 1)), 4) if n > 1 else 0,
        "info_density_rho": ib["info_density_rho"],
        "reachability": ib["reachability"],
        "fidelity_T1T2": ib["fidelity_T1T2"],
        "compression_T1T2": ib["compression_T1T2"],
        "fidelity_gt_compression": ib["fidelity_gt_compression"],
        "layered_fidelity_holds": ib["layered_fidelity_holds"],
        "node_score_top5": [[x["concept"], x["S"]] for x in ns[:5]],
        "node_score_mean": round(sum(x["S"] for x in ns) / len(ns), 3) if ns else 0.0,
        "low_confidence_relations": sum(1 for r in rels if isinstance(r.get("confidence"), (int, float)) and r["confidence"] < 0.6),
        "orphan_labels": sum(1 for l in labels if not l.get("concept")),
        "storyline_sentences": len((graph.get("theory") or {}).get("storyline") or []),
        "categories_in_5_7": 5 <= n <= 7,
        "core_names_focus_referent": (any(r.lower() in core_name.lower() for r in referents) if referents else None),
        "failure_modes": flags,
        "decode_unsupported_quotes": bad_quotes[:5],
        "decode_lens_coverage": lens["coverage"], "decode_lenses_covered": lens["covered"],
        # telemetry: a model's ratings of its own output. Recorded, never used to rank rounds.
        "telemetry": {"semantic_contribution": ib["semantic_contribution"], "decode_self_score": self_score},
    }


def score_parts(graph, rub):
    labels = graph.get("labels") or []
    return {"fidelity": rub["fidelity_T1T2"], "reach": rub["reachability"], "paradigm": rub["paradigm_completeness"],
            "specificity": round(min(1.0, rub["node_score_mean"] / 50.0), 3),
            "absorption": round(1.0 - rub["orphan_labels"] / max(1, len(labels)), 3)}


def total_score(parts):
    return round(sum(SCORE_WEIGHTS[k] * parts[k] for k in SCORE_WEIGHTS), 4)


# ---------------------------------------------------------------- model stages (levels 2-3, decode)
class Asker:
    """One prompt in, parsed JSON out. A stage that returns nothing usable is recorded with its cause, so that
    an empty layer in the result can be told apart from a model that had nothing to say."""

    def __init__(self, emit=None):
        self.diagnostics = []
        self.emit = emit or (lambda kind, payload: None)

    def __call__(self, ep, stage, prompt, kind="dict", **kw):
        out = chat(ep, [{"role": "user", "content": prompt}], **kw)
        val = (parse_json if kind == "dict" else parse_list_json)(out["content"]) if out["content"] else None
        if not val:
            cause = out.get("error") or ("output was cut off by the token limit" if out["finish_reason"] == "length"
                                         else "output could not be parsed as JSON")
            d = {"stage": stage, "model": out["model"], "error": cause}
            self.diagnostics.append(d)
            self.emit("stage.error", d)
        return val


def _as_list(v):
    if isinstance(v, list):
        return v
    return [] if v in (None, "") else [v]


def _text_list(v):
    out = []
    for x in _as_list(v):
        if isinstance(x, str):
            s = x.strip()
        elif isinstance(x, dict):
            s = "; ".join(str(val) for val in x.values() if isinstance(val, (str, int, float)) and str(val).strip())
        else:
            s = str(x)
        if s:
            out.append(s)
    return out


def agent_open_dialog(ask, ep, lang, dialog, excerpts, focus, y_current, feedback):
    """Level 1 on a general model (one call over the whole text). Used when no open-coding model is configured."""
    raw = ask(ep, "open", P.open_dialog(lang, focus, dialog, y_current, feedback), kind="list") or []
    lines = [(e["i"], e.get("role", ""), e["text"], _toks(e["text"])) for e in excerpts]
    labels = []
    for item in raw:
        if not isinstance(item, dict) or not str(item.get("label", "")).strip():
            continue
        ev = str(item.get("evidence", "")).strip()
        ev_toks = _toks(ev)
        best, best_sc = None, 0.0
        for i, role, text, lt in lines:           # trace the evidence back to its turn by word overlap
            sc = len(ev_toks & lt) / len(ev_toks) if ev_toks else (1.0 if ev and ev in text else 0.0)
            if sc > best_sc:
                best, best_sc = (i, role, text), sc
        hit = best if best_sc >= 0.6 else None
        label = str(item["label"]).strip()
        labels.append({"label": label, "evidence": ev, "turn_id": hit[0] if hit else None,
                       "role": hit[1] if hit else "", "target": "", "coder": ep.model,
                       "checks": {"format_ok": True, "verbatim_ok": bool(hit) and checks.is_verbatim(ev, hit[2]),
                                  "outside_words": checks.outside_words(label, hit[2]) if hit else [],
                                  "imposed_connectives": checks.imposed_connectives(label, ev)}})
    return labels


def agent_concepts(ask, ep, lang, labels, focus, feedback=None):
    labeled = [{"i": i, "label": l.get("label", ""), "evidence": l.get("evidence", "")} for i, l in enumerate(labels)]
    raw = ask(ep, "concepts", P.concepts(lang, focus, labeled, feedback), kind="list", temperature=0.7) or []
    out = []
    for c in raw:
        if not isinstance(c, dict) or not str(c.get("concept", "")).strip():
            continue
        ids = [i for i in _as_list(c.get("label_ids")) if isinstance(i, int) and 0 <= i < len(labels)]
        freq = c.get("freq") if isinstance(c.get("freq"), (int, float)) else 0
        attrs = c.get("attributes") if isinstance(c.get("attributes"), dict) else {}
        out.append({"concept": str(c["concept"]).strip(), "freq": int(freq) or len(ids), "label_ids": ids, "attributes": attrs})
    return out


def agent_axial(ask, ep, lang, concepts, focus, feedback=None):
    slim = [{"concept": c["concept"], "freq": c.get("freq", 0), "attributes": c.get("attributes", {}),
             "evidence": " ".join((c.get("evidence") or "").split()[:60])} for c in concepts]
    raw = ask(ep, "axial", P.axial(lang, focus, slim, naming_examples(lang)[0], feedback), temperature=0.3) or {}
    cats, rels = [], []
    for c in _as_list(raw.get("categories")):
        if isinstance(c, dict) and str(c.get("name", "")).strip():
            cats.append({"name": str(c["name"]).strip(), "c6_slot": P.c6_normalize(c.get("c6_slot", "")) or str(c.get("c6_slot", "")),
                         "concepts": [str(x).strip() for x in _as_list(c.get("concepts")) if str(x).strip()]})
    for r in _as_list(raw.get("relations")):
        if isinstance(r, dict) and r.get("from") and r.get("to"):
            conf = r.get("confidence")
            rels.append({"from": str(r["from"]).strip(), "to": str(r["to"]).strip(), "type": P.rel_normalize(r.get("type")),
                         "evidence": str(r.get("evidence", "")), "confidence": conf if isinstance(conf, (int, float)) else None})
    return cats, rels


def agent_selective(ask, ep, lang, cats, rels, focus, feedback=None):
    slim = [{"name": c["name"], "c6_slot": c["c6_slot"], "concepts": c["concepts"]} for c in cats]
    raw = ask(ep, "selective", P.selective(lang, focus, slim, rels, naming_examples(lang)[1], feedback), temperature=0.4) or {}
    core = raw.get("core_category") if isinstance(raw.get("core_category"), dict) else {}
    theory = raw.get("theory") if isinstance(raw.get("theory"), dict) else {}
    return ({"name": str(core.get("name", "")).strip(), "mapping": [str(m).strip() for m in _as_list(core.get("mapping")) if str(m).strip()]},
            {"storyline": _text_list(theory.get("storyline") or core.get("storyline")), "propositions": _text_list(theory.get("propositions"))})


def decode_evidence(cats, concepts, labels, per_category=3):
    by_name = {c["concept"]: c for c in concepts}
    out = []
    for cat in cats:
        quotes = []
        for cn in cat.get("concepts") or []:
            for i in (by_name.get(cn) or {}).get("label_ids") or []:
                q = labels[i].get("evidence", "")
                if q and q not in quotes:
                    quotes.append(q)
        if quotes:
            out.append({"category": cat["name"], "quotes": quotes[:per_category]})
    return out


def agent_decode(ask, settings, lang, lens, focus, core_name, storyline, evidence):
    prompt = P.decode(lang, lens, focus, core_name, storyline, evidence)
    raw = ask(settings.decoder, "decode", prompt, temperature=0.8)
    if not raw and settings.decoder is not settings.reasoner:
        raw = ask(settings.reasoner, "decode", prompt, temperature=0.8)
    out = {}
    for k, v in (raw or {}).items():
        key = P.DECODE_ALIAS.get(k, k)
        if key in P.DECODE_KEYS:
            out[key] = v.strip() if isinstance(v, str) else "; ".join(_text_list(v))
    return out


def agent_ib_semantic(ask, ep, lang, core_name, storyline, cats):
    info = [{"name": c.get("name", ""), "concepts": c.get("concepts", [])} for c in cats]
    raw = ask(ep, "telemetry", P.ib_semantic(lang, core_name, storyline, info), kind="list", retries=2) or []
    vals = [float(s["contribution"]) for s in raw if isinstance(s, dict) and isinstance(s.get("contribution"), (int, float))]
    return round(sum(vals) / len(vals), 3) if vals else None


def agent_decode_selfscore(ask, ep, lang, decode):
    raw = ask(ep, "telemetry", P.decode_selfscore(lang, decode), max_tokens=1000, retries=2) or {}
    alias = dict(zip(P.LENS_ZH, P.LENS_KEYS))
    out = {alias.get(k, k): v for k, v in raw.items() if isinstance(v, (int, float))}
    return out or None


# ---------------------------------------------------------------- the loop
def _link(labels, concepts, cats, core, rels):
    """Two-way index between layers, so every category can be traced down to the words someone said."""
    idx2concept = {}
    for c in concepts:
        for i in c.get("label_ids") or []:
            idx2concept.setdefault(i, c["concept"])
    ctoks = [(c["concept"], _toks(c.get("evidence", ""))) for c in concepts]
    for i, l in enumerate(labels):
        if i in idx2concept:
            l["concept"] = idx2concept[i]
            continue
        lt = _toks(l.get("evidence", ""))
        best, best_sc = "", 0.0
        for cn, ct in ctoks:                       # fallback for labels no concept claimed: word overlap
            sc = len(lt & ct) / len(lt) if lt and ct else 0.0
            if sc > best_sc:
                best, best_sc = cn, sc
        l["concept"] = best if best_sc >= 0.5 else ""
    for c in concepts:
        c["label_ids"] = [i for i, l in enumerate(labels) if l.get("concept") == c["concept"]]
    turns = {}
    for l in labels:
        if l.get("concept") and l.get("turn_id") is not None:
            turns.setdefault(l["concept"], set()).add(l["turn_id"])
    supports = [{"from": l["label"], "to": l["concept"], "type": "supports", "evidence": l.get("evidence", "")}
                for l in labels if l.get("concept")]
    abstracts = [{"from": cn, "to": cat["name"], "type": "abstracts_to"} for cat in cats for cn in cat.get("concepts") or []]
    for m in core.get("mapping") or []:           # the core category is linked back to the categories it subsumes
        rels.append({"from": m, "to": core.get("name", ""), "type": "abstracts_to", "evidence": "", "confidence": 1.0})
    return supports, abstracts, {k: sorted(v) for k, v in turns.items()}


def encode(units, focus, *, settings, max_rounds=1, context=None, compare=False, open_mode="auto", max_targets=None,
           lang=None, lens=None, on_event=None):
    """Code a transcript (str) or a list of quotes. Returns {"graph", "rubric", "status", "rounds", "round", "score"}.

    status: passed (all gates clear) | best_effort (complete, some gate failed) | incomplete (a layer is missing)
    | failed (no open codes at all). With max_rounds > 1 every round is scored by program and the best-scoring
    round is returned, which need not be the first one that passes. Failed gates feed the next round.
    """
    emit = on_event or (lambda kind, payload: None)
    lang, lens = lang or settings.lang, lens or settings.lens
    focus = (focus or "").strip()
    if not focus:
        raise ValueError("a research focus is required")
    turns = segment.parse_turns(units) if isinstance(units, str) else [{"role": "", "text": str(u).strip()} for u in units if str(u).strip()]
    excerpts = segment.participant_excerpts(turns)
    if not excerpts:
        raise ValueError("no participant text to code")
    source_text = NL.join(e["text"] for e in excerpts)
    hooks = precompute_hooks([e["text"] for e in excerpts])
    dialog = NL.join("[%d] %s%s" % (e["i"], (e["role"] + ": ") if e["role"] else "", e["text"]) for e in excerpts)
    if open_mode == "auto":
        open_mode = "target" if settings.opencoder.configured else "dialog"
    referents = (context or {}).get("referents")
    F = P.FEEDBACK[lang]
    ep = settings.reasoner
    ask = Asker(emit)
    models = settings.describe()
    if open_mode == "dialog":
        models.update(open_coding=ep.model, open_coding_is_post_trained=False, open_coding_base="")
    coded = {e["i"] for e in excerpts}
    emit("start", {"focus": focus, "excerpts": len(excerpts), "open_mode": open_mode, "models": models, "max_rounds": max_rounds,
                   "turns": [{"i": i, "role": t["role"], "text": t["text"], "coded": i in coded} for i, t in enumerate(turns)]})

    cached, open_info = None, {}
    best, y_current, fb = None, "", []
    for rd in range(1, max_rounds + 1):
        emit("round.start", {"round": rd, "of": max_rounds})
        ask.diagnostics = []
        if open_mode == "target":
            if cached is None:
                cached, open_info = opencoder.open_code(excerpts, focus, settings, context=context, compare=compare,
                                                        max_targets=max_targets, on_event=emit)
            labels = [dict(l) for l in cached]
        else:
            emit("open.start", {"coder": ep.model, "post_trained": False, "targets": None})
            labels = agent_open_dialog(ask, ep, lang, dialog, excerpts, focus, y_current, fb)
            open_info = {"coder": ep.model, "post_trained": False, "labels": len(labels),
                         "scorecard": checks.summarize([l["checks"] for l in labels])}
            emit("open.done", {**open_info, "items": [{k: l[k] for k in ("label", "evidence", "turn_id", "role", "checks")} for l in labels]})
        if not labels:
            fb = [F["open_failed"]]
            emit("round.done", {"round": rd, "passed": False, "failed": fb, "score": 0.0})
            if open_mode == "target":
                break                       # greedy decoding: another round would return the same empty result
            continue
        fb23 = fb if open_mode == "target" else None      # with fixed labels, feedback goes to levels 2-3 instead
        concepts = agent_concepts(ask, ep, lang, labels, focus, fb23)
        for c in concepts:                  # evidence is rebuilt from label ids, not asked from the model again
            c["evidence"] = " ".join(labels[i]["evidence"] for i in c["label_ids"] if labels[i].get("evidence"))
        emit("concepts.done", {"concepts": [{k: c[k] for k in ("concept", "attributes", "label_ids")} for c in concepts]})
        cats, rels = agent_axial(ask, ep, lang, concepts, focus, fb23) if concepts else ([], [])
        emit("axial.done", {"categories": cats, "relations": rels})
        core, theory = agent_selective(ask, ep, lang, cats, rels, focus, fb23) if cats else ({"name": "", "mapping": []}, {"storyline": [], "propositions": []})
        emit("selective.done", {"core_category": core, "theory": theory})
        supports, abstracts, concept_turns = _link(labels, concepts, cats, core, rels)
        decode = agent_decode(ask, settings, lang, lens, focus, core["name"], theory["storyline"],
                              decode_evidence(cats, concepts, labels)) if core["name"] else {}
        if decode.get("cultural_logic"):    # the decoding feeds back into the storyline (T3 is built both ways)
            marker = P.DECODE_MARKER[lang]
            if not any(marker.strip() in s for s in theory["storyline"]):
                theory["storyline"].append(marker + decode["cultural_logic"])
        emit("decode.done", {"decode": decode})
        graph = {"focus": focus, "lang": lang, "lens": lens, "models": models, "open_coding": open_info,
                 "excerpts": [{"i": e["i"], "role": e["role"], "text": e["text"]} for e in excerpts],
                 "labels": labels, "concepts": concepts, "categories": cats, "relations": rels,
                 "supports": supports, "abstracts_to": abstracts, "concept_turns": concept_turns,
                 "core_category": core, "theory": theory, "decode": decode,
                 "reflexive": P.reflexive(lang, len(labels), len(concepts), len(cats), models["open_coding"])}
        semantic = self_score = None
        if settings.telemetry and core["name"]:
            semantic = agent_ib_semantic(ask, ep, lang, core["name"], theory["storyline"], cats)
            self_score = agent_decode_selfscore(ask, ep, lang, decode) if decode else None
        ib = ib_metrics(graph, len(source_text), semantic)
        passed, failed = gates(graph, ib)
        rub = rubric(graph, hooks, ib, source_text, self_score, referents)
        parts = score_parts(graph, rub)
        score = total_score(parts)
        complete = bool(concepts and cats and rels and core["name"])
        rub.update(score=score, score_parts=parts, gates_passed=passed, gates_failed=failed, round=rd,
                   diagnostics=[d for d in ask.diagnostics if d["stage"] != "telemetry"])
        emit("round.done", {"round": rd, "passed": passed, "failed": failed, "score": score, "parts": parts})
        this = {"graph": graph, "rubric": rub, "score": score, "round": rd,
                "status": "passed" if passed else ("best_effort" if complete else "incomplete")}
        if best is None or score > best["score"]:
            best = this
        fb = list(failed)
        if parts["fidelity"] < 0.8:
            fb.append(F["fidelity"])
        if parts["paradigm"] < 1.0:
            fb.append(F["paradigm"])
        if parts["specificity"] < 0.4:
            fb.append(F["specific"])
        if parts["absorption"] < 0.8:
            fb.append(F["absorb"])
        if decode.get("counter_example"):
            fb.append(F["counter"] + decode["counter_example"])
        y_current = core["name"]
    if best is None:
        reason = "; ".join(fb + [d["error"] for d in ask.diagnostics] + (open_info.get("errors") or []))
        emit("done", {"status": "failed", "reason": reason, "open_coding": open_info})
        return {"graph": None, "rubric": None, "status": "failed", "rounds": max_rounds, "round": 0, "score": 0.0,
                "reason": reason, "open_coding": open_info}
    emit("done", {"status": best["status"], "round": best["round"], "score": best["score"]})
    return {"graph": best["graph"], "rubric": best["rubric"], "status": best["status"], "rounds": max_rounds,
            "round": best["round"], "score": best["score"]}
