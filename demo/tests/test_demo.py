"""Offline tests of the demo server: python3 -m unittest discover -s demo/tests
A rule-based mock stands in for the models and for GitHub; no mail is sent."""
import http.client
import io
import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "demo"))
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "agent" / "tests"))

TMP = Path(tempfile.mkdtemp())
os.environ["DEMO_ACCESS_FILE"] = str(TMP / "access.json")

import access  # noqa: E402
import mock_server  # noqa: E402
import server  # noqa: E402
from anthro_agent.config import Endpoint, Settings  # noqa: E402

EXAMPLE = (ROOT / "agent" / "examples" / "synthetic_interview.txt").read_text(encoding="utf-8")
FOCUS = "How night-market food vendors decide whether to accept mobile payments"


class FakeGitHub(BaseHTTPRequestHandler):
    accounts = {"code-listed": ("listed-login", []), "code-mail": ("someone", ["x@allowed.example"]), "code-nobody": ("stranger", ["s@else.example"])}

    def log_message(self, *a):
        pass

    def _send(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        form = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        self._send({"access_token": "tok-" + form["code"][0]} if form["code"][0] in self.accounts else {"error": "bad_code"})

    def do_GET(self):
        login, mails = self.accounts[self.headers["Authorization"].split("tok-")[1]]
        if self.path == "/user":
            return self._send({"login": login})
        self._send([{"email": m, "verified": True} for m in mails] + [{"email": "unverified@allowed.example", "verified": False}])


class Client:
    """A tiny browser: keeps cookies, sends the same headers the page sends."""

    def __init__(self, port):
        self.port, self.cookies = port, {}

    def request(self, method, path, body=None, headers=None, raw=False):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h = {"Cookie": "; ".join("%s=%s" % kv for kv in self.cookies.items())}
        if body is not None:
            h.update({"Content-Type": "application/json", "X-Requested-With": "demo"})
        h.update(headers or {})
        conn.request(method, path, json.dumps(body) if body is not None else None, h)
        res = conn.getresponse()
        data = res.read()
        for k, v in res.getheaders():
            if k.lower() == "set-cookie":
                name, _, rest = v.partition("=")
                val = rest.split(";")[0]
                if val:
                    self.cookies[name] = val
                else:
                    self.cookies.pop(name, None)
        conn.close()
        if raw:
            return res, data
        try:
            return res.status, json.loads(data)
        except ValueError:
            return res.status, data.decode()

    def events(self, method, path, body=None):
        res, data = self.request(method, path, body, raw=True)
        out = []
        for block in data.decode().split("\n\n"):
            m = re.match(r"event: (\S+)\ndata: (.*)", block, re.S)
            if m:
                out.append((m.group(1), json.loads(m.group(2))))
        return res.status, out


class DemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models, model_url = mock_server.start()
        cls.gh = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
        threading.Thread(target=cls.gh.serve_forever, daemon=True).start()
        gh_url = "http://127.0.0.1:%d" % cls.gh.server_address[1]
        os.environ.update({"DEMO_PORT": "0", "MAIL_MODE": "console", "DEMO_SECRET": "s" * 32, "DEMO_RUNS_DIR": str(TMP / "runs"),
                           "DEMO_PUBLIC_URL": "http://demo.test", "GITHUB_CLIENT_ID": "id", "GITHUB_CLIENT_SECRET": "secret",
                           "GITHUB_OAUTH_BASE": gh_url, "GITHUB_API_BASE": gh_url, "DEMO_RUNS_PER_DAY": "3", "DEMO_MAX_WORDS": "600"})
        ep = Endpoint(base_url=model_url, model="general", max_tokens=8000)
        oc = Endpoint(base_url=model_url, model="opencoding", max_tokens=512)
        cls.settings = Settings(reasoner=ep, decoder=ep, opencoder=oc, opencoder_base_model="base", telemetry=False)
        cls.srv = server.make_server(server.Cfg(), cls.settings)
        cls.srv.app.opencoder_status = lambda: cls.status
        cls.status = "online"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.port = cls.srv.server_address[1]
        access.save({"emails": ["jane@example.org"], "domains": ["allowed.example"], "github": ["listed-login"]})

    @classmethod
    def tearDownClass(cls):
        for s in (cls.srv, cls.gh, cls.models):
            s.shutdown()

    def setUp(self):
        type(self).status = "online"
        self.srv.app.limiter.hits.clear()
        self.srv.app.limiter.days.clear()
        self.models.state.clear()
        self.models.state["calls"] = []

    def sign_in(self, email="jane@example.org"):
        c = Client(self.port)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(c.request("POST", "/api/auth/request", {"email": email})[0], 200)
            for _ in range(50):
                if "sign-in code" in buf.getvalue():
                    break
                time.sleep(0.02)
        code = re.search(r": (\d{6}) ", buf.getvalue()).group(1)
        self.assertEqual(c.request("POST", "/api/auth/verify", {"email": email, "code": code}), (200, {"ok": True}))
        return c

    # ---- the gate
    def test_everything_needs_a_session(self):
        c = Client(self.port)
        for path in ("/api/me", "/api/examples", "/api/runs/20260101-000000-abcdef", "/api/runs/20260101-000000-abcdef/events"):
            self.assertEqual(c.request("GET", path)[0], 401, path)
        for path in ("/api/runs", "/api/chat"):
            self.assertEqual(c.request("POST", path, {})[0], 401, path)
        res, page = c.request("GET", "/", raw=True)
        self.assertEqual(res.status, 200)
        self.assertIn("default-src 'none'", res.getheader("Content-Security-Policy"))
        for secret in (b"opencoding", b"127.0.0.1", b"/v1"):     # the public page names no model and no endpoint
            self.assertNotIn(secret, page)
        self.assertEqual(c.request("GET", "/api/config")[1]["auth"], {"email": True, "github": True})
        for path in ("/../server.py", "/server.py", "/.env", "/access.json", "/web/../access.json"):
            self.assertEqual(c.request("GET", path)[0], 401, path)       # only the three page files are ever served

    def test_email_code_only_for_listed_addresses(self):
        c = Client(self.port)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(c.request("POST", "/api/auth/request", {"email": "mallory@else.example"}), (200, {"ok": True}))
            self.assertEqual(c.request("POST", "/api/auth/request", {"email": "not-an-address"})[0], 400)
            time.sleep(0.1)
        self.assertNotIn("sign-in code", buf.getvalue())        # same answer, but nothing was sent
        self.assertEqual(c.request("POST", "/api/auth/verify", {"email": "mallory@else.example", "code": "000000"})[0], 401)
        self.assertEqual(self.sign_in("anyone@allowed.example").request("GET", "/api/me")[1]["user"]["name"], "anyone@allowed.example")

    def test_code_is_single_use_and_guess_limited(self):
        c = Client(self.port)
        buf = io.StringIO()
        with redirect_stdout(buf):
            c.request("POST", "/api/auth/request", {"email": "jane@example.org"})
            time.sleep(0.1)
        code = re.search(r": (\d{6}) ", buf.getvalue()).group(1)
        wrong = "%06d" % ((int(code) + 1) % 1000000)
        for _ in range(5):
            self.assertEqual(c.request("POST", "/api/auth/verify", {"email": "jane@example.org", "code": wrong})[0], 401)
        self.assertEqual(c.request("POST", "/api/auth/verify", {"email": "jane@example.org", "code": code})[0], 401)   # burned
        c2 = self.sign_in()
        self.assertEqual(c2.request("GET", "/api/me")[0], 200)

    def test_request_rate_limit(self):
        c = Client(self.port)
        with redirect_stdout(io.StringIO()):
            codes = [c.request("POST", "/api/auth/request", {"email": "jane@example.org"})[0] for _ in range(6)]
        self.assertEqual(codes, [200] * 5 + [429])

    def test_removing_someone_ends_their_session(self):
        c = self.sign_in("temp@allowed.example")
        self.assertEqual(c.request("GET", "/api/me")[0], 200)
        access.save({"emails": ["jane@example.org"], "domains": [], "github": ["listed-login"]})
        try:
            self.assertEqual(c.request("GET", "/api/me")[0], 401)
        finally:
            access.save({"emails": ["jane@example.org"], "domains": ["allowed.example"], "github": ["listed-login"]})

    def test_forged_or_cross_site_requests_are_refused(self):
        c = self.sign_in()
        good = c.cookies["sid"]
        c.cookies["sid"] = good[:-4] + ("0000" if not good.endswith("0000") else "1111")
        self.assertEqual(c.request("GET", "/api/me")[0], 401)
        c.cookies["sid"] = good
        self.assertEqual(c.request("POST", "/api/runs", {"text": "x", "focus": "y"}, headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(c.request("POST", "/api/runs", {"text": "x", "focus": "y"}, headers={"Origin": "null"})[0], 403)
        for origin in ("http://127.0.0.1:%d" % self.port, "http://127.0.0.1", "http://demo.test"):     # same site, port dropped on the way
            self.assertEqual(c.request("POST", "/api/runs", {"text": "x", "focus": "y"}, headers={"Origin": origin})[0], 400, origin)
        self.assertEqual(c.request("POST", "/api/runs", {"text": "x"}, headers={"X-Requested-With": ""})[0], 403)

    def test_github_sign_in(self):
        for code, expect in (("code-listed", "@listed-login"), ("code-mail", "@someone"), ("code-nobody", None)):
            c = Client(self.port)
            res, _ = c.request("GET", "/auth/github/start", raw=True)
            loc = urllib.parse.urlsplit(res.getheader("Location"))
            q = urllib.parse.parse_qs(loc.query)
            self.assertEqual(q["redirect_uri"], ["http://demo.test/auth/github/callback"])
            with redirect_stdout(io.StringIO()):
                res, _ = c.request("GET", "/auth/github/callback?code=%s&state=%s" % (code, q["state"][0]), raw=True)
            if expect:
                self.assertEqual(res.getheader("Location"), "/")
                self.assertEqual(c.request("GET", "/api/me")[1]["user"]["name"], expect)
            else:
                self.assertEqual(res.getheader("Location"), "/?signin=denied")
                self.assertEqual(c.request("GET", "/api/me")[0], 401)
        c = Client(self.port)                                   # a callback without the state cookie goes nowhere
        res, _ = c.request("GET", "/auth/github/callback?code=code-listed&state=whatever", raw=True)
        self.assertEqual(res.getheader("Location"), "/?signin=failed")

    # ---- the workbench
    def run_once(self, c, **extra):
        status, data = c.request("POST", "/api/runs", {"text": EXAMPLE, "focus": FOCUS, "compare": True, **extra})
        self.assertEqual(status, 202, data)
        return data["run_id"], c.events("GET", "/api/runs/%s/events" % data["run_id"])[1]

    def test_run_streams_and_is_private(self):
        c = self.sign_in()
        with redirect_stdout(io.StringIO()):
            run_id, events = self.run_once(c)
        kinds = [k for k, _ in events]
        self.assertEqual(kinds[0], "start")
        self.assertEqual(kinds[-1], "end")
        for k in ("open.label", "open.done", "concepts.done", "axial.done", "selective.done", "decode.done", "round.done", "saved"):
            self.assertIn(k, kinds)
        start = events[0][1]
        self.assertEqual(len(start["turns"]), 16)
        self.assertTrue(start["models"]["open_coding_is_post_trained"])
        label = next(p for k, p in events if k == "open.label")
        self.assertIn("financial", label["base"]["checks"]["outside_words"])
        status, data = c.request("GET", "/api/runs/" + run_id)
        self.assertEqual(status, 200)
        self.assertEqual(len(data["graph"]["categories"]), 6)
        self.assertEqual(c.events("GET", "/api/runs/%s/events?from=%d" % (run_id, len(events) - 2))[1][-1][0], "end")
        with redirect_stdout(io.StringIO()):
            other = self.sign_in("other@allowed.example")
        self.assertIn(run_id, [r["run_id"] for r in c.request("GET", "/api/runs")[1]["runs"]])
        self.assertEqual(other.request("GET", "/api/runs")[1]["runs"], [])
        self.assertEqual(other.request("GET", "/api/runs/" + run_id)[0], 404)             # someone else's run
        self.assertEqual(other.request("GET", "/api/runs/%s/events" % run_id)[0], 404)
        self.assertEqual(c.request("GET", "/api/me")[1]["quota"]["runs_left"], 2)

    def test_limits(self):
        c = self.sign_in()
        self.assertEqual(c.request("POST", "/api/runs", {"text": "word " * 601, "focus": FOCUS})[0], 400)
        self.assertEqual(c.request("POST", "/api/runs", {"text": EXAMPLE, "focus": "x"})[0], 400)
        with redirect_stdout(io.StringIO()):
            for _ in range(3):
                self.run_once(c)
        status, data = c.request("POST", "/api/runs", {"text": EXAMPLE, "focus": FOCUS})
        self.assertEqual(status, 429, data)

    def test_offline_model_needs_consent_and_is_labelled(self):
        type(self).status = "offline"
        c = self.sign_in()
        status, data = c.request("POST", "/api/runs", {"text": EXAMPLE, "focus": FOCUS})
        self.assertEqual((status, data["error"]), (409, "opencoder_offline"))
        with redirect_stdout(io.StringIO()):
            _, events = self.run_once(c, allow_general_model=True)
        self.assertFalse(events[0][1]["models"]["open_coding_is_post_trained"])
        self.assertEqual({call["model"] for call in self.models.state["calls"]}, {"general"})

    def test_upstream_errors_are_not_shown(self):
        self.models.state["http_status"] = 401
        c = self.sign_in()
        buf = io.StringIO()
        with redirect_stdout(buf):
            _, events = self.run_once(c)
        err = next(p for k, p in events if k == "error")
        self.assertNotIn("401", json.dumps(err))
        self.assertIn("MODEL ERROR: HTTP 401", buf.getvalue())   # the cause is in the server log

    def test_chat_reads_only_own_run(self):
        c = self.sign_in()
        with redirect_stdout(io.StringIO()):
            run_id, _ = self.run_once(c)
            status, events = c.events("POST", "/api/chat", {"run_id": run_id, "messages": [{"role": "user", "content": "What is the core category?"}]})
            self.assertEqual([k for k, _ in events], ["tool.call", "tool.result", "answer", "end"])
            self.assertIn("Accepting phone payments", events[2][1]["text"])
            other = self.sign_in("other@allowed.example")
            _, events = other.events("POST", "/api/chat", {"run_id": run_id, "messages": [{"role": "user", "content": "What is the core category?"}]})
        self.assertIn("unknown", events[-2][1]["text"])          # the tool found no coding for this person
        self.assertEqual(c.request("POST", "/api/chat", {"messages": []})[0], 400)


if __name__ == "__main__":
    unittest.main()
