"""零调用引语预筛（专家组定稿 2026-11-02）：15–200 词、完整句、单一说话人、无访谈者话轮、内部无省略号、方括号占比低。"""
import re
TAG = re.compile(r"\s*\[#[^\]]*\]\s*$")
TURN = re.compile(r"(?:^|[.?!]\s+|\n)\s*(?:Q|I|R|A|Int|INT|Interviewer|Researcher|Respondent|Moderator|Facilitator|P\d+|[A-Z][a-z]{1,15})\s*\d*\s*:\s", re.M)
ELL = re.compile(r"\.\s*\.\s*\.|…|\[\s*\.\.\.\s*\]")
BR = re.compile(r"\[[^\]]*\]|\([^)]*\)")


ATTR = re.compile(r"\s*[\(\[]([^\(\)\[\]]{1,80})[\)\]]\s*[.,;]?\s*$")


def split_attr(q):
    """去掉句末的出处标注（(Respondent #21)、[#B2]、(Kevin Doherty)），返回 (正文, 标注列表)。"""
    t, attrs = TAG.sub("", " ".join((q or "").split())).strip(), []
    for _ in range(3):
        m = ATTR.search(t)
        if not m or m.group(1).strip() in ("...", "…") or len(t[:m.start()].split()) < 3:
            break
        attrs.insert(0, m.group(1).strip()); t = t[:m.start()].rstrip()
    t = t.strip()
    if len(t) > 2 and t[0] in "\"“'‘" and t[-1] in "\"”'’" and t.count(t[0]) + t.count("”") <= 2:
        t = t[1:-1].strip()
    return t, attrs


def clean(q):
    return split_attr(q)[0]


def problems(q):
    t = clean(q)
    out = []
    n = len(t.split())
    if not 15 <= n <= 200:
        out.append(f"words={n}")
    s = t.lstrip("\"'“‘([ ")
    if not s or not s[0].isupper():
        out.append("not sentence start")
    if not re.search(r"[.?!][\"'”’)\]]*$", t):
        out.append("not sentence end")
    if TURN.search(t) or re.search(r"\binterviewer\b", t, re.I):
        out.append("speaker turn")
    if ELL.search(t):
        out.append("ellipsis")
    br = sum(len(m.group(0)) for m in BR.finditer(t))
    if br / max(1, len(t)) > 0.10:
        out.append("bracket ratio")
    return out


def unit_quotes(u):
    """返回 [(原编号, 干净引语, 出处标注)]，只留过筛的。"""
    return [(i,) + split_attr(q) for i, q in enumerate(u["quotes"], 1) if not problems(q)]
