#!/usr/bin/env python3
"""
Rubric judge — sub-agent backend. NO API KEY, NO NETWORK.

Binary and unweighted: every criterion is PASS/FAIL and every one is mandatory, so the
rubric passes only if all pass.

Two-phase, mirroring ProjectBench's tier3 sub-agent backend:

  Phase 1 (during the verifier run)
      No verdict exists yet, so this writes a self-contained judge request into the judge
      dir -- criteria_payload.json, source.txt (the candidate diff), changed_files.txt (the
      FULL text of every file the diff touched), and PROMPT.md -- prints nothing, and exits 0.
      The verifier then scores on tests alone.

      What the judge deliberately does NOT get: the task instruction (a criterion that has to
      defer to the prompt is a Major "not self-contained" rubric defect -- handing the judge the
      prompt would let such a criterion pass and hide the defect), the golden solution/fix.patch
      (seeing it turns
      the judge into a similarity checker, reintroducing the very overfitting the rubric exists
      to catch), the tests/test.patch (same failure mode, and the tests already score that),
      the before/after images (UI-evaluation criteria are out of scope by definition), and
      browse access to the wider repo (unavailable at rescore time, so it would work in phase 1
      and silently not in phase 2).

  Phase 2 (after the run, orchestrated outside the container)
      A judge sub-agent reads PROMPT.md and writes verdict.json next to it. Re-running this
      script (or `mm_run.sh <task> rescore`) reads that verdict and prints "pass" or "fail".

Because the judge never calls out, there is no proxy, no bridge, no credentials, and no
[verifier.env] block anywhere.

Contract (test.sh depends on all three):
  * prints "pass" or "fail" on stdout, or NOTHING when no verdict is available yet
  * writes the per-criterion detail to <judge dir>/summary.json
  * ALWAYS exits 0, so the judge can never fail the run

Env:
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
from pathlib import Path

DEFAULT_JUDGE_DIR = "/logs/verifier/judge"
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


def changed_paths(diff: str) -> list:
    """Paths touched by the (already harness-filtered) diff, in order."""
    out = []
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                p = parts[-1][2:]                  # strip the b/ prefix
                if p and p not in out:
                    out.append(p)
    return out


def collect_changed_files(repo: str, diff: str, budget: int = 200_000) -> str:
    """Full current text of every file the diff touched.

    A hunk shows three lines of context, which is often too little to decide a criterion that
    is genuinely true of the change (e.g. "the helper is defined in the same module"). Whole
    files remove that class of false 0 while staying bounded by the size of the change.
    """
    blob, used = [], 0
    for rel in changed_paths(diff):
        fp = Path(repo) / rel
        if not fp.is_file():                       # deleted or renamed away
            continue
        try:
            text = fp.read_text(errors="replace")
        except Exception:
            continue
        chunk = "\n===== %s =====\n%s" % (rel, text)
        if used + len(chunk) > budget:
            blob.append("\n[... remaining changed files omitted for length ...]\n")
            break
        blob.append(chunk); used += len(chunk)
    return "".join(blob)


def write_request(criteria, diff, jdir: Path, changed: str = "") -> None:
    """Lay down everything a judge sub-agent needs, with no further context."""
    jdir.mkdir(parents=True, exist_ok=True)
    payload = [{"id": c["id"], "criterion": c["criterion"]} for c in criteria]
    (jdir / "criteria_payload.json").write_text(json.dumps(payload, indent=2))
    (jdir / "source.txt").write_text(diff)
    extra = []
    if changed.strip():
        (jdir / "changed_files.txt").write_text(changed)
        extra.append("- `changed_files.txt` — the FULL current text of every file the diff "
                     "touched. Use it when a hunk alone is too little context to decide a "
                     "criterion.")
    extra_block = ("\n" + "\n".join(extra)) if extra else ""
    verdict = jdir / "verdict.json"
    ids = ", ".join(c["id"] for c in criteria)
    (jdir / "PROMPT.md").write_text(f"""# Rubric judge (sub-agent)

You are the rubric judge. Grade the APPROACH of a code change, not whether its tests pass.

System contract:
{JUDGE_SYSTEM}

Inputs in this directory ({jdir}):
- `criteria_payload.json` — {len(criteria)} criteria, each {{id, criterion}}.
- `source.txt` — the candidate diff. Test, spec and snapshot files are already stripped out,
  so everything you see is product code the submission changed.{extra_block}

You are NOT given the task instruction, the reference/golden fix, the tests, or the rest of the
repository. Judge only what is here. If a criterion cannot be decided from these inputs, score it 0 — but note that a
criterion which is undecidable here is a defect in the rubric, not in the submission.

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

    # Phase 2: a verdict is already there -> score it.
    res = read_verdict(criteria, jdir)
    if res is not None:
        verdict, failed = res
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

    # Phase 1: no verdict yet -> lay down the request and stay silent.
    diff = candidate_diff(a.repo)
    if not diff.strip():
        sys.stderr.write("[judge] empty candidate diff; nothing to grade\n")
        return 0
    changed = collect_changed_files(a.repo, diff)
    write_request(criteria, diff, jdir, changed=changed)
    sys.stderr.write(
        "[judge] no verdict at %s yet; wrote the judge request to %s (%s). Have the judge "
        "sub-agent produce verdict.json, then rescore. Scoring on tests alone until then.\n"
        % (jdir / "verdict.json", jdir, ", ".join(sorted(f.name for f in jdir.iterdir()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
