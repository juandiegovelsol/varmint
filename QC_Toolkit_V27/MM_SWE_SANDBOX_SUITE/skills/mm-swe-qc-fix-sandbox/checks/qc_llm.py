#!/usr/bin/env python3
"""One optional model read for the QC audit: a single Claude Messages call, cached, never required.

The audit is otherwise free and offline, and it has to stay usable that way: a headless sandbox
with no proxy, a CB without credentials, a re-run seconds after the last one. So every path out of
here that is not a parsed reply returns (None, reason), and the caller falls back to its static
scan. Nothing in this module can fail the audit.

CREDENTIALS resolve in mm_run.sh's resolve_creds order: live env, then ~/.claude/settings.json's
`env`, then the anonymizer defaults (http://localhost:8091, placeholder key). A copy rather than an
import, because the two skills install as separate folders and neither may assume the other.

THE CACHE IS WHAT MAKES THIS AFFORDABLE AND STABLE. mm_run.sh's qc_gate() re-invokes `fix.py qc`
seconds after /run-check, and fix.py re-audits after every repair. Keyed on the exact request, the
second read of an unchanged instruction costs nothing and cannot come back with a different answer.
The cache lives outside the task bundle on purpose: qc_digest hashes the bundle, and a file
written into it would make every recorded run look stale.

Env:
  MM_QC_LLM=0            skip the model read entirely (also: off / false / no)
  MM_QC_LLM_MODEL        model name (default: JUDGE_MODEL, then claude-sonnet-5)
  MM_QC_LLM_CACHE        cache directory (default ~/.cache/mm-swe-qc/llm)
  MM_QC_LLM_TIMEOUT      seconds per attempt (default 45; two attempts)
  ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY / SETTINGS_JSON   as in mm_run.sh
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request

DEFAULT_BASE = "http://localhost:8091"
DEFAULT_KEY = "anonymizer-placeholder"
DEFAULT_MODEL = "claude-sonnet-5"        # the anonymizer wants PLAIN model names
ATTEMPTS = 2
# qc_all gives qc_structure 300s in total, and it does network fetches of its own. Two attempts at
# 45s plus the backoff keeps the worst case for this read under two minutes.
TIMEOUT = float(os.environ.get("MM_QC_LLM_TIMEOUT") or 45)


def disabled():
    return (os.environ.get("MM_QC_LLM") or "").strip().lower() in ("0", "off", "false", "no")


def _settings_env(name):
    path = os.environ.get("SETTINGS_JSON") or os.path.expanduser("~/.claude/settings.json")
    try:
        with open(path, encoding="utf-8") as f:
            val = (json.load(f).get("env") or {}).get(name)
    except (OSError, ValueError, AttributeError):
        return ""
    return str(val).strip() if val else ""


def _setting(name):
    return (os.environ.get(name) or "").strip() or _settings_env(name)


def credentials():
    base = _setting("ANTHROPIC_BASE_URL") or DEFAULT_BASE
    key = _setting("ANTHROPIC_API_KEY") or DEFAULT_KEY
    model = ((os.environ.get("MM_QC_LLM_MODEL") or "").strip() or _setting("JUDGE_MODEL")
             or DEFAULT_MODEL)
    return base.rstrip("/"), key, model


def _cache_dir():
    return os.environ.get("MM_QC_LLM_CACHE") or os.path.expanduser("~/.cache/mm-swe-qc/llm")


def _cache_path(digest):
    return os.path.join(_cache_dir(), digest + ".json")


def _cache_get(digest):
    try:
        with open(_cache_path(digest), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _cache_put(digest, entry):
    try:
        os.makedirs(_cache_dir(), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=_cache_dir(), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=1)
        os.replace(tmp, _cache_path(digest))
    except OSError:
        pass                                     # an unwritable cache only costs a repeat call


def _post(url, headers, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    last = ""
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r), ""
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code} from {url}"
            try:                                 # surface the API's own message, if it sent one
                # Proxies nest the API's JSON error inside a string; drop the escaping and take
                # the innermost plain "message".
                raw = exc.read().decode("utf-8", "replace").replace("\\", "")
                msgs = [m for m in re.findall(r'"message"\s*:\s*"([^"]+)"', raw)
                        if not m.lstrip().startswith("{")]
                if msgs:
                    last += f": {msgs[0][:200]}"
            except Exception:
                pass
            if exc.code < 500 and exc.code != 429:
                break                            # a bad request or a bad key will not improve
        except (urllib.error.URLError, OSError, ValueError) as exc:
            reason = getattr(exc, "reason", exc)
            last = f"{url} unreachable ({reason})"
            if isinstance(reason, ConnectionRefusedError):
                break                            # nothing is listening; a retry only adds delay
        if attempt + 1 < ATTEMPTS:
            time.sleep(2 * (attempt + 1))
    return None, last


def _cost_log(model, usage):
    """Silent cost-ledger hook (mmswe-runner/mm_cost.py). Never raises, never prints; a missing
    runner skill just means no row."""
    try:
        import importlib.util
        here = os.path.dirname(os.path.abspath(__file__))
        for p in (os.path.join(here, "..", "..", "mmswe-runner", "mm_cost.py"),
                  os.path.expanduser("~/.claude/skills/mmswe-runner/mm_cost.py")):
            if os.path.isfile(p):
                spec = importlib.util.spec_from_file_location("mm_cost", p)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.log_api_call("qc_instruction_read", model, usage)
                return
    except Exception:
        pass


def _extract_json(text):
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


# Current models think before they answer and that thinking counts against max_tokens: the
# instruction read spends ~4k tokens thinking, so a 1024 cap stopped every reply before its text.
def ask_json(system, user, max_tokens=16000):
    """Returns (reply_dict, meta) or (None, reason). meta = {"model", "cached", "usage"}."""
    if disabled():
        return None, "turned off (MM_QC_LLM=0)"
    base, key, model = credentials()
    digest = hashlib.sha256(json.dumps([model, system, user, max_tokens]).encode()).hexdigest()
    hit = _cache_get(digest)
    if hit and isinstance(hit.get("reply"), dict):
        return hit["reply"], {"model": model, "cached": True, "usage": hit.get("usage") or {}}

    resp, err = _post(base + "/v1/messages",
                      {"x-api-key": key, "anthropic-version": "2023-06-01",
                       "content-type": "application/json"},
                      # No `temperature`: current models reject it ("deprecated for this model",
                      # HTTP 400), which silently forced the static fallback on every audit.
                      {"model": model, "max_tokens": max_tokens,
                       "system": system, "messages": [{"role": "user", "content": user}]})
    if resp is None:
        return None, err
    _cost_log(model, resp.get("usage"))      # paid even if the reply below is unusable
    text = "".join(b.get("text", "") for b in resp.get("content") or []
                   if isinstance(b, dict) and b.get("type") == "text")
    reply = _extract_json(text)
    if reply is None:
        return None, f"{model} replied without a JSON object"
    usage = resp.get("usage") or {}
    _cache_put(digest, {"model": model, "reply": reply, "usage": usage,
                        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    return reply, {"model": model, "cached": False, "usage": usage}
