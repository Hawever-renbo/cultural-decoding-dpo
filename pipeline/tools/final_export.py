"""Z6 收尾导出（2026-11-03，零调用）：试跑(v1)＋全量 v1＋全量 v2 → out/all/
  pairs.csv / pairs.jsonl        主文件：通过 严格 R1、丢关键词（v2 版检查）、dup_span 的对
  pairs_flagged.csv / .jsonl     被这三项任一项标记的对（不丢，另存；flag 列写原因）
  stats.json、README_stats.md    计数、缺陷占比、长度/词袋 AUC、调用与花费"""
import csv, json, sys, time
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
import z6, z6v2 as V, z6v2_ab as AB

OUT = ROOT / "out" / "all"; OUT.mkdir(parents=True, exist_ok=True)
allu = {u["unit_id"]: u for u in z6.eligible()}
m = z6.rjson(z6.SPK_MAP) or {}
main, flagged = [], []
for tag, cdir, ver in (("trial", "trial", "v1"), ("full", "full", "v1"), (V.TAG, V.TAG, "v2")):
    for r in z6.all_recs(tag):
        u = allu[r["unit_id"]]; card = z6.rjson(z6.card_dir(cdir) / f"{r['paper_id']}.json")
        spk = card["units"].get(r["unit_id"], {}).get("speakers", {}); ctext = z6.card_text(card["card"])
        qt = {i: t for i, t, _ in u["fq"]}
        for j, p in enumerate(r["final"], 1):
            if ver == "v2":
                t, d = V.out_type(p)
            else:
                t, d = p["type"], z6.normdef(p["defect"]) if p["type"] == "F" else ""
            fl = []
            if V.dup_span(p): fl.append("dup_span")
            bad = AB.r1_strict(p["chosen_label"], qt[p["quote_id"]], ctext)
            if bad: fl.append("R1_strict:" + ",".join(bad))
            lk = AB.lost_closed(p)
            if lk: fl.append("lost_keyword:" + ",".join(lk))
            row = {"原文": z6.origin(u, card), "chosen": z6.render(p["chosen_label"], p["quote_id"], p["span"]),
                   "rejected": z6.render(p["rejected_label"], p["quote_id"], p["span"]), "版本": ver, "类型": V.TYPE_ZH2[t], "缺陷标签": d,
                   "说话人": z6.anon_speaker(m, r["paper_id"], spk.get(str(p["quote_id"]))),
                   "pair_id": f"Z6{'' if ver == 'v1' else 'v2'}-{r['unit_id']}-{j}", "文章id": r["paper_id"], "unit_id": r["unit_id"],
                   "差异说明": p.get("note", ""), "batch": tag, "type": t, "quote_id": p["quote_id"], "span": p["span"],
                   "chosen_label": p["chosen_label"], "rejected_label": p["rejected_label"], "flag": ";".join(fl)}
            (flagged if fl else main).append(row)
z6.wjson(z6.SPK_MAP, m)
COLS = ["原文", "chosen", "rejected", "版本", "类型", "缺陷标签", "说话人", "pair_id", "文章id", "unit_id", "差异说明"]
def dump(rows, stem, extra=()):
    with open(OUT / f"{stem}.jsonl", "w", encoding="utf-8") as f:
        for x in rows: f.write(json.dumps(x, ensure_ascii=False) + "\n")
    with open(OUT / f"{stem}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS + list(extra), extrasaction="ignore"); w.writeheader(); w.writerows(rows)
dump(main, "pairs"); dump(flagged, "pairs_flagged", ["flag"])

# ── 统计 ──
vt = lambda rows: {f"{v}/{t}": n for (v, t), n in sorted(Counter((x["版本"], x["类型"]) for x in rows).items())}
st = dict(generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"), main_total=len(main), flagged_total=len(flagged),
          main_by_version=dict(Counter(x["版本"] for x in main)), main_by_version_type=vt(main), flagged_by_version_type=vt(flagged),
          flag_reasons=dict(Counter(f.split(":")[0] for x in flagged for f in x["flag"].split(";"))))
st["defect_share"] = {}
for v in ("v1", "v2"):
    F = [x for x in main if x["版本"] == v and x["type"] == "F"]
    st["defect_share"][v] = {k: round(n / len(F), 3) for k, n in Counter(x["缺陷标签"] for x in F).most_common()}
st["auc"] = {}
for v in ("v1", "v2"):
    for t in ("D", "K", "F", "C"):
        ps = [x for x in main if x["版本"] == v and x["type"] == t]
        if ps:
            st["auc"][f"{v}/{V.TYPE_ZH2[t]}"] = dict(n=len(ps), len_auc=AB.lauc(ps), bow_auc=AB.bow(ps))
    ps = [x for x in main if x["版本"] == v]
    st["auc"][f"{v}/全部"] = dict(n=len(ps), len_auc=AB.lauc(ps), bow_auc=AB.bow(ps))
led = z6.jl(z6.LEDGER)
grp = lambda tg: ("v2 全量" if ":full_v2:" in tg else "v1 全量" if ":full:" in tg else "试跑" if ":trial:" in tg else "A/B v2" if ":abv2:" in tg else "其他(探针/译文等)")
cg = defaultdict(lambda: [0, 0.0])
for x in led:
    g = cg[grp(x.get("tag", ""))]; g[0] += 1; g[1] += x.get("cost") or 0
st["calls"] = {k: dict(calls=a, cost_usd=round(b, 2)) for k, (a, b) in cg.items()}
st["calls_total"] = len(led); st["cost_total_usd"] = round(sum(x.get("cost") or 0 for x in led), 2)
st["cost_note"] = "cost = API 等价美元（claude -p 报的 total_cost_usd）；订阅额度内的调用不另收费，额外用量（extra credit）部分实付"
st["units"] = {"v1(含试跑)": len(z6.all_recs("trial")) + len(z6.all_recs("full")), "v2": len(z6.all_recs(V.TAG))}
(OUT / "stats.json").write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")

L = [f"# Z6 直出 — 最终导出（{st['generated_at']} ）", "",
     f"主文件 `pairs.csv` / `pairs.jsonl`：**{len(main)}** 对；标记另存 `pairs_flagged.csv` / `.jsonl`：{len(flagged)} 对（flag 列写原因）。",
     f"单元：v1（含试跑）{st['units']['v1(含试跑)']}，v2 {st['units']['v2']}。", "",
     "列：原文, chosen, rejected, 版本, 类型(深读/抓重点/缺陷/对照), 缺陷标签, 说话人(匿名 S-<文章>-<n>), pair_id, 文章id, unit_id, 差异说明。", "",
     "标记规则（零调用，两版同一套）：严格 R1（label 里的实词须见于所引引语，或闭集虚词/报告动词，或背景卡专名）；丢关键词（label 覆盖的小句里的群体词/量词须保留）；dup_span（label 里自带 «…»/[n] 或 span 自身重复）。", "",
     "## 计数（主文件，版本×类型）", "", "| 版本/类型 | 对数 |", "|---|---|"] + [f"| {k} | {n} |" for k, n in st["main_by_version_type"].items()] + [
     "", f"标记原因：{st['flag_reasons']}", "", "## 缺陷占比（F）", ""]
for v, d in st["defect_share"].items():
    L.append(f"- {v}：" + "，".join(f"{k} {x:.1%}" for k, x in d.items()))
L += ["", "## 长度 AUC / 词袋 AUC（chosen vs rejected；0.5＝无偏）", "", "| 版本/类型 | n | 长度 AUC | 词袋 AUC |", "|---|---|---|---|"]
L += [f"| {k} | {x['n']} | {x['len_auc']} | {x['bow_auc']} |" for k, x in st["auc"].items()]
L += ["", "## 调用与花费（台账 out/claude_ledger.jsonl）", "", "| 部分 | 调用 | 美元 |", "|---|---|---|"]
L += [f"| {k} | {x['calls']} | {x['cost_usd']} |" for k, x in sorted(st["calls"].items())]
L += [f"| 合计 | {st['calls_total']} | {st['cost_total_usd']} |", "", st["cost_note"], "",
      "## 注意：深读/对照有长度与词面偏置", "",
      "v1 的深读对 chosen 几乎总比 rejected 长（长度 AUC≈1.0），对照对也接近 1.0，词袋 AUC 也高——模型可以只学「长的/带 because 的更好」。"
      "用 v1 训练时建议：用带长度归一的目标（SimPO、R-DPO），或只用 v1 的缺陷(F)对。", "",
      "v2 拆出类型后，v2 的「深读」（只剩 reason 型）和「对照」（只剩 flatten 型）单看仍有同样的长度偏置（≈1.0）；"
      "v2 整体长度 AUC≈0.50，是因为「抓重点」方向相反（rejected 更长）、imposed_connective 缺陷对也是 rejected 更长，互相抵消。"
      "所以 v2 要整体混着用才平衡；只取 v2 深读或对照训练时同样建议 SimPO/R-DPO。"]
(OUT / "README_stats.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print(json.dumps({k: st[k] for k in ("main_total", "flagged_total", "main_by_version_type", "flag_reasons", "units", "cost_total_usd")}, ensure_ascii=False))
