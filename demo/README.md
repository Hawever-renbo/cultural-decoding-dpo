# demo/: the agent with the post-trained model, by invitation

A small web app that runs [`../agent/`](../agent/) with the post-trained open-coding model at level 1. Visitors paste interview text and a research focus, watch the three levels come in, compare the post-trained model with the untrained base model on their own text, and ask the agent about the result.

Standard library only. One process, no database.

## Who gets in

The demo is closed by default. `access.json` lists who may sign in, by three kinds of rule:

| Rule | Who it lets in | How they sign in |
|---|---|---|
| `email` | one address | a 6-digit code sent to that address |
| `domain` | every address at a domain | the same |
| `github` | one GitHub account | "Sign in with GitHub" |

A GitHub account is also let in if one of its *verified* addresses matches an `email` or `domain` rule.

```bash
python3 access.py add domain example.org
python3 access.py add email alice@example.com
python3 access.py add github some-login
python3 access.py list
python3 access.py remove email alice@example.com
```

The file is read on every request: adding someone works at once, and removing someone ends their session. It is git-ignored because it holds people's addresses.

What the gate does and does not do:
- A code is sent only to listed addresses, and the page answers the same way whether or not an address is listed.
- Codes last 10 minutes, work once, and allow 5 guesses. Requests are rate-limited per address and per visitor.
- Sessions are signed cookies (7 days). Each person sees only their own runs.
- The model endpoints are known to the server only. The open-coding model stays on localhost.
- Per person and per day: 12 runs and 60 questions by default; 1,500 words per run. Runs are deleted after 24 hours.

## Run it

On the machine that serves the post-trained model:

```bash
# 1. the model: base + LoRA adapter under vLLM, on 127.0.0.1:8000 as "opencoding" (and "base")
bash scripts/serve_opencoding.sh start          # from the training repository

# 2. the demo
cd demo
cp .env.example .env                            # fill in: DEMO_SECRET, DEMO_PUBLIC_URL, SMTP_*, REASONER_*
python3 access.py add domain example.org
python3 server.py                               # listens on 127.0.0.1:8787

# 3. a public https address in front of 127.0.0.1:8787 (any TLS tunnel or reverse proxy)
```

`server.py` prints what is configured and warns about anything missing. When the model service is stopped, the page says the post-trained model is offline and offers to run level 1 on the general model instead, labelled as such.

**Mail.** Any SMTP account works. With Gmail: turn on 2-step verification, create an app password, and set `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`.

**GitHub sign-in (optional).** Create an OAuth app (GitHub → Settings → Developer settings → OAuth Apps) with the callback `<DEMO_PUBLIC_URL>/auth/github/callback`, and set `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`. The app asks only for `user:email`.

## Tests

```bash
python3 -m unittest discover -s demo/tests      # from the repository root; offline
```

They cover the gate (listed and unlisted addresses, single-use codes, guess and rate limits, forged cookies, cross-site requests, GitHub sign-in, removal ending a session), run streaming and privacy between visitors, quotas, the offline-model path, and that upstream errors are not shown to visitors.

## Local development

```bash
python3 agent/tests/mock_server.py 8011 &       # a rule-based stand-in for the models
cd demo && MAIL_MODE=console DEMO_SECRET=dev REASONER_BASE_URL=http://127.0.0.1:8011/v1 REASONER_MODEL=general \
  OPENCODER_BASE_URL=http://127.0.0.1:8011/v1 OPENCODER_BASE_MODEL=base python3 server.py
```

`MAIL_MODE=console` prints sign-in codes to the server log instead of mailing them. The mock's answers are canned; they show the plumbing, not how any model behaves.
