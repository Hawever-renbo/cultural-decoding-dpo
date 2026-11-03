"""零调用：把专家一在 Z5 pilot（v1.7.1，2026-11-01）判「对」的对抽出来，供定稿 few-shot 时挑 4–6 对。只读旧线。"""
import ast, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.units import OLD, OO, jl
man = json.load(open(OLD / "web/data/z5_pilot_manifest.json"))
items = {it["pair_id"]: it for it in man["items"]}
ans = [r for r in jl(OO / "人审_web/answers_20261102-112552.jsonl") if r["expert_id"] == "X1" and r["pair_id"] in items and r["t_submit"]]
P = {p["pair_id"]: p for p in jl(OO / "z5_pairs.jsonl")}
fix = {}
if (OO / "z5_pilot_fixes.jsonl").exists():
    for r in jl(OO / "z5_pilot_fixes.jsonl"):
        fix[r.get("pair_id") or r.get("source_pair_id")] = r
site = {p["pair_id"]: p for p in json.load(open(OLD / "web/data/pairs.real.json"))["pairs"]}
def el(x):
    if isinstance(x, str):
        try: x = ast.literal_eval(x)
        except Exception: return x
    return f"{x.get('code')} — [{x.get('quote_id')}] «{x.get('evidence')}»" if isinstance(x, dict) else str(x)
out = []
for a in ans:
    it = items[a["pair_id"]]; sp = it["source_pair_id"]; p = P.get(sp) or P.get(sp.replace("-p2", "")) or {}
    s = site[a["pair_id"]]
    cmp_ = [c for c in s["chain"] if c.get("cmp")]
    win = it.get("winner_shown_as")
    A, B = (cmp_[0]["A"], cmp_[0]["B"]) if cmp_ else (None, None)
    chosen, rejected = (A, B) if win == "A" else (B, A)
    cert = p.get("certificate") if isinstance(p.get("certificate"), dict) else {}
    out.append(dict(site_pair_id=a["pair_id"], source_pair_id=sp, unit_id=it["unit_id"], kind=it["kind"], defect=it.get("defect"),
                    d_style=it.get("d_style"), verdict=a["verdict"], reason=a.get("reason"), slot=cmp_[0]["label"] if cmp_ else None,
                    chosen=chosen, rejected=rejected, why_wrong=cert.get("why_wrong"),
                    quotes=[q["text"] for q in s["quotes"]], background=s["background"]))
dst = Path(__file__).resolve().parent / "pilot_x1.jsonl"
with open(dst, "w", encoding="utf-8") as f:
    for r in out: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(dst, len(out), sum(r["verdict"] == "对" for r in out), "对")
for r in out:
    print(f"{r['site_pair_id']} {r['kind']}/{r['defect'] or r['d_style']} {r['verdict']}\n   C: {r['chosen']}\n   R: {r['rejected']}")
