#!/usr/bin/env bash
# =============================================================================
# Behavioural verifier for fossasia__eventyay-4158-mm.
#
# eventyay-specific bits that EVERY task from this repo needs (keep them when
# retargeting this harness at another eventyay candidate):
#   * the python project root is /app/app, not /app  -> `cd /app/app` for pytest
#   * eventyay has no sqlite fallback                -> `harbor_pg_start` first
#     (the helper is baked into the image; it starts the in-image PostgreSQL
#     cluster over loopback, which needs no network)
#   * DJANGO_SETTINGS_MODULE comes from app/pyproject.toml, do not override it
#   * NOTHING is installed here — the verify run is OFFLINE.
#
# The suite is run, never grepped: no source file is inspected for the fix.
# =============================================================================
set -uo pipefail

mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml

: > "$STDOUT_LOG"
: > "$STDERR_LOG"

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# ── Robustness + idempotency ──────────────────────────────────────────────────
# 1. Restore EVERY path test.patch touches to the pristine harbor_base state, so
#    agent edits to test files cannot affect scoring and the apply is idempotent.
#    Paths come from the `diff --git a/... b/...` headers, which exist for every
#    entry type (text, binary, rename, delete) unlike `+++ b/`.
# 2. Additionally restore the whole test tree, which is where any PRE-EXISTING
#    test scored as p2p would live — those are not named in test.patch and would
#    otherwise be tamperable.
# 3. Clean ONLY the directories named by the patch. A bare `git clean -fdq -- .`
#    would wipe /app/.harbor_assets and the agent's own new files.
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
    sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
  } | sort -u
)
for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null \
    || rm -f "/app/$_p" 2>/dev/null \
    || true
done
git -C /app checkout harbor_base -- app/tests 2>/dev/null || true
git -C /app clean -fdq -- $(printf '%s\n' $_patch_paths | xargs -r -n1 dirname | sort -u) 2>/dev/null || true

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# ── Database ──────────────────────────────────────────────────────────────────
# eventyay only supports PostgreSQL (django.contrib.postgres / JSONB / ARRAY).
# The cluster and the `pretix` database were created at IMAGE BUILD time; this
# only starts the server on 127.0.0.1:5432. Offline.
echo "== starting in-image postgres ==" | tee -a "$STDOUT_LOG"
harbor_pg_start >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || { echo "ERROR: postgres unavailable" | tee -a "$STDERR_LOG"; exit 1; }

# ── Test-only deps ────────────────────────────────────────────────────────────
# pytest / pytest-django / pytest-env and the full application dependency set are
# BAKED at image build time (`uv sync --frozen --all-extras --group test`).
echo "== checking pinned test deps (no install) ==" | tee -a "$STDOUT_LOG"
python -c "import pytest, django, pytest_django; print('pytest', pytest.__version__, '| django', django.get_version())" \
  | tee -a "$STDOUT_LOG"

# ── Run f2p + p2p tests ───────────────────────────────────────────────────────
# Only the suite added by test.patch is run; it holds every f2p and every p2p.
# `-p no:cacheprovider` keeps /app free of .pytest_cache, `-p no:randomly` /
# `-p no:sugar` keep the report deterministic and machine-readable.
echo "== running f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
cd /app/app || { echo "no /app/app" | tee -a "$STDERR_LOG"; exit 1; }

run_suite() {
  python -m pytest \
    "tests/harborreviewscores4158/test_review_score_validation.py" \
    -p no:cacheprovider -p no:sugar -p no:xdist \
    -q --junitxml="$REPORT" \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "(tests exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"
}

report_has_testcases() {
  python3 - "$REPORT" <<'PY'
import sys, os, xml.etree.ElementTree as ET
path = sys.argv[1]
if not os.path.exists(path):
    sys.exit(1)
try:
    tree = ET.parse(path)
except Exception:
    sys.exit(1)
sys.exit(0 if next(tree.iter('testcase'), None) is not None else 1)
PY
}

run_suite

# One-shot retry ONLY when the report is missing or carries ZERO <testcase> elements --
# i.e. the runner crashed or collection aborted before any test was recorded, which would
# otherwise be scored as a false 0.0.  A report full of FAILURES is a real verdict and is
# never retried.
if ! report_has_testcases; then
  echo "== JUnit report has no testcases; retrying the suite once ==" | tee -a "$STDOUT_LOG"
  rm -f "$REPORT"
  run_suite
  report_has_testcases \
    && echo "== retry produced a populated report ==" | tee -a "$STDOUT_LOG" \
    || echo "== retry still produced no testcases ==" | tee -a "$STDERR_LOG"
fi

# ── Compute reward ────────────────────────────────────────────────────────────
echo "== computing reward ==" | tee -a "$STDOUT_LOG"
# Rubric judge - SUB-AGENT backend: no API key, no network. On the first pass there is no
# verdict yet, so judge.py writes a judge request under /logs/verifier/judge/ and prints
# nothing. The `|| echo ""` is load-bearing: the judge must never be able to fail the run.
RUBRIC=""
if [ -f /tests/rubrics.json ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app \
             2>/logs/verifier/judge.log || echo "")
  echo "Rubric verdict: ${RUBRIC:-pending (judge request written; rescore after grading)}"
fi

python3 /tests/verifier.py --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
