"""零调用的离线复查（不替换在跑的检查；只读检查点）。
1) 快照：trial+full 已留对 → out/z6_snapshot_<时间>/pairs.csv、pairs.jsonl
2) R1 严格版（专家组 2026-11-02 定）：原词＝所引引语里的词＋闭集白名单（报告动词含 ask、虚词、引语词的屈折/时态变体）；背景卡只算专有名词。
3) 「丢关键词」检查：D 对 chosen 保留引语原因小句 ≥80% 实义词；引语 span 里的群体名词、频率/数量词必须出现在 chosen。
用法：python3 tools/strict_checks.py"""
import csv, json, re, sys, time
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from lib import checks as C
import z6

TS = time.strftime("%Y%m%d-%H%M")
SNAP = ROOT / "out" / f"z6_snapshot_{TS}"; SNAP.mkdir(parents=True, exist_ok=True)
allu = {u["unit_id"]: u for u in z6.eligible()}
rows = []
for tag in ("trial", "full"):
    d = ROOT / "out" / tag / "units"
    if not d.exists():
        continue
    for f in sorted(d.glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        card = json.loads((z6.card_dir(tag) / f"{r['paper_id']}.json").read_text(encoding="utf-8"))
        u = allu[r["unit_id"]]
        qt = {i: t for i, t, _ in u["fq"]}
        for j, p in enumerate(r["final"], 1):
            rows.append(dict(pair_id=f"Z6-{r['unit_id']}-{j}", batch=tag, unit_id=r["unit_id"], paper_id=r["paper_id"], type=p["type"],
                             defect=z6.normdef(p.get("defect")) if p["type"] == "F" else "", quote_id=p["quote_id"], span=p["span"],
                             chosen=z6.render(p["chosen_label"], p["quote_id"], p["span"]), rejected=z6.render(p["rejected_label"], p["quote_id"], p["span"]),
                             chosen_label=p["chosen_label"], rejected_label=p["rejected_label"], note=p.get("note", ""),
                             review_verdict=p.get("review", {}).get("verdict"), review_reason=p.get("review", {}).get("reason"),
                             _quote=qt.get(p["quote_id"], ""), _card=z6.card_text(card["card"])))

# ── 2) R1 严格版 ──
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
    bad = []
    for w in dict.fromkeys(x.lower() for x in C.toks(label)):
        if w in C.STOP or w in C.LINKERS or w in C.LINK_WORDS or w in C.REPORT_VERBS or w in C.EXTRA_FUNC or w.isdigit():
            continue
        if not C.lemmas(w) & have:
            bad.append(w)
    return bad

# ── 3) 丢关键词 ──
CONN = re.compile(r"\b(because|'cause|cos|since|so that|so|in order to|if|unless|when|whenever|but|although|though|even though|despite|whereas|which means|that's why|that is why)\b", re.I)
GROUP = {"women", "woman", "men", "man", "white", "whites", "black", "kids", "children", "child", "girls", "boys", "immigrants", "immigrant",
         "migrants", "parents", "mothers", "fathers", "families", "people", "students", "patients", "staff", "nurses", "doctors", "teachers",
         "workers", "colleagues", "friends", "neighbours", "neighbors", "locals", "foreigners", "refugees", "elderly", "youth", "everyone", "everybody"}
FREQ = {"all", "always", "never", "few", "most", "many", "some", "often", "sometimes", "usually", "rarely", "seldom", "every", "each", "none",
        "nobody", "nothing", "everything", "constantly", "mostly", "hardly", "only", "almost", "nearly", "much", "more", "less", "lot", "lots"}
PHRASES = ["all the time", "every time", "a lot", "most of the time", "at all"]

def has(label, w):
    L = set()
    for x in C.toks(label):
        L |= C.lemmas(x)
    return bool(C.lemmas(w) & L)

def lost_keywords(p):
    probs = []
    span, lab = p["span"], p["chosen_label"]
    if p["type"] == "D":
        m = CONN.search(span)
        if m:
            clause = re.split(r"[.;:!?—–]|,\s+(?:and|but)\b", span[m.end():])[0]
            cw = [w for w in C.content(clause) if w not in C.LINK_WORDS]
            if cw:
                kept = sum(1 for w in cw if has(lab, w))
                if kept / len(cw) < 0.8:
                    probs.append(f"reason clause kept {kept}/{len(cw)}: «{m.group(0)}{clause[:80]}»")
        else:
            probs.append("no connective in span (not checked)")
    low = " " + " ".join(w.lower() for w in C.toks(span)) + " "
    labl = " " + " ".join(w.lower() for w in C.toks(lab)) + " "
    for ph in PHRASES:
        if f" {ph} " in low and f" {ph} " not in labl:
            probs.append(f"lost '{ph}'")
    for w in dict.fromkeys(x.lower() for x in C.toks(span)):
        if (w in GROUP or w in FREQ) and not has(lab, w) and not any(w in ph.split() and f" {ph} " in low for ph in PHRASES):
            probs.append(f"lost '{w}'")
    return probs

for r in rows:
    r["r1_strict"] = r1_strict(r["chosen_label"], r["_quote"], r["_card"])
    r["lost_kw"] = lost_keywords(r)

# 写快照
with open(SNAP / "pairs.jsonl", "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, ensure_ascii=False) + "\n")
with open(SNAP / "pairs.csv", "w", encoding="utf-8-sig", newline="") as f:
    cols = ["pair_id", "batch", "type", "defect", "unit_id", "paper_id", "chosen", "rejected", "note", "review_verdict", "r1_strict", "lost_kw"]
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
    for r in rows:
        w.writerow({**r, "r1_strict": "; ".join(r["r1_strict"]), "lost_kw": "; ".join(r["lost_kw"])})

n = Counter(r["type"] for r in rows)
r1f = Counter(r["type"] for r in rows if r["r1_strict"])
words = Counter(w for r in rows for w in r["r1_strict"])
real = lambda r: [x for x in r["lost_kw"] if not x.startswith("no connective")]
lk = Counter(r["type"] for r in rows if real(r))
lk_reason = Counter(r["type"] for r in rows if any(x.startswith("reason clause") for x in r["lost_kw"]))
lk_word = Counter(r["type"] for r in rows if any(x.startswith("lost '") for x in r["lost_kw"]))
noconn = sum(1 for r in rows if "no connective in span (not checked)" in r["lost_kw"])
lostw = Counter(x for r in rows for x in r["lost_kw"] if x.startswith("lost '"))
rep = dict(snapshot=str(SNAP), pairs=len(rows), by_type=dict(n), by_batch=dict(Counter(r["batch"] for r in rows)),
           r1_strict_fail=sum(r1f.values()), r1_strict_fail_by_type=dict(r1f), r1_top15=words.most_common(15),
           lost_kw_fail=sum(lk.values()), lost_kw_by_type=dict(lk), lost_reason_clause_by_type=dict(lk_reason), lost_word_by_type=dict(lk_word),
           D_without_connective=noconn, lost_words_top=lostw.most_common(12),
           both_fail=sum(1 for r in rows if r["r1_strict"] and real(r)))
(SNAP / "strict_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(rep, ensure_ascii=False, indent=1))
ex = [r for r in rows if real(r)]
import random; random.seed(3)
for r in random.sample([r for r in ex if any(x.startswith("reason clause") for x in r["lost_kw"])], 2) + random.sample([r for r in ex if r["type"] != "D"], 1):
    print("\nEX", r["pair_id"], r["type"], r["defect"], r["lost_kw"]); print("  span:", r["span"][:220]); print("  C:", r["chosen_label"]); print("  R:", r["rejected_label"])
