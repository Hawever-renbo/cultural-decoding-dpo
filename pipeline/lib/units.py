"""从旧线只读取单元：原话（quotes）＋背景（文章卡 context）＋Rubric（z5_rubrics items）。不写旧线任何文件。
单元顺序＝旧线冻结顺序 out/z5_select.json + out/z5_select_more.json（已排除 A1/A2 留出论文、D0 及以前各轮用过的论文）。
再排除：z1–z5 已造对用过的单元、审核站（web/data/pairs.real*.json）上的单元。"""
import glob, json
from pathlib import Path

OLD = Path(__file__).resolve().parent.parent.parent / "合成数据线"
OO = OLD / "out"


def jl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def order():
    s = json.load(open(OO / "z5_select.json"))["order"]
    m = json.load(open(OO / "z5_select_more.json"))["order"]
    return list(dict.fromkeys(s + m))


def excluded():
    used, why = set(), {}
    for f in ("z1_pairs.jsonl", "z2_pairs.jsonl", "z3_pairs.jsonl", "z4_pairs.jsonl", "z5_pairs.jsonl"):
        if (OO / f).exists():
            for r in jl(OO / f):
                if r.get("unit_id"):
                    used.add(r["unit_id"]); why.setdefault(r["unit_id"], f)
    for f in glob.glob(str(OLD / "web/data/pairs.real*.json")):
        for p in json.load(open(f))["pairs"]:
            used.add(p["unit_id"]); why.setdefault(p["unit_id"], Path(f).name)
    hold = json.load(open(OO / "z5_holdout.json"))
    return used, why, set(map(str, hold["A1"] + hold["A2"]))


def load(ids=None):
    """返回 [unit]，unit = dict(unit_id, paper_id, journal, quotes, quote_kinds, background(dict|None), rubric(list|None), src)。"""
    ordr = order()
    used, _, hold = excluded()
    want = [u for u in ordr if u not in used] if ids is None else list(ids)
    ws = set(want)
    rev = {u["cand_id"]: u for u in jl(OO / "u3_reviewed.jsonl") if u.get("cand_id") in ws}
    cards = {c["unit_id"]: c for c in jl(OO / "z5_cards.jsonl") if c["unit_id"] in ws}
    rubs = {r["unit_id"]: r for r in jl(OO / "z5_rubrics.jsonl") if r["unit_id"] in ws}
    raw = {}
    need = ws - set(rev)
    if need:
        with open(OO / "u3_candidates.jsonl", encoding="utf-8") as f:
            for l in f:
                c = json.loads(l)
                if c["cand_id"] in need:
                    raw[c["cand_id"]] = c["unit"]
    out = []
    for k in want:
        u = rev.get(k) or raw.get(k)
        if u is None or str(u["paper_id"]) in hold or u["spec_only"]["front_words"] == 0:
            continue
        card, rub = cards.get(k), rubs.get(k)
        out.append(dict(unit_id=k, paper_id=str(u["paper_id"]), journal=u.get("journal"), quotes=u["quotes"],
                        quote_kinds=u.get("quote_kinds"), background=None,
                        rubric=(rub or {}).get("items") if rub and str(rub.get("usable")) == "True" else None,
                        src="u3_reviewed" if k in rev else "u3_candidates",
                        front_text=u["spec_only"].get("front_text"), heading=u["spec_only"].get("heading"),
                        section_text=" ".join(x["text"] for x in u["spec_only"].get("sentences") or []),
                        opus_card=(card or {}).get("context"), opus_rubric=(rub or {}).get("items") if rub else None))
    return out
