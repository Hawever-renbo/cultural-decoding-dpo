"""Z6 直出（专家组定稿 2026-11-02；B 臂：每篇一次 Sonnet 写卡＋Rubric，同篇单元共用）。
流程：零调用引语预筛 → 按篇选单元 → 卡＋Rubric（每篇 1 次，Sonnet）→ 生成（每单元 1 次，Sonnet high，6 对：2D 3F 1C）
      → 零调用检查（格式、证据逐字、单处差异、改动幅度/长度比、R1 闭集白名单、单元内去重）→ 复核（每单元 1 次，Sonnet，一个顺序）→ 导出。
用法：python3 z6.py probe | select --units 30 [--tag trial] | run --tag trial [--workers 4] | export --tag trial | report --tag trial | status
      run 不带 --tag 时＝全量：按顺序取所有过筛单元（排除 trial 已用），到 STOP_AT 或额度为止（rc=75 外部续跑）。"""
import argparse, csv, hashlib, json, random, re, sys, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from lib import checks as C, units as U, prefilter as PF
from lib.claude_cli import claude_json, CallsLocked, calls_allowed, LEDGER

OUT = ROOT / "out"
CFG = dict(GEN_MODEL="sonnet", GEN_EFFORT="high", CARD_MODEL="sonnet", CARD_EFFORT="medium", REV_MODEL="sonnet", REV_EFFORT="medium",
           FRONT_WORDS=1500, SECTION_WORDS=500, UNITS_PER_PAPER=3, F_EDIT_MAX=6, F_LEN_RATIO=0.15, D_EDIT_MAX=20, C_LEN_RATIO=0.10,
           DEDUP=0.80, SEED=20261102)
DEFECTS = ["overgeneralization", "outside_word", "category_confusion", "lost_qualifier", "misattached_connective", "lost_in_vivo"]
FEW_EXCLUDE = {"RP-c12afd", "RP-38d869"}
FEW_DEFECT = {"S3ins": "outside_word: inserted unsupported inference", "E9": "outside_word: evaluative word not in the quote",
              "E1c": "outside_word: added consequence the speaker never states"}
P = lambda name: (ROOT / "prompts" / name).read_text(encoding="utf-8")
jl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def wjson(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp"); tmp.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(p)


def rjson(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cap(t, n):
    w = (t or "").split()
    return " ".join(w[:n]) + (" …[truncated]" if len(w) > n else "")


# ───── 选单元 ─────
def eligible(exclude=()):
    out = []
    for u in U.load():
        if u["unit_id"] in exclude:
            continue
        q = PF.unit_quotes(u)
        if q:
            out.append(dict(u, fq=q))
    return out


def st_select(a):
    tag = a.tag or "trial"
    dst = OUT / tag / "units.json"
    if dst.exists():
        raise SystemExit(f"✗ {dst} 已有")
    E = eligible()
    by = defaultdict(list)
    for u in E:
        by[u["paper_id"]].append(u)
    rng = random.Random(CFG["SEED"])
    ov_papers = [p for p in dict.fromkeys(u["paper_id"] for u in E if u["opus_rubric"]) if len(by[p]) >= 2]
    multi = [p for p in dict.fromkeys(u["paper_id"] for u in E) if len(by[p]) >= 2 and p not in ov_papers]
    rng.shuffle(multi)
    picks, n_ov = [], 0
    for p in ov_papers[:4] + multi:
        us = sorted(by[p], key=lambda u: (not u["opus_rubric"], u["unit_id"]))[: CFG["UNITS_PER_PAPER"]]
        us = us[: a.units - len(picks)]
        picks += us
        if len(picks) >= a.units:
            break
    wjson(dst, [u["unit_id"] for u in picks])
    print(f"  选了 {len(picks)} 单元 / {len({u['paper_id'] for u in picks})} 篇；有 Opus rubric 的 {sum(bool(u['opus_rubric']) for u in picks)}；过筛单元总数 {len(E)}")


# ───── 卡＋Rubric（每篇一次）─────
CARD_SCHEMA = {"type": "object", "required": ["card", "units"], "properties": {
    "card": {"type": "object", "required": ["research_question", "site_population", "data_collection", "section_topic"],
             "properties": {k: {"type": "string"} for k in ("research_question", "site_population", "data_collection", "section_topic")}},
    "units": {"type": "array", "items": {"type": "object", "required": ["unit_id", "speakers", "rubric"], "properties": {
        "unit_id": {"type": "string"},
        "speakers": {"type": "array", "items": {"type": "object", "required": ["quote_id", "speaker"],
                                                "properties": {"quote_id": {"type": "integer"}, "speaker": {"type": "string"}}}},
        "rubric": {"type": "array", "items": {"type": "object", "required": ["quote_id", "span", "item"],
                                              "properties": {"quote_id": {"type": "integer"}, "span": {"type": "string"}, "item": {"type": "string"}}}}}}}}}


def quotes_plain(u):
    return "\n".join(f"[{i}] {t}" for i, t, _ in u["fq"])


def quotes_block(u):
    return "\n".join(f"[{i}] {t}" + (f"  (attribution: {'; '.join(at)})" if at else "") for i, t, at in u["fq"])


def card_dir(tag):
    return OUT / "cards" if tag == "trial" else OUT / f"cards_{tag}"


def card_for_paper(pid, us, tag):
    p = card_dir(tag) / f"{pid}.json"
    have = rjson(p)
    if have and set(have["unit_ids"]) >= {u["unit_id"] for u in us}:
        return have
    user = [f"FRONT MATTER:\n{cap(us[0]['front_text'], CFG['FRONT_WORDS'])}"]
    for u in us:
        user.append(f"=== UNIT {u['unit_id']} ===\nSECTION HEADING: {u['heading'] or '无'}\nAUTHOR'S SECTION TEXT:\n{cap(u['section_text'], CFG['SECTION_WORDS'])}\nQUOTES:\n{quotes_block(u)}")
    parsed, meta = claude_json(P("card.md"), "\n\n".join(user), CARD_SCHEMA, model=CFG["CARD_MODEL"], effort=CFG["CARD_EFFORT"], tag=f"z6card:{tag}:{pid}")
    if parsed is None:
        return None
    rec = dict(paper_id=pid, unit_ids=[u["unit_id"] for u in us], card=parsed["card"], units={}, meta=meta)
    for x in parsed.get("units") or []:
        u = next((v for v in us if v["unit_id"] == x.get("unit_id")), None)
        if not u:
            continue
        qt = {i: t for i, t, _ in u["fq"]}
        items = []
        for it in x.get("rubric") or []:
            ok = it.get("quote_id") in qt and C._alnum(it.get("span", "")) and C._alnum(it["span"]) in C._alnum(qt[it["quote_id"]])
            items.append(dict(it, span_ok=bool(ok)))
        rec["units"][u["unit_id"]] = dict(speakers={str(s["quote_id"]): s["speaker"] for s in x.get("speakers") or []}, rubric=items)
    wjson(p, rec)
    return rec


def card_text(card):
    lab = dict(research_question="Research question", site_population="Site and participants", data_collection="How the data were collected",
               section_topic="This section of the study")
    return "\n".join(f"{lab[k]}: {card.get(k) or '无'}" for k in lab)


# ───── 生成 ─────
def fewshot_pool():
    rows = [r for r in jl(ROOT / "fewshot/pilot_x1.jsonl") if r["verdict"] == "对" and r["site_pair_id"] not in FEW_EXCLUDE]
    return {"D": [r for r in rows if r["kind"] == "D"], "F": [r for r in rows if r["kind"] == "F"]}


def fewshot_text(uid):
    pool = fewshot_pool()
    h = int(hashlib.sha256(uid.encode()).hexdigest()[:8], 16)
    out = []
    for k in ("D", "F"):
        r = pool[k][h % len(pool[k])]
        m = re.search(r"\[(\d+)\]", r["chosen"] or "")
        qi = int(m.group(1)) if m else 1
        q = r["quotes"][qi - 1] if 0 < qi <= len(r["quotes"]) else r["quotes"][0]
        out.append(f"--- example ({'D' if k == 'D' else 'F, defect ' + FEW_DEFECT.get(r['defect'], str(r['defect']))}) ---\nQUOTE [{qi}]: {cap(q, 120)}\nCHOSEN: {r['chosen']}\nREJECTED: {r['rejected']}")
    return "\n".join(out)


def defects_for(uid):
    h = int(hashlib.sha256(("d" + uid).encode()).hexdigest()[:8], 16)
    rot = DEFECTS[h % 6:] + DEFECTS[:h % 6]
    return rot[:3]


GEN_SCHEMA = {"type": "object", "required": ["pairs"], "properties": {"pairs": {"type": "array", "items": {"type": "object",
    "required": ["type", "defect", "quote_id", "span", "chosen_label", "rejected_label", "note"],
    "properties": {"type": {"type": "string", "enum": ["D", "F", "C"]}, "defect": {"type": "string"}, "quote_id": {"type": "integer"},
                   "span": {"type": "string"}, "chosen_label": {"type": "string"}, "rejected_label": {"type": "string"}, "note": {"type": "string"}}}}}}


def rubric_text(cu):
    its = [it for it in (cu or {}).get("rubric", []) if it.get("span_ok")]
    return "\n".join(f"- [{it['quote_id']}] «{it['span']}»: {it['item']}" for it in its) or "无"


def gen_unit(u, card, tag):
    cu = card["units"].get(u["unit_id"])
    df = defects_for(u["unit_id"])
    sysp = P("gen.md").replace("{FEWSHOT}", fewshot_text(u["unit_id"]))
    user = (f"BACKGROUND CARD:\n{card_text(card['card'])}\n\nQUOTES:\n{quotes_block(u)}\n\nRUBRIC (what a faithful deep coding must capture):\n{rubric_text(cu)}\n\n"
            f"Assigned defect types for the 3 F pairs: {', '.join(df)}.\nNow write the 6 pairs.")
    return claude_json(sysp, user, GEN_SCHEMA, model=CFG["GEN_MODEL"], effort=CFG["GEN_EFFORT"], tag=f"z6gen:{tag}:{u['unit_id']}")


def normdef(d):
    d = (d or "").strip().lower()
    return next((x for x in DEFECTS if d.startswith(x)), d.split(":")[0].strip())


def render(label, qid, span):
    return f"{label.strip()} — [{qid}] «{span.strip()}»"


def local_checks(u, card, pairs):
    qt = {i: t for i, t, _ in u["fq"]}
    allowed = " ".join(qt.values()) + " " + card_text(card["card"])
    kept, dropped = [], []
    for p in pairs:
        pr = None
        qid, span = p.get("quote_id"), p.get("span") or ""
        cl, rl = (p.get("chosen_label") or "").strip(), (p.get("rejected_label") or "").strip()
        if p.get("type") not in ("D", "F", "C") or not cl or not rl or not span:
            pr = "format"
        elif qid not in qt or not C._alnum(span) or C._alnum(span) not in C._alnum(qt[qid]):
            pr = "evidence_not_verbatim"
        elif " ".join(cl.lower().split()) == " ".join(rl.lower().split()):
            pr = "identical"
        else:
            nb, edit = C.diff_info(cl, rl)
            ch, rj = render(cl, qid, span), render(rl, qid, span)
            lc, lr = C.nwords(ch), C.nwords(rj)
            ratio = abs(lc - lr) / max(lc, lr)
            if nb != 1:
                pr = "not_single_diff"
            elif p["type"] == "F" and (edit > CFG["F_EDIT_MAX"] or ratio > CFG["F_LEN_RATIO"]):
                pr = "edit_or_length"
            elif p["type"] == "D" and edit > CFG["D_EDIT_MAX"]:
                pr = "edit_or_length"
            elif p["type"] == "C" and ratio > CFG["C_LEN_RATIO"]:
                pr = "edit_or_length"
            else:
                bad = C.r1_closed(cl, allowed)
                if bad:
                    pr = "R1"; p["r1_words"] = bad
        if pr is None:
            cw = set(C.content(cl))
            for k in kept:
                kw = set(C.content(k["chosen_label"]))
                if cw and kw and len(cw & kw) / min(len(cw), len(kw)) >= CFG["DEDUP"] and k["type"] == p["type"]:
                    pr = "dedup"; break
        (dropped if pr else kept).append(dict(p, local=pr))
    return kept, dropped


REV_SCHEMA = {"type": "object", "required": ["verdicts"], "properties": {"verdicts": {"type": "array", "items": {"type": "object",
    "required": ["pair_no", "verdict", "problem", "reason"], "properties": {"pair_no": {"type": "integer"},
    "verdict": {"type": "string", "enum": ["pass", "fail"]},
    "problem": {"type": "string", "enum": ["none", "inference_as_deep_reading", "chosen_unfaithful", "rejected_not_worse", "other"]},
    "reason": {"type": "string"}}}}}}


def review_unit(u, card, kept, tag):
    lines = []
    for i, p in enumerate(kept, 1):
        lab = {"D": "deep reading (chosen carries a stated reason/condition)", "C": "control (rejected flattens the connective)"}.get(p["type"], f"defect: {p['defect']}")
        lines.append(f"PAIR {i} [{lab}]\n  chosen:   {render(p['chosen_label'], p['quote_id'], p['span'])}\n  rejected: {render(p['rejected_label'], p['quote_id'], p['span'])}")
    user = f"BACKGROUND CARD:\n{card_text(card['card'])}\n\nQUOTES:\n{quotes_block(u)}\n\nPAIRS:\n" + "\n".join(lines)
    return claude_json(P("review.md"), user, REV_SCHEMA, model=CFG["REV_MODEL"], effort=CFG["REV_EFFORT"], tag=f"z6rev:{tag}:{u['unit_id']}")


def process_unit(u, card, tag):
    ck = OUT / tag / "units" / f"{u['unit_id']}.json"
    if ck.exists():
        return rjson(ck)
    g, gm = gen_unit(u, card, tag)
    if g is None:
        return None
    pairs = g.get("pairs") or []
    for p in pairs:
        p["defect_raw"] = p.get("defect", ""); p["defect"] = normdef(p.get("defect", "")) if p.get("type") == "F" else ""
    kept, dropped = local_checks(u, card, pairs)
    rv, rm = (None, {})
    if kept:
        rv, rm = review_unit(u, card, kept, tag)
        if rv is None:
            return None
        vd = {v["pair_no"]: v for v in rv.get("verdicts") or []}
        for i, p in enumerate(kept, 1):
            v = vd.get(i) or dict(verdict="fail", problem="other", reason="复核未返回")
            p["review"] = v
        final = [p for p in kept if p["review"]["verdict"] == "pass"]
    else:
        final = []
    rec = dict(unit_id=u["unit_id"], paper_id=u["paper_id"], n_gen=len(pairs), dropped_local=dropped, reviewed=kept, final=final,
               gen_meta=gm, rev_meta=rm, at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    wjson(ck, rec)
    return rec


def st_run(a):
    if not calls_allowed():
        raise SystemExit("✗ 调用锁着：CALLS_LOCKED 存在或未设 Z6_ALLOW_CALLS=1")
    tag = a.tag or "full"
    if a.tag:
        ids = rjson(OUT / tag / "units.json")
        allu = {u["unit_id"]: u for u in eligible()}
        us = [allu[i] for i in ids if i in allu]
    else:
        trial = set()
        for f in OUT.glob("*/units.json"):
            if f.parent.name != "full":
                trial |= set(rjson(f))
        us = eligible(exclude=trial)
    stop_at = a.stop_at
    by = defaultdict(list)
    for u in us:
        by[u["paper_id"]].append(u)
    papers = list(by)
    W = a.workers

    def do_paper(pid):
        if stop_at and time.strftime("%Y-%m-%dT%H:%M") >= stop_at:
            return 0
        done = [u for u in by[pid] if (OUT / tag / "units" / f"{u['unit_id']}.json").exists()]
        if len(done) == len(by[pid]):
            return 0
        card = card_for_paper(pid, by[pid], tag)
        if card is None:
            print(f"  ✗ card {pid}", flush=True); return 0
        n = 0
        for u in by[pid]:
            r = process_unit(u, card, tag)
            if r:
                n += len(r["final"]); print(f"  {u['unit_id']}: gen {r['n_gen']} local-drop {len(r['dropped_local'])} final {len(r['final'])}", flush=True)
        return n
    with ThreadPoolExecutor(max_workers=W) as ex:
        list(ex.map(do_paper, papers))
    st_export(a)


# ───── 导出与报告 ─────
TYPE_ZH = {"D": "深读", "F": "缺陷", "C": "对照"}


def origin(u, card):
    return f"{card_text(card['card'])}\n\n{quotes_plain(u)}"


def all_recs(tag):
    return [rjson(p) for p in sorted((OUT / tag / "units").glob("*.json"))]


SPK_MAP = OUT / "speaker_map.json"     # 内部用：匿名 ID ↔ 卡片里的说话人描述（可能含真名），不进 CSV


def anon_speaker(m, pid, desc):
    d = " ".join((desc or "").lower().split())
    if not d or d == "无":
        return f"S-{pid}-NA"
    pm = m.setdefault(pid, {})
    if d not in pm:
        pm[d] = f"S-{pid}-{len(pm) + 1}"
    return pm[d]


def st_export(a):
    tags = [a.tag] if a.tag else ["trial", "full"]          # 不带 tag＝总表：试跑＋全量
    allu = {u["unit_id"]: u for u in eligible()}
    m = rjson(SPK_MAP) or {}
    rows = []
    for tag in tags:
        if not (OUT / tag / "units").exists():
            continue
        for r in all_recs(tag):
            u = allu[r["unit_id"]]; card = rjson(card_dir(tag) / f"{r['paper_id']}.json")
            spk = card["units"].get(r["unit_id"], {}).get("speakers", {})
            for j, p in enumerate(r["final"], 1):
                rows.append({"原文": origin(u, card), "chosen": render(p["chosen_label"], p["quote_id"], p["span"]),
                             "rejected": render(p["rejected_label"], p["quote_id"], p["span"]), "pair_id": f"Z6-{r['unit_id']}-{j}",
                             "类型": TYPE_ZH[p["type"]] + (f":{normdef(p['defect'])}" if p["type"] == "F" else ""), "差异说明": p.get("note", ""),
                             "文章id": r["paper_id"], "说话人": anon_speaker(m, r["paper_id"], spk.get(str(p["quote_id"]))), "unit_id": r["unit_id"],
                             "batch": tag})
    wjson(SPK_MAP, m)
    d = OUT / (a.tag or "full"); d.mkdir(parents=True, exist_ok=True)
    with open(d / "pairs.jsonl", "w", encoding="utf-8") as f:
        for x in rows:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    with open(d / "pairs.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["原文", "chosen", "rejected", "pair_id", "类型", "差异说明", "文章id", "说话人"], extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    print(f"  导出 {len(rows)} 对（{'+'.join(tags)}）→ {d}/pairs.csv")


def auc(pos_scores_vs):
    return sum(pos_scores_vs) / len(pos_scores_vs) if pos_scores_vs else None


def st_report(a):
    tag = a.tag or "trial"
    R = all_recs(tag)
    for r in R:
        for p in r["dropped_local"] + r["reviewed"] + r["final"]:
            if p.get("type") == "F":
                p["defect"] = normdef(p.get("defect"))
    led = [x for x in jl(LEDGER) if f":{tag}:" in x.get("tag", "")]
    calls = Counter(x["tag"].split(":")[0] for x in led)
    cost = round(sum(x.get("cost") or 0 for x in led), 3)
    gen = sum(r["n_gen"] for r in R)
    loc = Counter(p["local"] for r in R for p in r["dropped_local"])
    rev = Counter(p["review"]["problem"] for r in R for p in r["reviewed"] if p["review"]["verdict"] == "fail")
    fin = [p for r in R for p in r["final"]]
    r1_den = gen - sum(v for k, v in loc.items() if k in ("format", "evidence_not_verbatim", "identical", "not_single_diff", "edit_or_length"))
    out = dict(units=len(R), calls=dict(calls), calls_total=sum(calls.values()), cost_usd=cost, pairs_generated=gen, dropped_local=dict(loc),
               reviewed=sum(len(r["reviewed"]) for r in R), dropped_review=dict(rev), kept=len(fin), kept_per_unit=round(len(fin) / max(1, len(R)), 2),
               kept_by_type=dict(Counter(p["type"] for p in fin)), kept_defects=dict(Counter(p["defect"] for p in fin if p["type"] == "F")),
               gen_by_type=dict(Counter(p["type"] for r in R for p in r["dropped_local"] + r["reviewed"])),
               r1_block_rate=round(loc.get("R1", 0) / max(1, r1_den), 3))
    # 长度 AUC（只用长度猜 chosen；平局 0.5）
    def lauc(ps):
        s = []
        for p in ps:
            lc, lr = C.nwords(p["chosen_label"]), C.nwords(p["rejected_label"])
            s.append(1 if lc > lr else 0.5 if lc == lr else 0)
        return round(auc(s), 3) if s else None
    out["length_auc"] = {k: lauc([p for p in fin if p["type"] == k]) for k in ("D", "F", "C")} | {"all": lauc(fin)}
    out["length_auc_F_by_defect"] = {d: lauc([p for p in fin if p.get("defect") == d]) for d in DEFECTS}
    try:
        from sklearn.feature_extraction.text import CountVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import GroupKFold
        from sklearn.metrics import roc_auc_score
        import numpy as np
        X, y, g = [], [], []
        for i, p in enumerate(fin):
            X += [p["chosen_label"], p["rejected_label"]]; y += [1, 0]; g += [i, i]
        if len(fin) >= 10:
            y, g = np.array(y), np.array(g)
            prob = np.zeros(len(y))
            for tr, te in GroupKFold(n_splits=5).split(X, y, g):
                v = CountVectorizer(lowercase=True, token_pattern=r"[A-Za-z']+")
                Xtr = v.fit_transform([X[i] for i in tr])
                m = LogisticRegression(max_iter=2000, C=1.0).fit(Xtr, y[tr])
                prob[te] = m.predict_proba(v.transform([X[i] for i in te]))[:, 1]
            out["bow_auc_5fold"] = round(float(roc_auc_score(y, prob)), 3)
            v = CountVectorizer(token_pattern=r"[A-Za-z']+"); Xa = v.fit_transform(X)
            m = LogisticRegression(max_iter=2000).fit(Xa, y); co = m.coef_[0]; names = v.get_feature_names_out()
            o = co.argsort()
            out["bow_top_rejected_words"] = [names[i] for i in o[:8]]; out["bow_top_chosen_words"] = [names[i] for i in o[-8:][::-1]]
    except Exception as e:
        out["bow_auc_err"] = str(e)[:200]
    wjson(OUT / tag / "report.json", out)
    print(json.dumps(out, ensure_ascii=False, indent=1))


def st_probe(_a):
    if not calls_allowed():
        raise SystemExit("✗ 调用锁着")
    r, m = claude_json("Reply with JSON only.", f"Return ok=true. ts={time.time()}", {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}},
                       model="sonnet", effort="low", tag="z6probe:probe:x")
    print("probe:", r, m.get("cost"))


def st_status(a):
    """零调用进度：试跑＋全量的单元数、留下的对、调用次数与美元（台账）。"""
    out = {}
    for tag in ("trial", "full"):
        R = all_recs(tag) if (OUT / tag / "units").exists() else []
        out[tag] = dict(units_done=len(R), kept=sum(len(r["final"]) for r in R))
    led = jl(LEDGER) if LEDGER.exists() else []
    for tag in ("trial", "full"):
        L = [x for x in led if f":{tag}:" in x.get("tag", "")]
        out[tag].update(calls=len(L), cost_usd=round(sum(x.get("cost") or 0 for x in L), 2), errors=sum(1 for x in L if not x.get("ok")))
    out["total_kept"] = out["trial"]["kept"] + out["full"]["kept"]
    out["total_cost_usd"] = round(out["trial"]["cost_usd"] + out["full"]["cost_usd"], 2)
    out["last_call"] = led[-1].get("at") if led else None
    st = OUT / "STOPPED_ON_LIMIT.txt"
    out["stopped_on_limit"] = st.read_text().strip() if st.exists() and st.stat().st_mtime > time.time() - 3600 else None
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["probe", "select", "run", "export", "report", "status"])
    ap.add_argument("--units", type=int, default=30)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--stop-at", dest="stop_at", default=None, help="YYYY-MM-DDTHH:MM（本地时间），到点不再开新篇")
    a = ap.parse_args()
    dict(probe=st_probe, select=st_select, run=st_run, export=st_export, report=st_report, status=st_status)[a.stage](a)
