"""Offline tests: python -m unittest discover -s tests   (no network, no model; a rule-based mock stands in)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import mock_server  # noqa: E402
from anthro_agent import checks, llm, opencoder, pipeline, segment  # noqa: E402
from anthro_agent import prompts as P  # noqa: E402
from anthro_agent.agent import Agent  # noqa: E402
from anthro_agent.config import Endpoint, Settings  # noqa: E402
from anthro_agent.store import RunStore, Session  # noqa: E402
from anthro_agent.tools import ToolContext, build_registry  # noqa: E402

EXAMPLE = (Path(__file__).resolve().parent.parent / "examples" / "synthetic_interview.txt").read_text(encoding="utf-8")
FOCUS = "How night-market food vendors decide whether to accept mobile payments"


def settings(url, post_trained=True, **kw):
    ep = Endpoint(base_url=url, model="general", max_tokens=8000)
    oc = Endpoint(base_url=url if post_trained else "", model="opencoding", max_tokens=512,
                  extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    return Settings(reasoner=ep, decoder=ep, opencoder=oc, opencoder_base_model="base", opencoder_concurrency=4,
                    runs_dir=Path(tempfile.mkdtemp()), **kw)


class Deterministic(unittest.TestCase):
    def test_turns_and_interviewer_filter(self):
        turns = segment.parse_turns(EXAMPLE)
        self.assertEqual(len(turns), 16)
        ex = segment.participant_excerpts(turns)
        self.assertEqual({e["role"] for e in ex}, {"Rosa", "Tomas"})
        self.assertEqual(len(ex), 8)

    def test_targets_are_verbatim_spans(self):
        for e in segment.participant_excerpts(segment.parse_turns(EXAMPLE)):
            spans = segment.target_spans(e["text"], 6, 45)
            self.assertTrue(spans)
            for s in spans:
                self.assertIn(s, e["text"])

    def test_plan_matches_training_format(self):
        ex = segment.participant_excerpts(segment.parse_turns(EXAMPLE))
        jobs, dropped = opencoder.plan(ex, FOCUS, {"site": "A night market"})
        self.assertEqual(dropped, 0)
        user = jobs[0]["user"]
        self.assertTrue(user.startswith("Research question: Not stated in the provided text.\nSite and participants: A night market\n"))
        self.assertIn("\nThis section of the study: " + FOCUS + "\n\n[1] ", user)
        self.assertTrue(user.endswith("»\n\nWrite ONE code for the target excerpt."))
        self.assertLessEqual(max(len(j["excerpts"]) for j in jobs), 5)
        _, dropped = opencoder.plan(ex, FOCUS, max_targets=3)
        self.assertGreater(dropped, 0)

    def test_code_checks(self):
        ex = {2: "I prefer working with hawkers, but the checkoff services at the cooperative are also good."}
        ok = checks.check_code("prefer working with hawkers, but the checkoff services are also good — [2] «I prefer working with hawkers, but the checkoff services at the cooperative are also good.»", ex, (2, ex[2]))
        self.assertTrue(ok["format_ok"] and ok["verbatim_ok"] and ok["target_exact"])
        self.assertEqual(ok["outside_words"], [])
        bad = checks.check_code("<code>distrust of formal institutions because of delays</code> — [2] «I prefer working with hawkers»\nWait, I should not add words.", ex)
        self.assertTrue(bad["markup"] and bad["extra_text"])
        self.assertIn("distrust", bad["outside_words"])
        self.assertEqual(bad["imposed_connectives"], ["because"])
        self.assertFalse(checks.check_code("I prefer hawkers — [2] «I like the hawkers best»", ex)["verbatim_ok"])
        self.assertFalse(checks.check_code("no code here", ex)["format_ok"])

    def test_truncated_json_is_healed(self):
        self.assertEqual(llm.parse_list_json('[{"a": 1}, {"b": 2}, {"c": '), [{"a": 1}, {"b": 2}])
        self.assertEqual(llm.parse_json('```json\n{"a": {"b": 1}}\n```'), {"a": {"b": 1}})
        self.assertIsNone(llm.parse_list_json("nothing"))

    def test_gates(self):
        cats = [{"name": "Hiding takings from the market office, part %d" % i, "c6_slot": s, "concepts": ["c%d" % i]} for i, s in enumerate(P.C6_SLOTS)]
        cats[0]["concepts"] += ["c6", "c7"]
        g = {"labels": [{"label": "l", "concept": "c0"}] * 12, "concepts": [{"concept": "c%d" % i} for i in range(8)],
             "categories": cats, "core_category": {"name": "Keeping the money visible"},
             "relations": [{"from": c["name"], "to": "Keeping the money visible", "type": "abstracts_to"} for c in cats]}
        ib = pipeline.ib_metrics(g, 1000)
        self.assertEqual(ib["reachability"], 1.0)
        self.assertEqual(pipeline.gates(g, ib), (True, []))
        g["categories"][0]["name"] = "Coping strategies"
        g["categories"][1]["c6_slot"] = "P"
        g["relations"][2]["type"] = "vibes"
        failed = " | ".join(pipeline.gates(g, pipeline.ib_metrics(g, 1000))[1])
        for gate in ("G3", "G4 paradigm incomplete, missing: CC", "G8"):
            self.assertIn(gate, failed)
        g["categories"] = g["categories"][:3]
        self.assertIn("G9 number of categories", " | ".join(pipeline.gates(g)[1]))

    def test_unsupported_quotes(self):
        src = "Cash I can count at night, but the phone money, I only see a number."
        self.assertEqual(pipeline.unsupported_quotes({"surface": 'She says "Cash I can count at night" and moves on.'}, src), [])
        self.assertEqual(len(pipeline.unsupported_quotes({"surface": 'She says "phones make me feel deeply insecure" often.'}, src)), 1)


class WithMockModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.url = mock_server.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.srv.state.clear()
        self.srv.state["calls"] = []

    def test_full_run_with_post_trained_open_coding(self):
        events = []
        res = pipeline.encode(EXAMPLE, FOCUS, settings=settings(self.url), compare=True, on_event=lambda k, p: events.append(k))
        g, r = res["graph"], res["rubric"]
        self.assertEqual(res["status"], "passed", r["gates_failed"])
        self.assertTrue(g["models"]["open_coding_is_post_trained"])
        self.assertEqual(g["models"]["open_coding"], "opencoding")
        src = " ".join(e["text"] for e in g["excerpts"])
        for l in g["labels"]:                       # every stored quote is really in the transcript
            self.assertTrue(checks.is_verbatim(l["evidence"], src))
            self.assertEqual(l["checks"]["outside_words"], [])
            self.assertTrue(l["base"]["checks"]["markup"])
            self.assertIn("financial", l["base"]["checks"]["outside_words"])
        self.assertEqual(g["open_coding"]["scorecard"]["outside_word_labels"], 0.0)
        self.assertEqual(g["open_coding"]["base"]["scorecard"]["outside_word_labels"], 1.0)
        self.assertEqual(r["orphan_labels"], 0)
        self.assertEqual(r["fidelity_T1T2"], 1.0)
        self.assertEqual(r["decode_unsupported_quotes"], [])
        self.assertTrue(any("from decoding" in s for s in g["theory"]["storyline"]))
        self.assertEqual(events[0], "start")
        self.assertEqual(events[-1], "done")
        for k in ("open.start", "open.label", "open.done", "concepts.done", "axial.done", "selective.done", "decode.done", "round.done"):
            self.assertIn(k, events)
        oc_calls = [c for c in self.srv.state["calls"] if c["model"] == "opencoding"]
        self.assertTrue(oc_calls and all(c["extra"] == {"enable_thinking": False} for c in oc_calls))
        self.assertTrue(all(c["extra"] is None for c in self.srv.state["calls"] if c["model"] == "general"))

    def test_rounds_keep_the_best_score_and_reuse_labels(self):
        self.srv.state["drop_concepts"] = True      # half of the concepts are left out of every category
        res = pipeline.encode(EXAMPLE, FOCUS, settings=settings(self.url, telemetry=False), max_rounds=2)
        self.assertEqual(res["rounds"], 2)
        self.assertLess(res["rubric"]["fidelity_T1T2"], 1.0)
        n_targets = res["graph"]["open_coding"]["targets"]
        self.assertEqual(sum(1 for c in self.srv.state["calls"] if c["model"] == "opencoding"), n_targets)   # coded once
        self.assertEqual(res["rubric"]["telemetry"], {"semantic_contribution": None, "decode_self_score": None})

    def test_invented_quote_in_decoding_is_flagged(self):
        self.srv.state["fake_quote"] = "the phone makes me feel modern and proud of my stall"
        res = pipeline.encode(EXAMPLE, FOCUS, settings=settings(self.url, telemetry=False))
        self.assertEqual(len(res["rubric"]["decode_unsupported_quotes"]), 1)
        self.assertIn("decode_unsupported_quotes:1", res["rubric"]["failure_modes"])

    def test_general_model_fallback_and_zh(self):
        res = pipeline.encode(EXAMPLE, FOCUS, settings=settings(self.url, post_trained=False), lang="en")
        g = res["graph"]
        self.assertFalse(g["models"]["open_coding_is_post_trained"])
        self.assertEqual(g["models"]["open_coding"], "general")
        self.assertTrue(g["labels"] and all(l["turn_id"] is not None for l in g["labels"]))
        self.assertEqual({c["model"] for c in self.srv.state["calls"]}, {"general"})

    def test_bad_request_surfaces_instead_of_retrying(self):
        self.srv.state["http_status"] = 401
        with self.assertRaises(llm.LLMError):
            pipeline.encode(EXAMPLE, FOCUS, settings=settings(self.url))

    def test_tools_and_agent_loop(self):
        s = settings(self.url, telemetry=False)
        store = RunStore(s.runs_dir)
        ctx = ToolContext(settings=s, store=store, session=Session(), limits={"max_words": 2000, "max_rounds": 1})
        reg = build_registry()
        self.assertIn("no coding exists yet", reg.call("gt_coding_overview", {}, ctx))
        self.assertIn("too long", reg.call("gt_code", {"text": "word " * 2001, "focus": FOCUS}, ctx))
        out = json.loads(reg.call("gt_code", {"text": EXAMPLE, "focus": FOCUS, "max_rounds": 5}, ctx))
        self.assertEqual(out["status"], "passed")
        self.assertEqual(ctx.session.active_run, out["run_id"])
        ov = json.loads(reg.call("gt_coding_overview", {}, ctx))
        self.assertEqual(ov["counts"]["categories"], 6)
        cat = json.loads(reg.call("gt_coding_categories", {}, ctx))["categories"][0]["name"]
        tr = json.loads(reg.call("gt_coding_trace", {"name": cat[:30]}, ctx))
        quote = tr["trace"][0]["concepts"][0]["labels"][0]["quote"]
        self.assertIn(quote, EXAMPLE)
        self.assertIn("error", json.loads(reg.call("gt_coding_trace", {"name": "zzz"}, ctx)))
        self.assertEqual(json.loads(reg.call("gt_coding_labels", {"query": "drawer", "limit": 2}, ctx))["count"], 2)
        for name in ("gt_coding_core", "gt_coding_concepts", "gt_coding_relations", "gt_coding_decode", "gt_coding_rubric"):
            self.assertNotIn('"error"', reg.call(name, {}, ctx)[:20], name)
        for mode in ("native", "text"):
            seen = []
            ans = Agent(s, reg, ctx, tool_mode=mode).run([{"role": "user", "content": "What is the core category?"}],
                                                          on_event=lambda k, p: seen.append(k))
            self.assertEqual(ans, "The core category is: Accepting phone payments only as far as the vendor can still see her money.")
            self.assertEqual(seen, ["tool.call", "tool.result", "answer"])
        with self.assertRaises(ValueError):
            store.load("../etc")


if __name__ == "__main__":
    unittest.main()
