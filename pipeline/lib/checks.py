"""Z6 零调用本地检查：格式、chosen≠rejected、R1（chosen 不得引入引语里没有的实义词）、三道硬闸（两侧都查）。
分词、stem、_roots、停用词、连接词表照抄 合成数据线/lib/gates_z5.py；硬闸的 hits/not_in_quote 照抄 lib/hardgates_z5.py；
词表从旧线 lib/wordlists/ 复制到 Z6_直出/wordlists/（只读副本）。R1 加了 D-230(a) 的否定/代词缩写归一。"""
import re
from pathlib import Path

WL_DIR = Path(__file__).resolve().parent.parent / "wordlists"
TOK = re.compile(r"[A-Za-z0-9]+(?:[’'][A-Za-z]+)*")
STOP = set("""a an the of to in on for and or but with by from as at is are was were be been being it its this that these those he she they
them his her their him we our us you your i me my mine who whom which what when where how than then so such into onto about over under
own speaker speakers participant participants s not no do does did has have had will would can could also there here very more most
other another one two both each all any some""".split())
LINKERS = {"though", "although", "yet", "while", "whereas", "because", "since", "still", "even", "after", "before", "until", "once",
           "then", "now", "again", "ever", "never", "always"}
LINK_WORDS = {"because", "cause", "cos", "since", "due", "owing", "why", "reason", "order", "that", "if", "unless", "whenever", "long", "case",
              "otherwise", "else", "once", "but", "yet", "though", "although", "despite", "spite", "instead", "rather", "whereas", "unlike",
              "however", "hand", "compared", "than", "so", "therefore", "means", "leads", "lead", "led", "end", "ends", "ended", "results",
              "result", "resulted", "when", "escape", "escaping", "while", "to", "for", "as", "from", "against", "by"}
CONTRACT = {"isn't": "is not", "aren't": "are not", "wasn't": "was not", "weren't": "were not", "don't": "do not", "doesn't": "does not",
            "didn't": "did not", "can't": "can not", "cannot": "can not", "won't": "will not", "wouldn't": "would not", "couldn't": "could not",
            "shouldn't": "should not", "haven't": "have not", "hasn't": "has not", "hadn't": "had not", "it's": "it is", "we're": "we are",
            "they're": "they are", "you're": "you are", "i'm": "i am", "i've": "i have", "we've": "we have", "they've": "they have",
            "that's": "that is", "there's": "there is", "he's": "he is", "she's": "she is", "i'd": "i would", "i'll": "i will"}
CFG = dict(R1_MAX_NEW=0, R1_SCOPE="diff")   # R1_SCOPE：diff＝只查 chosen 比 rejected 多出的词（旧线 R1 口径：D 插入）；full＝查整条 chosen。待专家组定


def _expand(t):
    t = (t or "").replace("’", "'").replace("‘", "'")
    return re.sub(r"[A-Za-z]+'[A-Za-z]+", lambda m: CONTRACT.get(m.group(0).lower(), m.group(0)), t)


def toks(t):
    return TOK.findall(_expand(t))


def stem(w):
    w = w.lower().replace("'", "")
    for suf in ("ingly", "edly", "ing", "ed", "es", "s", "ly"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def content(t):
    return [w.lower() for w in toks(t) if w.lower() not in STOP]


def _roots(w):
    w = w.lower().replace("'", "")
    r = {w, stem(w)}
    if w.endswith("s") and len(w) > 4:
        r |= {w[:-1], stem(w[:-1])}
    if w.endswith("es") and len(w) > 5:
        r |= {w[:-2]}
    if w.endswith("ies") and len(w) > 5:
        r |= {w[:-3] + "y"}
    if w.endswith("ied") and len(w) > 5:
        r |= {w[:-3] + "y"}
    return r


def _root_set(text):
    s = set()
    for w in toks(text):
        s |= _roots(w)
    return s


def offquote_words(text, quote_text):
    q = _root_set(quote_text)
    return [w for w in dict.fromkeys(content(text)) if not _roots(w) & q and w not in LINKERS and w not in LINK_WORDS and not w.isdigit()]


def r1(chosen, quote_text, rejected=""):
    """返回 (ok, 引语外实义词)。diff 口径：rejected 里已有的词不算（两侧共用的标签措辞不由 R1 管）。"""
    new = offquote_words(chosen, quote_text)
    if CFG["R1_SCOPE"] == "diff" and rejected:
        rr = _root_set(rejected)
        new = [w for w in new if not _roots(w) & rr]
    return len(new) <= CFG["R1_MAX_NEW"], new


# 硬闸已按专家组定稿（2026-11-02）整体取消；这里不再检查身份/创伤/怪罪词。
REPORT_VERBS = {"say", "says", "said", "saying", "tell", "tells", "told", "telling", "explain", "explains", "explained", "explaining",
                "describe", "describes", "described", "describing", "report", "reports", "reported", "reporting",
                "ask", "asks", "asked", "asking"}   # PI 2026-11-02 16:52 批：ask 进报告动词白名单
EXTRA_FUNC = {"herself", "himself", "themselves", "itself", "myself", "ourselves", "yourself", "she", "he", "her", "his", "him", "they",
              "not", "no", "without", "via", "per", "within", "among", "between", "through", "during", "toward", "towards", "upon",
              "whether", "just", "only", "still", "even", "too", "also", "being", "having", "getting", "get", "gets", "got"}


def lemmas(w):
    """词元归一（闭集白名单用）：屈折变体都算同一个词。"""
    w = w.lower().replace("'", "")
    r = _roots(w)
    if w.endswith("ing") and len(w) > 5:
        r |= {w[:-3] + "e", w[:-3]}
        if len(w) > 6 and w[-4] == w[-5]:
            r.add(w[:-4])
    if w.endswith("ed") and len(w) > 4:
        r |= {w[:-1], w[:-2]}
        if len(w) > 5 and w[-3] == w[-4]:
            r.add(w[:-3])
    if w.endswith("er") and len(w) > 4:
        r |= {w[:-2], w[:-1]}
    if w.endswith("est") and len(w) > 5:
        r |= {w[:-3], w[:-2]}
    return r


def r1_closed(chosen_label, allowed_text):
    """R1 闭集白名单：chosen 里每个词都要在原话或背景卡里（词元归一后），或属虚词／报告动词。返回外来词列表（空＝过）。"""
    have = set()
    for w in toks(allowed_text):
        have |= lemmas(w)
    out = []
    for w in dict.fromkeys(x.lower() for x in toks(chosen_label)):
        if w in STOP or w in LINKERS or w in LINK_WORDS or w in REPORT_VERBS or w in EXTRA_FUNC or w.isdigit():
            continue
        if not lemmas(w) & have:
            out.append(w)
    return out


# ── 格式 ──
EVID = re.compile(r"«([^»]+)»")


def _alnum(s):
    return re.sub(r"[^a-z0-9]+", "", _expand(s).lower())


def evidence_verbatim(text, quote_text):
    """text 里每段 «…» 证据都必须逐字（忽略标点空白大小写，… 处可断开）出现在引语里。没有 «» 时不查。"""
    bad = []
    q = _alnum(quote_text)
    for e in EVID.findall(text or ""):
        parts = [p for p in re.split(r"…|\.\.\.", e) if _alnum(p)]
        if not all(_alnum(p) in q for p in parts):
            bad.append(e[:60])
    return bad


import difflib


def diff_info(a, b):
    """词级 diff：返回 (非相同块数, 改动词数=两侧改动区较长者)。"""
    A, B = [w.lower() for w in toks(a)], [w.lower() for w in toks(b)]
    ops = [o for o in difflib.SequenceMatcher(a=A, b=B, autojunk=False).get_opcodes() if o[0] != "equal"]
    edit = max(sum(o[2] - o[1] for o in ops), sum(o[4] - o[3] for o in ops)) if ops else 0
    return len(ops), edit


def nwords(t):
    return len(toks(t))
