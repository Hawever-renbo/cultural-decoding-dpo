"""Run store: each coding run is a folder with graph.json, rubric.json and meta.json."""
import json
import re
import secrets
import time
from pathlib import Path

RUN_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")


class RunStore:
    def __init__(self, root):
        self.root = Path(root)

    def new_id(self):
        return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)

    def _dir(self, run_id):
        if not RUN_ID_RE.match(run_id or ""):
            raise ValueError("invalid run id")
        return self.root / run_id

    def save(self, run_id, result, meta=None):
        d = self._dir(run_id)
        d.mkdir(parents=True, exist_ok=True)
        graph = result.get("graph") or {}
        info = {"run_id": run_id, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "status": result.get("status"),
                "round": result.get("round"), "rounds": result.get("rounds"), "score": result.get("score"),
                "focus": graph.get("focus", ""), "models": graph.get("models", {}),
                "core_category": (graph.get("core_category") or {}).get("name", ""), **(meta or {})}
        for name, obj in (("graph.json", graph), ("rubric.json", result.get("rubric") or {}), ("meta.json", info)):
            (d / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return info

    def load(self, run_id):
        d = self._dir(run_id)
        if not (d / "graph.json").is_file():
            raise KeyError("no such run: " + run_id)
        return {name: json.loads((d / (name + ".json")).read_text(encoding="utf-8")) for name in ("graph", "rubric", "meta")}

    def list(self):
        if not self.root.is_dir():
            return []
        out = []
        for d in sorted(self.root.iterdir(), reverse=True):
            if RUN_ID_RE.match(d.name) and (d / "meta.json").is_file():
                out.append(json.loads((d / "meta.json").read_text(encoding="utf-8")))
        return out

    def latest_id(self):
        runs = self.list()
        return runs[0]["run_id"] if runs else None


class Session:
    """What one conversation is looking at: its active run."""

    def __init__(self, active_run=None):
        self.active_run = active_run
