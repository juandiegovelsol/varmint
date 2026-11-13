#!/usr/bin/env python3
"""Host-side rubric judge for MM SWE tasks — a fallback for the in-container judge.

Why this exists: if the verifier's judge can't reach the anonymizer (proxy down, override
not applied, creds not forwarded), `quality` comes back 0 or missing and you cannot tell
"the code is bad" from "the judge never ran". This grades the same rubric HERE on the host,
where localhost:8091 is always reachable, so QC always gets a number.

Grades the CANDIDATE DIFF (what the agent changed), not the whole repo — that is what a
rubric about approach/scope is actually about. Test/harness files are excluded so the judge
never grades the suite the agent may have touched.

Pure stdlib (urllib): no `anthropic` SDK, so nothing to install anywhere.
Scoring is BINARY and UNWEIGHTED: every criterion is PASS/FAIL and every one is mandatory,
so the rubric passes only if all criteria pass. Prints "pass" or "fail" plus the failing ids.

Usage:
  mm_grade_rubrics.py --rubrics tests/rubrics.json --workspace <collected workspace dir>
  mm_grade_rubrics.py --rubrics tests/rubrics.json --diff-file some.patch
Env: ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY, JUDGE_MODEL (default claude-sonnet-5)
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path

# Files whose changes must NOT be graded (the harness, not the fix).
EXCLUDE_RE = re.compile(r"(\.test\.[jt]sx?$|(^|/)tests?/|(^|/)__tests__/|\.spec\.[jt]sx?$|"
                        r"(^|/)test\.patch$|(^|/)node_modules/|(^|/)\.git/)")
BASE_REFS = ("harbor_base", "HEAD~1", "HEAD")


def diff_from_workspace(ws: Path, budget: int = 120_000) -> str:
    """git diff of the candidate's changes, harness files removed."""
    if not (ws / ".git").exists():
        sys.stderr.write(f"[grade] {ws} is not a git checkout; cannot diff\n")
        return ""
    for ref in BASE_REFS:
        try:
            out = subprocess.run(["git", "-C", str(ws), "diff", ref],
                                 capture_output=True, text=True, timeout=120)
        except Exception as exc:
            sys.stderr.write(f"[grade] git diff failed: {exc}\n"); return ""
        if out.returncode == 0 and out.stdout.strip():
            sys.stderr.write(f"[grade] diffing against {ref}\n")
            return filter_diff(out.stdout, budget)
    sys.stderr.write("[grade] no non-empty diff against any of %s\n" % (BASE_REFS,))
    return ""


def filter_diff(diff: str, budget: int) -> str:
    """Drop per-file hunks that belong to the test harness, then apply a size budget."""
    kept, cur, keep = [], [], True
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if keep and cur:
                kept.extend(cur)
            parts = line.split()
            path = parts[-1][2:] if len(parts) >= 4 else ""
            keep = not EXCLUDE_RE.search(path)
            cur = [line]
        else:
            cur.append(line)
    if keep and cur:
        kept.extend(cur)
    blob = "".join(kept)
    if len(blob) > budget:
        blob = blob[:budget] + "\n[... diff truncated for length ...]\n"
    return blob


def load_criteria(rubrics: Path):
    """Accept {"criteria":[...]} or the ProjectBench {"milestones":[{"criteria":[...]}]}."""
    doc = json.loads(rubrics.read_text())
    raw = doc.get("criteria")
    if raw is None:
        raw = [c for m in doc.get("milestones", []) for c in m.get("criteria", [])]
    out = []
    for c in raw or []:
        out.append({"id": c["id"], "category": c.get("category", ""),
                    "criterion": c.get("criterion") or c.get("description", "")})
    return out


SYSTEM = ("You are a strict senior engineer grading the QUALITY and APPROACH of a code change "
          "(not whether tests pass). Judge each criterion as BINARY: 1=satisfied, 0=not satisfied "
          'or no clear evidence. No partial credit, no 0.5 — if unsure, score 0. Respond ONLY '
          'JSON: {"scores":{"<id>":{"score":0|1}, ...}}. Every id must appear.')


def user_prompt(criteria, material):
    payload = [{"id": c["id"], "category": c["category"], "criterion": c["criterion"]}
               for c in criteria]
    return json.dumps({"criteria": payload}) + "\n\nCANDIDATE DIFF:\n" + material


def _cost_log(model, resp):
    """Silent cost-ledger hook (mm_cost.py beside this file). Never raises, never prints."""
    try:
        import importlib.util
        p = Path(__file__).resolve().with_name("mm_cost.py")
        spec = importlib.util.spec_from_file_location("mm_cost", str(p))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.log_api_call("rubric_grader", model, (resp or {}).get("usage"))
    except Exception:
        pass


def post_json(url, headers, body, attempts=6, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as exc:
            if attempt == attempts - 1:
                sys.stderr.write(f"[grade] call to {url} failed after retries: {exc}\n")
                return None
            time.sleep(2 * (attempt + 1))
    return None


def extract_scores(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        sys.stderr.write("[grade] judge reply had no JSON object\n"); return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"[grade] judge reply was not valid JSON ({exc}) — likely truncated\n")
        return None
    return obj.get("scores", obj) if isinstance(obj, dict) else None


def grade_openai(criteria, material):
    """OpenAI-format backend — the SAME channel tests/judge.py's API backend uses.

    Tried first so the host-side fallback agrees with the in-container judge on endpoint AND
    model. Grading the same rubric through a different model was a real hazard: the two could
    return different verdicts for the same diff and nothing said which one the reward meant.
    """
    base = (os.environ.get("EVAL_BASE_URL") or os.environ.get("OPENAI_API_BASE") or "").strip()
    key = (os.environ.get("EVAL_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    model = (os.environ.get("EVAL_MODEL") or "").strip()
    if not base or not key or not model:
        sys.stderr.write("[grade] openai-format backend unavailable "
                         "(EVAL_BASE_URL/EVAL_API_KEY/EVAL_MODEL incomplete)\n")
        return None
    resp = post_json(base.rstrip("/") + "/chat/completions",
                     {"Authorization": "Bearer %s" % key, "Content-Type": "application/json"},
                     {"model": model, "temperature": 0,
                      "messages": [{"role": "system", "content": SYSTEM},
                                   {"role": "user", "content": user_prompt(criteria, material)}]})
    if not resp:
        return None
    _cost_log(model, resp)
    try:
        text = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        sys.stderr.write("[grade] openai-format reply had no message content\n"); return None
    scores = extract_scores(text)
    if scores is not None:
        sys.stderr.write(f"[grade] graded via openai-format model={model}\n")
    return scores


def grade_anthropic(criteria, material):
    """Claude-format backend — the fallback, for a bundle with no OpenAI channel configured."""
    base = os.environ.get("ANTHROPIC_BASE_URL")
    key = os.environ.get("ANTHROPIC_API_KEY")
    model = os.environ.get("JUDGE_MODEL") or os.environ.get("PB_JUDGE_MODEL") or "claude-sonnet-5"
    if not base or not key:
        sys.stderr.write("[grade] no ANTHROPIC_BASE_URL/API_KEY\n"); return None
    # Scale the output budget with rubric size; a fixed cap truncates the JSON reply mid-object.
    max_tokens = min(32000, max(4000, 120 * len(criteria)))
    resp = post_json(base.rstrip("/") + "/v1/messages",
                     {"x-api-key": key, "anthropic-version": "2023-06-01",
                      "content-type": "application/json"},
                     {"model": model, "max_tokens": max_tokens, "system": SYSTEM,
                      "messages": [{"role": "user",
                                    "content": user_prompt(criteria, material)}]})
    if not resp:
        return None
    _cost_log(model, resp)
    text ="".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
    scores = extract_scores(text)
    if scores is not None:
        sys.stderr.write(f"[grade] graded via claude-format model={model}\n")
    return scores


def judge(criteria, material):
    """Returns (verdict, failed_ids, raw_scores) or None. Scoring is one path per backend."""
    scores = grade_openai(criteria, material)
    if scores is None:
        scores = grade_anthropic(criteria, material)
    if not isinstance(scores, dict):
        sys.stderr.write("[grade] no backend produced a scores map\n"); return None
    failed, graded = [], 0
    for c in criteria:
        raw = scores.get(c["id"], {})
        try:
            v = float(raw.get("score") if isinstance(raw, dict) else raw)
        except (TypeError, ValueError, AttributeError):
            failed.append(c["id"])                # ungraded == not demonstrated == fail
            continue
        graded += 1
        # Strictly binary: only a full 1 passes. A partial/hedged score (0.5) is NOT
        # satisfied — rounding it up would smuggle partial credit back in.
        if v < 0.999:
            failed.append(c["id"])
    if graded == 0:
        return None
    sys.stderr.write(f"[grade] {graded}/{len(criteria)} criteria graded\n")
    if failed:
        sys.stderr.write("[grade] failed criteria: %s\n" % ", ".join(failed))
    return (("fail", failed, scores) if failed else ("pass", [], scores))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rubrics", required=True)
    ap.add_argument("--workspace", help="collected workspace (git checkout) to diff")
    ap.add_argument("--diff-file", help="pre-computed diff to grade instead")
    ap.add_argument("--verdict-out", help="also write the scores here as verdict.json, so "
                                          "`mm_run.sh <task> rescore` can fold this grade "
                                          "into the run's reward")
    a = ap.parse_args()
    rub = Path(a.rubrics)
    if not rub.is_file():
        sys.stderr.write(f"[grade] no rubrics at {rub}\n"); return 0
    criteria = load_criteria(rub)
    if not criteria:
        sys.stderr.write("[grade] rubrics file has no criteria\n"); return 0
    if a.diff_file:
        # filter here too — harness hunks must never reach the judge, whatever the source
        material = filter_diff(Path(a.diff_file).read_text(errors="replace"), 120_000)
    elif a.workspace:
        material = diff_from_workspace(Path(a.workspace))
    else:
        sys.stderr.write("[grade] need --workspace or --diff-file\n"); return 0
    if not material.strip():
        sys.stderr.write("[grade] nothing to grade (empty diff)\n"); return 0
    res = judge(criteria, material)
    if res is None:
        sys.stderr.write("[grade] rubric judge unavailable\n"); return 0
    verdict, failed, scores = res
    # Persist the grade where the task's OWN judge.py looks for it. Without this the host-side
    # verdict was printed and nothing more: it never reached reward.txt, and `rescore` — which
    # reads verdict.json — could not pick it up, so a run the in-container judge missed stayed
    # scored on tests alone no matter how many times it was graded here.
    if a.verdict_out:
        try:
            out = Path(a.verdict_out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({"scores": scores}, indent=2))
            sys.stderr.write(f"[grade] wrote {out}\n")
        except OSError as exc:
            sys.stderr.write(f"[grade] could not write {a.verdict_out}: {exc}\n")
    sys.stderr.write(f"[grade] host-side rubric verdict: {verdict}"
                     + (f" (failed: {', '.join(failed)})" if failed else "") + "\n")
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
