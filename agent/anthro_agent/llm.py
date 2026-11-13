"""OpenAI-compatible chat client on the standard library (no SDK dependency)."""
import json
import re
import time
import urllib.error
import urllib.request

THINK_RE = re.compile(r"<think>.*?</think>", re.S)
TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}


class LLMError(RuntimeError):
    """A request that will not succeed by retrying (bad key, unknown model, request too large)."""


def _post(ep, body):
    headers = {"Content-Type": "application/json"}
    if ep.api_key:
        headers["Authorization"] = "Bearer " + ep.api_key
    req = urllib.request.Request(ep.url, data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=ep.timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def chat(ep, messages, *, temperature=None, max_tokens=None, tools=None, model=None, retries=3, backoff=4.0):
    """One chat completion. Returns {"content", "tool_calls", "finish_reason", "usage", "model"}.

    Raises LLMError on errors that retrying cannot fix; returns content "" if every attempt came back empty.
    """
    if not ep.configured:
        raise LLMError("model endpoint is not configured (set *_BASE_URL and *_MODEL)")
    budget = max_tokens if max_tokens is not None else ep.max_tokens
    budget = max(min(budget, ep.max_tokens), min(ep.min_tokens, ep.max_tokens))
    body = {"model": model or ep.model, "messages": messages, "max_tokens": budget}
    if temperature is not None:
        body["temperature"] = temperature
    if tools:
        body["tools"] = tools
    body.update(ep.extra_body or {})
    last = "no attempt made"
    for attempt in range(max(1, retries)):
        try:
            data = _post(ep, body)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            if e.code not in RETRYABLE:
                hint = " (this server allows fewer output tokens: lower the endpoint's *_MAX_TOKENS)" if "max_tokens" in detail else ""
                raise LLMError(f"HTTP {e.code} from {body['model']}: {detail}{hint}") from None
            last = f"HTTP {e.code}: {detail}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as e:
            last = f"{type(e).__name__}: {e}"
        else:
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            content = THINK_RE.sub("", msg.get("content") or "").strip()
            calls = _tool_calls(msg, content)
            if content or calls:
                if calls and not msg.get("tool_calls"):
                    content = TOOL_CALL_RE.sub("", content).strip()
                return {"content": content, "tool_calls": calls, "finish_reason": choice.get("finish_reason"),
                        "usage": data.get("usage") or {}, "model": data.get("model") or body["model"]}
            last = "empty completion (finish_reason=%s)" % choice.get("finish_reason")
        if attempt + 1 < retries:
            time.sleep(backoff * (attempt + 1))
    return {"content": "", "tool_calls": [], "finish_reason": "error", "usage": {}, "model": body["model"], "error": last}


def _tool_calls(msg, content):
    """Native tool calls, or <tool_call>{...}</tool_call> blocks left in the text by servers that do not parse them."""
    out = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        out.append({"id": tc.get("id") or "call_%d" % len(out), "name": fn.get("name", ""),
                    "arguments": _args(fn.get("arguments"))})
    if out:
        return out
    for m in TOOL_CALL_RE.finditer(content or ""):
        try:
            obj = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("name"):
            out.append({"id": "call_%d" % len(out), "name": obj["name"], "arguments": _args(obj.get("arguments"))})
    return out


def _args(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            val = json.loads(raw)
            return val if isinstance(val, dict) else {}
        except ValueError:
            return {}
    return {}


def complete(ep, prompt, *, system=None, temperature=None, max_tokens=None, model=None, retries=3):
    """Single-prompt completion. Returns the text, or None if nothing usable came back."""
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    out = chat(ep, messages, temperature=temperature, max_tokens=max_tokens, model=model, retries=retries)
    return out["content"] or None


def parse_json(txt):
    """First {...} object in a completion, or None."""
    if not txt:
        return None
    s, e = txt.find("{"), txt.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        val = json.loads(txt[s:e + 1])
    except ValueError:
        return None
    return val if isinstance(val, dict) else None


def parse_list_json(txt):
    """First [...] array in a completion. If the output was cut off by the token limit, close the array after
    the last complete object and keep what was parsed (only the trailing half-object is lost)."""
    if not txt:
        return None
    s = txt.find("[")
    if s < 0:
        return None
    e = txt.rfind("]")
    for cand in ([txt[s:e + 1], txt[s:]] if e > s else [txt[s:]]):
        try:
            val = json.loads(cand)
            return val if isinstance(val, list) else None
        except ValueError:
            pass
    full = txt[s:]
    idx = len(full)
    while True:
        idx = full.rfind("}", 0, idx)
        if idx < 0:
            return None
        try:
            val = json.loads(full[:idx + 1] + "]")
            return val if isinstance(val, list) else None
        except ValueError:
            continue
