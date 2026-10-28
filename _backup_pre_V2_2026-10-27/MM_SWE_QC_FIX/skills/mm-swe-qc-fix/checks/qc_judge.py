#!/usr/bin/env python3
"""Step 7.6 - verify the RUBRIC JUDGE MECHANICS (the rubric-template plumbing) - NEW in v3.1.

Usage:
    python3 check_judge.py "task_<taskId>/deliverables"    # the four-folder root
    python3 check_judge.py "path/to/Tasks"                 # a bare Tasks/

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

  * JUDGE_FILE   tests/judge.py exists, is non-empty, compiles.               [Fail - Rubric Quality]
  * JUDGE_SHAPE  judge.py carries the template's load-bearing markers         (candidate; confirm vs template)
                 (sys.path strip, sub-agent two-phase, exits 0).
  * NO_CREDS     task.toml has NO [verifier.env] and NO ANTHROPIC_* /         [Fail - Broken Structure]
                 JUDGE_MODEL (leftovers from the legacy "api" backend).
  * CONFIG       tests/config.json has "rubric_file": "rubrics.json".         [Fail - Rubric Quality]
  * TEST_SH      tests/test.sh runs judge.py, passes --rubric to the          [Fail - Broken Structure]
                 verifier, and keeps the load-bearing `|| echo ""`.
  * VERIFIER     tests/verifier.py parses --rubric and gates 1.0 -> 0.5.      (candidate)
  * NO_SHADOW    no file in tests/ is named after a stdlib module             [Fail - Rubric Quality]
                 (select.py, json.py, types.py, io.py, queue.py, ...).

Heuristics flag CANDIDATES (confirm by hand) unless marked [FAIL]. The behavioural half of
Step 7.6 (a judge request appears under the run's verifier/judge/, and oracle shows
`rubric: "pass"` after `rescore`) needs the gate run and is printed as a manual step. Standard
library only; never runs the judge or the verifier.
"""
import sys, os, re, py_compile, tempfile


# AGREED ERROR CATEGORY (2026-08-03). The rubric's structure dimension enumerates a CLOSED list
# of 11 files: task.toml, instruction.md, evidence_bundle.json, environment/Dockerfile,
# ASSET_MANIFEST.json, solution/fix.patch, solution/solve.sh, tests/config.json,
# tests/test.patch, tests/test.sh, tests/verifier.py. `tests/rubrics.json` and `tests/judge.py`
# are NOT in it, so a missing or broken rubric/judge is booked on the RUBRIC dimension, not as
# [Fail - Broken Structure]. Getting this wrong puts the wrong value in the eval dropdown even
# when the defect itself was spotted correctly.
RUBRIC_DIM = "[Fail - Rubric Quality]"
STRUCT_DIM = "[Fail - Broken Structure]"      # only for files in the closed 11

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


def locate(root):
    root = os.path.normpath(root)
    base = os.path.basename(root)
    if base == "Tasks":
        return root
    if os.path.isdir(os.path.join(root, "Tasks")):
        return os.path.join(root, "Tasks")
    if os.path.isfile(os.path.join(root, "task.toml")):
        return root
    return None


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
                    "[Fail - Rubric Quality]")
        return None
    if os.path.getsize(jp) == 0:
        add("FAIL", "tests/judge.py is EMPTY. [Fail - Rubric Quality]")
        return None
    try:
        py_compile.compile(jp, cfile=os.path.join(tempfile.gettempdir(), "qc_judge_check.pyc"), doraise=True)
        add("INFO", "tests/judge.py present and compiles")
    except Exception as e:
        add("FAIL", f"tests/judge.py does not compile: {e}. [Fail - Rubric Quality]")
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
        add("FAIL", "task.toml missing - cannot confirm the judge is keyless. [Fail - Broken Structure]")
        return
    hits = re.findall(r"ANTHROPIC_[A-Z_]+|JUDGE_MODEL", txt)
    if "[verifier.env]" in txt:
        add("FAIL", "task.toml has a [verifier.env] block - the sub-agent judge needs NO env. "
                    "Remove it (legacy 'api' backend). [Fail - Rubric Quality]")
    if hits:
        add("FAIL", f"task.toml references {sorted(set(hits))} - the judge is a sub-agent and needs "
                    f"no credentials. Remove them. [Fail - Rubric Quality]")
    if not hits and "[verifier.env]" not in txt:
        add("INFO", "task.toml is keyless (no [verifier.env], no ANTHROPIC_* / JUDGE_MODEL)")


def check_config(tasks):
    cp = os.path.join(tasks, "tests", "config.json")
    txt = read(cp)
    if txt is None:
        add("FAIL", "tests/config.json missing - it is one of the closed 11 files. "
                    "[Fail - Broken Structure]")
        return
    if '"rubric_file"' not in txt:
        add("FAIL", 'tests/config.json has no "rubric_file" key - the rubric is never picked up. '
                    'Add "rubric_file": "rubrics.json". [Fail - Rubric Quality]')
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
        add("FAIL", "tests/test.sh missing - it is one of the closed 11 files. [Fail - Broken Structure]")
        return
    if "judge.py" not in txt:
        add("FAIL", "tests/test.sh never invokes judge.py - the rubric is not run. "
                    "[Fail - Rubric Quality]")
    # Must be --rubric passed to the VERIFIER, not judge.py's own --rubrics flag. A plain
    # substring test matches "--rubrics" and so can never fail, which let a task compute
    # RUBRIC and then call verifier.py without it -- every verdict silently discarded.
    passes_rubric = re.search(r"verifier\.py[^\n|;&]*--rubric(?!s)", txt) is not None
    if not passes_rubric:
        add("WARN", "tests/test.sh does not pass --rubric to verifier.py - the verdict can't reach "
                    "the gate (note: judge.py's own --rubrics does NOT count). "
                    "Confirm the verifier call.")
    if 'judge.py' in txt and '|| echo ""' not in txt and "|| echo ''" not in txt:
        add("WARN", 'tests/test.sh runs judge.py without the load-bearing `|| echo \"\"` - the judge '
                    'must never be able to fail the run.')
    if txt and "judge.py" in txt and passes_rubric:
        add("INFO", "tests/test.sh invokes judge.py and passes --rubric to the verifier")


def check_verifier(tasks):
    vp = os.path.join(tasks, "tests", "verifier.py")
    txt = read(vp)
    if txt is None:
        add("FAIL", "tests/verifier.py missing. [Fail - Broken Structure]")
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
                    f"real module and fail somewhere unrelated. Rename them. [Fail - Broken Structure]")
    else:
        add("INFO", "no tests/ file shadows a stdlib module")


def note_placeholder(tasks):
    rp = os.path.join(tasks, "tests", "rubrics.json")
    txt = read(rp) or ""
    if PLACEHOLDER.search(txt):
        add("INFO", "rubrics.json looks like the always-pass stub - the judge wiring should still be "
                    "correct, but the judge has nothing substantive to grade (valid only if the task "
                    "is genuinely 100% behavioral-test-covered).")


# ------------------------------------------------- checks ADDED in MM_SWE_QC
def check_hygiene(tasks):
    """Compiled bytecode and other build junk must not ship in a deliverable."""
    import glob
    junk = []
    for pat in ("**/__pycache__", "**/*.pyc", "**/.DS_Store", "**/node_modules"):
        junk += [p for p in glob.glob(os.path.join(tasks, pat), recursive=True)]
    if junk:
        rels = sorted({os.path.relpath(j, tasks) for j in junk})
        add("FAIL", f"build junk committed in the bundle: {rels[:6]}"
                    f"{' ...' if len(rels) > 6 else ''}. A stale .pyc can shadow a deleted .py. "
                    f"[Fail - Broken Structure]")
    else:
        add("INFO", "no __pycache__ / .pyc / .DS_Store / node_modules in the bundle")


def check_testsh_syntax(tasks):
    """test.sh is grepped elsewhere but never parsed; a syntax error scores 0.0 everywhere."""
    import subprocess
    ts = os.path.join(tasks, "tests", "test.sh")
    if not os.path.isfile(ts):
        return
    try:
        r = subprocess.run(["bash", "-n", ts], capture_output=True, text=True, timeout=30)
    except Exception as exc:
        add("WARN", f"could not syntax-check tests/test.sh ({exc})"); return
    if r.returncode != 0:
        add("FAIL", f"tests/test.sh is not valid bash: {r.stderr.strip().splitlines()[:2]}. "
                    f"Every run would score 0.0. [Fail - Broken Structure]")
    else:
        add("INFO", "tests/test.sh parses (bash -n)")


def check_judge_identical(tasks, template=None):
    """judge.py must be byte-identical to the shipped template - a contributor editing the
    judge changes grading semantics invisibly."""
    import hashlib
    jp = os.path.join(tasks, "tests", "judge.py")
    if not os.path.isfile(jp):
        return
    tpl = template or os.environ.get("MM_RUBRIC_TEMPLATE")
    if not tpl or not os.path.isfile(tpl):
        add("MANUAL", "judge.py byte-identity vs the rubric-template copy not checked "
                      "(set MM_RUBRIC_TEMPLATE=/path/to/rubric-template/tests/judge.py)")
        return
    h = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()
    if h(jp) == h(tpl):
        add("INFO", "tests/judge.py is byte-identical to the rubric-template copy")
    else:
        add("FAIL", f"tests/judge.py DIFFERS from the template ({tpl}) - the judge was edited, "
                    f"which changes grading semantics. [Fail - Rubric Quality]")


# ------------------------------------------------- reward.json shape (ADDED)
# harbor parses reward.json into VerifierResult.rewards: dict[str, float] and takes it in
# PREFERENCE to reward.txt. Any non-numeric top-level value raises a pydantic ValidationError
# that aborts the trial before a reward is recorded - and because reward.txt is still written
# inside the container, the run LOOKS scored while harbor stored nothing. Credit: this failure
# mode was identified in the review toolkit (v3.2a).
NON_NUMERIC_KEYS = {"f2p", "p2p", "rubric", "rubric_failed", "failed", "failed_ids",
                    "breakdown", "tests", "detail", "details"}
_NUMERIC_RHS = re.compile(r"^(-?\d|float\(|int\(|len\(|sum\(|round\(|abs\(|min\(|max\()")
_LITERAL_NON_NUMERIC_RHS = re.compile(r"""^(["']|\[|\{|None\b|True\b|False\b|f["'])""")
# A subscript/lookup on a literal yields a SCALAR, so `{"pass": 1}.get(x, -1)` and
# `{...}[k]` are numeric even though the RHS starts with `{`. Without this the check flags the
# canonical `rubric_pass` line - i.e. it fails the very convention it exists to enforce.
_LOOKUP_ON_LITERAL = re.compile(r"^[\{\[].*[\}\]]\s*(\.get\(|\[)")


def check_reward_json_numeric(tasks):
    vp = os.path.join(tasks, "tests", "verifier.py")
    if not os.path.isfile(vp):
        return
    txt = open(vp, errors="replace").read()
    if "reward.json" not in txt:
        return
    m = re.search(r"json\.dump\(\s*([A-Za-z_]\w*)", txt)
    if not m:
        add("WARN", "verifier.py writes reward.json but the dumped object could not be traced - "
                    "confirm BY HAND that every top-level value is a plain float/int.")
        return
    var, offenders = m.group(1), []
    for key, rhs in re.findall(rf"\b{re.escape(var)}\[[\"']([^\"']+)[\"']\]\s*=\s*(.+)", txt):
        if "#" in rhs and not re.match(r"""^\s*["']""", rhs):
            rhs = rhs.split("#", 1)[0]
        rhs = rhs.strip().rstrip(",")
        if _NUMERIC_RHS.match(rhs) or _LOOKUP_ON_LITERAL.match(rhs):
            continue
        if key in NON_NUMERIC_KEYS or _LITERAL_NON_NUMERIC_RHS.match(rhs):
            offenders.append(f"{key} = {rhs[:44]}")
    if offenders:
        add("FAIL", f"verifier.py writes NON-NUMERIC value(s) into reward.json: {offenders}. "
                    f"harbor parses it as dict[str, float] and prefers it to reward.txt, so this "
                    f"aborts the trial with a ValidationError while reward.txt still gets written "
                    f"- the run looks scored but nothing is stored. Flatten per-test outcomes to "
                    f"`f2p::<name>` = 1.0/0.0. [Fail - Gate Broken]")
    else:
        add("INFO", "verifier.py's reward.json values look numeric (harbor-parseable)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    tasks = locate(sys.argv[1])

    print(f"\nVarmint Sheriffs judge-mechanics verification (v3.1 Step 7.6) - "
          f"{os.path.abspath(sys.argv[1])}")
    print(f"Tasks/ = {tasks or 'NOT FOUND'}\n")

    if not tasks:
        add("FAIL", "no Tasks/ dir found - cannot audit judge mechanics. [Fail - Broken Structure]")
        _report()
        return

    check_judge_file(tasks)
    check_creds(tasks)
    check_config(tasks)
    check_test_sh(tasks)
    check_verifier(tasks)
    check_shadow(tasks)
    note_placeholder(tasks)
    # --- added in MM_SWE_QC ---
    check_hygiene(tasks)
    check_testsh_syntax(tasks)
    check_judge_identical(tasks)
    check_reward_json_numeric(tasks)

    add("MANUAL", "BEHAVIOURAL (manual, needs the gate run): reproduce oracle/nop (Step 0.6), then "
                  "confirm a judge request (criteria_payload.json, source.txt, changed_files.txt, "
                  "PROMPT.md) appeared "
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
    # MM_SWE_QC: the orchestrator keys off the exit code, so a hard [FAIL] must be non-zero.
    sys.exit(1 if fail_count else 0)

