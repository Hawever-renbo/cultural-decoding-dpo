"""Z6 全量 v2（2026-11-02 22:21 PI「切新版」批准）。v1 代码 z6.py / prompts/ 原样保留作记录，本文件只 import。
v2 = prompts_v2 + z6v2_ab 的零调用检查 v2，另加三处改动：
 1. d_kind=emphasis 的 D 对 → 独立类型 K「抓重点」（生成方式不变）
 2. c_kind=impose 的 C 对 → 类型 F，缺陷标签 imposed_connective（不再算对照）；flatten 仍是 C「对照」
 3. 零调用格式检查 dup_span：label 里自带 «…»／[n] 引用、或 span 自身重复（B40 那种重复引语）→ 丢；label 原样照抄引语（in-vivo）不算
检查点 out/full_v2/units/<uid>.json；只跑新单元（v1 已完成的、试跑单元一律跳过）；卡片复用 out/cards_full/。
用法：python3 z6v2.py run [--workers 4] [--stop-at ...] | export | status"""
import argparse, csv, json, re, sys, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parent; sys.path.insert(0, str(ROOT))
import z6
import z6v2_ab as AB
from lib import checks as C
from lib.claude_cli import claude_json, calls_allowed

OUT = z6.OUT; TAG = "full_v2"; VER = "v2"
UD = OUT / TAG / "units"; UD.mkdir(parents=True, exist_ok=True)
STOP_FLAG = ROOT / "STOP_V2"   # 建这个文件＝在单元之间优雅停（在跑的单元做完并存检查点）
DEFECTS_V2 = z6.DEFECTS + ["imposed_connective"]
TYPE_ZH2 = {"D": "深读", "K": "抓重点", "F": "缺陷", "C": "对照"}
_orig_card_dir = z6.card_dir
z6.card_dir = lambda tag: OUT / "cards_full" if tag == TAG else _orig_card_dir(tag)   # v2 复用 v1 全量卡片（卡片提示词没变）

def dup_span(p):
    """B40：label 自己又带了一遍 «span»／[n]，render 后引语出现两次。"""
    span = p.get("span") or ""
    for lab in (p.get("chosen_label") or "", p.get("rejected_label") or ""):
        if "«" in lab or "»" in lab or re.search(r"\[\d+\]", lab):
            return True
    a = C._alnum(span); h = len(a) // 2
    if a and len(a) >= 20 and len(a) % 2 == 0 and a[:h] == a[h:]:
        return True
    return False

def out_type(p):
    """生成时的 type/d_kind/c_kind → 导出类型与缺陷标签。"""
    if p["type"] == "D" and p.get("d_kind") == "emphasis":
        return "K", ""
    if p["type"] == "C" and p.get("c_kind") == "impose":
        return "F", "imposed_connective"
    return p["type"], (p.get("defect") or "") if p["type"] == "F" else ""

def type_label(t, d):
    return TYPE_ZH2[t] + (f":{d}" if t == "F" else "")

def local_checks(u, card, pairs):
    pre_drop, rest = [], []
    for p in pairs:
        (pre_drop if dup_span(p) else rest).append(p)
    kept, dropped = AB.local_checks_v2(u, card, rest)
    return kept, [dict(p, local="dup_span") for p in pre_drop] + dropped

def gen(u, card):
    cu = card["units"].get(u["unit_id"])
    df = z6.defects_for(u["unit_id"]); ck = AB.c_kind_for(u["unit_id"])
    sysp = AB.PV2("gen.md").replace("{FEWSHOT}", z6.fewshot_text(u["unit_id"]))
    user = (f"BACKGROUND CARD:\n{z6.card_text(card['card'])}\n\nQUOTES:\n{z6.quotes_block(u)}\n\nRUBRIC (what a faithful deep coding must capture):\n{z6.rubric_text(cu)}\n\n"
            f"Assigned defect types for the 3 F pairs: {', '.join(df)}.\nAssigned c_kind for the C pair: {ck}.\nNow write the 6 pairs.")
    return claude_json(sysp, user, AB.GEN2_SCHEMA, model="sonnet", effort="high", tag=f"z6gen:{TAG}:{u['unit_id']}")

def review(u, card, kept):
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
    return claude_json(AB.PV2("review.md"), user, AB.REV2_SCHEMA, model="sonnet", effort="medium", tag=f"z6rev:{TAG}:{u['unit_id']}")

def finalize(p):
    t, d = out_type(p)
    return dict(p, out_type=t, out_defect=d, version=VER)

def process(u, card):
    ck = UD / f"{u['unit_id']}.json"
    if ck.exists():
        return z6.rjson(ck)
    g, gm = gen(u, card)
    if g is None:
        return None
    pairs = g.get("pairs") or []
    for p in pairs:
        p["defect_raw"] = p.get("defect", ""); p["defect"] = z6.normdef(p.get("defect", "")) if p.get("type") == "F" else ""
    kept, dropped = local_checks(u, card, pairs)
    rm = {}
    if kept:
        rv, rm = review(u, card, kept)
        if rv is None:
            return None
        vd = {v["pair_no"]: v for v in rv.get("verdicts") or []}
        for i, p in enumerate(kept, 1):
            p["review"] = vd.get(i) or dict(verdict="fail", problem="other", reason="复核未返回")
    final = [finalize(p) for p in kept if p["review"]["verdict"] == "pass"]
    rec = dict(unit_id=u["unit_id"], paper_id=u["paper_id"], version=VER, n_gen=len(pairs), dropped_local=dropped, reviewed=kept, final=final,
               gen_meta=gm, rev_meta=rm, at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    z6.wjson(ck, rec)
    return rec

def todo_units():
    skip = set()
    for f in OUT.glob("*/units.json"):
        if f.parent.name not in ("full", TAG, "ab_v2"):
            skip |= set(z6.rjson(f))                         # 试跑单元
    skip |= {p.stem for p in (OUT / "full" / "units").glob("*.json")}   # v1 已完成：不重生成
    return [u for u in z6.eligible() if u["unit_id"] not in skip]

def st_run(a):
    if not calls_allowed():
        raise SystemExit("✗ 调用锁着：CALLS_LOCKED 存在或未设 Z6_ALLOW_CALLS=1")
    by = defaultdict(list)
    for u in todo_units():
        by[u["paper_id"]].append(u)
    def do_paper(pid):
        if (a.stop_at and time.strftime("%Y-%m-%dT%H:%M") >= a.stop_at) or STOP_FLAG.exists():
            return 0
        if all((UD / f"{u['unit_id']}.json").exists() for u in by[pid]):
            return 0
        card = z6.card_for_paper(pid, by[pid], TAG)
        if card is None:
            print(f"  ✗ card {pid}", flush=True); return 0
        n = 0
        for u in by[pid]:
            if (a.stop_at and time.strftime("%Y-%m-%dT%H:%M") >= a.stop_at) or STOP_FLAG.exists():
                break
            r = process(u, card)
            if r:
                n += len(r["final"]); print(f"  v2 {u['unit_id']}: gen {r['n_gen']} local-drop {len(r['dropped_local'])} final {len(r['final'])}", flush=True)
        return n
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(do_paper, list(by)))
    st_export(a)

def st_export(a):
    """总表：试跑(v1)＋全量 v1＋全量 v2 → out/all/pairs.csv/jsonl。dup_span 对两版都零调用过滤。"""
    allu = {u["unit_id"]: u for u in z6.eligible()}
    m = z6.rjson(z6.SPK_MAP) or {}
    rows, ndup = [], Counter()
    for tag, cdir, ver in (("trial", "trial", "v1"), ("full", "full", "v1"), (TAG, TAG, "v2")):
        if not (OUT / tag / "units").exists():
            continue
        for r in z6.all_recs(tag):
            u = allu[r["unit_id"]]; card = z6.rjson(z6.card_dir(cdir) / f"{r['paper_id']}.json")
            spk = card["units"].get(r["unit_id"], {}).get("speakers", {})
            for j, p in enumerate(r["final"], 1):
                if dup_span(p):
                    ndup[ver] += 1; continue
                if ver == "v2":
                    t, d = p.get("out_type") or out_type(p)[0], p.get("out_defect") if "out_type" in p else out_type(p)[1]
                else:
                    t, d = p["type"], z6.normdef(p["defect"]) if p["type"] == "F" else ""
                rows.append({"原文": z6.origin(u, card), "chosen": z6.render(p["chosen_label"], p["quote_id"], p["span"]),
                             "rejected": z6.render(p["rejected_label"], p["quote_id"], p["span"]),
                             "pair_id": f"Z6{'' if ver == 'v1' else 'v2'}-{r['unit_id']}-{j}", "类型": type_label(t, d), "版本": ver,
                             "差异说明": p.get("note", ""), "文章id": r["paper_id"], "说话人": z6.anon_speaker(m, r["paper_id"], spk.get(str(p["quote_id"]))),
                             "unit_id": r["unit_id"], "batch": tag, "version": ver, "type": t, "defect": d})
    z6.wjson(z6.SPK_MAP, m)
    d = OUT / "all"; d.mkdir(parents=True, exist_ok=True)
    with open(d / "pairs.jsonl", "w", encoding="utf-8") as f:
        for x in rows:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    with open(d / "pairs.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["原文", "chosen", "rejected", "pair_id", "类型", "版本", "差异说明", "文章id", "说话人"], extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    c = Counter((x["版本"], x["类型"].split(":")[0]) for x in rows)
    print(f"  导出 {len(rows)} 对 → {d}/pairs.csv；{dict(sorted(c.items()))}；dup_span 过滤 {dict(ndup)}")

def st_status(a):
    R = z6.all_recs(TAG)
    fin = [p for r in R for p in r["final"]]
    F = [p for p in fin if p.get("out_type") == "F"]
    led = z6.jl(z6.LEDGER) if z6.LEDGER.exists() else []
    L = [x for x in led if f":{TAG}:" in x.get("tag", "")]
    cost = sum(x.get("cost") or 0 for x in L)
    out = dict(v2_units=len(R), v2_kept=len(fin), kept_per_unit=round(len(fin) / max(1, len(R)), 2), calls=len(L), cost_usd=round(cost, 2),
               cost_per_unit=round(cost / max(1, len(R)), 3), errors=sum(1 for x in L if not x.get("ok")),
               by_type=dict(Counter(p.get("out_type") for p in fin)),
               defect_share={k: round(v / max(1, len(F)), 3) for k, v in Counter(p.get("out_defect") for p in F).most_common()},
               local_drop=dict(Counter(p["local"] for r in R for p in r["dropped_local"])), first_at=min((r["at"] for r in R), default=None))
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("stage", choices=["run", "export", "status"])
    ap.add_argument("--workers", type=int, default=4); ap.add_argument("--stop-at", dest="stop_at", default=None)
    a = ap.parse_args(); dict(run=st_run, export=st_export, status=st_status)[a.stage](a)
