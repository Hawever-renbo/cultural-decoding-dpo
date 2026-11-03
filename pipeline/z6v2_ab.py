"""Z6 提示词 v2 的 A/B（不改在跑的 z6.py、prompts/、lib/checks.py；只 import 读）。
v2：prompts_v2/gen.md、review.md；D 两种（reason／emphasis）、C 两种（flatten／impose，按单元轮换）；
零调用检查 v2：严格 R1（所引引语词＋闭集白名单＋背景卡专名）；丢关键词只查封闭群体词/量词、只查 label 覆盖的那一小句。
用法：python3 z6v2_ab.py select [--n 60] | run [--workers 3] | compare | blind"""
import argparse, csv, hashlib, json, random, re, sys, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parent; sys.path.insert(0, str(ROOT))
import z6
from lib import checks as C
from lib.claude_cli import claude_json, calls_allowed

AB = ROOT / "out" / "ab_v2"; (AB / "units").mkdir(parents=True, exist_ok=True)
PV2 = lambda n: (ROOT / "prompts_v2" / n).read_text(encoding="utf-8")
GEN2_SCHEMA = json.loads(json.dumps(z6.GEN_SCHEMA))
it = GEN2_SCHEMA["properties"]["pairs"]["items"]
it["required"] += ["d_kind", "c_kind"]; it["properties"]["d_kind"] = {"type": "string"}; it["properties"]["c_kind"] = {"type": "string"}
REV2_PROBLEMS = ["none", "no_grounds", "wrong_emphasis", "lost_own_reason", "lost_group_or_quantity", "evaluative_or_diagnostic", "actor_swap",
                 "chosen_unfaithful", "rejected_not_worse", "other"]
REV2_SCHEMA = json.loads(json.dumps(z6.REV_SCHEMA))
REV2_SCHEMA["properties"]["verdicts"]["items"]["properties"]["problem"]["enum"] = REV2_PROBLEMS

def c_kind_for(uid):
    return "flatten" if int(hashlib.sha256(("c" + uid).encode()).hexdigest()[:8], 16) % 2 == 0 else "impose"

# ── 严格 R1、丢关键词（v2）──
def proper_nouns(text):
    out = set()
    for m in re.finditer(r"(?<![.!?:]\s)(?<!^)\b([A-Z][a-zA-Z]+|[A-Z]{2,})\b", text, re.M):
        out |= C.lemmas(m.group(1))
    return out

def r1_strict(label, quote, card):
    have = set()
    for w in C.toks(quote):
        have |= C.lemmas(w)
    have |= proper_nouns(card)
    return [w for w in dict.fromkeys(x.lower() for x in C.toks(label))
            if not (w in C.STOP or w in C.LINKERS or w in C.LINK_WORDS or w in C.REPORT_VERBS or w in C.EXTRA_FUNC or w.isdigit())
            and not C.lemmas(w) & have]

GROUP = {"women", "woman", "men", "man", "white", "whites", "black", "blacks", "kids", "children", "girls", "boys", "immigrants", "migrants", "people"}
QUANT = {"few", "all", "most", "many", "some", "every", "always", "never", "only"}
def clauses(span):
    return [c for c in re.split(r"[.;:!?—–]|,\s+(?=(?:and|but|so|because|or)\b)", span) if c.strip()]
def has(label, w):
    L = set()
    for x in C.toks(label):
        L |= C.lemmas(x)
    return bool(C.lemmas(w) & L)
def focus_text(p):
    cl, rl = p["chosen_label"], p["rejected_label"]
    if p["type"] == "D" and p.get("d_kind") == "emphasis":
        return cl
    import difflib
    A, B = C.toks(cl), C.toks(rl)
    ops = [o for o in difflib.SequenceMatcher(a=[w.lower() for w in A], b=[w.lower() for w in B], autojunk=False).get_opcodes() if o[0] != "equal"]
    seg = " ".join(" ".join(A[o[1]:o[2]] + B[o[3]:o[4]]) for o in ops)
    return seg or cl
def lost_closed(p):
    if p["type"] == "F" and p.get("defect") == "lost_qualifier":
        return []
    ft = set(w for w in C.content(focus_text(p)))
    cs = clauses(p["span"])
    if not cs or not ft:
        return []
    best = max(cs, key=lambda c: len({w for w in C.content(c)} & ft) + 0.001 * len(c))
    if not {w for w in C.content(best)} & ft:
        return []
    return [w for w in dict.fromkeys(x.lower() for x in C.toks(best)) if (w in GROUP or w in QUANT) and not has(p["chosen_label"], w)]

def local_checks_v2(u, card, pairs):
    qt = {i: t for i, t, _ in u["fq"]}
    ctext = z6.card_text(card["card"])
    kept, dropped = [], []
    for p in pairs:
        pr = None
        qid, span = p.get("quote_id"), p.get("span") or ""
        cl, rl = (p.get("chosen_label") or "").strip(), (p.get("rejected_label") or "").strip()
        emph = p.get("type") == "D" and p.get("d_kind") == "emphasis"
        if p.get("type") not in ("D", "F", "C") or not cl or not rl or not span:
            pr = "format"
        elif qid not in qt or not C._alnum(span) or C._alnum(span) not in C._alnum(qt[qid]):
            pr = "evidence_not_verbatim"
        elif " ".join(cl.lower().split()) == " ".join(rl.lower().split()):
            pr = "identical"
        else:
            nb, edit = C.diff_info(cl, rl)
            lc, lr = C.nwords(z6.render(cl, qid, span)), C.nwords(z6.render(rl, qid, span))
            ratio = abs(lc - lr) / max(lc, lr)
            if emph:
                if C.nwords(rl) < C.nwords(cl):
                    pr = "edit_or_length"
            elif nb != 1:
                pr = "not_single_diff"
            elif p["type"] == "F" and (edit > 6 or ratio > 0.15):
                pr = "edit_or_length"
            elif p["type"] == "D" and edit > 20:
                pr = "edit_or_length"
            elif p["type"] == "C" and ratio > 0.10:
                pr = "edit_or_length"
            if pr is None:
                bad = r1_strict(cl, qt[qid], ctext)
                if bad:
                    pr = "R1_strict"; p["r1_words"] = bad
            if pr is None:
                lk = lost_closed(p)
                if lk:
                    pr = "lost_keyword"; p["lost_words"] = lk
        if pr is None:
            cw = set(C.content(cl))
            for k in kept:
                kw = set(C.content(k["chosen_label"]))
                if cw and kw and len(cw & kw) / min(len(cw), len(kw)) >= 0.8 and k["type"] == p["type"]:
                    pr = "dedup"; break
        (dropped if pr else kept).append(dict(p, local=pr))
    return kept, dropped

def gen_v2(u, card):
    cu = card["units"].get(u["unit_id"])
    df = z6.defects_for(u["unit_id"]); ck = c_kind_for(u["unit_id"])
    sysp = PV2("gen.md").replace("{FEWSHOT}", z6.fewshot_text(u["unit_id"]))
    user = (f"BACKGROUND CARD:\n{z6.card_text(card['card'])}\n\nQUOTES:\n{z6.quotes_block(u)}\n\nRUBRIC (what a faithful deep coding must capture):\n{z6.rubric_text(cu)}\n\n"
            f"Assigned defect types for the 3 F pairs: {', '.join(df)}.\nAssigned c_kind for the C pair: {ck}.\nNow write the 6 pairs.")
    return claude_json(sysp, user, GEN2_SCHEMA, model="sonnet", effort="high", tag=f"z6gen:abv2:{u['unit_id']}")

def review_v2(u, card, kept):
    lines = []
    for i, p in enumerate(kept, 1):
        if p["type"] == "D":
            lab = "deep reading: chosen codes what the speaker stresses" if p.get("d_kind") == "emphasis" else "deep reading: chosen carries a stated reason/condition"
        elif p["type"] == "C":
            lab = "control: rejected imposes a causal link the speaker never states" if p.get("c_kind") == "impose" else "control: rejected flattens the speaker's connective"
        else:
            lab = f"defect: {p['defect']}"
        lines.append(f"PAIR {i} [{lab}]\n  chosen:   {z6.render(p['chosen_label'], p['quote_id'], p['span'])}\n  rejected: {z6.render(p['rejected_label'], p['quote_id'], p['span'])}")
    user = f"BACKGROUND CARD:\n{z6.card_text(card['card'])}\n\nQUOTES:\n{z6.quotes_block(u)}\n\nPAIRS:\n" + "\n".join(lines)
    return claude_json(PV2("review.md"), user, REV2_SCHEMA, model="sonnet", effort="medium", tag=f"z6rev:abv2:{u['unit_id']}")

def process(u, card):
    ck = AB / "units" / f"{u['unit_id']}.json"
    if ck.exists():
        return json.loads(ck.read_text(encoding="utf-8"))
    g, gm = gen_v2(u, card)
    if g is None:
        return None
    pairs = g.get("pairs") or []
    for p in pairs:
        p["defect_raw"] = p.get("defect", ""); p["defect"] = z6.normdef(p.get("defect", "")) if p.get("type") == "F" else ""
    kept, dropped = local_checks_v2(u, card, pairs)
    rm = {}
    if kept:
        rv, rm = review_v2(u, card, kept)
        if rv is None:
            return None
        vd = {v["pair_no"]: v for v in rv.get("verdicts") or []}
        for i, p in enumerate(kept, 1):
            p["review"] = vd.get(i) or dict(verdict="fail", problem="other", reason="复核未返回")
    final = [p for p in kept if p["review"]["verdict"] == "pass"]
    rec = dict(unit_id=u["unit_id"], paper_id=u["paper_id"], n_gen=len(pairs), dropped_local=dropped, reviewed=kept, final=final,
               gen_meta=gm, rev_meta=rm, at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    z6.wjson(ck, rec)
    return rec

# ── 选单元、跑、比较、盲评 ──
def v1rec(uid):
    return json.loads((ROOT / "out/full/units" / f"{uid}.json").read_text(encoding="utf-8"))

def st_select(a):
    dst = AB / "units.json"
    if dst.exists():
        raise SystemExit("已选过")
    recs = [json.loads(f.read_text(encoding="utf-8")) for f in sorted((ROOT / "out/full/units").glob("*.json"))]
    strata = defaultdict(list)
    for r in recs:
        t = Counter(p["type"] for p in r["final"])
        strata[(min(t["D"], 2), min(t["C"], 1), "F3" if t["F"] >= 3 else "F<3")].append(r["unit_id"])
    rng = random.Random(20261102); N = sum(len(v) for v in strata.values()); pick = []
    for k in sorted(strata):
        v = sorted(strata[k]); rng.shuffle(v)
        pick += v[:max(1, round(a.n * len(v) / N))]
    pick = pick[:a.n]
    z6.wjson(dst, pick); print(f"选了 {len(pick)} / {N} 个全量已完成单元；层数 {len(strata)}")

def st_run(a):
    if not calls_allowed():
        raise SystemExit("调用锁着")
    ids = json.loads((AB / "units.json").read_text())
    allu = {u["unit_id"]: u for u in z6.eligible()}
    def one(uid):
        u = allu[uid]; card = json.loads((z6.card_dir("full") / f"{u['paper_id']}.json").read_text(encoding="utf-8"))
        r = process(u, card)
        if r: print(f"  {uid}: gen {r['n_gen']} local-drop {len(r['dropped_local'])} final {len(r['final'])}", flush=True)
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(one, ids))

def lauc(ps):
    s = [1 if C.nwords(p["chosen_label"]) > C.nwords(p["rejected_label"]) else 0.5 if C.nwords(p["chosen_label"]) == C.nwords(p["rejected_label"]) else 0 for p in ps]
    return round(sum(s) / len(s), 3) if s else None

def bow(ps):
    if len(ps) < 10:
        return None
    from sklearn.feature_extraction.text import CountVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    from sklearn.metrics import roc_auc_score
    import numpy as np
    X, y, g = [], [], []
    for i, p in enumerate(ps):
        X += [p["chosen_label"], p["rejected_label"]]; y += [1, 0]; g += [i, i]
    y, g = np.array(y), np.array(g); prob = np.zeros(len(y))
    for tr, te in GroupKFold(n_splits=5).split(X, y, g):
        v = CountVectorizer(token_pattern=r"[A-Za-z']+"); m = LogisticRegression(max_iter=2000).fit(v.fit_transform([X[i] for i in tr]), y[tr])
        prob[te] = m.predict_proba(v.transform([X[i] for i in te]))[:, 1]
    return round(float(roc_auc_score(y, prob)), 3)

def metrics(R):
    fin = [p for r in R for p in r["final"]]
    rev = [p for r in R for p in r["reviewed"]]
    F = [p for p in fin if p["type"] == "F"]
    out = dict(units=len(R), generated=sum(r["n_gen"] for r in R), local_drop=sum(len(r["dropped_local"]) for r in R),
               local_by=dict(Counter(p["local"] for r in R for p in r["dropped_local"])), reviewed=len(rev),
               review_fail=sum(p["review"]["verdict"] == "fail" for p in rev), review_by=dict(Counter(p["review"]["problem"] for p in rev if p["review"]["verdict"] == "fail")),
               kept=len(fin), kept_per_unit=round(len(fin) / max(1, len(R)), 2), kept_by_type=dict(Counter(p["type"] for p in fin)),
               defect_share={d: round(sum(p["defect"] == d for p in F) / max(1, len(F)), 3) for d in z6.DEFECTS})
    out["review_block_rate"] = round(out["review_fail"] / max(1, out["reviewed"]), 3)
    for t in ("D", "F", "C"):
        ps = [p for p in fin if p["type"] == t]
        out[f"len_auc_{t}"] = lauc(ps); out[f"bow_auc_{t}"] = bow(ps)
    out["len_auc_all"] = lauc(fin); out["bow_auc_all"] = bow(fin)
    out["subkinds"] = dict(Counter(p["type"] + ":" + (p.get("d_kind") or p.get("c_kind") or "-") for p in fin if p["type"] in "DC"))
    return out

def st_compare(a):
    ids = json.loads((AB / "units.json").read_text())
    done = [i for i in ids if (AB / "units" / f"{i}.json").exists()]
    R1 = [v1rec(i) for i in done]; R2 = [json.loads((AB / "units" / f"{i}.json").read_text()) for i in done]
    m1, m2 = metrics(R1), metrics(R2)
    d = lambda x: abs(x - 0.5) if x is not None else None
    crit = {
        "net_kept_per_unit v2≥0.9·v1": m2["kept_per_unit"] >= 0.9 * m1["kept_per_unit"],
        "D len AUC ≤0.60": m2["len_auc_D"] is not None and m2["len_auc_D"] <= 0.60,
        "C len AUC ≤0.60": m2["len_auc_C"] is not None and m2["len_auc_C"] <= 0.60,
        "D BoW ≤0.70": m2["bow_auc_D"] is not None and m2["bow_auc_D"] <= 0.70,
        "C BoW ≤0.70": m2["bow_auc_C"] is not None and m2["bow_auc_C"] <= 0.70,
        "F len AUC not worse >0.03 (|AUC−0.5|)": d(m2["len_auc_F"]) <= d(m1["len_auc_F"]) + 0.03,
        "F BoW not worse >0.03": m2["bow_auc_F"] <= m1["bow_auc_F"] + 0.03,
        "each defect share ≤25%": all(v <= 0.25 for v in m2["defect_share"].values()),
        "defect share change ≤10 pts": all(abs(m2["defect_share"][k] - m1["defect_share"][k]) <= 0.10 for k in z6.DEFECTS),
        "review block rate ≤1.5×v1": m2["review_block_rate"] <= 1.5 * max(m1["review_block_rate"], 1e-9),
    }
    rep = dict(units_compared=len(done), v1=m1, v2=m2, criteria=crit, all_pass=all(crit.values()))
    z6.wjson(AB / "compare.json", rep); print(json.dumps(rep, ensure_ascii=False, indent=1))

def st_blind(a):
    ids = json.loads((AB / "units.json").read_text())
    done = [i for i in ids if (AB / "units" / f"{i}.json").exists()]
    allu = {u["unit_id"]: u for u in z6.eligible()}
    rng = random.Random(7)
    def take(recs, ver):
        ps = [(r["unit_id"], p) for r in recs for p in r["final"]]
        by = defaultdict(list)
        for x in ps: by[x[1]["type"]].append(x)
        quota = {"D": 10, "F": 15, "C": 5}; out = []
        for t, q in quota.items():
            v = by[t]; rng.shuffle(v); out += v[:q]
        return [(ver, uid, p) for uid, p in out]
    items = take([v1rec(i) for i in done], "v1") + take([json.loads((AB / "units" / f"{i}.json").read_text()) for i in done], "v2")
    rng.shuffle(items)
    dst = AB / "blind"; dst.mkdir(exist_ok=True)
    rows, key = [], []
    for k, (ver, uid, p) in enumerate(items, 1):
        u = allu[uid]; q = next(t for i, t, _ in u["fq"] if i == p["quote_id"])
        bid = f"B{k:02d}"
        rows.append({"盲评编号": bid, "引语": q, "chosen": z6.render(p["chosen_label"], p["quote_id"], p["span"]),
                     "rejected": z6.render(p["rejected_label"], p["quote_id"], p["span"]), "类型": z6.TYPE_ZH[p["type"]],
                     "第1条_有原文依据": "", "第2条_抓对重点": "", "第3条_保留自己的理由": "", "第4条_保留群体词量词": "", "备注": ""})
        key.append(dict(盲评编号=bid, version=ver, unit_id=uid, type=p["type"], subkind=p.get("d_kind") or p.get("c_kind") or p.get("defect") or ""))
    with open(dst / "z6_ab_blind.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(dst / "z6_ab_blind_KEY.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(key[0])); w.writeheader(); w.writerows(key)
    print(len(rows), Counter(k["version"] for k in key))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("stage", choices=["select", "run", "compare", "blind"])
    ap.add_argument("--n", type=int, default=60); ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args(); dict(select=st_select, run=st_run, compare=st_compare, blind=st_blind)[a.stage](a)
