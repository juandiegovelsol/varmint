#!/usr/bin/env python3
"""Step 7.6 - verify the RUBRIC JUDGE MECHANICS (the rubric-template plumbing) - NEW in v3.1.

Usage:
    python3 check_judge.py "task_<taskId>/deliverables"    # the four-folder root
    python3 check_judge.py "path/to/Tasks"                 # a bare Tasks/

`check_rubrics.py` (Step 0.55) audits the rubric *content*; this script audits the *machinery that
runs it* - the `rubric-template` files wired into `tests/`.

THE JUDGE GRADES IN-BAND. `tests/judge.py` calls the model from inside the verifier phase
(`call_eval_api`), and in Mode A that is REQUIRED - qc_rubric_format owns that requirement
(`rubfmt_judge_backend`) together with the `task.toml` wiring it needs. The sub-agent path is the
FALLBACK, not the design: when no verdict can be obtained the judge writes a self-contained request
under `/logs/verifier/judge/`, prints nothing, and scoring falls back to tests alone; a sub-agent can
then write `verdict.json` and `mm_run.sh <task> rescore` folds it in from the existing JUnit XML.
That fallback is what guarantees the judge can never fail a run. What is barred is shipping it as the
only route to a verdict - a rubric that only ever grades on a manual follow-up is decorative, and the
follow-up is routinely skipped.

This header used to say the verifier NEVER calls a model, and that the rubric was therefore
"compatible with, not a replacement for, the keyless gate". Both describe the superseded sub-agent-
only design. Only a Mode B task is keyless now; a Mode A verifier holds `EVAL_*` credentials
precisely so it can grade during the run.

THE REWARD IS BINARY: `{0.0, 1.0}`. A failed rubric forces `0.0` - it does NOT cap at `0.5`, and
there is no middle rung for a partial fix either, because the four count keys already carry how
close it got. A `pass` or a `not graded` verdict never lowers a score. `rubric_passed` records
`1` pass / `0` fail / `-1` not graded. The canonical writer is
`template/tests/verifier_reward_block.py`; a verifier that can still emit `0.5` is
`rubfmt_verifier_reward_domain`, blocking.

This script statically confirms the machinery is wired and will run:

  * JUDGE_FILE   tests/judge.py exists, is non-empty, compiles.               [Fail - Rubric Quality]
  * JUDGE_SHAPE  judge.py carries the load-bearing markers (sys.path strip,   (candidate; confirm vs
                 the sub-agent fallback, exits 0) - i.e. it was not gutted.     reference/judge.py)
                 The STUB carries them too, so this is not evidence of
                 in-band grading; that is rubfmt_judge_backend's call.
  * CONFIG       tests/config.json has "rubric_file": "rubrics.json".         [Fail - Rubric Quality]
  * TEST_SH      tests/test.sh runs judge.py, passes --rubric to the          [Fail - Broken Structure]
                 verifier, and keeps the load-bearing `|| echo ""`.
  * VERIFIER     tests/verifier.py parses --rubric and zeroes a failed        (candidate)
                 rubric: 1.0 -> 0.0. A mention of 0.5 is itself the warning.
  * NO_SHADOW    no file in tests/ is named after a stdlib module             [Fail - Rubric Quality]
                 (select.py, json.py, types.py, io.py, queue.py, ...).
  * NO_PROXY     no litellm / ml.scale.com endpoint hardcoded in task.toml,   [Fail - Broken Structure]
                 verifier.py, judge.py, test.sh or config.json.

NOT GRADED HERE: task.toml's [verifier] / [verifier.env] blocks. qc_rubric_format owns them, and
grades them with a mode distinction this check never had -- network_mode for every task,
[verifier.env] for Mode A only. A NO_CREDS bullet used to sit in the list above, requiring the
OPPOSITE (no [verifier.env] at all); see the note where its check_creds() was deleted.

Heuristics flag CANDIDATES (confirm by hand) unless marked [FAIL]. The behavioural half of
Step 7.6 (the oracle run records `rubric_passed: 1` in-band, or - if the judge fell back - a request
appears under the run's verifier/judge/ and `rescore` folds the verdict in) needs the gate run and is
printed as a manual step. Standard library only; never runs the judge or the verifier.
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
    # Flat Tasks/task.toml or nested Tasks/<any-name>/task.toml - see qc_layout.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from qc_layout import find_task_dir, AmbiguousLayout
    try:
        found = find_task_dir(root)
    except AmbiguousLayout as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    if found:
        return found
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
records = []       # structured mirror, for --emit-findings


def add(level, msg, fid=None, category=None, tier="bundle", needs=None):
    global fail_count
    findings.append((level, msg))
    if level == "FAIL":
        fail_count += 1
    records.append({"level": level, "msg": msg, "id": fid or _slug(msg),
                    "category": category, "tier": tier, "needs": needs})


def _slug(msg):
    words = re.findall(r"[a-z0-9]+", re.sub(r"\[[^\]]*\]", "", msg).lower())
    skip = {"the", "a", "an", "is", "at", "in", "of", "to", "not", "no", "tests", "py"}
    return "judge_" + "_".join([w for w in words if w not in skip][:4] or ["finding"])


def check_judge_file(tasks):
    jp = os.path.join(tasks, "tests", "judge.py")
    if not os.path.exists(jp):
        add("FAIL", "tests/judge.py MISSING - the rubric-template judge harness is not wired in. "
                    "[Fail - Rubric Quality]", fid="judge_missing")
        return None
    if os.path.getsize(jp) == 0:
        add("FAIL", "tests/judge.py is EMPTY. [Fail - Rubric Quality]", fid="judge_missing")
        return None
    try:
        py_compile.compile(jp, cfile=os.path.join(tempfile.gettempdir(), "qc_judge_check.pyc"), doraise=True)
        add("INFO", "tests/judge.py present and compiles")
    except Exception as e:
        add("FAIL", f"tests/judge.py does not compile: {e}. [Fail - Rubric Quality]",
            fid="judge_compile")
        return None
    txt = read(jp) or ""
    # Load-bearing markers: these confirm judge.py was not GUTTED. They do NOT confirm it grades.
    #
    # "never edit judge.py" used to sit on this line and is no longer true -- judge.py is edited
    # under the CB's approval, either by copying reference/judge.py or by merging
    # template/tests/judge_api_block.py into an adapted judge (RUBRIC_MODES.md §2c). What must
    # survive that edit is this list.
    #
    # ALL FIVE DESCRIBE THE SUB-AGENT FALLBACK, which the stock stub also has -- so a green marker
    # check is NOT evidence of in-band grading, and must not be read as one. Whether call_eval_api
    # is present at all is qc_rubric_format's call (rubfmt_judge_backend, blocking). Measured:
    # reference/judge.py matches all five AND has call_eval_api; template/tests/judge.py matches all
    # five with call_eval_api NOWHERE in it. Requiring the API backend here too would only duplicate
    # a blocking finding as a WARN.
    markers = {
        "sys.path strip (stdlib-shadow defence)": "sys.path[:]",
        # Retained in the in-band judge as the fallback, which is why this is still required. The
        # label used to read "sub-agent, no API key", describing the whole judge rather than one
        # path through it -- and reading as though an API key were a defect.
        "the sub-agent fallback path": re.compile(r"NO API KEY|no api key|sub-agent", re.I),
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
        add("WARN", f"tests/judge.py is missing load-bearing marker(s): {missing}. Diff it against "
                    f"reference/judge.py — the in-band judge the skill's own fixes install, which "
                    f"keeps the sub-agent path as its fallback. Do NOT diff against "
                    f"template/tests/judge.py: that is the stub, and it has no API backend.",
            fid="judge_drift")
    else:
        add("INFO", "tests/judge.py carries the load-bearing markers (the sub-agent fallback is "
                    "intact — this says nothing about whether it grades in-band; that is "
                    "rubfmt_judge_backend's call)")
    return txt


# check_creds() WAS HERE, and is DELETED rather than left unreferenced.
#
# It failed a task for HAVING a [verifier.env] block, or for mentioning ANTHROPIC_* /
# JUDGE_MODEL, on the premise that the judge is always a keyless sub-agent and those are
# leftovers of a retired "api" backend. In-band grading reversed that premise: Mode A now
# REQUIRES the block, and qc_rubric_format.check_verifier_env reports its absence as a blocking
# Fail. The two checks asserted opposite requirements about the same four lines.
#
# It was already excluded from the run list, so it emitted nothing -- but it was kept "as a
# function for reference", which is precisely how the superseded policy would have come back. Its
# `legacy_creds` fid outlived the fix that implemented it (removed from fix.py; see SKILL.md), so
# it could only ever have produced a finding no repair routes.
#
# Credentials never enter a bundle either way: [verifier.env] holds ${VAR} REFERENCES that harbor
# expands at run time. A LITERAL secret is a security escalation, not a mechanical repair, and
# qc_judge.check_hardcoded_proxy still scans task.toml for hardcoded endpoints.


def check_config(tasks):
    cp = os.path.join(tasks, "tests", "config.json")
    txt = read(cp)
    if txt is None:
        add("FAIL", "tests/config.json missing - it is one of the closed 11 files. "
                    "[Fail - Broken Structure]", fid="config_missing")
        return
    if '"rubric_file"' not in txt:
        add("FAIL", 'tests/config.json has no "rubric_file" key - the rubric is never picked up. '
                    'Add "rubric_file": "rubrics.json". [Fail - Rubric Quality]',
            fid="rubric_file")
    elif not re.search(r'"rubric_file"\s*:\s*"rubrics\.json"', txt):
        add("WARN", 'tests/config.json "rubric_file" is present but not "rubrics.json" - confirm it '
                    'points at the shipped rubric file.', fid="rubric_file")
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
        add("FAIL", "tests/test.sh missing - it is one of the closed 11 files. [Fail - Broken Structure]",
            fid="testsh_missing")
        return
    if "judge.py" not in txt:
        add("FAIL", "tests/test.sh never invokes judge.py - the rubric is not run. "
                    "[Fail - Rubric Quality]", fid="test_sh_judge")
    # Must be --rubric passed to the VERIFIER, not judge.py's own --rubrics flag. A plain
    # substring test matches "--rubrics" and so can never fail, which let a task compute
    # RUBRIC and then call verifier.py without it -- every verdict silently discarded.
    passes_rubric = re.search(r"verifier\.py[^\n|;&]*--rubric(?!s)", txt) is not None
    if not passes_rubric:
        add("WARN", "tests/test.sh does not pass --rubric to verifier.py - the verdict can't reach "
                    "the gate (note: judge.py's own --rubrics does NOT count). "
                    "Confirm the verifier call.", fid="test_sh_judge")
    if 'judge.py' in txt and '|| echo ""' not in txt and "|| echo ''" not in txt:
        add("WARN", 'tests/test.sh runs judge.py without the load-bearing `|| echo \"\"` - the judge '
                    'must never be able to fail the run.', fid="test_sh_judge")
    if txt and "judge.py" in txt and passes_rubric:
        add("INFO", "tests/test.sh invokes judge.py and passes --rubric to the verifier")


def check_verifier(tasks):
    vp = os.path.join(tasks, "tests", "verifier.py")
    txt = read(vp)
    if txt is None:
        add("FAIL", "tests/verifier.py missing. [Fail - Broken Structure]", fid="verifier_missing")
        return
    if "--rubric" not in txt:
        add("WARN", "tests/verifier.py does not parse --rubric - the rubric gate is not applied "
                    "(confirm the 5 template edits were made).", fid="verifier_no_rubric_flag")
    else:
        add("INFO", "tests/verifier.py parses --rubric")
    if "reward.json" not in txt:
        add("WARN", "tests/verifier.py does not write reward.json - the per-test counts are needed "
                    "to answer 'did this f2p pass on nop?' (an aggregate cannot).",
            fid="verifier_no_reward_json", category="gate")
    # INVERTED. This used to warn when 0.5 was ABSENT ("confirm the gate turns 1.0 into 0.5"),
    # which is backwards under the binary policy and fired on BOTH reference tasks - i.e. it told
    # CBs to ADD partial credit. The reward is binary: a failed rubric zeroes a 1.0, and a strict
    # subset of f2p passing is 0.0, because a half-fix must not read as solved to pass@k.
    # qc_rubric_format owns the authoritative version of this check.
    if "0.5" in txt:
        add("WARN", "tests/verifier.py mentions 0.5 somewhere - worth a look, because the reward "
                    "is pass/fail only. Read the two lines around it and check it is not (a) "
                    "half credit when only some f2p tests pass, or (b) a failed rubric capping "
                    "the score at 0.5 instead of zeroing it. If it is neither - a timeout, a "
                    "ratio, a threshold - ignore this; it is a keyword match, not a verdict.",
            fid="verifier_partial_credit")


def check_shadow(tasks):
    tdir = os.path.join(tasks, "tests")
    if not os.path.isdir(tdir):
        return
    bad = [f for f in os.listdir(tdir) if f in STDLIB_SHADOW]
    if bad:
        add("FAIL", f"tests/ contains file(s) named after stdlib module(s): {bad} - they shadow the "
                    f"real module and fail somewhere unrelated. Rename them. [Fail - Broken Structure]",
            fid="stdlib_shadow")
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
    """Compiled bytecode and other build junk must not ship in a deliverable.

    __MACOSX is the archive-extraction artifact: macOS `zip` writes a parallel tree of
    AppleDouble resource forks, and unzipping a bundle that was ever round-tripped through
    macOS leaves it behind. It is never part of a task and is pure noise in a deliverable.
    """
    import glob
    junk = []
    for pat in ("**/__pycache__", "**/*.pyc", "**/.DS_Store", "**/node_modules", "**/__MACOSX"):
        junk += [p for p in glob.glob(os.path.join(tasks, pat), recursive=True)]
    if junk:
        rels = sorted({os.path.relpath(j, tasks) for j in junk})
        add("FAIL", f"build junk committed in the bundle: {rels[:6]}"
                    f"{' ...' if len(rels) > 6 else ''}. A stale .pyc can shadow a deleted .py. "
                    f"[Fail - Broken Structure]", fid="junk")
    else:
        add("INFO", "no __pycache__ / .pyc / .DS_Store / node_modules / __MACOSX in the bundle")


# A bundle must not name the model gateway it happens to be run behind. Credentials and the
# endpoint are injected at run time through the anonymizer, so a hardcoded host is both a
# portability defect (it only resolves inside one network) and a leak of internal infrastructure
# into a deliverable.
#
# THE DEFECT IS AN ENDPOINT, NOT A WORD. This was `litellm|ml\.scale\.com`, which matched the
# product name anywhere -- including the prose in judge.py's own docstring ("chat-completions
# call to the LiteLLM proxy", "EVAL_API_KEY  LiteLLM proxy key"). Both reference tasks tripped
# it on those two comment lines, so every correct bundle carried a phantom [Fail - Broken
# Structure]. A comment naming the mechanism leaks nothing and resolves nowhere; only a host or
# URL does. So the three alternatives below match endpoint SHAPES:
#   1. any URL pointing at the proxy          https://litellm-proxy.../v1
#   2. a bare hostname, >=2 dots + a TLD      litellm-proxy.ml.scale.com
#      (two dots are required so `litellm.completion(...)` -- an SDK call, not an endpoint --
#       does not match, while the real host still does)
#   3. the internal domain in any form        ml.scale.com
PROXY_HOSTS = re.compile(
    r"https?://[^\s\"'`]*litellm"
    r"|litellm[\w-]*\.[\w-]+\.[a-z]{2,}"
    r"|\bml\.scale\.com\b", re.I)
# Where a hardcoded endpoint actually breaks something. environment/Dockerfile is deliberately
# NOT scanned: a build stage may legitimately need a registry or mirror, and that is an
# environment decision rather than a grading one.
PROXY_SCAN = ("task.toml", "tests/verifier.py", "tests/judge.py",
              "tests/test.sh", "tests/config.json")


def check_hardcoded_proxy(tasks):
    """No file that decides the reward may hardcode the litellm proxy endpoint."""
    hits = []
    for rel in PROXY_SCAN:
        txt = read(os.path.join(tasks, rel))
        if txt is None:
            continue
        for n, line in enumerate(txt.splitlines(), 1):
            if PROXY_HOSTS.search(line):
                hits.append(f"{rel}:{n}: {line.strip()[:80]}")
    if hits:
        add("FAIL", f"hardcoded model-proxy endpoint in the bundle ({len(hits)} line(s)): "
                    f"{hits[:4]}{' ...' if len(hits) > 4 else ''}. The endpoint and credentials "
                    f"are injected at run time through the anonymizer - a task must never name "
                    f"the gateway it is run behind. Remove the literal and read it from the "
                    f"environment. [Fail - Broken Structure]", fid="hardcoded_proxy")
    else:
        add("INFO", f"no litellm / ml.scale.com endpoint hardcoded in {', '.join(PROXY_SCAN)}")


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
                    f"Every run would score 0.0. [Fail - Broken Structure]", fid="testsh_syntax")
    else:
        add("INFO", "tests/test.sh parses (bash -n)")


def check_judge_identical(tasks, template=None):
    """Does judge.py still match the copy it was installed from?

    The docstring here used to read "judge.py must be byte-identical to the shipped template - a
    contributor editing the judge changes grading semantics invisibly". The premise is right and the
    conclusion is now wrong twice over: judge.py IS edited, under approval, to add the required API
    backend (RUBRIC_MODES.md §2c), and template/tests/judge.py is the STUB -- byte-identity to it
    means no call_eval_api and therefore rubfmt_judge_backend, blocking. The comparison target
    worth setting MM_RUBRIC_TEMPLATE to is reference/judge.py.

    So a mismatch is a WARN, not a FAIL. See the note at the else-branch.
    """
    import hashlib
    jp = os.path.join(tasks, "tests", "judge.py")
    if not os.path.isfile(jp):
        return
    tpl = template or os.environ.get("MM_RUBRIC_TEMPLATE")
    if not tpl or not os.path.isfile(tpl):
        add("MANUAL", "judge.py byte-identity not checked (set MM_RUBRIC_TEMPLATE to a judge to "
                      "compare against — use the skill's reference/judge.py, the in-band copy its "
                      "own fixes install, NOT template/tests/judge.py, which is the stub with no "
                      "API backend)",
            fid="judge_identity_unchecked", needs="MM_RUBRIC_TEMPLATE")
        return
    h = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()
    if h(jp) == h(tpl):
        add("INFO", f"tests/judge.py is byte-identical to the comparison copy ({tpl})")
    else:
        # DOWNGRADED from FAIL, and it stays downgraded even though the API backend is now
        # REQUIRED. Byte-identity to the bundled template matched NEITHER reference task, so as a
        # hard failure this flagged correct bundles. A judge can carry the required call_eval_api
        # and still differ here - task-specific adaptation is legitimate. Whether the backend is
        # present at all is qc_rubric_format's call (rubfmt_judge_backend, blocking); the
        # substantive protection here is the load-bearing marker check in check_judge_file(), which
        # confirms the judge was not gutted. Drift alone is a signal worth reading, not a verdict.
        add("WARN", f"tests/judge.py differs from the comparison copy ({tpl}). Expected if the "
                    f"judge was adapted for this task; confirm the contract still holds - grades "
                    f"in-band when it can, prints pass/fail or nothing, writes summary.json, "
                    f"ALWAYS exits 0.",
            fid="judge_drift")


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
# canonical `rubric_passed` line - i.e. it fails the very convention it exists to enforce.
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
                    "confirm BY HAND that every top-level value is a plain float/int.",
            fid="reward_json_untraced", category="gate")
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
                    f"`f2p::<name>` = 1.0/0.0. [Fail - Gate Broken]",
            fid="reward_json_nonnumeric", category="gate")
    else:
        add("INFO", "verifier.py's reward.json values look numeric (harbor-parseable)",
            category="gate")


LEVEL_SEV = {"FAIL": "FAIL", "WARN": "CANDIDATE", "MANUAL": "OPEN", "INFO": "OK"}


def export_findings(path):
    """Translate native (level, msg) records into the shared Finding model.

    Routing is driven by the `[Fail - X]` tag the message already carries, so a judge-detected
    GATE defect books against the gate category instead of being filed under whichever tool
    happened to notice it. Level maps straight onto the shared ladder: WARN was always a
    "candidate to confirm by hand", MANUAL was always "cannot be decided here"."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from qc_common import Finding, dump_findings, normalize_dim, category_for_dim
    out = []
    for r in records:
        dim = normalize_dim(r["msg"])
        cat = r["category"] or category_for_dim(dim, "rubric_judge")
        out.append(Finding(r["id"], r["msg"], LEVEL_SEV[r["level"]], category=cat,
                           rubric_dim=dim, tier=r["tier"], needs=r["needs"],
                           source=["qc_judge"]))
    dump_findings(out, path)
    return len(out)


def main():
    argv = list(sys.argv[1:])
    emit = None
    if "--emit-findings" in argv:
        i = argv.index("--emit-findings")
        emit = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i:i + 2]
    if not argv:
        print(__doc__)
        sys.exit(1)
    tasks = locate(argv[0])

    print(f"\nVarmint Sheriffs judge-mechanics verification (v3.1 Step 7.6) - "
          f"{os.path.abspath(argv[0])}")
    print(f"Tasks/ = {tasks or 'NOT FOUND'}\n")

    if not tasks:
        add("FAIL", "no Tasks/ dir found - cannot audit judge mechanics. [Fail - Broken Structure]",
            fid="no_tasks_dir")
        _report()
        if emit:
            export_findings(emit)
        return

    # MODE GATE. The judge harness only has to exist when a rubric does. A task with no
    # tests/rubrics.json is in Mode B (no rubric layer) - a legal shape - so demanding judge.py
    # and a "rubric_file" key there failed correct bundles. qc_rubric_format.py owns the shape
    # decision and reports it as a BLOCKING Fail when the shape is wrong; this check only audits
    # the machinery of a rubric that is actually present.
    has_rubric = os.path.isfile(os.path.join(tasks, "tests", "rubrics.json"))
    if has_rubric:
        check_judge_file(tasks)
        check_config(tasks)
    else:
        add("INFO", "no tests/rubrics.json - Mode B (no rubric layer). judge.py and "
                    '"rubric_file" are correctly absent; nothing to audit here. Whether this task '
                    "SHOULD carry a rubric is qc_rubric_format.py's call.")
    # task.toml's two verifier blocks are graded by qc_rubric_format, which owns them, and they
    # are gated DIFFERENTLY there -- the distinction this check never had, and the reason its
    # check_creds() is gone rather than merely unwired (see the note above its former site):
    #
    #   rubfmt_verifier_network_mode   EVERY TASK. A sealed verifier cannot install what the tests
    #                                 need, so the f2p test fails and a correct submission scores
    #                                 0.0 -- rubric or no rubric.
    #   rubfmt_verifier_env           MODE A ONLY. Nothing reads EVAL_* without a judge, and the
    #                                 block's bare "${VAR}" entries would make harbor demand host
    #                                 credentials for an otherwise keyless oracle/nop. Requiring
    #                                 it of Mode B tasks is what produced the original false
    #                                 failures.
    check_test_sh(tasks)
    check_verifier(tasks)
    check_shadow(tasks)
    note_placeholder(tasks)
    # --- added in MM_SWE_QC ---
    check_hygiene(tasks)
    check_hardcoded_proxy(tasks)
    check_testsh_syntax(tasks)
    check_judge_identical(tasks)
    check_reward_json_numeric(tasks)

    add("MANUAL", "BEHAVIOURAL (manual, needs the gate run): reproduce oracle/nop (Step 0.6), then "
                  "confirm the oracle reward.json shows `rubric_passed: 1` - graded IN-BAND, with no "
                  "rescore. `rubric_passed: -1` on an oracle run means the judge never reached its "
                  "endpoint (check [verifier] network_mode and [verifier.env]), not that grading is "
                  "merely pending. If the judge fell back, a request (criteria_payload.json, "
                  "source.txt, changed_files.txt, PROMPT.md) appears under the run's verifier/judge/ "
                  "for a sub-agent to grade, and `rescore` folds that verdict in. The reward is "
                  "BINARY: reward.txt is a bare float in {0.0, 1.0} and a failed rubric on an "
                  "all-f2p-pass run reads 0.0, never 0.5 - a half-fix must not read as solved to "
                  "pass@k.",
        fid="behavioural_rescore", needs="rescore")

    _report()
    if emit:
        n = export_findings(emit)
        print(f"  wrote {n} finding(s) -> {emit}")


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

