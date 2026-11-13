"""A stand-in OpenAI-compatible server for tests. Its answers are canned and rule-based: they exercise the
plumbing (formats, parsing, gates, tools, streaming) and say nothing about how any real model behaves."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TARGET_RE = re.compile(r"Target excerpt: \[(\d+)\] «(.+)»", re.S)
SLOTS = ["P", "CC", "Ctx", "IC", "S", "Csq"]


def _json_after(prompt, marker):
    """The JSON value that follows `marker` (the pipeline puts its data at the end of the prompt)."""
    tail = prompt.split(marker, 1)[1].lstrip()
    return json.JSONDecoder().raw_decode(tail)[0]


def answer(body, state):
    msgs = body["messages"]
    system = msgs[0]["content"] if msgs[0]["role"] == "system" else ""
    last = msgs[-1]
    prompt = last.get("content") or ""
    model = body["model"]
    state["calls"].append({"model": model, "tools": bool(body.get("tools")), "extra": body.get("chat_template_kwargs")})
    if state.get("fail_model") == model:
        return None
    if "in-vivo open coding" in system:                                   # level 1, one target span
        m = TARGET_RE.search(prompt)
        n, span = m.group(1), m.group(2)
        words = span.rstrip(".?!").split()
        if model == "base":                                               # markup + words the speaker never used
            return "<code>financial anxiety shapes %s</code> — [%s] «%s»" % (" ".join(words[:4]).lower(), n, span)
        return "%s — [%s] «%s»" % (" ".join(words[:9]), n, span)
    if "research assistant" in system:                                    # the agent loop
        text_mode = "<tool_call>" in system
        if last["role"] == "tool" or "<tool_response>" in prompt:
            payload = prompt if text_mode else last["content"]
            core = re.search(r'"core_category": "([^"]+)"', payload)
            return "The core category is: %s." % (core.group(1) if core else "unknown")
        if text_mode:
            return '<tool_call>{"name": "gt_coding_overview", "arguments": {}}</tool_call>'
        return {"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "gt_coding_overview", "arguments": "{}"}}]}
    if '"contribution"' in prompt:                                        # telemetry: self-ratings
        return json.dumps([{"name": "x", "contribution": 0.5}])
    if "thick_description" in prompt:
        return json.dumps({"thick_description": 4, "contextualisation": 3, "emic_etic": 4, "chain_of_meaning": 3, "reflexivity": 3})
    if '"label_ids"' in prompt:                                           # concepts
        labels = _json_after(prompt, "(with index i):" if "(with index i):" in prompt else "（带索引 i）：")
        k = max(2, min(8, len(labels) // 2))
        return json.dumps([{"concept": "Concept %d on guarding the stall's takings" % j, "freq": 2,
                            "label_ids": [l["i"] for l in labels if l["i"] % k == j],
                            "attributes": {"actor": "vendor", "motive": "keeping control of income"}} for j in range(k)])
    if '"c6_slot"' in prompt and '"core_category"' not in prompt:        # axial
        concepts = _json_after(prompt, "Concepts:" if "Concepts:" in prompt else "概念：")
        cats = [{"name": "Weighing phone payments against cash, dimension %d" % i, "c6_slot": SLOTS[i], "concepts": []} for i in range(6)]
        for j, c in enumerate(concepts):
            if not (state.get("drop_concepts") and j % 2):
                cats[j % 6]["concepts"].append(c["concept"])
        rels = [{"from": cats[i]["name"], "to": cats[0]["name"], "type": "causal", "evidence": "e", "confidence": 0.8} for i in range(1, 6)]
        return json.dumps({"categories": cats, "relations": rels})
    if '"core_category"' in prompt:                                       # selective
        cats = _json_after(prompt, "Categories:" if "Categories:" in prompt else "范畴：")
        return json.dumps({"core_category": {"name": "Accepting phone payments only as far as the vendor can still see her money",
                                             "mapping": [c["name"] for c in cats]},
                           "theory": {"storyline": ["Vendors take phone payments when refusing costs customers."],
                                      "propositions": ["The more young customers a stall has, the sooner it accepts phone payments; if stalls with many young customers refuse them, the proposition is refuted."]}})
    if '"surface"' in prompt or '"表层"' in prompt:                        # decode
        ev = _json_after(prompt, "invent a quotation):" if "invent a quotation):" in prompt else "不得自拟引语）：")
        q = ev[0]["quotes"][0]
        quote = state.get("fake_quote") or q
        return json.dumps({"surface": "Vendors say: \"%s\"" % quote, "functional": "f", "emotional": "e", "social": "s",
                           "cultural": "c", "cultural_logic": "Visible money is trusted money.", "symbolic_meaning": "m", "counter_example": ""})
    if '"label":"","evidence":""' in prompt:                              # level 1 on a general model (whole text)
        lines = re.findall(r"^\[\d+\] (?:\w+: )?(.+)$", prompt, re.M)
        return json.dumps([{"label": " ".join(l.split()[:6]), "evidence": " ".join(l.split()[:12])} for l in lines])
    return "unrecognised prompt"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):                                   # /v1/models, used by health checks
        data = json.dumps({"object": "list", "data": [{"id": m} for m in ("opencoding", "base", "general")]}).encode()
        self.send_response(200 if self.path.endswith("/models") else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        state = self.server.state
        if state.get("http_status"):
            self.send_response(state["http_status"])
            self.end_headers()
            self.wfile.write(b'{"error": "forced"}')
            return
        out = answer(body, state)
        msg = {"role": "assistant", "content": out} if isinstance(out, str) else {"role": "assistant", "content": None, **(out or {})}
        if out is None:
            msg = {"role": "assistant", "content": ""}
        data = json.dumps({"model": body["model"], "choices": [{"message": msg, "finish_reason": "stop"}], "usage": {}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start(port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.state = {"calls": []}
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d/v1" % srv.server_address[1]


if __name__ == "__main__":
    import sys
    srv, url = start(int(sys.argv[1]) if len(sys.argv) > 1 else 8011)
    print("mock model server at", url, "(models: any; 'opencoding' and 'base' answer the open-coding prompt)", flush=True)
    threading.Event().wait()
