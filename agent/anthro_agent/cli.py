"""Command line: run a coding, talk to the agent, inspect runs.

  python -m anthro_agent check                          show which models are configured
  python -m anthro_agent code -f interview.txt --focus "..."   run three-level coding
  python -m anthro_agent chat [--run RUN_ID]            talk to the agent about a coding
  python -m anthro_agent runs | tools
"""
import argparse
import json
import sys

from .agent import Agent
from .config import Settings
from .llm import LLMError
from .pipeline import encode
from .store import RunStore, Session
from .tools import ToolContext, build_registry


def _progress(kind, p):
    if kind == "start":
        m = p["models"]
        print("coding %d excerpts | open coding: %s%s | levels 2-3: %s" % (
            p["excerpts"], m["open_coding"], " (post-trained)" if m["open_coding_is_post_trained"] else "", m["reasoner"]), file=sys.stderr)
    elif kind == "open.start" and p.get("targets"):
        print("  level 1: %d target spans" % p["targets"], file=sys.stderr)
    elif kind == "open.done":
        print("  level 1: %d labels  %s" % (p.get("labels", 0), json.dumps(p.get("scorecard") or {})), file=sys.stderr)
    elif kind == "concepts.done":
        print("  level 2: %d concepts" % len(p["concepts"]), file=sys.stderr)
    elif kind == "axial.done":
        print("  level 2: %d categories, %d relations" % (len(p["categories"]), len(p["relations"])), file=sys.stderr)
    elif kind == "selective.done":
        print("  level 3: core category = %s" % p["core_category"].get("name"), file=sys.stderr)
    elif kind == "stage.error":
        print("  ! %s (%s): %s" % (p["stage"], p["model"], p["error"]), file=sys.stderr)
    elif kind == "round.done":
        print("  round %d: %s  score %.3f  %s" % (p["round"], "PASS" if p["passed"] else "gates failed", p["score"],
                                                 "; ".join(p["failed"])), file=sys.stderr)


def cmd_check(args, settings):
    d = settings.describe()
    print("open coding : %s%s" % (d["open_coding"] or "(not set)", "  [post-trained model]" if d["open_coding_is_post_trained"] else "  [general model; set OPENCODER_* to use the post-trained one]"))
    if d["open_coding_base"]:
        print("  compare with base model: " + d["open_coding_base"])
    print("levels 2-3  : %s" % (d["reasoner"] or "(not set: REASONER_BASE_URL / REASONER_MODEL)"))
    print("decoding    : %s" % (d["decoder"] or "(not set)"))
    print("language    : %s   lens: %s   runs: %s" % (settings.lang, settings.lens, settings.runs_dir))
    return 0 if settings.reasoner.configured else 1


def cmd_code(args, settings):
    text = open(args.file, encoding="utf-8", errors="ignore").read() if args.file else sys.stdin.read()
    units = [s.strip() for s in text.split("\n") if s.strip()] if args.units else text
    context = {k: v for k, v in (("research_question", args.question), ("site", args.site), ("method", args.method)) if v}
    res = encode(units, args.focus, settings=settings, max_rounds=args.rounds, context=context, compare=args.compare,
                 lang=args.lang, lens=args.lens, on_event=None if args.quiet else _progress)
    if not res.get("graph"):
        print("coding failed: %s" % res.get("reason"), file=sys.stderr)
        return 2
    store = RunStore(settings.runs_dir)
    run_id = store.new_id()
    store.save(run_id, res)
    g, r = res["graph"], res["rubric"]
    if args.json:
        print(json.dumps({"run_id": run_id, "graph": g, "rubric": r}, ensure_ascii=False, indent=2))
        return 0
    print("\nrun %s  [%s, round %d of %d, score %.3f]" % (run_id, res["status"], res["round"], res["rounds"], res["score"]))
    print("compression  %s" % r["compression"])
    print("core         %s" % g["core_category"].get("name"))
    for c in g["categories"]:
        print("  [%-3s] %s" % (c["c6_slot"], c["name"]))
    for s in (g["theory"].get("propositions") or [])[:6]:
        print("  - " + s)
    if r["gates_failed"]:
        print("gates failed: " + "; ".join(r["gates_failed"]))
    print("saved to %s" % (settings.runs_dir / run_id))
    return 0


def cmd_chat(args, settings):
    store = RunStore(settings.runs_dir)
    session = Session(args.run or store.latest_id())
    ctx = ToolContext(settings=settings, store=store, session=session, on_event=None if args.quiet else _progress)
    agent = Agent(settings, build_registry(), ctx)
    print("agent ready. %s  (empty line or Ctrl-D to quit)" % ("Loaded run " + session.active_run if session.active_run else "No coding loaded yet."))
    history = []

    def show(kind, p):
        if kind == "tool.call":
            print("  -> %s(%s)" % (p["name"], ", ".join("%s=%r" % kv for kv in p["arguments"].items())), file=sys.stderr)
    while True:
        try:
            msg = input("\nyou> ").strip()
        except EOFError:
            break
        if not msg:
            break
        history.append({"role": "user", "content": msg})
        answer = agent.run(history, on_event=show)
        history.append({"role": "assistant", "content": answer})
        print("\nagent> " + answer)
    return 0


def cmd_runs(args, settings):
    for m in RunStore(settings.runs_dir).list():
        print("%s  %-11s %.3f  %s" % (m["run_id"], m.get("status"), m.get("score") or 0, m.get("core_category")))
    return 0


def cmd_tools(args, settings):
    for t in build_registry().tools.values():
        print("%-22s %s" % (t.name, t.description))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="anthro_agent", description="Grounded-theory coding agent for interview and ethnographic material.")
    ap.add_argument("--env-file", help="path to a .env file with the model endpoints")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="show the configured models")
    c = sub.add_parser("code", help="run three-level coding on a text")
    c.add_argument("--focus", required=True, help="research focus Y")
    c.add_argument("-f", "--file", help="transcript file (default: stdin)")
    c.add_argument("--units", action="store_true", help="treat each line as one quote instead of a transcript")
    c.add_argument("--rounds", type=int, default=1, help="coding rounds; the best-scoring round is kept (default 1)")
    c.add_argument("--lang", choices=["en", "zh"], help="language of concepts, categories and theory")
    c.add_argument("--lens", choices=["general", "market"], help="decoding lens")
    c.add_argument("--compare", action="store_true", help="also code each span with the base model (needs OPENCODER_BASE_MODEL)")
    c.add_argument("--question", help="research question, for the context card")
    c.add_argument("--site", help="site and participants, for the context card")
    c.add_argument("--method", help="how the data were collected, for the context card")
    c.add_argument("--json", action="store_true", help="print the full graph and rubric as JSON")
    c.add_argument("--quiet", action="store_true")
    ch = sub.add_parser("chat", help="talk to the agent")
    ch.add_argument("--run", help="run id to load (default: the latest run)")
    ch.add_argument("--quiet", action="store_true")
    sub.add_parser("runs", help="list saved runs")
    sub.add_parser("tools", help="list the agent's tools")
    args = ap.parse_args(argv)
    try:
        settings = Settings.from_env(args.env_file)
        if args.cmd in ("code", "chat") and not settings.reasoner.configured:
            print("REASONER_BASE_URL and REASONER_MODEL are not set (see .env.example).", file=sys.stderr)
            return 1
        return {"check": cmd_check, "code": cmd_code, "chat": cmd_chat, "runs": cmd_runs, "tools": cmd_tools}[args.cmd](args, settings)
    except (LLMError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
