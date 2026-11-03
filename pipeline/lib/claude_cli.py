"""Z6 直出：Claude CLI 调用封装。逻辑照抄 合成数据线/lib/claude_cli.py（D-233 版：任何订阅额度文字 → rc=75 退出，续跑靠盘缓存）。
差别：缓存、台账、STOP 文件都落在 Z6_直出/out/；多一道调用锁——Z6_直出/CALLS_LOCKED 存在、或没设 Z6_ALLOW_CALLS=1 时，任何真调用直接报错（缓存命中照常）。
调用形态：claude -p --model M --effort E --tools "" --system-prompt S --json-schema J --output-format json --no-session-persistence --strict-mcp-config，提示词走 stdin，cwd 为空临时目录。"""
import hashlib, json, os, re, subprocess, tempfile, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
CACHE = OUT / "cache_claude"
LEDGER = OUT / "claude_ledger.jsonl"
LOCK_FILE = ROOT / "CALLS_LOCKED"
STOP_FILE = OUT / "STOPPED_ON_LIMIT.txt"
_lock = threading.Lock()
_CWD = tempfile.mkdtemp(prefix="z6_claude_cwd_")
MODELS = {"sonnet", "opus", "haiku"}
EFFORTS = {"low", "medium", "high"}
QUOTA_RE = re.compile(r"(session|usage|weekly|daily|monthly|opus|sonnet|5-hour|five-hour)\s+limit|hit your (\w+ )?limit"
                      r"|limit (will )?resets?|out of (extra )?usage", re.I)


class CallsLocked(RuntimeError):
    pass


def quota_hit(err):
    return bool(err) and bool(QUOTA_RE.search(err))


def _key(model, effort, system, user, schema, rep):
    return hashlib.sha1(json.dumps([model, effort, system, user, schema, rep], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def cache_path(model, effort, system, user, schema, rep=0):
    k = _key(model, effort, system, user, schema, rep)
    return CACHE / f"{model}-{effort}" / k[:2] / f"{k}.json"


def calls_allowed():
    return (not LOCK_FILE.exists()) and os.environ.get("Z6_ALLOW_CALLS") == "1"


def _ledger(row):
    with _lock:
        OUT.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def claude_json(system, user, schema, model="sonnet", effort="medium", rep=0, tag="", timeout=900):
    """返回 (parsed 或 None, meta)。碰额度 → 写 STOP 文件、os._exit(75)。"""
    assert model in MODELS and effort in EFFORTS, (model, effort)
    cp = cache_path(model, effort, system, user, schema, rep)
    if cp.exists():
        rec = json.loads(cp.read_text(encoding="utf-8"))
        if rec.get("parsed") is not None:
            return rec["parsed"], {**rec.get("meta", {}), "cached": True}
    if not calls_allowed():
        raise CallsLocked("模型调用被锁：删除 CALLS_LOCKED 并设 Z6_ALLOW_CALLS=1 才能调用（须 PI 确认）")
    cmd = ["claude", "-p", "--model", model, "--effort", effort, "--tools", "", "--system-prompt", system,
           "--json-schema", json.dumps(schema), "--output-format", "json", "--no-session-persistence", "--strict-mcp-config"]
    parsed, meta = None, {}
    for attempt in range(3):
        t0, err = time.time(), None
        try:
            p = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=timeout, cwd=_CWD)
            out = json.loads(p.stdout) if p.stdout.strip().startswith("{") else {}
            if not out:
                err = f"rc={p.returncode} stderr={p.stderr[:300]} stdout={p.stdout[:300]}"
            elif out.get("is_error"):
                err = f"is_error: {str(out.get('result'))[:300]}"
            parsed = out.get("structured_output") if out and not out.get("is_error") else None
            meta = dict(cost=out.get("total_cost_usd"), duration_ms=out.get("duration_ms"), model_id=",".join(out.get("modelUsage") or {}),
                        usage={k: v for k, v in (out.get("usage") or {}).items()
                               if k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")})
        except subprocess.TimeoutExpired:
            err = f"timeout {timeout}s"
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
        _ledger(dict(tag=tag, model=model, effort=effort, rep=rep, attempt=attempt, ok=parsed is not None, err=err,
                     wall_s=round(time.time() - t0, 2), **meta, at=time.strftime("%Y-%m-%dT%H:%M:%S")))
        if parsed is not None:
            break
        if quota_hit(err):
            with _lock:
                STOP_FILE.write_text(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{err}\n", encoding="utf-8")
            os._exit(75)
        low = (err or "").lower()
        time.sleep(60 * (attempt + 1) if any(s in low for s in ("rate", "limit", "overloaded", "429")) else 3 * (attempt + 1))
    if parsed is not None:
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps(dict(model=model, effort=effort, rep=rep, tag=tag, parsed=parsed, meta=meta,
                                      at=time.strftime("%Y-%m-%dT%H:%M:%S")), ensure_ascii=False), encoding="utf-8")
    return parsed, {**meta, "cached": False}


def ledger_summary(tag_prefix=""):
    if not LEDGER.exists():
        return {}
    rows = [json.loads(l) for l in open(LEDGER, encoding="utf-8")]
    rows = [r for r in rows if r.get("tag", "").startswith(tag_prefix)]
    return dict(calls=len(rows), ok=sum(bool(r.get("ok")) for r in rows), cost_equiv=round(sum(r.get("cost") or 0 for r in rows), 3))
