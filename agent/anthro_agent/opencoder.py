"""Level 1: in-vivo open coding, one target span at a time.

With a post-trained open-coding model configured (OPENCODER_*), every target span is sent to it in the format
it was trained on: a short context card, the numbered excerpts of one unit, and one target span to code. The
answer is one line, `label — [n] «verbatim quote»`, and is checked by program (never by another model).

Without one, the same request goes to the general model, so the agent still runs end to end; the run record
says which model coded.
"""
from concurrent.futures import ThreadPoolExecutor

from . import checks, segment
from .config import PKG_DIR
from .llm import chat

NOT_STATED = "Not stated in the provided text."
CARD = (("research_question", "Research question"), ("site", "Site and participants"),
        ("method", "How the data were collected"), ("section", "This section of the study"))
TASK = "Target excerpt: [{n}] «{span}»\n\nWrite ONE code for the target excerpt."


def system_prompt():
    return (PKG_DIR / "prompts" / "open_coding_system.txt").read_text(encoding="utf-8").strip()


def build_card(focus, context=None):
    ctx = {k: (v or "").strip() for k, v in (context or {}).items()}
    if not ctx.get("section"):
        ctx["section"] = (focus or "").strip()
    return "\n".join("%s: %s" % (title, ctx.get(key) or NOT_STATED) for key, title in CARD)


def plan(excerpts, focus, context=None, max_targets=None):
    """Turn excerpts [{"i", "role", "text"}] into coding jobs. Each job carries the full user message for one
    target span plus what is needed to check the answer and to trace it back to its turn."""
    excerpts = segment.split_long(excerpts)
    card = build_card(focus, context)
    jobs = []
    for w, positions in enumerate(segment.windows(excerpts, max_words=380, max_excerpts=5)):
        local = {k: excerpts[pos]["text"] for k, pos in enumerate(positions, 1)}
        source = card + "\n\n" + "\n".join("[%d] %s" % (k, t) for k, t in local.items())
        for k, pos in enumerate(positions, 1):
            for span in segment.target_spans(excerpts[pos]["text"], min_words=6, max_words=45):
                jobs.append({"window": w, "n": k, "turn_id": excerpts[pos]["i"], "role": excerpts[pos].get("role", ""),
                             "span": span, "excerpts": local,
                             "user": source + "\n\n" + TASK.format(n=k, span=span)})
    dropped = 0
    if max_targets and len(jobs) > max_targets:
        dropped = len(jobs) - max_targets
        jobs = jobs[:max_targets]
    for i, job in enumerate(jobs):
        job["i"] = i
    return jobs, dropped


def _one(ep, model, system, job):
    out = chat(ep, [{"role": "system", "content": system}, {"role": "user", "content": job["user"]}],
               temperature=0, max_tokens=min(ep.max_tokens, 512), model=model, retries=2, backoff=1.5)
    raw = out["content"]
    res = checks.check_code(raw, job["excerpts"], (job["n"], job["span"]))
    parsed = checks.parse_code(raw)
    return {"label": parsed[0] if parsed else "", "quote": parsed[2] if parsed else "", "raw": raw[:600],
            "checks": res, "error": out.get("error", "")}


def open_code(excerpts, focus, settings, *, context=None, compare=False, max_targets=None, on_event=None):
    """Code every target span. Returns (labels, info).

    labels: [{"label", "evidence", "turn_id", "role", "target", "coder", "checks", "base"?}] in text order,
    holding only answers that parsed and whose quote is verbatim. info: counts and check rates.
    """
    emit = on_event or (lambda kind, payload: None)
    post_trained = settings.opencoder.configured
    ep = settings.opencoder if post_trained else settings.reasoner
    model = ep.model
    base_model = settings.opencoder_base_model if (compare and post_trained) else ""
    system = system_prompt()
    jobs, dropped = plan(excerpts, focus, context, max_targets)
    emit("open.start", {"targets": len(jobs), "dropped": dropped, "coder": model, "post_trained": post_trained,
                        "base": base_model})

    def run(job):
        row = {"i": job["i"], "turn_id": job["turn_id"], "role": job["role"], "n": job["n"], "target": job["span"],
               "coder": model, **_one(ep, model, system, job)}
        if base_model:
            row["base"] = _one(ep, base_model, system, job)
        emit("open.label", {k: v for k, v in row.items() if k != "raw"})
        return row

    with ThreadPoolExecutor(max_workers=settings.opencoder_concurrency) as pool:
        rows = list(pool.map(run, jobs))

    labels = []
    for row in rows:
        c = row["checks"]
        if not (c["format_ok"] and row["label"]):
            continue
        # The evidence stored with a label is always text that is really in the excerpt: the model's quote if it
        # is verbatim, otherwise the target span it was asked to code.
        evidence = row["quote"] if c["verbatim_ok"] else row["target"]
        item = {"label": row["label"], "evidence": evidence, "turn_id": row["turn_id"], "role": row["role"],
                "target": row["target"], "coder": row["coder"], "checks": c}
        if "base" in row:
            item["base"] = {"label": row["base"]["label"], "checks": row["base"]["checks"], "model": base_model}
        labels.append(item)
    info = {"coder": model, "post_trained": post_trained, "targets": len(jobs), "dropped_targets": dropped,
            "labels": len(labels), "scorecard": checks.summarize([r["checks"] for r in rows]),
            "errors": sorted({r["error"] for r in rows if r.get("error")})[:3]}
    if base_model:
        info["base"] = {"model": base_model, "scorecard": checks.summarize([r["base"]["checks"] for r in rows])}
    emit("open.done", info)
    return labels, info
