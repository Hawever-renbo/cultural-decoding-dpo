"""Settings. Every model is reached through an OpenAI-compatible chat-completions endpoint set by environment
variables, so the agent does not depend on any particular provider or host.

  REASONER_*    levels 2-3, the decode step and the conversation loop          (required)
  OPENCODER_*   level 1, the post-trained open-coding model                    (optional)
  DECODER_*     the thick-description step, if it should use another model     (optional)
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
ROOT_DIR = PKG_DIR.parent


def load_env_file(path=None):
    """Read KEY=VALUE lines into os.environ. Variables that are already set win. Returns the path read, or None."""
    candidates = [path] if path else [os.environ.get("AGENT_ENV_FILE"), Path.cwd() / ".env", ROOT_DIR / ".env"]
    for cand in candidates:
        if not cand:
            continue
        p = Path(cand)
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if key.startswith("export "):
                key = key[7:].strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            os.environ.setdefault(key, val)
        return p
    return None


def _json_env(name, default=None):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return dict(default or {})
    try:
        val = json.loads(raw)
    except ValueError as e:
        raise ValueError(f"{name} must be a JSON object: {e}") from None
    if not isinstance(val, dict):
        raise ValueError(f"{name} must be a JSON object")
    return val


def _int_env(name, default):
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


@dataclass
class Endpoint:
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    extra_body: dict = field(default_factory=dict)
    max_tokens: int = 8000     # ceiling for one completion
    min_tokens: int = 0        # floor; reasoning models spend part of the budget before the answer
    timeout: int = 300

    @property
    def configured(self):
        return bool(self.base_url and self.model)

    @property
    def url(self):
        u = self.base_url.rstrip("/")
        return u if u.endswith("/chat/completions") else u + "/chat/completions"

    @classmethod
    def from_env(cls, prefix, **defaults):
        return cls(
            base_url=os.environ.get(prefix + "_BASE_URL", "").strip(),
            model=os.environ.get(prefix + "_MODEL", defaults.get("model", "")).strip(),
            api_key=os.environ.get(prefix + "_API_KEY", "").strip(),
            extra_body=_json_env(prefix + "_EXTRA_BODY", defaults.get("extra_body")),
            max_tokens=_int_env(prefix + "_MAX_TOKENS", defaults.get("max_tokens", 8000)),
            min_tokens=_int_env(prefix + "_MIN_TOKENS", defaults.get("min_tokens", 0)),
            timeout=_int_env(prefix + "_TIMEOUT", defaults.get("timeout", 300)),
        )


@dataclass
class Settings:
    reasoner: Endpoint = field(default_factory=Endpoint)
    decoder: Endpoint = field(default_factory=Endpoint)
    opencoder: Endpoint = field(default_factory=Endpoint)
    opencoder_base_model: str = ""      # served name of the untrained base model, for side-by-side comparison
    opencoder_concurrency: int = 6
    lang: str = "en"                    # language of concepts, categories, theory: en | zh
    lens: str = "general"               # decode lens: general | market
    telemetry: bool = True              # LLM self-ratings, recorded but never used to select or gate on score
    runs_dir: Path = field(default_factory=lambda: Path.home() / ".anthro_agent" / "runs")

    @classmethod
    def from_env(cls, env_file=None):
        load_env_file(env_file)
        reasoner = Endpoint.from_env("REASONER", max_tokens=24000, min_tokens=4096)
        decoder = Endpoint.from_env("DECODER", max_tokens=24000, min_tokens=4096)
        if not decoder.configured:
            decoder = reasoner
        # The open-coding model is served with thinking off and a short context, as it was trained and evaluated.
        opencoder = Endpoint.from_env(
            "OPENCODER", model="opencoding", max_tokens=512, timeout=120,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        lang = os.environ.get("AGENT_LANG", "en").strip().lower() or "en"
        lens = os.environ.get("AGENT_LENS", "general").strip().lower() or "general"
        if lang not in ("en", "zh"):
            raise ValueError("AGENT_LANG must be en or zh")
        if lens not in ("general", "market"):
            raise ValueError("AGENT_LENS must be general or market")
        runs = os.environ.get("AGENT_RUNS_DIR", "").strip()
        return cls(
            reasoner=reasoner, decoder=decoder, opencoder=opencoder,
            opencoder_base_model=os.environ.get("OPENCODER_BASE_MODEL", "").strip(),
            opencoder_concurrency=max(1, _int_env("OPENCODER_CONCURRENCY", 6)),
            lang=lang, lens=lens,
            telemetry=os.environ.get("AGENT_TELEMETRY", "1").strip() not in ("0", "false", "no", "off"),
            runs_dir=Path(runs).expanduser() if runs else Path.home() / ".anthro_agent" / "runs",
        )

    def describe(self):
        """Model names only (no URLs or keys), for display and for the run record."""
        return {
            "open_coding": self.opencoder.model if self.opencoder.configured else self.reasoner.model,
            "open_coding_is_post_trained": self.opencoder.configured,
            "open_coding_base": self.opencoder_base_model if self.opencoder.configured else "",
            "reasoner": self.reasoner.model,
            "decoder": self.decoder.model,
        }
