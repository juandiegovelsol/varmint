# API-BACKEND BLOCK for tests/judge.py -- lifted verbatim from reference/judge.py, which is
# byte-identical in both reference tasks and verified grading in-band in a live oracle run.
#
# Use this file ONLY if you are adding the API backend to a judge you already have. If you are
# writing tests/judge.py from scratch, or the existing one is the sub-agent-only stub, copy
# ../../reference/judge.py whole instead -- it needs no edits and it is task-agnostic.
#
# WHY THIS IS REQUIRED. A sub-agent-only judge cannot grade during the run: it writes a request,
# prints nothing, and the verifier scores on tests alone, so every run records
# rubric_passed = -1 until a human grades PROMPT.md and reruns rescore. That step is routinely
# skipped, which makes the rubric decorative. qc_rubric_format reports it as the blocking
# finding `rubfmt_judge_backend`.
#
# THE FUNCTION NAME IS LOAD-BEARING: the check greps for `call_eval_api`. Keep it.
#
# THREE THINGS TO MERGE, beyond pasting the code below:
#   1. imports:  json, os, re, sys, time, urllib.error, urllib.request
#   2. in main(), BEFORE falling back to write_request(), grade in-band and persist the scores
#      so the verdict is auditable and a rescore is idempotent:
#
#          scores = call_eval_api(criteria, diff, changed)
#          if scores is not None:
#              (jdir / "verdict.json").write_text(json.dumps(scores, indent=2))
#              res = read_verdict(criteria, jdir)      # ONE scoring path for BOTH backends
#              if res is not None:
#                  return emit(*res)
#
#   3. task.toml -- the block is inert without it, and this half IS auto-fixable:
#          [verifier]      network_mode = "public"
#          [verifier.env]  EVAL_API_KEY / EVAL_BASE_URL / EVAL_MODEL
#      python3 fix.py apply <Tasks> --approve verifier_network_mode --approve verifier_env --apply
#
# NEVER RAISES. Every failure path returns None so the caller falls through to the sub-agent
# request -- KEEP that fallback, it is what guarantees the judge can never fail a run.

# Bounded well inside the 2400s verifier timeout even in the worst case
# (API_ATTEMPTS * API_TIMEOUT_SEC + backoff).
API_TIMEOUT_SEC = 300
API_ATTEMPTS = 3

JUDGE_SYSTEM = (
    "You are a strict senior engineer grading the APPROACH of a code change -- not whether "
    "its tests pass. Score each rubric criterion STRICTLY BINARY: 1 = fully satisfied, "
    "0 = not satisfied. There is NO partial credit: if a criterion is only partially met, "
    "ambiguous, or has no clear evidence, score 0. Be strict; when unsure, score 0."
)


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
