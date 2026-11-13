"""Deterministic text handling: transcript -> speaker turns -> excerpts -> target spans. No model calls."""
import re

NL = "\n"
TS_RE = re.compile(r"^\[?\d{1,2}:\d{2}(?::\d{2})?\s*(?:-|–|—|to)?\s*(?:\d{1,2}:\d{2}(?::\d{2})?)?\]?\s*")
ROLE_LINE_RE = re.compile(r"^(?P<role>[A-Za-z一-鿿][\w .'\-一-鿿]{0,28}?)\s*[:：]\s*(?P<text>\S.*)$")
HEADER_RE = re.compile(r"^(?:SPEAKER[_ ]?\w+|Speaker\s+\w+|说话人\s*\w+)\b[\s:：\-]*(?P<rest>.*)$")
INTERVIEWER_RE = re.compile(
    r"^(?:interviewer|researcher|moderator|facilitator|ethnographer|int|q|i|r|访谈者|采访者|主持人|研究者|提问者)\d*$", re.I)
SENT_RE = re.compile(r"[^.!?…。！？]+(?:[.!?…。！？]+[\"”’')\]]*|$)")
WORD_RE = re.compile(r"\S+")


def nwords(text):
    return len(WORD_RE.findall(text or ""))


def parse_turns(raw):
    """Split a transcript into speaker turns [{"role", "text"}].

    Understood line shapes: `Name: text`, a speaker header on its own line (`SPEAKER_01`, `Speaker 2`), and a
    leading timestamp. Text with no speaker marks at all is split into one turn per paragraph (or per line).
    """
    lines = [ln.strip("\f").rstrip() for ln in (raw or "").replace("\r\n", NL).replace("\r", NL).split(NL)]
    turns, cur, seen_role = [], None, False
    for line in lines:
        s = TS_RE.sub("", line.strip())
        if not s:
            if cur and not seen_role:          # blank line ends a paragraph in unmarked text
                turns.append(cur)
                cur = None
            continue
        role, text = None, s
        h = HEADER_RE.match(s)
        m = None if h else ROLE_LINE_RE.match(s)
        if h:
            role = s[: len(s) - len(h.group("rest"))].strip(" :：-")
            text = TS_RE.sub("", h.group("rest").strip())
        elif m and nwords(m.group("role")) <= 3:
            role, text = m.group("role").strip(), m.group("text").strip()
        if role is not None:
            seen_role = True
            if cur:
                turns.append(cur)
            cur = {"role": role, "text": text}
        elif cur:
            cur["text"] = (cur["text"] + " " + text).strip()
        else:
            cur = {"role": "", "text": text}
    if cur:
        turns.append(cur)
    turns = [t for t in turns if t["text"].strip()]
    if not seen_role and len(turns) == 1 and NL in (raw or "").strip():
        turns = [{"role": "", "text": ln.strip()} for ln in raw.split(NL) if ln.strip()]
    return turns


def is_interviewer(role):
    return bool(INTERVIEWER_RE.match((role or "").strip().replace(" ", "")))


def participant_excerpts(turns):
    """Turns to code: everything except interviewer turns. Returns [{"i", "role", "text"}] with i = turn index."""
    return [{"i": i, "role": t["role"], "text": t["text"]} for i, t in enumerate(turns)
            if t["text"].strip() and not is_interviewer(t["role"])]


def split_sentences(text):
    """Sentence spans as (start, end) offsets into text. Abbreviation-blind on purpose: short pieces are merged later."""
    spans = []
    for m in SENT_RE.finditer(text or ""):
        a, b = m.span()
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        if b > a:
            spans.append((a, b))
    return spans


def target_spans(text, min_words=7, max_words=60):
    """Verbatim spans of an excerpt to code, each a whole sentence or a run of adjacent sentences.

    A sentence shorter than min_words is joined to its neighbour, so that a span carries a complete statement;
    a join never exceeds max_words unless a single sentence is already longer.
    """
    spans = split_sentences(text)
    out, cur = [], None
    for a, b in spans:
        if cur is None:
            cur = [a, b]
            continue
        cur_n, new_n = nwords(text[cur[0]:cur[1]]), nwords(text[a:b])
        if (cur_n < min_words or new_n < min_words) and cur_n + new_n <= max_words:
            cur[1] = b
        else:
            out.append(tuple(cur))
            cur = [a, b]
    if cur is not None:
        out.append(tuple(cur))
    return [text[a:b] for a, b in out if nwords(text[a:b]) >= 3]


def windows(excerpts, max_words=380, max_excerpts=8):
    """Group consecutive excerpts into units small enough for the open-coding model's context.
    Returns lists of positions into `excerpts`."""
    out, cur, cur_words = [], [], 0
    for pos, ex in enumerate(excerpts):
        n = nwords(ex["text"])
        if cur and (cur_words + n > max_words or len(cur) >= max_excerpts):
            out.append(cur)
            cur, cur_words = [], 0
        cur.append(pos)
        cur_words += n
    if cur:
        out.append(cur)
    return out


def split_long(excerpts, max_words=220):
    """Split an over-long excerpt at sentence boundaries so that it fits a window. Keeps the turn index."""
    out = []
    for ex in excerpts:
        if nwords(ex["text"]) <= max_words:
            out.append(ex)
            continue
        text, start, last_end, count = ex["text"], None, None, 0
        for a, b in split_sentences(text):
            n = nwords(text[a:b])
            if start is not None and count + n > max_words:
                out.append({**ex, "text": text[start:last_end]})
                start, count = None, 0
            if start is None:
                start = a
            last_end, count = b, count + n
        if start is not None:
            out.append({**ex, "text": text[start:last_end]})
    return out
