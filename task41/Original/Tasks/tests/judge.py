#!/usr/bin/env python3
"""
Rubric judge — API backend, with the sub-agent backend as fallback.

Binary and unweighted: every criterion is PASS/FAIL and every one is mandatory, so the
rubric passes only if all pass.

Backend selection, in order:

  API (preferred, in-band)
      When EVAL_API_KEY and EVAL_BASE_URL are set, grade the criteria in one
      chat-completions call to the proxy, write the resulting scores map to verdict.json
      in the judge dir, then score it through the SAME read_verdict path the sub-agent
      backend uses. Any failure here falls through to the sub-agent request below — the
      judge must never fail the run.

  Sub-agent (fallback, out-of-band), two-phase:

  Phase 1 (during the verifier run)
      No verdict exists yet, so this writes a self-contained judge request into the judge
      dir -- criteria_payload.json, source.txt (the candidate diff), PROMPT.md -- prints
      nothing, and exits 0. The verifier then scores on tests alone.

  Phase 2 (after the run, orchestrated outside the container)
      A judge sub-agent reads PROMPT.md and writes verdict.json next to it. Re-running this
      script (or `mm_run.sh <task> rescore`) reads that verdict and prints "pass" or "fail".

Contract (test.sh depends on all three):
  * prints "pass" or "fail" on stdout, or NOTHING when no verdict is available yet
  * writes the per-criterion detail to <judge dir>/summary.json
  * ALWAYS exits 0, so the judge can never fail the run

Env:
  EVAL_API_KEY      proxy key; absent => skip the API backend entirely
  EVAL_BASE_URL     OpenAI-compatible base
  EVAL_MODEL        model name as registered on the proxy
  EVAL_USER         optional; sent as the request's `user` so the proxy can attribute spend
  PB_JUDGE_DIR      where the request/verdict live (default /logs/verifier/judge)
  PB_JUDGE_VERDICT  explicit path to verdict.json (overrides the default location)

IMPORTANT: never name a file in tests/ after a stdlib module (select.py, json.py, types.py,
io.py, queue.py). It shadows the real module and the failure surfaces somewhere unrelated.
The sys.path strip below defends against it.
"""
import os
import sys

_self_dir = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _self_dir]

import argparse
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_JUDGE_DIR = "/logs/verifier/judge"
# Bounded well inside the 2400s verifier timeout even in the worst case
# (API_ATTEMPTS * API_TIMEOUT_SEC + backoff).
API_TIMEOUT_SEC = 300
API_ATTEMPTS = 3
# Hunks for these paths never reach the judge: it must grade the fix, not the harness the
# submission may have edited.
EXCLUDE_RE = re.compile(
    r"(\.test\.[jt]sx?$|\.spec\.[jt]sx?$|(^|/)tests?/|(^|/)__tests__/|"
    r"(^|/)__snapshots__/|(^|/)node_modules/|(^|/)\.git/)"
)
BASE_REFS = ("harbor_base", "HEAD")

JUDGE_SYSTEM = (
    "You are a strict senior engineer grading the APPROACH of a code change -- not whether "
    "its tests pass. Score each rubric criterion STRICTLY BINARY: 1 = fully satisfied, "
    "0 = not satisfied. There is NO partial credit: if a criterion is only partially met, "
    "ambiguous, or has no clear evidence, score 0. Be strict; when unsure, score 0."
)


def judge_dir() -> Path:
    return Path(os.environ.get("PB_JUDGE_DIR") or DEFAULT_JUDGE_DIR)


def candidate_diff(repo: str, budget: int = 120_000) -> str:
    for ref in BASE_REFS:
        try:
            out = subprocess.run(["git", "-C", repo, "diff", ref],
                                 capture_output=True, text=True, timeout=120)
        except Exception as exc:
            sys.stderr.write("[judge] git diff failed: %s\n" % exc)
            return ""
        if out.returncode == 0 and out.stdout.strip():
            sys.stderr.write("[judge] diffing against %s\n" % ref)
            return filter_diff(out.stdout, budget)
    sys.stderr.write("[judge] no non-empty diff found\n")
    return ""


def filter_diff(diff: str, budget: int) -> str:
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
    return blob[:budget] + "\n[... truncated ...]\n" if len(blob) > budget else blob


def build_user_prompt(criteria, diff: str, changed: str) -> str:
    """The API-backend counterpart of PROMPT.md, with the same inputs and exclusions.

    Deliberately withheld, exactly as in the sub-agent request: the task instruction, the
    golden fix.patch, tests/test.patch, and the screenshots. See the module docstring for
    why each one would corrupt the grade.
    """
    payload = json.dumps(
        [{"id": c["id"], "criterion": c["criterion"]} for c in criteria], indent=2
    )
    ids = ", ".join(c["id"] for c in criteria)
    parts = [
        "Grade the APPROACH of the code change below against each rubric criterion.",
        "",
        "## Criteria",
        payload,
        "",
        "## Candidate diff (test/spec/snapshot files already stripped)",
        "```diff",
        diff,
        "```",
    ]
    if changed.strip():
        parts += [
            "",
            "## Full current text of every file the diff touched",
            "Use this when a hunk alone is too little context to decide a criterion.",
            changed,
        ]
    parts += [
        "",
        "## Output",
        'Reply with JSON only, no prose and no code fences: {"scores": {"<id>": 0 or 1}}.',
        f"All {len(criteria)} ids must be present: {ids}.",
        "Score 1 only when the criterion is fully satisfied with clear evidence in the "
        "change; otherwise score 0. There is no partial credit.",
    ]
    return "\n".join(parts)


def extract_scores_object(text: str):
    """Parse the model reply into a dict, tolerating fences and surrounding prose."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\n?", "", candidate)
        candidate = re.sub(r"\n?```$", "", candidate.strip())
    try:
        return json.loads(candidate)
    except Exception:
        pass
    start, depth = None, 0
    for i, ch in enumerate(candidate):
        if ch == "{":
            if start is None:
                start = i
            depth += 1
        elif ch == "}" and start is not None:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(candidate[start : i + 1])
                except Exception:
                    start, depth = None, 0
    return None


def call_eval_api(criteria, diff: str, changed: str):
    """Grade via the proxy. Returns a scores-shaped dict, or None to fall back.

    Never raises: every failure path returns None so the caller can fall through to the
    sub-agent request and the run is never failed by the judge.
    """
    api_key = (os.environ.get("EVAL_API_KEY") or "").strip()
    base_url = (os.environ.get("EVAL_BASE_URL") or "").strip().rstrip("/")
    model = (os.environ.get("EVAL_MODEL") or "").strip()
    if not api_key or not base_url or not model:
        sys.stderr.write(
            "[judge] API backend unavailable (EVAL_API_KEY/EVAL_BASE_URL/EVAL_MODEL "
            "incomplete); falling back to the sub-agent request\n"
        )
        return None

    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": build_user_prompt(criteria, diff, changed)},
        ],
    }
    # The proxy attributes spend per `user`; without it this call is unattributable.
    if os.environ.get("EVAL_USER"):
        body["user"] = os.environ["EVAL_USER"]

    url = base_url + "/chat/completions"
    data = json.dumps(body).encode("utf-8")
    for attempt in range(1, API_ATTEMPTS + 1):
        try:
            req = urllib.request.Request(
                url,
                data=data,
                method="POST",
                headers={
                    "Authorization": "Bearer %s" % api_key,
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=API_TIMEOUT_SEC) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            content = json.loads(raw)["choices"][0]["message"]["content"]
            obj = extract_scores_object(content)
            if not isinstance(obj, dict):
                sys.stderr.write(
                    "[judge] attempt %d: reply was not JSON: %r\n" % (attempt, content[:400])
                )
            else:
                sys.stderr.write("[judge] graded via API model=%s\n" % model)
                return obj
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                pass
            sys.stderr.write(
                "[judge] attempt %d: HTTP %s %s\n" % (attempt, exc.code, detail)
            )
            # 4xx other than 429 will not fix themselves; stop retrying.
            if 400 <= exc.code < 500 and exc.code != 429:
                break
        except Exception as exc:
            sys.stderr.write(
                "[judge] attempt %d: %s: %s\n" % (attempt, exc.__class__.__name__, exc)
            )
        if attempt < API_ATTEMPTS:
            time.sleep(2 ** attempt)
    sys.stderr.write("[judge] API backend gave up; falling back to the sub-agent request\n")
    return None


def write_request(criteria, diff, jdir: Path) -> None:
    """Lay down everything a judge sub-agent needs, with no further context."""
    jdir.mkdir(parents=True, exist_ok=True)
    payload = [{"id": c["id"], "criterion": c["criterion"]} for c in criteria]
    (jdir / "criteria_payload.json").write_text(json.dumps(payload, indent=2))
    (jdir / "source.txt").write_text(diff)
    verdict = jdir / "verdict.json"
    ids = ", ".join(c["id"] for c in criteria)
    (jdir / "PROMPT.md").write_text(f"""# Rubric judge (sub-agent)

You are the rubric judge. Grade the APPROACH of a code change, not whether its tests pass.

System contract:
{JUDGE_SYSTEM}

Inputs in this directory ({jdir}):
- `criteria_payload.json` — {len(criteria)} criteria, each {{id, criterion}}.
- `source.txt` — the candidate diff. Test, spec and snapshot files are already stripped out,
  so everything you see is product code the submission changed.

Score each criterion **1 or 0 — never 0.5 or any fraction**. 1 = fully satisfied,
0 = not satisfied, ambiguous, or no clear evidence. Be strict; when unsure, score 0.

The rubric is unweighted and every criterion is mandatory: a single 0 fails the whole rubric,
so do not withhold a 1 over style preferences the criterion does not actually state.

Write ONLY this JSON to `{verdict}`:

    {{"scores": {{"<criterion id>": {{"score": 0|1}}, ...}}}}

All {len(criteria)} ids must appear: {ids}. Verify the file parses before you finish.
""")


def read_verdict(criteria, jdir: Path):
    """Return ("pass"|"fail", failed_ids) or None when no usable verdict exists."""
    vp = Path(os.environ.get("PB_JUDGE_VERDICT") or (jdir / "verdict.json"))
    if not vp.is_file():
        return None
    try:
        obj = json.loads(vp.read_text())
    except Exception as exc:
        sys.stderr.write("[judge] verdict unreadable (%s)\n" % exc)
        return None
    scores = obj.get("scores", obj)
    if not isinstance(scores, dict):
        sys.stderr.write("[judge] verdict has no scores map\n")
        return None
    failed, graded = [], 0
    for c in criteria:
        raw = scores.get(c["id"])
        if raw is None:
            failed.append(c["id"])            # not graded == not demonstrated == fail
            continue
        try:
            v = float(raw.get("score") if isinstance(raw, dict) else raw)
        except (TypeError, ValueError, AttributeError):
            failed.append(c["id"])
            continue
        graded += 1
        if v < 1.0:                            # strictly binary: only a full 1 passes
            failed.append(c["id"])
    if graded == 0:
        sys.stderr.write("[judge] verdict contained no usable scores\n")
        return None
    return ("fail" if failed else "pass"), failed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rubrics", required=True)
    ap.add_argument("--repo", default="/app")
    ap.add_argument("--judge-dir", default=None)
    a = ap.parse_args()

    jdir = Path(a.judge_dir) if a.judge_dir else judge_dir()
    try:
        doc = json.load(open(a.rubrics))
    except Exception as exc:
        sys.stderr.write("[judge] cannot read %s: %s\n" % (a.rubrics, exc))
        return 0
    criteria = [c for c in (doc.get("criteria") or []) if c.get("id") and c.get("criterion")]
    if not criteria:
        sys.stderr.write("[judge] no criteria in %s\n" % a.rubrics)
        return 0

    def emit(verdict, failed) -> int:
        """Publish a verdict: summary.json, then stdout LAST."""
        try:
            jdir.mkdir(parents=True, exist_ok=True)
            json.dump({"rubric": verdict, "failed": failed,
                       "criteria_total": len(criteria)},
                      open(jdir / "summary.json", "w"), indent=2)
        except Exception:
            pass
        sys.stderr.write("[judge] verdict=%s%s\n"
                         % (verdict, (" failed=%s" % ", ".join(failed)) if failed else ""))
        print(verdict)
        return 0

    # An existing verdict.json always wins: it is either a sub-agent verdict or this
    # script's own API result being rescored, and re-grading would cost a second call.
    res = read_verdict(criteria, jdir)
    if res is not None:
        return emit(*res)

    diff = candidate_diff(a.repo)
    if not diff.strip():
        sys.stderr.write("[judge] empty candidate diff; nothing to grade\n")
        return 0

    # Preferred: grade in-band via the proxy. Persist the scores as verdict.json so the
    # grade is auditable and a rescore is idempotent, then score it through read_verdict
    # so both backends share one scoring path.
    scores = call_eval_api(criteria, diff, "")
    if scores is not None:
        try:
            jdir.mkdir(parents=True, exist_ok=True)
            (jdir / "verdict.json").write_text(json.dumps(scores, indent=2))
        except OSError as exc:
            sys.stderr.write("[judge] could not persist verdict.json: %s\n" % exc)
        res = read_verdict(criteria, jdir)
        if res is not None:
            return emit(*res)
        sys.stderr.write("[judge] API verdict had no usable scores; writing the request\n")

    # Fallback: lay down the sub-agent request and stay silent.
    write_request(criteria, diff, jdir)
    sys.stderr.write(
        "[judge] no verdict at %s yet; wrote the judge request to %s "
        "(criteria_payload.json, source.txt, PROMPT.md). Have the judge sub-agent produce "
        "verdict.json, then rescore. Scoring on tests alone until then.\n"
        % (jdir / "verdict.json", jdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
