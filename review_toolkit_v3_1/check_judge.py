#!/usr/bin/env python3
"""Step 7.6 - verify the RUBRIC JUDGE MECHANICS (the rubric-template plumbing) - NEW in v3.1.

Usage:
    python3 check_judge.py "task_<taskId>/deliverables"    # the four-folder root
    python3 check_judge.py "path/to/Tasks"                 # a bare Tasks/
    python3 check_judge.py "path/to/Tasks/<task_id>"       # the bundle itself (V2)

Layouts: V2 (TASK101+) nests the bundle at Tasks/<task_id>/; V1 kept task.toml directly in Tasks/.

NEW COMPONENT (v3.1). `check_rubrics.py` (Step 0.55) audits the rubric *content*; this script
audits the *machinery that runs it* - the `rubric-template` files wired into `tests/`. The judge
is a **sub-agent**: the verifier NEVER calls a model. It is two-phase - (1) during the run
`tests/judge.py` finds no verdict, writes a self-contained judge request under
`/logs/verifier/judge/`, and scores on tests alone; (2) after the run a judge sub-agent writes
`verdict.json` and `mm_run.sh <task> rescore` folds it into the reward from the existing JUnit XML.
The rubric is therefore **compatible with, not a replacement for, the keyless gate**: separate at
run time, folded into `reward.txt`/`reward.json` only at rescore time, and it can only turn a `1.0`
into `0.5`, never toward `0.0`.

This script statically confirms the task ships a working, keyless sub-agent judge:

  * JUDGE_FILE   tests/judge.py exists, is non-empty, compiles.               [FAIL - Missing/Broken Rubrics]
  * JUDGE_SHAPE  judge.py carries the template's load-bearing markers         (candidate; confirm vs template)
                 (sys.path strip, sub-agent two-phase, exits 0).
  * NO_CREDS     task.toml has NO [verifier.env] and NO ANTHROPIC_* /         [FAIL - Broken Structure]
                 JUDGE_MODEL (leftovers from the legacy "api" backend).
  * CONFIG       tests/config.json has "rubric_file": "rubrics.json".         [FAIL - Missing/Broken Rubrics]
  * TEST_SH      tests/test.sh runs judge.py, passes --rubric to the          [FAIL - Broken Structure]
                 verifier, and keeps the load-bearing `|| echo ""`.
  * VERIFIER     tests/verifier.py parses --rubric and gates 1.0 -> 0.5.      (candidate)
  * NO_SHADOW    no file in tests/ is named after a stdlib module             [FAIL - Broken Structure]
                 (select.py, json.py, types.py, io.py, queue.py, ...).

Heuristics flag CANDIDATES (confirm by hand) unless marked [FAIL]. The behavioural half of
Step 7.6 (a judge request appears under the run's verifier/judge/, and oracle shows
`rubric: "pass"` after `rescore`) needs the gate run and is printed as a manual step. Standard
library only; never runs the judge or the verifier.
"""
import sys, os, re, py_compile, tempfile

# stdlib modules a tests/ file must never shadow (a shadow fails somewhere unrelated).
STDLIB_SHADOW = {
    "select.py", "json.py", "types.py", "io.py", "queue.py", "re.py", "os.py", "sys.py",
    "abc.py", "enum.py", "copy.py", "time.py", "string.py", "token.py", "code.py",
    "keyword.py", "signal.py", "socket.py", "struct.py", "array.py", "random.py",
}
# always-pass stub markers (a stub task legitimately needs no real judge grading, but the
# wiring should still be present and correct if judge.py ships).
PLACEHOLDER = re.compile(r"always[_-]pass|written in english", re.I)


def read(path):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()
    except Exception:
        return None


BUNDLE_MARKERS = ("task.toml", "instruction.md", "tests", "solution", "environment")


def looks_like_bundle(d):
    return any(os.path.exists(os.path.join(d, m)) for m in BUNDLE_MARKERS)


def task_dirs(tasks):
    """Every bundle in a Tasks/ folder: Tasks/ itself (V1) or each Tasks/<task_id>/ (V2)."""
    if looks_like_bundle(tasks):
        return [tasks]
    return sorted(os.path.join(tasks, d) for d in os.listdir(tasks)
                  if os.path.isdir(os.path.join(tasks, d)) and looks_like_bundle(os.path.join(tasks, d)))


def locate(root):
    """The bundle (the folder holding task.toml) for the deliverables root, Tasks/, or the
    bundle itself: Tasks/<task_id>/ in V2 (TASK101+), Tasks/ in V1. None if absent/ambiguous."""
    root = os.path.normpath(root)
    tasks = root if os.path.basename(root) == "Tasks" else os.path.join(root, "Tasks")
    if os.path.isfile(os.path.join(root, "task.toml")) or (
            not os.path.isdir(tasks) and looks_like_bundle(root)):
        return root
    if not os.path.isdir(tasks):
        return None
    found = task_dirs(tasks)
    if len(found) > 1:
        print(f"warning: {len(found)} task bundles under {tasks} - pass the one to check: "
              f"{[os.path.basename(f) for f in found]}", file=sys.stderr)
    return found[0] if len(found) == 1 else None


findings = []      # (level, msg)   level in {FAIL, WARN, INFO, MANUAL}
fail_count = 0


def add(level, msg):
    global fail_count
    findings.append((level, msg))
    if level == "FAIL":
        fail_count += 1


def check_judge_file(tasks):
    jp = os.path.join(tasks, "tests", "judge.py")
    if not os.path.exists(jp):
        add("FAIL", "tests/judge.py MISSING - the rubric-template judge harness is not wired in. "
                    "[FAIL - Missing/Broken Rubrics]")
        return None
    if os.path.getsize(jp) == 0:
        add("FAIL", "tests/judge.py is EMPTY. [FAIL - Missing/Broken Rubrics]")
        return None
    try:
        # cfile outside the bundle: the default writes tests/__pycache__/ INTO the deliverable
        py_compile.compile(jp, cfile=os.path.join(tempfile.gettempdir(), "qc_judge_check.pyc"), doraise=True)
        add("INFO", "tests/judge.py present and compiles")
    except Exception as e:
        add("FAIL", f"tests/judge.py does not compile: {e}. [FAIL - Missing/Broken Rubrics]")
        return None
    txt = read(jp) or ""
    # load-bearing markers from the template (never edit judge.py; these confirm it wasn't gutted)
    markers = {
        "sys.path strip (stdlib-shadow defence)": "sys.path[:]",
        "sub-agent, no API key": re.compile(r"NO API KEY|no api key|sub-agent", re.I),
        "writes the judge request": "write_request",
        "reads the verdict": "read_verdict",
        "always exits 0": re.compile(r"return 0|exit\(0\)|sys\.exit\(0\)|sys\.exit\(main", re.I),
    }
    missing = []
    for label, pat in markers.items():
        found = pat.search(txt) if hasattr(pat, "search") else (pat in txt)
        if not found:
            missing.append(label)
    if missing:
        add("WARN", f"tests/judge.py is missing expected template marker(s): {missing}. It must be "
                    f"the verbatim rubric-template judge.py - diff it against the template.")
    else:
        add("INFO", "tests/judge.py carries the template's load-bearing markers (still confirm "
                    "byte-for-byte against the rubric-template copy)")
    return txt


def check_creds(tasks):
    tp = os.path.join(tasks, "task.toml")
    txt = read(tp)
    if txt is None:
        add("FAIL", "task.toml missing - cannot confirm the judge is keyless. [FAIL - Broken Structure]")
        return
    hits = re.findall(r"ANTHROPIC_[A-Z_]+|JUDGE_MODEL", txt)
    if "[verifier.env]" in txt:
        add("FAIL", "task.toml has a [verifier.env] block - the sub-agent judge needs NO env. "
                    "Remove it (legacy 'api' backend). [FAIL - Broken Structure]")
    if hits:
        add("FAIL", f"task.toml references {sorted(set(hits))} - the judge is a sub-agent and needs "
                    f"no credentials. Remove them. [FAIL - Broken Structure]")
    if not hits and "[verifier.env]" not in txt:
        add("INFO", "task.toml is keyless (no [verifier.env], no ANTHROPIC_* / JUDGE_MODEL)")


def check_config(tasks):
    cp = os.path.join(tasks, "tests", "config.json")
    txt = read(cp)
    if txt is None:
        add("FAIL", "tests/config.json missing - cannot confirm rubric_file wiring. "
                    "[FAIL - Missing/Broken Rubrics]")
        return
    if '"rubric_file"' not in txt:
        add("FAIL", 'tests/config.json has no "rubric_file" key - the rubric is never picked up. '
                    'Add "rubric_file": "rubrics.json". [FAIL - Missing/Broken Rubrics]')
    elif not re.search(r'"rubric_file"\s*:\s*"rubrics\.json"', txt):
        add("WARN", 'tests/config.json "rubric_file" is present but not "rubrics.json" - confirm it '
                    'points at the shipped rubric file.')
    else:
        add("INFO", 'tests/config.json wires "rubric_file": "rubrics.json"')
    for exotic in ("judge_model", "source_paths", "rubric_criteria"):
        if f'"{exotic}"' in txt:
            add("WARN", f'tests/config.json carries a non-standard key "{exotic}" - not part of the '
                        f'template; remove unless intentional.')


def check_test_sh(tasks):
    sp = os.path.join(tasks, "tests", "test.sh")
    txt = read(sp)
    if txt is None:
        add("FAIL", "tests/test.sh missing. [FAIL - Broken Structure]")
        return
    if "judge.py" not in txt:
        add("FAIL", "tests/test.sh never invokes judge.py - the rubric is not run. "
                    "[FAIL - Broken Structure]")
    if "--rubric" not in txt:
        add("WARN", "tests/test.sh does not pass --rubric to verifier.py - the verdict can't reach "
                    "the gate. Confirm the verifier call.")
    if 'judge.py' in txt and '|| echo ""' not in txt and "|| echo ''" not in txt:
        add("WARN", 'tests/test.sh runs judge.py without the load-bearing `|| echo \"\"` - the judge '
                    'must never be able to fail the run.')
    if txt and "judge.py" in txt and '--rubric' in txt:
        add("INFO", "tests/test.sh invokes judge.py and passes --rubric to the verifier")


def check_verifier(tasks):
    vp = os.path.join(tasks, "tests", "verifier.py")
    txt = read(vp)
    if txt is None:
        add("FAIL", "tests/verifier.py missing. [FAIL - Broken Structure]")
        return
    if "--rubric" not in txt:
        add("WARN", "tests/verifier.py does not parse --rubric - the rubric gate is not applied "
                    "(confirm the 5 template edits were made).")
    else:
        add("INFO", "tests/verifier.py parses --rubric")
    if "reward.json" not in txt:
        add("WARN", "tests/verifier.py does not write reward.json - the per-test map is needed to "
                    "answer 'did this f2p pass on nop?' (aggregate 0.5 can't).")
    # gate should withhold 1.0 -> 0.5 only, never push toward 0.0
    if re.search(r'==\s*["\']fail["\']', txt) and "0.5" not in txt:
        add("WARN", "tests/verifier.py checks a 'fail' rubric but no 0.5 gate value is visible - "
                    "confirm the gate turns 1.0 into 0.5 (never toward 0.0).")


def check_shadow(tasks):
    tdir = os.path.join(tasks, "tests")
    if not os.path.isdir(tdir):
        return
    bad = [f for f in os.listdir(tdir) if f in STDLIB_SHADOW]
    if bad:
        add("FAIL", f"tests/ contains file(s) named after stdlib module(s): {bad} - they shadow the "
                    f"real module and fail somewhere unrelated. Rename them. [FAIL - Broken Structure]")
    else:
        add("INFO", "no tests/ file shadows a stdlib module")


def note_placeholder(tasks):
    rp = os.path.join(tasks, "tests", "rubrics.json")
    txt = read(rp) or ""
    if PLACEHOLDER.search(txt):
        add("INFO", "rubrics.json looks like the always-pass stub - the judge wiring should still be "
                    "correct, but the judge has nothing substantive to grade (valid only if the task "
                    "is genuinely 100% behavioral-test-covered).")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    tasks = locate(sys.argv[1])

    print(f"\nVarmint Sheriffs judge-mechanics verification (v3.1 Step 7.6) - "
          f"{os.path.abspath(sys.argv[1])}")
    print(f"task bundle = {tasks or 'NOT FOUND'}\n")

    if not tasks:
        add("FAIL", "no task bundle found (Tasks/<task_id>/ in V2, Tasks/ in V1) - cannot audit "
                    "judge mechanics. [FAIL - Broken Structure]")
        _report()
        return

    check_judge_file(tasks)
    check_creds(tasks)
    check_config(tasks)
    check_test_sh(tasks)
    check_verifier(tasks)
    check_shadow(tasks)
    note_placeholder(tasks)

    add("MANUAL", "BEHAVIOURAL (manual, needs the gate run): reproduce oracle/nop (Step 0.6), then "
                  "confirm a judge request (criteria_payload.json, source.txt, PROMPT.md) appeared "
                  "under the run's verifier/judge/, and that after grading + `rescore` the oracle "
                  "reward.json shows `rubric: \"pass\"`. reward.txt stays a bare float in "
                  "{0.0, 0.5, 1.0}; a failed rubric on an all-f2p-pass run reads 0.5, never 0.0.")

    _report()


LEVEL_ORDER = {"FAIL": 0, "WARN": 1, "MANUAL": 2, "INFO": 3}
LEVEL_TAG = {"FAIL": "[FAIL]", "WARN": "[check]", "MANUAL": "[manual]", "INFO": "[ok]"}


def _report():
    print("-- Judge-mechanics findings (v3.1 Step 7.6)")
    for level, msg in sorted(findings, key=lambda f: LEVEL_ORDER[f[0]]):
        print(f"     {LEVEL_TAG[level]:>8} {msg}")
    warns = sum(1 for l, _ in findings if l == "WARN")
    print(f"\nSUMMARY: {fail_count} hard [FAIL], {warns} candidate(s) to confirm by hand. A judge "
          f"[FAIL] is a Structure-class defect (broken/credentialed judge wiring) - fold it into "
          f"Step 10 like a #1 fault. Then run the behavioural half against the reproduced gate.")


if __name__ == "__main__":
    main()
