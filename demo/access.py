#!/usr/bin/env python3
"""Who may use the demo. The list lives in a JSON file next to the server and is read on every request, so a
change takes effect at once and removing someone also ends their session.

  python3 access.py list
  python3 access.py add email  alice@example.org     one address (signs in with an emailed code)
  python3 access.py add domain example.org           every address at this domain
  python3 access.py add github some-login            a GitHub account (signs in with GitHub)
  python3 access.py remove email alice@example.org
  python3 access.py check alice@example.org

The file is git-ignored: it holds people's addresses and must not be committed.
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s.]{2,}$")
KINDS = {"email": "emails", "domain": "domains", "github": "github"}


def default_path():
    return Path(os.environ.get("DEMO_ACCESS_FILE") or Path(__file__).resolve().parent / "access.json")


def norm_email(value):
    v = (value or "").strip().lower()
    return v if len(v) <= 254 and EMAIL_RE.match(v) else ""


def load(path=None):
    p = Path(path or default_path())
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {key: sorted({str(x).strip().lower() for x in data.get(key) or [] if str(x).strip()}) for key in KINDS.values()}


def save(data, path=None):
    p = Path(path or default_path())
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".access-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def email_rule(email, data=None):
    """The rule that lets this address in ("email:..." or "domain:..."), or "" if none does."""
    e = norm_email(email)
    if not e:
        return ""
    data = data if data is not None else load()
    if e in data["emails"]:
        return "email:" + e
    domain = e.rsplit("@", 1)[1]
    return "domain:" + domain if domain in data["domains"] else ""


def github_rule(login, verified_emails=(), data=None):
    """The rule that lets this GitHub account in: its login, or one of its verified addresses."""
    data = data if data is not None else load()
    lg = (login or "").strip().lower()
    if lg and lg in data["github"]:
        return "github:" + lg
    for e in verified_emails:
        rule = email_rule(e, data)
        if rule:
            return rule
    return ""


def rule_still_holds(rule, data=None):
    """Re-check a session's rule against the current list."""
    data = data if data is not None else load()
    kind, _, value = (rule or "").partition(":")
    return bool(value) and kind in KINDS and value in data[KINDS[kind]]


def main(argv):
    if len(argv) >= 1 and argv[0] == "list":
        data = load()
        for kind, key in KINDS.items():
            for v in data[key]:
                print("%-7s %s" % (kind, v))
        if not any(data.values()):
            print("(empty: nobody can sign in)")
        return 0
    if len(argv) == 2 and argv[0] == "check":
        rule = email_rule(argv[1])
        print("allowed by " + rule if rule else "not allowed")
        return 0 if rule else 1
    if len(argv) == 3 and argv[0] in ("add", "remove") and argv[1] in KINDS:
        kind, value = argv[1], argv[2].strip().lower().lstrip("@")
        if kind == "email" and not norm_email(value):
            print("not an email address: " + value, file=sys.stderr)
            return 2
        if kind == "domain" and not re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", value):
            print("not a domain: " + value, file=sys.stderr)
            return 2
        if kind == "github" and not re.match(r"^[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?$", value):
            print("not a GitHub login: " + value, file=sys.stderr)
            return 2
        data = load()
        items = set(data[KINDS[kind]])
        (items.add if argv[0] == "add" else items.discard)(value)
        data[KINDS[kind]] = sorted(items)
        save(data)
        print("%s %s %s" % ("added" if argv[0] == "add" else "removed", kind, value))
        return 0
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
