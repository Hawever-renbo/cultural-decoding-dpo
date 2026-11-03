"""零调用自测。python3 tests/selftest.py"""
import csv, glob, json, os, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
os.environ.pop("Z6_ALLOW_CALLS", None)
from lib import checks as C, prefilter as PF
import z6
n = 0
def ok(c, m):
    global n; assert c, m; n += 1
ok(C.r1_closed("asks if she will have a sudden death", "will I have a sudden death?") == [], "ask whitelisted")
ok(C.r1_closed("bitterly asking", "how can families return") == ["bitterly"], "outside word caught")
ok(C.r1_closed("herself reminding sometimes, but says God blessed her", "Sometimes I have to remind myself, but God has really blessed me.") == [], "lemma+reporting")
ok(C.diff_info("a b c d", "a b X d") == (1, 1) and C.diff_info("a X c Y", "a b c d")[0] == 2, "diff")
ok(PF.problems("Q: what? A: yes I think so, it was a long day and we all went home after the meeting ended late.") != [], "turn")
ok(PF.problems("I went there … and it was fine, we stayed for a while and then came home again that night.") != [], "ellipsis")
ok(PF.problems("I went there and it was fine, we stayed for a while and then came home again that night. (P3)") == [], "attr strip")
ok(PF.split_attr("“I feel respected.” (Respondent #21)")[1] == ["Respondent #21"], "attr")
# 试跑检查点用新白名单重放：R1 只会更少
R = [json.load(open(p)) for p in glob.glob("out/trial/units/*.json")]
r1_old = sum(1 for r in R for p in r["dropped_local"] if p["local"] == "R1")
allu = {u["unit_id"]: u for u in z6.eligible()}
r1_new = 0
for r in R:
    card = json.load(open(z6.card_dir("trial") / f"{r['paper_id']}.json"))
    _, dr = z6.local_checks(allu[r["unit_id"]], card, [dict(p) for p in r["dropped_local"] + r["reviewed"]])
    r1_new += sum(1 for p in dr if p["local"] == "R1")
ok(r1_new <= r1_old, f"R1 replay {r1_old}->{r1_new}")
print(f"R1 replay on trial: {r1_old} -> {r1_new}")
# 导出：说话人匿名、CSV 无出处标注
class A: tag = "trial"
z6.st_export(A)
rows = list(csv.DictReader(open("out/trial/pairs.csv", encoding="utf-8-sig")))
ok(len(rows) == 139, f"trial rows {len(rows)}")
ok(all(re.fullmatch(r"S-\d+-(\d+|NA)", r["说话人"]) for r in rows), "speaker anonymized")
ok(not any("(attribution:" in r["原文"] for r in rows), "no attribution in 原文")
spk = json.load(open("out/speaker_map.json")); names = [d for pm in spk.values() for d in pm]
leak = [r["pair_id"] for r in rows if any(d in r["原文"].lower() for d in names if len(d) > 12)]
print("speaker descriptions appearing verbatim in 原文:", len(leak))
try:
    z6.claude_json("x", "y", {"type": "object"}); ok(False, "lock")
except z6.CallsLocked:
    ok(True, "calls locked without env")
print(f"selftest OK {n} checks")
