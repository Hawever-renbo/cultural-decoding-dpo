"""Deterministic checks on an open code `label — [n] «quote»`. Program checks only: no model judges here.

The definitions follow the ones used to evaluate the post-trained model (format, verbatim quote, label words
that appear nowhere in the excerpts, connectives the quote does not contain, text after the answer).
"""
import re

CODE_RE = re.compile(r"^\s*[-*\d.)\s]*(?P<label>.+?)\s+[—–-]{1,2}\s+\[(?P<n>\d+)\]\s+[«\"“](?P<quote>.+?)[»\"”]\s*$")
WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")
MARKUP_RE = re.compile(r"</?(?:code|label|em|b|i|strong)>", re.I)
TEMPLATE_MARKERS = ("<label>", "<verbatim", "verbatim quote>")
CONNECTIVES = {"because", "so", "therefore", "thus", "hence", "since", "although", "though", "but", "however",
               "yet", "whereas", "despite", "consequently", "while"}
STOP = set("""a an the and or nor of to in on at by for with from as is are was were be been being am do does did
doing have has had having not no it its this that these those there here than then very just also too i me my mine
myself we us our ours you your yours he him his himself she her hers herself they them their theirs themselves one
ones someone people person who whom whose which what when where why how all any each both some such own same other
others can could would should will shall may might must about into over after before again further once only more
most so s t don didn doesn isn wasn aren weren won wouldn couldn says said say saying asks asked ask asking tells
told tell describes described explains explained notes noted thinks thought think speaker speakers""".split())


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')).strip()


def words(s):
    return WORD_RE.findall(norm(s).lower())


def stem(w):
    return w[:6] if len(w) > 6 else w


def _alnum(s):
    return re.sub(r"[^a-z0-9一-鿿]+", "", norm(s).lower())


def strip_markup(label):
    """Untrained models often wrap the label in <code>..</code> or <..>; do not count the wrapper as words."""
    s = (label or "").strip()
    if any(t in s.lower() for t in TEMPLATE_MARKERS) and len(s) <= 20:
        return s, False
    s2 = MARKUP_RE.sub("", s).strip()
    had = s2 != s
    if len(s2) >= 2 and s2[0] == "<" and s2[-1] == ">":
        s2, had = s2[1:-1].strip(), True
    return s2, had


def parse_code(text):
    """First well-formed code line in a completion -> (label, n, quote, had_markup), or None."""
    for line in (text or "").splitlines():
        m = CODE_RE.match(norm(line))
        if m and m.group("label").strip():
            label, had = strip_markup(m.group("label").strip())
            if label:
                return label, int(m.group("n")), m.group("quote").strip(), had
    return None


def is_verbatim(quote, excerpt):
    """The quote appears in the excerpt, ignoring case, spacing and punctuation; an ellipsis may join two parts."""
    hay = _alnum(excerpt)
    parts = [p for p in re.split(r"…|\.\.\.", quote or "") if _alnum(p)]
    return bool(parts) and all(_alnum(p) in hay for p in parts)


def outside_words(label, source_text):
    """Content words of the label that occur nowhere in the excerpts (also not as a shared 6-letter stem)."""
    have = set(words(source_text))
    stems = {stem(w) for w in have}
    seen, out = set(), []
    for w in words(label):
        if len(w) >= 3 and w not in STOP and w not in have and stem(w) not in stems and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def imposed_connectives(label, quote):
    in_quote = set(words(quote))
    return [w for w in dict.fromkeys(words(label)) if w in CONNECTIVES and w not in in_quote]


def has_extra_text(text):
    """Any non-empty line besides the code itself, e.g. self-commentary appended after the answer."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return len(lines) > 1 and any(CODE_RE.match(norm(ln)) for ln in lines)


def check_code(raw, excerpts, target=None):
    """Score one completion against the excerpts {n: text} it was shown. target = (n, span) if one was requested."""
    parsed = parse_code(raw)
    if not parsed:
        return {"format_ok": False, "verbatim_ok": False, "outside_words": [], "imposed_connectives": [],
                "extra_text": False, "markup": False, "target_exact": False}
    label, n, quote, had_markup = parsed
    source = " ".join(excerpts.values())
    res = {"format_ok": True, "verbatim_ok": is_verbatim(quote, excerpts.get(n, "")),
           "outside_words": outside_words(label, source), "imposed_connectives": imposed_connectives(label, quote),
           "extra_text": has_extra_text(raw), "markup": had_markup}
    if target is not None:
        res["target_exact"] = n == target[0] and _alnum(quote) == _alnum(target[1])
    return res


def summarize(rows):
    """Rates over a list of check dicts (the open-coding scorecard shown next to a run)."""
    n = len(rows)
    ok = [r for r in rows if r.get("format_ok")]

    def rate(pred, pool=None):
        pool = rows if pool is None else pool
        return round(sum(1 for r in pool if pred(r)) / len(pool), 3) if pool else None
    return {"n": n, "format_ok": rate(lambda r: r.get("format_ok")), "verbatim_ok": rate(lambda r: r.get("verbatim_ok")),
            "outside_word_labels": rate(lambda r: bool(r.get("outside_words")), ok),
            "imposed_connective_labels": rate(lambda r: bool(r.get("imposed_connectives")), ok),
            "extra_text": rate(lambda r: r.get("extra_text")), "markup": rate(lambda r: r.get("markup"))}
