#!/usr/bin/env python3
"""Access-restricted demo of the coding agent. Standard library only.

  python3 server.py            reads ./.env (see .env.example), serves on DEMO_HOST:DEMO_PORT

Who gets in is decided by access.json (see access.py):
  - email one-time code: an allow-listed address (or any address at an allow-listed domain) receives a
    6-digit code and proves it owns the mailbox;
  - GitHub sign-in: an allow-listed login, or an account with an allow-listed verified address.
The list is re-read on every request, so removing an entry ends that person's session.

The server holds the model endpoints. They are never exposed to the browser; the open-coding model stays on
localhost and only this process talks to it.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import smtplib
import ssl
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))
sys.path.insert(0, str(HERE))

import access  # noqa: E402
from anthro_agent.agent import Agent  # noqa: E402
from anthro_agent.config import Settings, load_env_file  # noqa: E402
from anthro_agent.llm import LLMError  # noqa: E402
from anthro_agent.pipeline import encode  # noqa: E402
from anthro_agent.store import RUN_ID_RE, RunStore, Session  # noqa: E402
from anthro_agent.tools import ToolContext, build_registry  # noqa: E402

STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/index.html": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
SESSION_TTL = 7 * 24 * 3600
CODE_TTL = 600
MAX_BODY = 200_000


def _env(name, default=""):
    return os.environ.get(name, default).strip()


def _int(name, default):
    v = _env(name)
    return int(v) if v else default


class Cfg:
    def __init__(self):
        self.host = _env("DEMO_HOST", "127.0.0.1")
        self.port = _int("DEMO_PORT", 8787)
        self.public_url = _env("DEMO_PUBLIC_URL").rstrip("/")
        secret = _env("DEMO_SECRET")
        self.ephemeral_secret = not secret
        self.secret = (secret or secrets.token_hex(32)).encode()
        self.request_url = _env("DEMO_REQUEST_ACCESS_URL")
        self.mail_mode = _env("MAIL_MODE", "smtp" if _env("SMTP_HOST") else "off").lower()   # smtp | console | off
        self.smtp = {k: _env("SMTP_" + k.upper()) for k in ("host", "user", "password", "from")}
        self.smtp_port = _int("SMTP_PORT", 587)
        self.smtp_security = _env("SMTP_SECURITY", "starttls").lower()                       # starttls | ssl
        self.gh_id, self.gh_secret = _env("GITHUB_CLIENT_ID"), _env("GITHUB_CLIENT_SECRET")
        self.gh_oauth = _env("GITHUB_OAUTH_BASE", "https://github.com").rstrip("/")
        self.gh_api = _env("GITHUB_API_BASE", "https://api.github.com").rstrip("/")
        self.max_words = _int("DEMO_MAX_WORDS", 1500)
        self.max_targets = _int("DEMO_MAX_TARGETS", 90)
        self.runs_per_day = _int("DEMO_RUNS_PER_DAY", 12)
        self.chats_per_day = _int("DEMO_CHATS_PER_DAY", 60)
        self.max_concurrent = _int("DEMO_MAX_CONCURRENT", 2)
        self.keep_hours = _int("DEMO_KEEP_HOURS", 24)
        self.trust_proxy = _env("DEMO_TRUST_PROXY", "0") in ("1", "true", "yes")
        self.runs_dir = Path(_env("DEMO_RUNS_DIR") or HERE / "runs")

    @property
    def secure(self):
        return self.public_url.startswith("https://")

    @property
    def email_auth(self):
        return self.mail_mode in ("smtp", "console")

    @property
    def github_auth(self):
        return bool(self.gh_id and self.gh_secret and self.public_url)


# ---------------------------------------------------------------- small pieces
def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign(payload, secret):
    body = b64(json.dumps(payload, separators=(",", ":")).encode())
    return body + "." + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()


def unsign(token, secret):
    body, _, mac = (token or "").partition(".")
    if not body or not hmac.compare_digest(mac, hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    return payload if isinstance(payload, dict) and payload.get("exp", 0) > time.time() else None


class Limiter:
    """Sliding-window rate limits and per-day quotas, in memory."""

    def __init__(self):
        self.hits, self.days, self.lock = {}, {}, threading.Lock()

    def allow(self, key, limit, window):
        now = time.time()
        with self.lock:
            q = self.hits.setdefault(key, deque())
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def used(self, owner, kind):
        return self.days.get((owner, kind, time.strftime("%Y%m%d")), 0)

    def take(self, owner, kind, limit):
        key = (owner, kind, time.strftime("%Y%m%d"))
        with self.lock:
            if self.days.get(key, 0) >= limit:
                return False
            self.days[key] = self.days.get(key, 0) + 1
            for k in [k for k in self.days if k[2] != key[2]]:
                del self.days[k]
            return True

    def give_back(self, owner, kind):
        key = (owner, kind, time.strftime("%Y%m%d"))
        with self.lock:
            self.days[key] = max(0, self.days.get(key, 0) - 1)


def public_reason(err):
    """What a visitor is told when a model step fails. The raw cause goes to the server log only."""
    e = (err or "").lower()
    if "cut off" in e:
        return "the output was cut off"
    if "parsed" in e:
        return "the output could not be read"
    return "the model did not answer"


def scrub_result(res):
    """Remove raw upstream error text from a result before it is stored or shown."""
    graph, rub = res.get("graph") or {}, res.get("rubric") or {}
    (graph.get("open_coding") or {}).pop("errors", None)
    for d in rub.get("diagnostics") or []:
        d["error"] = public_reason(d.get("error"))
    return res


class OwnedStore:
    """A view of the run store that only shows one person's runs."""

    def __init__(self, store, owner):
        self.store, self.owner = store, owner

    def new_id(self):
        return self.store.new_id()

    def save(self, run_id, result, meta=None):
        return self.store.save(run_id, result, {**(meta or {}), "owner": self.owner})

    def load(self, run_id):
        data = self.store.load(run_id)
        if data["meta"].get("owner") != self.owner:
            raise KeyError("no such run")
        return data

    def latest_id(self):
        return None

    def list(self):
        return [m for m in self.store.list() if m.get("owner") == self.owner]


class Run:
    def __init__(self, run_id, owner):
        self.id, self.owner, self.events, self.done = run_id, owner, [], False
        self.cond, self.created = threading.Condition(), time.time()

    def push(self, kind, payload):
        with self.cond:
            self.events.append((kind, payload))
            self.cond.notify_all()

    def finish(self):
        with self.cond:
            self.done = True
            self.cond.notify_all()


class App:
    def __init__(self, cfg, settings):
        self.cfg, self.settings = cfg, settings
        self.store = RunStore(cfg.runs_dir)
        self.limiter = Limiter()
        self.codes, self.runs, self.lock = {}, {}, threading.Lock()
        self.slots = threading.BoundedSemaphore(cfg.max_concurrent)
        self._health = (0.0, "unknown")

    def log(self, who, what):
        print("%s  %-34s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), who or "-", what), flush=True)

    # ---- model availability
    def opencoder_status(self):
        ep = self.settings.opencoder
        if not ep.configured:
            return "not_configured"
        ts, status = self._health
        if time.time() - ts < 30:
            return status
        url = ep.base_url.rstrip("/").removesuffix("/chat/completions") + "/models"
        try:
            req = urllib.request.Request(url, headers={"Authorization": "Bearer " + ep.api_key} if ep.api_key else {})
            with urllib.request.urlopen(req, timeout=4) as r:
                ids = {m.get("id") for m in (json.loads(r.read()).get("data") or [])}
            status = "online" if ep.model in ids else "offline"
        except (urllib.error.URLError, OSError, ValueError):
            status = "offline"
        self._health = (time.time(), status)
        return status

    # ---- one-time codes
    def issue_code(self, email):
        code = "%06d" % secrets.randbelow(1_000_000)
        digest = hmac.new(self.cfg.secret, (email + ":" + code).encode(), hashlib.sha256).hexdigest()
        with self.lock:
            self.codes[email] = {"digest": digest, "exp": time.time() + CODE_TTL, "tries": 0}
            for k in [k for k, v in self.codes.items() if v["exp"] < time.time()]:
                del self.codes[k]
        return code

    def check_code(self, email, code):
        with self.lock:
            entry = self.codes.get(email)
            if not entry or entry["exp"] < time.time() or entry["tries"] >= 5:
                self.codes.pop(email, None)
                return False
            entry["tries"] += 1
            digest = hmac.new(self.cfg.secret, (email + ":" + code).encode(), hashlib.sha256).hexdigest()
            if hmac.compare_digest(digest, entry["digest"]):
                del self.codes[email]
                return True
            return False

    def send_code(self, email, code):
        if self.cfg.mail_mode == "console":
            print("[mail:console] sign-in code for %s: %s   (development only; set SMTP_* for real mail)" % (email, code), flush=True)
            return
        msg = EmailMessage()
        msg["Subject"] = "%s is your sign-in code" % code
        msg["From"] = self.cfg.smtp["from"] or self.cfg.smtp["user"]
        msg["To"] = email
        msg.set_content("Your sign-in code for the coding-agent demo is:\n\n    %s\n\nIt is valid for 10 minutes and can be used once.\n"
                        "If you did not ask for it, you can ignore this message.\n" % code)
        try:
            ctx = ssl.create_default_context()
            if self.cfg.smtp_security == "ssl":
                smtp = smtplib.SMTP_SSL(self.cfg.smtp["host"], self.cfg.smtp_port, timeout=20, context=ctx)
            else:
                smtp = smtplib.SMTP(self.cfg.smtp["host"], self.cfg.smtp_port, timeout=20)
                smtp.starttls(context=ctx)
            with smtp:
                if self.cfg.smtp["user"]:
                    smtp.login(self.cfg.smtp["user"], self.cfg.smtp["password"])
                smtp.send_message(msg)
            self.log("email:" + email, "code sent")
        except Exception as e:                      # noqa: BLE001 - never let mail errors reach the visitor
            self.log("email:" + email, "MAIL FAILED: %s: %s" % (type(e).__name__, e))

    # ---- runs
    def start_run(self, owner, text, focus, context, compare, lens, open_mode):
        run = Run(self.store.new_id(), owner)
        with self.lock:
            self.runs[run.id] = run
            for rid in [rid for rid, r in self.runs.items() if r.done and time.time() - r.created > 7200]:
                del self.runs[rid]

        def push(kind, payload):
            if kind == "stage.error":
                self.log(owner, "run %s stage %s failed: %s" % (run.id, payload.get("stage"), payload.get("error")))
                payload = {**payload, "error": public_reason(payload.get("error"))}
            elif kind == "open.done" and payload.get("errors"):
                self.log(owner, "run %s open coding errors: %s" % (run.id, payload["errors"]))
                payload = {k: v for k, v in payload.items() if k != "errors"}
            elif kind == "done" and payload.get("status") == "failed":
                self.log(owner, "run %s failed: %s" % (run.id, payload.get("reason")))
                payload = {"status": "failed", "reason": "The model did not answer."}
            run.push(kind, payload)

        def work():
            try:
                res = scrub_result(encode(text, focus, settings=self.settings, max_rounds=1, context=context, compare=compare,
                                          lens=lens, open_mode=open_mode, max_targets=self.cfg.max_targets, on_event=push))
                if res.get("graph"):
                    OwnedStore(self.store, owner).save(run.id, res)
                    run.push("saved", {"run_id": run.id, "status": res["status"], "rubric": res["rubric"],
                                       "reflexive": res["graph"]["reflexive"], "models": res["graph"]["models"]})
                self.log(owner, "run %s %s" % (run.id, res["status"]))
            except LLMError as e:
                self.log(owner, "run %s MODEL ERROR: %s" % (run.id, e))
                run.push("error", {"message": "A model service returned an error, so this run stopped. Please try again in a minute."})
            except Exception:                       # noqa: BLE001
                self.log(owner, "run %s CRASHED\n%s" % (run.id, traceback.format_exc()))
                run.push("error", {"message": "The run stopped because of an internal error."})
            finally:
                run.finish()
                self.slots.release()
        threading.Thread(target=work, daemon=True).start()
        return run

    def janitor(self):
        while True:
            time.sleep(1800)
            cutoff = time.time() - self.cfg.keep_hours * 3600
            try:
                for d in self.cfg.runs_dir.iterdir():
                    if RUN_ID_RE.match(d.name) and d.stat().st_mtime < cutoff:
                        shutil.rmtree(d, ignore_errors=True)
            except OSError:
                pass


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "demo"
    sys_version = ""

    def log_message(self, *args):
        pass

    @property
    def app(self):
        return self.server.app

    # ---- plumbing
    def ip(self):
        if self.app.cfg.trust_proxy:
            fwd = self.headers.get("CF-Connecting-IP") or (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            if fwd:
                return fwd
        return self.client_address[0]

    def send(self, status, body=b"", ctype="application/json; charset=utf-8", headers=()):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.common_headers()
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def common_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        if self.app.cfg.secure:
            self.send_header("Strict-Transport-Security", "max-age=31536000")

    def redirect(self, location, headers=()):
        self.send(302, b"", "text/plain", [("Location", location), *headers])

    def cookie(self, name):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == name:
                return v
        return ""

    def set_cookie(self, name, value, max_age, path="/"):
        attrs = "%s=%s; Path=%s; Max-Age=%d; HttpOnly; SameSite=Lax" % (name, value, path, max_age)
        return ("Set-Cookie", attrs + ("; Secure" if self.app.cfg.secure else ""))

    def user(self):
        """The signed-in person, if their session is valid and the rule that let them in still stands."""
        s = unsign(self.cookie("sid"), self.app.cfg.secret)
        if not s or not access.rule_still_holds(s.get("rule")):
            return None
        return s

    def body(self):
        """A same-origin JSON POST body, or None (the response has then been sent)."""
        # Two checks against cross-site requests. The custom header cannot be sent cross-origin without a CORS
        # preflight, which this server never grants. The Origin check is a second line; it compares host names
        # only, because proxies and some browser setups drop the port or change the scheme on the way.
        origin = self.headers.get("Origin")
        here = {_hostname(self.app.cfg.public_url), _hostname(self.headers.get("Host"))} - {""}
        self.close_connection = True                # every early return below leaves the request body unread
        if self.headers.get("X-Requested-With") != "demo" or (origin and _hostname(origin) not in here):
            self.app.log("-", "refused POST %s: origin=%r host=%r x-requested-with=%r" % (
                self.path.split("?")[0], origin, self.headers.get("Host"), self.headers.get("X-Requested-With")))
            self.send(403, {"error": "forbidden"})
            return None
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0 or n > MAX_BODY:
            self.send(413, {"error": "request too large"})
            return None
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            data = None
        if not isinstance(data, dict):
            self.send(400, {"error": "invalid JSON"})
            return None
        self.close_connection = False
        return data

    def sse_start(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.common_headers()
        self.end_headers()
        self.close_connection = True
        self._sse_lock, self._sse_open = threading.Lock(), True

    def sse(self, kind, payload=None):
        """Write one event. Safe to call from several threads; goes quiet once the browser has left."""
        with self._sse_lock:
            if not self._sse_open:
                return False
            try:
                data = (": keep-alive\n\n" if kind is None else "event: %s\ndata: %s\n\n" % (kind, json.dumps(payload, ensure_ascii=False)))
                self.wfile.write(data.encode())
                self.wfile.flush()
                return True
            except OSError:
                self._sse_open = False
                return False

    # ---- routing
    def do_GET(self):
        try:
            self.route_get()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:                           # noqa: BLE001
            self.app.log("-", "GET %s CRASHED\n%s" % (self.path.split("?")[0], traceback.format_exc()))
            try:
                self.send(500, {"error": "internal error"})
            except OSError:
                pass

    do_HEAD = do_GET

    def do_POST(self):
        try:
            self.route_post()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:                           # noqa: BLE001
            self.app.log("-", "POST %s CRASHED\n%s" % (self.path.split("?")[0], traceback.format_exc()))
            try:
                self.send(500, {"error": "internal error"})
            except OSError:
                pass

    def route_get(self):
        url = urllib.parse.urlsplit(self.path)
        path, query = url.path, urllib.parse.parse_qs(url.query)
        if path in STATIC:
            name, ctype = STATIC[path]
            return self.send(200, (HERE / "web" / name).read_bytes(), ctype)
        if path == "/healthz":
            return self.send(200, b"ok", "text/plain")
        if path == "/api/config":
            cfg = self.app.cfg
            return self.send(200, {"auth": {"email": cfg.email_auth, "github": cfg.github_auth}, "request_access_url": cfg.request_url})
        if path == "/auth/github/start":
            return self.github_start()
        if path == "/auth/github/callback":
            return self.github_callback(query)
        user = self.user()
        if not user:
            return self.send(401, {"error": "sign in first"})
        if path == "/api/me":
            return self.send(200, self.me(user))
        if path == "/api/examples":
            return self.send(200, {"examples": EXAMPLES})
        if path == "/api/runs":
            mine = OwnedStore(self.app.store, user["sub"]).list()[:5]
            return self.send(200, {"runs": [{k: m.get(k) for k in ("run_id", "created", "focus", "core_category", "status")} for m in mine]})
        m = re.match(r"^/api/runs/([0-9a-f-]{22})(/events)?$", path)
        if m:
            return self.run_events(user, m.group(1), query) if m.group(2) else self.run_result(user, m.group(1))
        self.send(404, {"error": "not found"})

    def route_post(self):
        path = urllib.parse.urlsplit(self.path).path
        if path not in ("/api/auth/request", "/api/auth/verify", "/api/auth/logout", "/api/runs", "/api/chat"):
            self.close_connection = True
            return self.send(404, {"error": "not found"})
        data = self.body()
        if data is None:
            return None
        if path == "/api/auth/request":
            return self.auth_request(data)
        if path == "/api/auth/verify":
            return self.auth_verify(data)
        if path == "/api/auth/logout":
            return self.send(200, {"ok": True}, headers=[self.set_cookie("sid", "", 0)])
        user = self.user()
        if not user:
            return self.send(401, {"error": "sign in first"})
        return self.run_create(user, data) if path == "/api/runs" else self.chat(user, data)

    # ---- sign-in
    def auth_request(self, data):
        app, ip = self.app, self.ip()
        email = access.norm_email(data.get("email"))
        if not app.cfg.email_auth:
            return self.send(400, {"error": "email sign-in is not enabled"})
        if not email:
            return self.send(400, {"error": "Enter a valid email address."})
        if not app.limiter.allow(("ip", ip), 20, 3600) or not app.limiter.allow(("mail", email), 5, 3600):
            return self.send(429, {"error": "Too many requests. Try again later."})
        rule = access.email_rule(email)
        if rule:                                    # same answer and same timing whether or not the address is listed
            code = app.issue_code(email)
            threading.Thread(target=app.send_code, args=(email, code), daemon=True).start()
        else:
            app.log("email:" + email, "code requested, not on the list")
        self.send(200, {"ok": True})

    def auth_verify(self, data):
        app = self.app
        email, code = access.norm_email(data.get("email")), re.sub(r"\D", "", str(data.get("code") or ""))
        if not app.limiter.allow(("verify", self.ip()), 30, 3600):
            return self.send(429, {"error": "Too many attempts. Try again later."})
        rule = access.email_rule(email) if email else ""
        if not (rule and len(code) == 6 and app.check_code(email, code)):
            return self.send(401, {"error": "That code is wrong or has expired."})
        app.log("email:" + email, "signed in (%s)" % rule)
        token = sign({"sub": "email:" + email, "name": email, "rule": rule, "exp": int(time.time()) + SESSION_TTL}, app.cfg.secret)
        self.send(200, {"ok": True}, headers=[self.set_cookie("sid", token, SESSION_TTL)])

    def github_start(self):
        cfg = self.app.cfg
        if not cfg.github_auth:
            return self.send(404, {"error": "GitHub sign-in is not enabled"})
        state = secrets.token_urlsafe(24)
        q = urllib.parse.urlencode({"client_id": cfg.gh_id, "redirect_uri": cfg.public_url + "/auth/github/callback",
                                    "scope": "user:email", "state": state, "allow_signup": "false"})
        cookie = sign({"s": state, "exp": int(time.time()) + 600}, cfg.secret)
        self.redirect(cfg.gh_oauth + "/login/oauth/authorize?" + q, [self.set_cookie("gh", cookie, 600, "/auth/github")])

    def github_callback(self, query):
        app, cfg = self.app, self.app.cfg
        clear = self.set_cookie("gh", "", 0, "/auth/github")
        saved = unsign(self.cookie("gh"), cfg.secret)
        state, code = (query.get("state") or [""])[0], (query.get("code") or [""])[0]
        if not cfg.github_auth or not saved or not code or not hmac.compare_digest(saved.get("s", ""), state):
            return self.redirect("/?signin=failed", [clear])
        try:
            token = _http_json(cfg.gh_oauth + "/login/oauth/access_token", {
                "client_id": cfg.gh_id, "client_secret": cfg.gh_secret, "code": code,
                "redirect_uri": cfg.public_url + "/auth/github/callback"}).get("access_token")
            if not token:
                raise ValueError("no access token")
            login = str(_http_json(cfg.gh_api + "/user", token=token).get("login") or "").lower()
            emails = [e["email"] for e in _http_json(cfg.gh_api + "/user/emails", token=token)
                      if isinstance(e, dict) and e.get("verified") and e.get("email")]
        except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as e:
            app.log("github:?", "sign-in failed: %s: %s" % (type(e).__name__, e))
            return self.redirect("/?signin=failed", [clear])
        rule = access.github_rule(login, emails) if login else ""
        if not rule:
            app.log("github:" + login, "not on the list")
            return self.redirect("/?signin=denied", [clear])
        app.log("github:" + login, "signed in (%s)" % rule)
        sid = sign({"sub": "github:" + login, "name": "@" + login, "rule": rule, "exp": int(time.time()) + SESSION_TTL}, cfg.secret)
        self.redirect("/", [clear, self.set_cookie("sid", sid, SESSION_TTL)])

    # ---- the workbench
    def me(self, user):
        app, cfg = self.app, self.app.cfg
        return {"user": {"name": user["name"]}, "models": app.settings.describe(), "opencoder": app.opencoder_status(),
                "limits": {"max_words": cfg.max_words, "keep_hours": cfg.keep_hours},
                "quota": {"runs_left": max(0, cfg.runs_per_day - app.limiter.used(user["sub"], "runs")),
                          "chats_left": max(0, cfg.chats_per_day - app.limiter.used(user["sub"], "chats"))}}

    def run_create(self, user, data):
        app, cfg, owner = self.app, self.app.cfg, user["sub"]
        text, focus = str(data.get("text") or "").strip(), " ".join(str(data.get("focus") or "").split())
        words = len(text.split())
        if not 5 <= len(focus) <= 300:
            return self.send(400, {"error": "State the research focus in one sentence (5 to 300 characters)."})
        if words < 20:
            return self.send(400, {"error": "Paste at least a few sentences of interview text."})
        if words > cfg.max_words:
            return self.send(400, {"error": "The text has %d words; this demo takes up to %d." % (words, cfg.max_words)})
        context = {k: " ".join(str((data.get("context") or {}).get(k) or "").split())[:300] for k in ("research_question", "site", "method")}
        lens = data.get("lens") if data.get("lens") in ("general", "market") else "general"
        status = app.opencoder_status()
        open_mode = "target" if status == "online" else "dialog"
        if status == "offline" and not data.get("allow_general_model"):   # a post-trained model exists but is down: ask first
            return self.send(409, {"error": "opencoder_offline", "message": "The post-trained open-coding model is offline right now."})
        if not app.slots.acquire(blocking=False):
            return self.send(429, {"error": "The demo is busy with other runs. Try again in a minute."})
        if not app.limiter.take(owner, "runs", cfg.runs_per_day):
            app.slots.release()
            return self.send(429, {"error": "You have used today's %d runs. Come back tomorrow." % cfg.runs_per_day})
        run = app.start_run(owner, text, focus, {k: v for k, v in context.items() if v},
                            bool(data.get("compare")) and open_mode == "target", lens, open_mode)
        app.log(owner, "run %s started (%d words, level 1 on %s)" % (run.id, words, "post-trained model" if open_mode == "target" else "general model"))
        self.send(202, {"run_id": run.id})

    def run_events(self, user, run_id, query):
        run = self.app.runs.get(run_id)
        if not run or run.owner != user["sub"]:
            return self.send(404, {"error": "no such run"})
        try:
            pos = max(0, int((query.get("from") or ["0"])[0]))
        except ValueError:
            pos = 0
        self.sse_start()
        while True:
            with run.cond:
                if pos >= len(run.events) and not run.done:
                    run.cond.wait(timeout=15)
                batch, done = run.events[pos:], run.done
            if not batch and not done:
                if not self.sse(None):
                    return
                continue
            for kind, payload in batch:
                if not self.sse(kind, payload):
                    return
            pos += len(batch)
            if done and pos >= len(run.events):
                self.sse("end", {})
                return

    def run_result(self, user, run_id):
        try:
            data = OwnedStore(self.app.store, user["sub"]).load(run_id)
        except (KeyError, ValueError):
            return self.send(404, {"error": "no such run"})
        self.send(200, {"run_id": run_id, "graph": data["graph"], "rubric": data["rubric"], "meta": {k: data["meta"].get(k) for k in ("status", "score", "created")}})

    def chat(self, user, data):
        app, cfg, owner = self.app, self.app.cfg, user["sub"]
        msgs = [{"role": m.get("role"), "content": str(m.get("content") or "")[:6000]} for m in (data.get("messages") or [])[-16:]
                if isinstance(m, dict) and m.get("role") in ("user", "assistant") and str(m.get("content") or "").strip()]
        if not msgs or msgs[-1]["role"] != "user":
            return self.send(400, {"error": "Write a question first."})
        if not app.limiter.take(owner, "chats", cfg.chats_per_day):
            return self.send(429, {"error": "You have used today's %d questions. Come back tomorrow." % cfg.chats_per_day})
        store = OwnedStore(app.store, owner)
        run_id = str(data.get("run_id") or "")
        try:
            store.load(run_id)
        except (KeyError, ValueError):
            run_id = None
        self.sse_start()
        ctx = ToolContext(settings=app.settings, store=store, session=Session(run_id),
                          on_event=lambda kind, p: self.sse("run.event", {"kind": kind}) if kind != "open.label" else None,
                          limits={"max_words": cfg.max_words, "max_rounds": 1, "max_targets": cfg.max_targets})
        registry = build_registry()
        plain_code = registry.tools["gt_code"].fn

        def guarded_code(args, tool_ctx):           # a coding started from the conversation counts as a run
            if not app.slots.acquire(blocking=False):
                return json.dumps({"error": "the demo is busy with other runs; try again in a minute"})
            try:
                if not app.limiter.take(owner, "runs", cfg.runs_per_day):
                    return json.dumps({"error": "today's run quota is used up"})
                out = plain_code(args, tool_ctx)
                if tool_ctx.session.active_run and tool_ctx.session.active_run != run_id:
                    self.sse("run.ready", {"run_id": tool_ctx.session.active_run})
                return out
            finally:
                app.slots.release()
        registry.tools["gt_code"].fn = guarded_code
        try:
            Agent(app.settings, registry, ctx).run(msgs, on_event=self.sse)
            app.log(owner, "chat answered")
        except LLMError as e:
            app.log(owner, "chat MODEL ERROR: %s" % e)
            self.sse("error", {"message": "The model service returned an error. Please try again in a minute."})
        except Exception:                           # noqa: BLE001
            app.log(owner, "chat CRASHED\n%s" % traceback.format_exc())
            self.sse("error", {"message": "The answer stopped because of an internal error."})
        self.sse("end", {})


def _hostname(value):
    """Host name of an Origin, a URL or a Host header, without scheme and port."""
    v = (value or "").strip().lower()
    if "://" in v:
        return urllib.parse.urlsplit(v).hostname or ""
    return urllib.parse.urlsplit("//" + v).hostname or "" if v else ""


def _http_json(url, form=None, token=None):
    headers = {"Accept": "application/json", "User-Agent": "coding-agent-demo"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = urllib.parse.urlencode(form).encode() if form else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=15) as r:
        return json.loads(r.read())


def _examples():
    ex = HERE.parent / "agent" / "examples" / "synthetic_interview.txt"
    return [{"id": "night-market", "title": "Night-market vendors and phone payments", "synthetic": True,
             "focus": "How night-market food vendors decide whether to accept mobile payments",
             "context": {"site": "Two food-stall vendors at a night market (fictional)", "method": "Semi-structured interview (synthetic example)"},
             "text": ex.read_text(encoding="utf-8").strip()}]


EXAMPLES = _examples()


def make_server(cfg=None, settings=None):
    cfg = cfg or Cfg()
    settings = settings or Settings.from_env()
    cfg.runs_dir.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    srv.daemon_threads = True
    srv.app = App(cfg, settings)
    return srv


def main():
    load_env_file(HERE / ".env")
    cfg, settings = Cfg(), Settings.from_env()
    problems = []
    if not settings.reasoner.configured:
        problems.append("REASONER_BASE_URL / REASONER_MODEL are not set: nothing can run")
    if not cfg.email_auth and not cfg.github_auth:
        problems.append("no sign-in method is enabled (set SMTP_* and/or GITHUB_CLIENT_* with DEMO_PUBLIC_URL): nobody can sign in")
    if cfg.ephemeral_secret:
        problems.append("DEMO_SECRET is not set: sessions end whenever the server restarts")
    if cfg.mail_mode == "console":
        problems.append("MAIL_MODE=console prints sign-in codes to this log: development only")
    if cfg.host not in ("127.0.0.1", "localhost", "::1") and not cfg.secure:
        problems.append("listening on %s without an https DEMO_PUBLIC_URL: put a TLS tunnel or proxy in front" % cfg.host)
    srv = make_server(cfg, settings)
    threading.Thread(target=srv.app.janitor, daemon=True).start()
    lst = access.load()
    print("demo on http://%s:%d   public url: %s" % (cfg.host, cfg.port, cfg.public_url or "(not set)"))
    print("sign-in: email code %s | GitHub %s" % ("on (%s)" % cfg.mail_mode if cfg.email_auth else "off", "on" if cfg.github_auth else "off"))
    print("access list: %d emails, %d domains, %d GitHub logins" % (len(lst["emails"]), len(lst["domains"]), len(lst["github"])))
    d = settings.describe()
    print("level 1: %s (%s) | levels 2-3: %s" % (d["open_coding"], srv.app.opencoder_status(), d["reasoner"]))
    for p in problems:
        print("WARNING: " + p)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
