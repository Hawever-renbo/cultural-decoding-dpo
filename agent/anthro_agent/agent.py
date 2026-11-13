"""The agent loop: a chat model that can call the coding tools until it has an answer.

Two tool protocols, because OpenAI-compatible servers differ:
  native  the request carries `tools`, the model answers with tool_calls         (most hosted APIs)
  text    tools are described in the system prompt and the model writes
          <tool_call>{"name": ..., "arguments": {...}}</tool_call>               (any chat model)
"""
import json
import os

from .config import PKG_DIR
from .llm import chat


def system_prompt():
    return (PKG_DIR / "prompts" / "agent_system.md").read_text(encoding="utf-8").strip()


TEXT_PROTOCOL = """

# Calling tools
You may call one or more tools. To call a tool, write on its own:
<tool_call>{"name": "<tool name>", "arguments": {<arguments as JSON>}}</tool_call>
The result comes back inside <tool_response></tool_response>. Call tools first; write your answer once you have what you need.
Available tools (JSON schema):
"""


class Agent:
    def __init__(self, settings, registry, ctx, *, max_steps=8, tool_mode=None):
        self.settings, self.registry, self.ctx = settings, registry, ctx
        self.max_steps = max_steps
        self.tool_mode = (tool_mode or os.environ.get("AGENT_TOOL_MODE", "native")).strip().lower()
        if self.tool_mode not in ("native", "text"):
            raise ValueError("AGENT_TOOL_MODE must be native or text")

    def run(self, history, on_event=None):
        """history: [{"role": "user"|"assistant", "content": str}], ending with the user's message.
        Returns the final answer. Emits ("tool.call" | "tool.result" | "answer", payload) while working."""
        emit = on_event or (lambda kind, payload: None)
        native = self.tool_mode == "native"
        system = system_prompt()
        if self.ctx.session.active_run:
            system += "\n\nA coding is loaded (run %s). Read it with the tools." % self.ctx.session.active_run
        else:
            system += "\n\nNo coding is loaded yet."
        if not native:
            system += TEXT_PROTOCOL + json.dumps(self.registry.specs(), ensure_ascii=False)
        messages = [{"role": "system", "content": system}] + [
            {"role": m["role"], "content": str(m.get("content", ""))} for m in history if m.get("role") in ("user", "assistant")]
        for _ in range(self.max_steps):
            out = chat(self.settings.reasoner, messages, temperature=0.3, tools=self.registry.specs() if native else None)
            calls = out["tool_calls"]
            if not calls:
                answer = out["content"] or "The model returned no answer (%s)." % out.get("error", "empty completion")
                emit("answer", {"text": answer})
                return answer
            if native:
                messages.append({"role": "assistant", "content": out["content"] or None, "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}
                    for c in calls]})
            else:
                messages.append({"role": "assistant", "content": (out["content"] + "\n" if out["content"] else "") + "\n".join(
                    "<tool_call>%s</tool_call>" % json.dumps({"name": c["name"], "arguments": c["arguments"]}, ensure_ascii=False) for c in calls)})
            results = []
            for c in calls:
                emit("tool.call", {"name": c["name"], "arguments": {k: (v if len(str(v)) <= 200 else str(v)[:200] + "…") for k, v in c["arguments"].items()}})
                result = self.registry.call(c["name"], c["arguments"], self.ctx)
                emit("tool.result", {"name": c["name"], "chars": len(result), "error": result.startswith('{"error"')})
                results.append((c, result))
            if native:
                messages.extend({"role": "tool", "tool_call_id": c["id"], "content": r} for c, r in results)
            else:
                messages.append({"role": "user", "content": "\n".join("<tool_response>\n%s\n</tool_response>" % r for _, r in results)})
        answer = "I stopped after %d tool steps without reaching an answer. Please narrow the question." % self.max_steps
        emit("answer", {"text": answer})
        return answer
