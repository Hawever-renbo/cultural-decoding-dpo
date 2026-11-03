"""给专家一抽 80 对（零调用，固定种子）：v1 20（深读7/缺陷7/对照6）＋ v2 60（深读/抓重点/缺陷/对照 各15）；
只从主文件 out/all/pairs.jsonl 抽；缺陷对按缺陷标签轮流；尽量每篇文章、每位说话人只出一次；v1 不取 A/B 用过的 60 单元。
输出 out/x1_round/sample_80.json、sample_80.csv"""
import csv, json, random, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SEED = "z6-x1-r1-20261103"
QUOTA = {"v1": {"深读": 7, "缺陷": 7, "对照": 6}, "v2": {"深读": 15, "抓重点": 15, "缺陷": 15, "对照": 15}}
rows = [json.loads(l) for l in open(ROOT / "out/all/pairs.jsonl", encoding="utf-8")]
ab = set(json.loads((ROOT / "out/ab_v2/units.json").read_text()))
rows = [r for r in rows if not (r["版本"] == "v1" and r["unit_id"] in ab)]
rng = random.Random(SEED)
used_p, used_s, used_u, pick = Counter(), set(), set(), []
for ver in ("v2", "v1"):
    for typ, q in QUOTA[ver].items():
        pool = [r for r in rows if r["版本"] == ver and r["类型"] == typ]
        rng.shuffle(pool)
        if typ == "缺陷":                                   # 缺陷标签轮流
            by = defaultdict(list)
            for r in pool: by[r["缺陷标签"]].append(r)
            labs = sorted(by); rng.shuffle(labs)
            order = []
            while any(by.values()):
                for l in labs:
                    if by[l]: order.append(by[l].pop(0))
            pool = order
        got = 0
        for rnd in range(3):                                # 先找没用过的文章，再放宽
            for r in pool:
                if got >= q: break
                if r in pick or r["unit_id"] in used_u: continue
                if rnd == 0 and (used_p[r["文章id"]] or r["说话人"] in used_s): continue
                if rnd == 1 and (used_p[r["文章id"]] >= 2 or r["说话人"] in used_s): continue
                if typ == "缺陷" and rnd < 2:
                    need = [x for x in pool if x not in pick]
                pick.append(r); used_p[r["文章id"]] += 1; used_s.add(r["说话人"]); used_u.add(r["unit_id"]); got += 1
        assert got == q, (ver, typ, got)
D = ROOT / "out/x1_round"
(D / "sample_80.json").write_text(json.dumps(dict(seed=SEED, quota=QUOTA, n=len(pick), items=pick), ensure_ascii=False, indent=1), encoding="utf-8")
with open(D / "sample_80.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["pair_id", "版本", "类型", "缺陷标签", "文章id", "说话人", "unit_id", "chosen", "rejected"], extrasaction="ignore")
    w.writeheader(); w.writerows(pick)
print(len(pick), dict(Counter((r["版本"], r["类型"]) for r in pick)))
print("缺陷标签", dict(Counter((r["版本"], r["缺陷标签"]) for r in pick if r["缺陷标签"])))
print("文章数", len({r["文章id"] for r in pick}), "说话人数", len({r["说话人"] for r in pick}), "单元数", len({r["unit_id"] for r in pick}))
