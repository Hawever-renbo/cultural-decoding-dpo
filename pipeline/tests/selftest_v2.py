"""z6v2 零调用自测。"""
import json, os, sys, glob
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); os.environ.pop("Z6_ALLOW_CALLS", None)
import z6v2 as V
ok = 0
def t(c, m):
    global ok
    assert c, m; ok += 1; print("✓", m)
span = "If you don't trust the people around you and if you don't feel like they trust you, that would be a scary and not very fun thing to be a part of."
b40 = dict(type="D", d_kind="reason", span=span, quote_id=6,
           chosen_label=f"scary thing if you don't trust the people around you — [6] «{span}»", rejected_label=f"scary thing — [6] «{span}»")
t(V.dup_span(b40), "B40 重复引语被 dup_span 抓到")
t(V.dup_span(dict(b40, span=span + " " + span, chosen_label="a", rejected_label="b")), "span 自身重复 → 丢")
t(not V.dup_span(dict(b40, chosen_label=span, rejected_label="scary thing")), "label 照抄引语（in-vivo）不误伤")
t(not V.dup_span(dict(b40, chosen_label="scary without trust", rejected_label="scary")), "正常 label 不误伤")
t(V.out_type(dict(type="D", d_kind="emphasis")) == ("K", ""), "emphasis → K 抓重点")
t(V.out_type(dict(type="D", d_kind="reason")) == ("D", ""), "reason → D 深读")
t(V.out_type(dict(type="C", c_kind="impose")) == ("F", "imposed_connective"), "impose → F:imposed_connective")
t(V.out_type(dict(type="C", c_kind="flatten")) == ("C", ""), "flatten → C 对照")
t(V.out_type(dict(type="F", defect="lost_qualifier")) == ("F", "lost_qualifier"), "F 缺陷标签不变")
t(V.type_label("K", "") == "抓重点" and V.type_label("F", "imposed_connective") == "缺陷:imposed_connective", "类型中文标签")
try:
    V.st_run(type("A", (), dict(workers=1, stop_at=None))()); t(False, "")
except SystemExit as e:
    t("锁" in str(e), "无 Z6_ALLOW_CALLS 时 run 拒绝调用")
todo = V.todo_units(); done_v1 = {Path(p).stem for p in glob.glob(str(ROOT / "out/full/units/*.json"))}
t(not ({u["unit_id"] for u in todo} & done_v1), f"v1 已完成单元不重跑（待跑 {len(todo)}）")
# 用 A/B v2 的 60 单元模拟新标签后的配比
R = [json.loads(Path(p).read_text()) for p in glob.glob(str(ROOT / "out/ab_v2/units/*.json"))]
fin = [V.finalize(p) for r in R for p in r["final"] if not V.dup_span(p)]
F = [p for p in fin if p["out_type"] == "F"]; sh = Counter(p["out_defect"] for p in F)
share = {k: round(v / len(F), 3) for k, v in sh.items()}
print("  A/B v2 重贴标签后：", dict(Counter(p["out_type"] for p in fin)), share)
t(max(share.values()) <= 0.25, "任一缺陷类型 ≤25%（含 imposed_connective）")
nd_ab = sum(V.dup_span(p) for r in R for p in r["final"])
nd_v1 = sum(V.dup_span(p) for p in (x for f in glob.glob(str(ROOT / "out/full/units/*.json")) for x in json.loads(Path(f).read_text())["final"]))
print(f"  dup_span 命中：A/B v2 final {nd_ab}，v1 全量 final {nd_v1}")
t(nd_ab >= 1, "A/B 里的 B40 类重复被抓到")
print(f"全部 {ok} 项通过")
