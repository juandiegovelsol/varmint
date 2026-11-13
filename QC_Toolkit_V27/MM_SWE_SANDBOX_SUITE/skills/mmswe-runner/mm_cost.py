#!/usr/bin/env python3
"""Cost ledger for the MM SWE suite: what every run in this sandbox spent on models.

SILENT BY DESIGN. Nothing here prints during a CB's work, and nothing in SKILL.md or the
commands mentions it. Every entry point swallows its own errors: a ledger that cannot be
written costs a missing row, never a failed run. The ledger is collected from the sandbox
before the task is delivered; it never travels with the deliverable.

    ~/.mm_swe_cost/ledger.json     (override: $MM_COST_HOME;  turn off: MM_COST=0)

Three sources, kept apart so none is counted twice:

  runs         one row per harbor job (both trial phases, pseudo-trial, check, analyze).
               Written by mm_run.sh after EVERY run, pass or fail. Oracle and nop are not
               recorded: they run no agent, so harbor has no model cost for them. The figure is
               harbor's own stats.cost_usd (Claude Code's total_cost_usd); ccusage re-prices the
               job's copied agent sessions as a cross-check, and a disagreement is flagged.
               Keyed on harbor's job id, so recording the same job twice updates one row.
  api_calls    direct Messages calls that are not Claude Code sessions, so ccusage cannot see
               them: the QC instruction read (qc_llm.py) and the host-side rubric grader
               (mm_grade_rubrics.py). Usage is stored raw and priced from LiteLLM's table.
  cb_sessions  the CB's OWN Claude Code sessions (~/.claude/projects), read with ccusage at the
               end of EVERY trial that ran, pass or fail. Each reading REPLACES the previous one:
               ccusage re-reads every session file each time, so a later reading already contains
               the earlier one, and adding them would double count. Reading after every trial
               (not only a passing one) means work done after a pass is still counted once the
               next trial ends. last_passing_trial keeps the reading taken at the latest pass.
               Trial agents are not in here -- their sessions live under the run dirs, not
               ~/.claude/projects, and are counted in `runs`.

Commands:
  mm_cost.py summary [--task ID] [--since YYYY-MM-DD] [--runs] [--json]
  mm_cost.py record-run --mode M --task-id ID --task-dir D --job DIR [--job DIR ...]
                        [--snapshot-sessions --trials-dir DIR
                         --trial-result TEXT [--trial-passed]]        (mm_run.sh calls this)
  mm_cost.py snapshot-sessions --task-id ID --task-dir D --trials-dir DIR
                               [--trial-result TEXT] [--trial-passed]
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(os.environ.get("MM_COST_HOME") or os.path.expanduser("~/.mm_swe_cost"))
LEDGER = HOME / "ledger.json"
LOCK = HOME / "ledger.lock"
PRICES = HOME / "prices.json"
NODE_DIR = HOME / "node"
NPM_CACHE = HOME / "npm-cache"

# Pinned. ccusage reads Claude Code's session JSONL and prices it from the same LiteLLM table.
CCUSAGE = "ccusage@20.0.45"
NODEJS_WHEEL = "nodejs-wheel==22.20.0"
PRICES_URL = ("https://raw.githubusercontent.com/BerriAI/litellm/main/"
              "model_prices_and_context_window.json")
PRICES_MAX_AGE = 7 * 86400
SCHEMA = 1


def enabled() -> bool:
    return (os.environ.get("MM_COST") or "1").strip().lower() not in ("0", "off", "false", "no")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


# ------------------------------------------------------------------ ledger file (locked RMW)

def _empty() -> dict:
    return {"schema": SCHEMA, "created": _now(), "updated": None,
            "runs": [], "api_calls": [], "cb_sessions": None, "totals": {}}


def _load() -> dict:
    if not LEDGER.exists():
        return _empty()
    data = _read_json(LEDGER)
    if isinstance(data, dict) and isinstance(data.get("runs"), list):
        data.setdefault("api_calls", [])
        data.setdefault("cb_sessions", None)
        return data
    # Unreadable: keep it aside rather than overwrite what may be the only copy.
    with contextlib.suppress(OSError):
        LEDGER.rename(LEDGER.with_name("ledger.json.unreadable-%d" % int(time.time())))
    return _empty()


def _save(data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(HOME), prefix=".ledger.", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    os.replace(tmp, LEDGER)


@contextlib.contextmanager
def _locked():
    HOME.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "a+") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        data = _load()
        yield data
        _recompute(data, _prices(fetch=False))
        data["updated"] = _now()
        _save(data)


# ------------------------------------------------------------------ pricing (direct API calls)

def _prices(fetch: bool) -> dict:
    cached = _read_json(PRICES)
    stale = True
    with contextlib.suppress(OSError):
        stale = time.time() - PRICES.stat().st_mtime > PRICES_MAX_AGE
    if fetch and (not isinstance(cached, dict) or stale):
        try:
            with urllib.request.urlopen(PRICES_URL, timeout=15) as r:
                table = json.load(r)
            table = {k: v for k, v in table.items() if "claude" in k and isinstance(v, dict)}
            if table:
                HOME.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=str(HOME), prefix=".prices.", suffix=".tmp")
                with os.fdopen(fd, "w") as f:
                    json.dump(table, f)
                os.replace(tmp, PRICES)
                cached = table
        except Exception:
            pass
    return cached if isinstance(cached, dict) else {}


def _norm_usage(u) -> dict:
    """Claude-format and OpenAI-format usage -> {input, output, cache_write, cache_read}."""
    u = u if isinstance(u, dict) else {}
    if "prompt_tokens" in u and "input_tokens" not in u:
        cached = _num((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
        return {"input": int((_num(u.get("prompt_tokens")) or 0) - cached),
                "output": int(_num(u.get("completion_tokens")) or 0),
                "cache_write": 0, "cache_read": int(cached)}
    return {"input": int(_num(u.get("input_tokens")) or 0),
            "output": int(_num(u.get("output_tokens")) or 0),
            "cache_write": int(_num(u.get("cache_creation_input_tokens")) or 0),
            "cache_read": int(_num(u.get("cache_read_input_tokens")) or 0)}


def _price_for(model, prices):
    if not model:
        return None
    m = str(model)
    for k in (m, m.split("/")[-1], "anthropic/" + m.split("/")[-1]):
        p = prices.get(k)
        if isinstance(p, dict) and _num(p.get("input_cost_per_token")) is not None:
            return p
    return None


def _cost(model, tokens, prices):
    p = _price_for(model, prices)
    if p is None:
        return None
    pin = p["input_cost_per_token"]
    return (tokens["input"] * pin
            + tokens["output"] * (_num(p.get("output_cost_per_token")) or 0)
            + tokens["cache_write"] * (_num(p.get("cache_creation_input_token_cost")) or pin * 1.25)
            + tokens["cache_read"] * (_num(p.get("cache_read_input_token_cost")) or pin * 0.1))


def _recompute(data: dict, prices: dict) -> None:
    for c in data.get("api_calls", []):
        if c.get("cost_usd") is None:
            c["cost_usd"] = _cost(c.get("model"), c.get("tokens") or _norm_usage({}), prices)
    data["totals"] = _totals(data.get("runs", []), data.get("api_calls", []),
                             data.get("cb_sessions"))


def _totals(runs, calls, cb) -> dict:
    runs_usd = sum(_num(r.get("cost_usd")) or 0 for r in runs)
    api_usd = sum(_num(c.get("cost_usd")) or 0 for c in calls)
    cb_usd = (_num((cb or {}).get("cost_usd")) or 0) if cb else 0
    return {"runs_usd": round(runs_usd, 6), "api_calls_usd": round(api_usd, 6),
            "cb_sessions_usd": round(cb_usd, 6), "total_usd": round(runs_usd + api_usd + cb_usd, 6),
            "runs": len(runs), "api_calls": len(calls),
            "api_calls_unpriced": sum(1 for c in calls if c.get("cost_usd") is None),
            "runs_mismatched": sum(1 for r in runs if r.get("mismatch"))}


# ------------------------------------------------------------------ public hook: direct API call

def log_api_call(source, model, usage, task_id=None, task_dir=None) -> None:
    """Called by qc_llm.py / mm_grade_rubrics.py after a REAL (paid) call. Never raises."""
    if not enabled():
        return
    try:
        with _locked() as d:
            d["api_calls"].append({
                "ts": _now(), "source": source, "model": model,
                "task_id": task_id or os.environ.get("MM_COST_TASK_ID") or None,
                "task_dir": task_dir or os.environ.get("MM_COST_TASK_DIR") or None,
                "tokens": _norm_usage(usage), "usage": usage if isinstance(usage, dict) else None,
                "cost_usd": None})
    except Exception:
        pass


# ------------------------------------------------------------------ ccusage

def _node():
    node = NODE_DIR / "nodejs_wheel" / "bin" / "node"
    if not node.exists():
        HOME.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                        "--no-warn-script-location", "--target", str(NODE_DIR), NODEJS_WHEEL],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=300)
    return node if node.exists() else None


def ccusage(config_dirs=None):
    """-> (parsed `ccusage session --json`, "") or (None, reason).

    config_dirs=None reads the default Claude config (the CB's own sessions). A list points
    CLAUDE_CONFIG_DIR at those dirs only (a run's copied agent sessions).
    """
    try:
        node = _node()
        if node is None:
            return None, "node unavailable (pip install %s failed)" % NODEJS_WHEEL
        # The wheel's bin/npx shim is a copied symlink with a broken relative require; npm's own
        # npx-cli.js is the reliable entry point.
        npx = NODE_DIR / "nodejs_wheel" / "lib" / "node_modules" / "npm" / "bin" / "npx-cli.js"
        env = dict(os.environ)
        env.update({"PATH": "%s:%s" % (node.parent, env.get("PATH", "")),
                    "npm_config_cache": str(NPM_CACHE), "npm_config_update_notifier": "false",
                    "npm_config_fund": "false", "npm_config_audit": "false",
                    "npm_config_loglevel": "silent", "NO_COLOR": "1"})
        if config_dirs is not None:
            env["CLAUDE_CONFIG_DIR"] = ",".join(str(d) for d in config_dirs)
        # cwd = the ledger dir, so no ccusage config in a task folder is auto-discovered.
        p = subprocess.run([str(node), str(npx), "-y", CCUSAGE, "session", "--json"],
                           cwd=str(HOME), env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=240)
        if p.returncode != 0:
            return None, "ccusage rc %d: %s" % (p.returncode, (p.stderr or "").strip()[-300:])
        return json.loads(p.stdout), ""
    except Exception as exc:
        return None, "ccusage failed: %s" % exc


def _session_rows(data, claude_only):
    rows = []
    for s in (data or {}).get("session") or []:
        if claude_only and s.get("agent", "claude") != "claude":
            continue
        rows.append({"agent": s.get("agent"), "session_id": s.get("period"),
                     "cost_usd": _num(s.get("totalCost")),
                     "input": s.get("inputTokens"), "output": s.get("outputTokens"),
                     "cache_write": s.get("cacheCreationTokens"),
                     "cache_read": s.get("cacheReadTokens"),
                     "models": s.get("modelsUsed"),
                     "last_activity": (s.get("metadata") or {}).get("lastActivity")})
    return rows


# ------------------------------------------------------------------ record-run

def _job_row(mode, task_id, task_dir, job):
    jp = Path(job).resolve()             # ccusage runs from the ledger dir, so no relative paths
    r = _read_json(jp / "result.json")
    if not isinstance(r, dict):
        return None                      # this job never produced a result -- nothing to record
    stats = r.get("stats") or {}
    attempts = []
    for res in sorted(jp.glob("*/result.json")):
        a = _read_json(res) or {}
        if "trial_name" not in a and "agent_result" not in a:
            continue                     # a stray older job dir (has "stats"), not an attempt
        ar = a.get("agent_result") or {}
        rew = ((a.get("verifier_result") or {}).get("rewards") or {})
        attempts.append({"name": res.parent.name, "cost_usd": _num(ar.get("cost_usd")),
                         "reward": rew.get("reward") if isinstance(rew, dict) else None,
                         "input": ar.get("n_input_tokens"), "cache": ar.get("n_cache_tokens"),
                         "output": ar.get("n_output_tokens")})
    harbor = _num(stats.get("cost_usd"))
    if harbor is None:
        # A job stopped by the circuit breaker can exit before harbor finalises its stats.
        per = [a["cost_usd"] for a in attempts if a["cost_usd"] is not None]
        harbor = sum(per) if per else None
    row = {"id": r.get("id") or "%s@%s" % (jp, r.get("started_at")),
           "mode": mode, "job": jp.name, "job_dir": str(jp),
           "task_id": task_id, "task_dir": task_dir,
           "started_at": r.get("started_at"), "finished_at": r.get("finished_at"),
           "recorded_at": _now(),
           "harbor_cost_usd": harbor,
           "tokens": {"input": stats.get("n_input_tokens"), "cache": stats.get("n_cache_tokens"),
                      "output": stats.get("n_output_tokens")},
           "attempts": attempts,
           "ccusage_cost_usd": None}
    dirs = sorted(str(d) for d in jp.glob("*/agent/sessions") if (d / "projects").is_dir())
    if dirs:
        data, err = ccusage(dirs)
        if data is not None:
            rows = _session_rows(data, claude_only=True)
            row["ccusage_cost_usd"] = sum(x["cost_usd"] or 0 for x in rows)
            row["ccusage_sessions"] = len(rows)
        else:
            row["ccusage_error"] = err
    h, c = row["harbor_cost_usd"], row["ccusage_cost_usd"]
    row["mismatch"] = bool(h is not None and c is not None
                           and abs(h - c) > max(0.01, 0.02 * max(h, c)))
    row["cost_usd"] = h if h is not None else c
    return row


def _snapshot(task_id, task_dir, trials_dir, result=None, passed=False):
    data, err = ccusage(None)
    snap = {"taken_at": _now(), "tool": CCUSAGE,
            "trigger": {"mode": "trial", "result": result or "unknown", "passed": bool(passed),
                        "task_id": task_id, "task_dir": task_dir, "trials_dir": trials_dir}}
    if data is not None:
        snap["sessions"] = _session_rows(data, claude_only=False)
        snap["cost_usd"] = _num(((data.get("totals") or {}).get("totalCost")))
        if snap["cost_usd"] is None:
            snap["cost_usd"] = sum(x["cost_usd"] or 0 for x in snap["sessions"])
    else:
        snap["cost_usd"] = None
        snap["error"] = err
    return snap


def _store_snapshot(d, snap):
    prev = d.get("cb_sessions") or {}
    passed = bool((snap.get("trigger") or {}).get("passed"))
    if snap.get("cost_usd") is None and prev.get("cost_usd") is not None:
        # A failed reading never erases a good one; the next trial tries again.
        prev["last_failed_snapshot"] = {"taken_at": snap["taken_at"], "error": snap.get("error"),
                                        "trigger": snap.get("trigger")}
        if passed:
            prev["passes_seen"] = (prev.get("passes_seen") or 0) + 1
        return
    snap["replaces"] = prev.get("taken_at")
    snap["readings"] = (prev.get("readings") or prev.get("passes_seen") or 0) + 1
    snap["passes_seen"] = (prev.get("passes_seen") or 0) + (1 if passed else 0)
    if passed and snap.get("cost_usd") is not None:
        snap["last_passing_trial"] = {"taken_at": snap["taken_at"], "cost_usd": snap["cost_usd"],
                                      "result": snap["trigger"].get("result")}
    else:
        snap["last_passing_trial"] = prev.get("last_passing_trial")
    d["cb_sessions"] = snap


def cmd_record_run(a) -> int:
    if not enabled():
        return 0
    jobs = list(a.job or [])
    if a.only_new:
        # Before-run pass: skip jobs already recorded (cheap unlocked read; the locked write
        # below re-checks), so a row is never overwritten with this run's task labels.
        known = {r.get("id") for r in (_read_json(LEDGER) or {}).get("runs", [])}
        jobs = [j for j in jobs if (_read_json(Path(j) / "result.json") or {}).get("id") not in known]
        if not jobs:
            return 0
    _prices(fetch=True)                  # refresh the price cache while a network is known up
    rows = [r for r in (_job_row(a.mode, a.task_id, a.task_dir, j) for j in jobs) if r]
    snap = (_snapshot(a.task_id, a.task_dir, a.trials_dir, a.trial_result, a.trial_passed)
            if a.snapshot_sessions else None)
    with _locked() as d:
        by_id = {r.get("id"): i for i, r in enumerate(d["runs"])}
        for row in rows:
            if row["id"] in by_id:
                if not a.only_new:
                    d["runs"][by_id[row["id"]]] = row
            else:
                d["runs"].append(row)
        if snap is not None:
            _store_snapshot(d, snap)
    return 0


def cmd_snapshot(a) -> int:
    if not enabled():
        return 0
    snap = _snapshot(a.task_id, a.task_dir, a.trials_dir, a.trial_result, a.trial_passed)
    with _locked() as d:
        _store_snapshot(d, snap)
    return 0


# ------------------------------------------------------------------ summary (team-facing)

def _money(x):
    return "     -" if x is None else "$%8.4f" % x


def _cell(x):
    return "-" if x is None else "$%.4f" % x


def cmd_summary(a) -> int:
    data = _read_json(LEDGER)
    if not isinstance(data, dict):
        print("no ledger at %s" % LEDGER)
        return 1
    _recompute(data, _prices(fetch=True))   # in memory only; summary never writes

    def keep(row, ts_key):
        if a.task and row.get("task_id") != a.task:
            return False
        if a.since and str(row.get(ts_key) or "")[:10] < a.since:
            return False
        return True

    runs = [r for r in data["runs"] if keep(r, "started_at")]
    calls = [c for c in data["api_calls"] if keep(c, "ts")]
    cb = data.get("cb_sessions")
    if cb and a.task and (cb.get("trigger") or {}).get("task_id") != a.task:
        cb = None
    if cb and a.since and str(cb.get("taken_at") or "")[:10] < a.since:
        cb = None
    tot = _totals(runs, calls, cb)

    if a.json:
        print(json.dumps({"ledger": str(LEDGER), "filters": {"task": a.task, "since": a.since},
                          "totals": tot, "runs": runs, "api_calls": calls, "cb_sessions": cb},
                         indent=1))
        return 0

    print("MM SWE cost ledger  %s" % LEDGER)
    print("  updated %s%s%s" % (data.get("updated") or "-",
                                 "   task=%s" % a.task if a.task else "",
                                 "   since=%s" % a.since if a.since else ""))
    print()
    by_mode = {}
    for r in runs:
        m = by_mode.setdefault(r.get("mode") or "?", [0, 0.0])
        m[0] += 1
        m[1] += _num(r.get("cost_usd")) or 0
    print("  harbor runs                %s   (%d runs)" % (_money(tot["runs_usd"]), tot["runs"]))
    for mode, (n, usd) in sorted(by_mode.items()):
        print("    %-24s %s   (%d)" % (mode, _money(usd), n))
    by_src = {}
    for c in calls:
        s = by_src.setdefault(c.get("source") or "?", [0, 0.0])
        s[0] += 1
        s[1] += _num(c.get("cost_usd")) or 0
    print("  direct API calls           %s   (%d calls%s)" % (
        _money(tot["api_calls_usd"]), tot["api_calls"],
        ", %d unpriced" % tot["api_calls_unpriced"] if tot["api_calls_unpriced"] else ""))
    for src, (n, usd) in sorted(by_src.items()):
        print("    %-24s %s   (%d)" % (src, _money(usd), n))
    if cb:
        print("  CB sessions (ccusage)      %s   (%d sessions, read %s after trial #%s: %s)" % (
            _money(cb.get("cost_usd")), len(cb.get("sessions") or []), cb.get("taken_at"),
            cb.get("readings") or cb.get("passes_seen"),
            (cb.get("trigger") or {}).get("result")))
        lp = cb.get("last_passing_trial")
        if lp:
            print("    at the last passing trial (%s): %s" % (lp.get("taken_at"),
                                                           _money(lp.get("cost_usd")).strip()))
        else:
            print("    no passing trial yet")
        if cb.get("error"):
            print("    reading failed: %s" % cb["error"])
        if cb.get("last_failed_snapshot"):
            print("    a later reading failed (%s) - value above is from the earlier pass"
                  % cb["last_failed_snapshot"].get("taken_at"))
    else:
        print("  CB sessions (ccusage)           -   (no trial recorded yet)")
    print("  " + "-" * 44)
    print("  total                      %s" % _money(tot["total_usd"]))
    if tot["runs_mismatched"]:
        print("\n  %d run(s) where harbor and ccusage disagree by more than 2%% - see --runs"
              % tot["runs_mismatched"])

    if a.runs:
        print("\n  %-20s %-20s %-10s %-10s %-9s %s" % (
            "started", "mode", "harbor", "ccusage", "attempts", "task"))
        for r in sorted(runs, key=lambda r: str(r.get("started_at"))):
            print("  %-20s %-20s %-10s %-10s %-9s %s%s" % (
                str(r.get("started_at") or "")[:19], r.get("mode"),
                _cell(r.get("harbor_cost_usd")), _cell(r.get("ccusage_cost_usd")),
                len(r.get("attempts") or []), r.get("task_id"), "  MISMATCH" if r.get("mismatch") else ""))
        for c in sorted(calls, key=lambda c: str(c.get("ts"))):
            print("  %-20s %-20s %-10s %-10s %-9s %s" % (
                str(c.get("ts") or "")[:19], c.get("source"), _cell(c.get("cost_usd")),
                "", "", c.get("task_id") or "-"))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="MM SWE cost ledger (%s)" % LEDGER)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("summary", help="totals by source, mode and task")
    s.add_argument("--task", help="only this task_id")
    s.add_argument("--since", help="only rows on/after this date (YYYY-MM-DD)")
    s.add_argument("--runs", action="store_true", help="also list every run and API call")
    s.add_argument("--json", action="store_true", help="machine-readable output")
    s.set_defaults(fn=cmd_summary)

    r = sub.add_parser("record-run")
    r.add_argument("--mode", required=True)
    r.add_argument("--task-id", default=None)
    r.add_argument("--task-dir", default=None)
    r.add_argument("--job", action="append")
    r.add_argument("--snapshot-sessions", action="store_true")
    r.add_argument("--trials-dir", default=None)
    r.add_argument("--only-new", action="store_true")
    r.add_argument("--trial-result", default=None)
    r.add_argument("--trial-passed", action="store_true")
    r.set_defaults(fn=cmd_record_run)

    n = sub.add_parser("snapshot-sessions")
    n.add_argument("--task-id", default=None)
    n.add_argument("--task-dir", default=None)
    n.add_argument("--trials-dir", default=None)
    n.add_argument("--trial-result", default=None)
    n.add_argument("--trial-passed", action="store_true")
    n.set_defaults(fn=cmd_snapshot)

    a = ap.parse_args(argv)
    if a.cmd == "summary":
        return a.fn(a)
    try:                                  # the runner's hooks must never fail a run
        return a.fn(a)
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
