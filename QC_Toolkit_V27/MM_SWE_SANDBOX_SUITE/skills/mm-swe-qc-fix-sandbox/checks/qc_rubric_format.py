#!/usr/bin/env python3
"""MM SWE QC - rubric FORMAT / STRUCTURE. Every finding here is a BLOCKING Fail.

THE RUBRIC LAYER HAS EXACTLY TWO LEGAL SHAPES. This check decides which one a task is in
and audits it against that shape:

  MODE A  RUBRIC     tests/rubrics.json + tests/judge.py ship, >=1 REAL criterion
  MODE B  NO_RUBRIC  neither ships; the --rubric gate stays wired but never fires

Anything else is a structural defect. Two cases matter most, and both used to pass:

  * an all-pass ("always_pass" / "The response is written in English") stub rubric is NOT
    a legal shape. It is a declaration that no rubric is needed, so the layer must be
    STRIPPED, not stubbed. A stub cannot fail any submission, yet it makes rubric_passed
    read 1 exactly as though a real rubric had been satisfied - so it fabricates a graded
    result. It is also unfalsifiable: with no criterion that can fail, every rubric-quality
    percentage band passes on a zero denominator.
  * a task with no rubric at all is CORRECT, not "missing rubrics". Requiring the layer
    unconditionally failed sound bundles.

WHY BLOCKING. `blocking` in qc_common means "until this is fixed, no other number means
anything", and every finding here qualifies: a stub fabricates a rubric verdict, and a
non-canonical reward.json makes harbor abort the trial BEFORE recording any reward while
reward.txt is still written inside the container - so the run looks scored when nothing was
stored. Neither can be judged around; they have to be fixed first.

WHAT THIS DOES NOT GRADE. Rubric *content* quality (the 11-issue appendix) is qc_rubrics.py.

THE JUDGE BACKEND *IS* PRESCRIBED, as of this revision, and task.toml's [verifier] /
[verifier.env] blocks ARE graded. Both were previously out of scope on the grounds
that "either backend is valid" and that the blocks "vary legitimately across tasks". That was
coherent while a sub-agent-only judge counted as complete. It does not survive the observation
that such a judge cannot grade during the run: it records rubric_passed = -1 on every run until
a human grades PROMPT.md and reruns rescore, which is routinely skipped -- so the rubric is
decorative in exactly the way an all-pass stub is. Requiring in-band grading collapses the
"legitimate variance": an API-backend judge has ONE working configuration.

  Mode A now requires   tests/judge.py with an API backend (call_eval_api)
                        [verifier.env] mapping EVAL_API_KEY / EVAL_BASE_URL / EVAL_MODEL

The sub-agent path stays legal AS A FALLBACK inside judge.py -- it is what keeps the judge from
ever failing a run. What is barred is shipping it as the only way the rubric is ever graded.

[verifier] network_mode = "public" IS REQUIRED IN BOTH MODES, and is the one part of this that
is not about the judge at all. It was Mode A only on the reasoning that with no judge there is
nothing to reach an endpoint -- true, and beside the point. The verifier phase also INSTALLS
what the tests need: `npm install`, `pip install`, or a bare `npx <runner>` resolving from the
registry. Under no-network those fail, the f2p test fails with them, and a CORRECT submission
records 0.0 -- a false negative whose reward looks perfectly legitimate. That is a mis-scored
run by the same standard the Mode A findings are blocking for, so it is blocking in both modes.
Tasks that pre-stage their test dependencies at build time (see the reference bundles'
/opt/verifier-deps pattern) do not exercise the permission; it costs them nothing to hold it,
and it stops the seal being a trap for every task that does not.

  Both modes require    [verifier] network_mode = "public"    check_verifier_network_mode
  Mode A additionally   [verifier.env] EVAL_* mapping         check_verifier_env

Only the [verifier.env] half stays mode-gated: in Mode B nothing reads EVAL_*, and writing the
block there would make harbor demand host vars for a run that is otherwise keyless (a bare
"${VAR}" with no ":-" default is a REQUIRED host var -- cli/jobs.py exits 1 with a "Missing
Environment Variables" table before any container starts).

Usage (standalone):  qc_rubric_format.py <root | Tasks dir> [...] [--json OUT]
Usage (as a QC component):  qc_rubric_format.py <root> --emit-findings OUT
Exit: 0 all tasks PASS - 1 at least one FAIL. Stdlib only, no network.
"""
import argparse, ast, json, os, re, sys

CANONICAL_SCHEMA = "rubrics.schema/v1"
LEGACY_SCHEMAS = {"projectbench.rubrics/v1"}

STUB_IDS = {"always_pass", "always-pass", "alwayspass"}
STUB_TEXT = re.compile(r"written in english|no rubric needed", re.I)

# A criterion that defers outside the code cannot be decided by the judge, which sees
# only the criterion, the diff and the changed files.
DEFERS = re.compile(
    r"\b(the (prompt|instruction|task|issue|ticket|request)s?\b"
    r"|as (requested|specified|described|instructed)|per the (prompt|instruction)"
    r"|the (golden|reference) (fix|solution|implementation)"
    r"|(project|repo|repository|codebase)'?s? (conventions?|style|standards?|patterns?))", re.I)
# Needs a rendered page, not code.
UI_ONLY = re.compile(r"\b(looks? (right|correct|good|off)|visually|renders? (correctly|properly)"
                     r"|is visible|pixel[- ]perfect)", re.I)
VAGUE = re.compile(r"\b(properly|appropriately|correctly|clean(ly)?|readable|maintainable"
                   r"|idiomatic|sensible|reasonabl[ey]|as needed|if necessary)\b", re.I)
FILEREF = re.compile(r"\b([A-Za-z0-9_.\-/]+\.(?:js|jsx|ts|tsx|mjs|cjs|css|scss|py|java|rb|go|rs))\b")

# EITHER judge backend is legal and NEITHER is enforced:
#   A1  keyless sub-agent   phase 1 writes a judge request, a sub-agent grades it, rescore
#                           folds the verdict in. No credentials in the bundle.
#   A2  API-capable         additionally grades in-band via the proxy when credentials reach
#                           the verifier at run time; falls back to A1 otherwise.
# Credentials are injected at run time (anonymizer), so their absence from task.toml is not a
# defect. What IS checked is that the bundle is internally consistent with its own backend.
JUDGE_API_MARKER = "call_eval_api"
# Backend-agnostic capabilities. Recommended, never required: their absence degrades grading
# quality but cannot fail a correct submission, so they are reported as WARN.
JUDGE_QUALITY_MARKERS = {
    "collect_changed_files": "full text of every changed file (a 3-line hunk is often too "
                             "little context to decide a criterion, causing false 0s)",
}
# The canonical reward.json keys, in the shape both golden tasks emit.
CANON_REWARD_KEYS = ["reward", "tests_passed", "f2p_passed", "f2p_total",
                     "p2p_passed", "p2p_total", "rubric_passed"]
# Closed value sets for the three graded keys. These are VERDICTS, not a scale: downstream
# analysis reads them positionally across the corpus, and a 0.5 makes "half solved" look like
# a distinct outcome when the gate treats anything short of 1.0 as a miss. A fail is a fail,
# so the repair for partial credit is to FLOOR to 0 -- never round to nearest, never cap at
# 0.5. The counts (f2p_passed/f2p_total/p2p_passed/p2p_total) are genuine tallies and are
# deliberately absent here.
REWARD_DOMAIN = {"reward": {0, 1}, "tests_passed": {0, 1}, "rubric_passed": {-1, 0, 1}}
# Functions whose first positional argument IS the reward.
REWARD_WRITERS = {"write_reward"}
# Test-path patterns the judge's EXCLUDE_RE must strip from the diff. The narrow older
# regex let harbor's own harbor_test.js and non-JS test files through. Matched against the
# EXCLUDE_RE block only (not the whole file, or prose in the docstring would satisfy them)
# and after stripping backslashes, so `_test\.` in the source reads as `_test.`.
JUDGE_EXCLUDE_MARKERS = {"_test.": "harbor_test.js / *_test.go / *_test.py",
                         "test_": "test_*.py / test_*.cpp",
                         "vitest.config": "vitest/jest config"}


def parses_rubric_flag(src):
    """Does verifier.py actually PARSE --rubric, as opposed to merely mentioning it?

    A substring test cannot tell the two apart, and both reference verifiers document the flag in
    their module docstring - so `"--rubric" in src` returned True for a verifier whose parsing had
    been removed entirely (measured). This walks the AST for a "--rubric" string CONSTANT used
    outside any docstring, which is the difference between code and prose.

    Falls back to the substring test if the file does not parse, so a syntax error downgrades this
    to the old behaviour rather than silently reporting "does not parse --rubric".
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return "--rubric" in src
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and "--rubric" in node.value and id(node) not in docstrings:
            return True
    return False


def strip_sh_comments(text):
    """bash source with whole-line comments removed, so a commented-out judge block does not
    satisfy the test.sh checks."""
    return "\n".join(ln for ln in (text or "").splitlines()
                     if not ln.lstrip().startswith("#"))


def exclude_re_block(src):
    """The text of the judge's `EXCLUDE_RE = re.compile(...)` call, backslashes stripped."""
    i = src.find("EXCLUDE_RE = re.compile(")
    if i < 0:
        return None
    depth, out = 0, []
    for ch in src[i + len("EXCLUDE_RE = re.compile"):]:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        out.append(ch)
    return "".join(out).replace("\\", "")


class Report:
    def __init__(self, task):
        self.task, self.mode, self.rows = task, "?", []

    def add(self, sev, check, msg):
        self.rows.append((sev, check, msg))

    def ok(self, check, msg):   self.add("OK", check, msg)
    def fail(self, check, msg): self.add("FAIL", check, msg)
    def warn(self, check, msg): self.add("WARN", check, msg)
    def open_(self, check, msg): self.add("OPEN", check, msg)

    @property
    def failed(self):
        return any(s == "FAIL" for s, _, _ in self.rows)

    def print(self):
        order = {"FAIL": 0, "WARN": 1, "OPEN": 2, "OK": 3}
        print(f"\n{'=' * 78}\n{self.task}\n  MODE: {self.mode}\n{'=' * 78}")
        for sev, check, msg in sorted(self.rows, key=lambda r: order[r[0]]):
            print(f"  [{sev:4}] {check:22} {msg}")
        print(f"\n  VERDICT: {'FAIL' if self.failed else 'PASS'}")


def read(path):
    try:
        return open(path, errors="replace").read()
    except OSError:
        return None


def load_json(path):
    try:
        return json.load(open(path)), None
    except Exception as exc:
        return None, str(exc)


def is_stub(c, doc):
    if str(c.get("id", "")).strip().lower() in STUB_IDS:
        return True
    if STUB_TEXT.search(str(c.get("criterion", ""))):
        return True
    if len(doc.get("criteria") or []) == 1 and STUB_TEXT.search(str(doc.get("description", ""))):
        return True
    return False


def golden_changed_files(task):
    diff = read(os.path.join(task, "solution", "fix.patch"))
    if not diff:
        return None
    return sorted({m for m in re.findall(r"^diff --git a/\S+ b/(\S+)", diff, re.M)})


def result_constants(node):
    """Numeric literals that can BE the assigned value, not ones that merely appear inside it.

    `reward = 0.5` and `reward = 1.0 if ok else 0.5` are decidable from the source; `round(x, 2)`
    is not, and reading its precision argument as a reward would be a false positive. Scaling
    counts (`reward = tests_passed * 0.5`), because halving is exactly the defect being hunted.
    """
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            yield node.value, node.lineno
    elif isinstance(node, ast.IfExp):            # ternary: both branches are results
        yield from result_constants(node.body)
        yield from result_constants(node.orelse)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div)):
        for side in (node.left, node.right):
            if isinstance(side, ast.Constant) and isinstance(side.value, (int, float)) \
                    and not isinstance(side.value, bool):
                yield side.value, side.lineno
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) \
            and isinstance(node.operand, ast.Constant) \
            and isinstance(node.operand.value, (int, float)):
        # `-1` parses as USub(Constant(1)); without this, rubric_passed = -1 reads as 1
        yield -node.operand.value, node.lineno


def assigned_name(target):
    """The reward key a target refers to: `reward`, `detail["reward"]`, `self.reward`."""
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
        return target.slice.value if isinstance(target.slice.value, str) else None
    return None


def check_reward_domain(r, task):
    """reward / tests_passed / rubric_passed must land in their closed sets -- FAIL in both modes.

    Runs unconditionally, which is the point: the older 0.5 hunt lived inside the
    `rubric == "fail"` branch of check_gate, so a verifier with a partial-credit ladder and no
    rubric gate reported nothing but a WARN about the missing gate. Partial credit mis-scores a
    run whether or not a rubric ships, so it is graded on its own.

    AST, not regex: docstrings that legitimately DESCRIBE a legacy 0.5 rung ("reward.txt stays a
    bare float in {0.0, 0.5, 1.0}") must not read as code that emits one.
    """
    v = read(os.path.join(task, "tests", "verifier.py"))
    if v is None:
        return                                   # verifier.present already failed
    try:
        tree = ast.parse(v)
    except SyntaxError as exc:
        r.open_("verifier.reward_domain",
                f"tests/verifier.py does not parse ({exc}); reward domains unchecked")
        return

    bad = []                                     # (lineno, key, value)

    def audit(key, node):
        for val, line in result_constants(node):
            if val not in REWARD_DOMAIN[key]:
                bad.append((line, key, val))

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            pairs = [(t, node.value) for t in node.targets]
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            pairs = [(node.target, node.value)] if node.value is not None else []
        else:
            pairs = []
        for target, value in pairs:
            key = assigned_name(target)
            if key in REWARD_DOMAIN:
                audit(key, value)

        # write_reward(0.5, tests_passed=0.5)
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in REWARD_WRITERS:
                if node.args:
                    audit("reward", node.args[0])
                for kw in node.keywords:
                    if kw.arg in REWARD_DOMAIN:
                        audit(kw.arg, kw.value)

        # a reward.json dict built inline: {"reward": 0.5, "tests_passed": 0.5}
        if isinstance(node, ast.Dict):
            for k, val in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value in REWARD_DOMAIN:
                    audit(k.value, val)

    if bad:
        shown = ", ".join(f"line {ln}: {k} = {val!r}" for ln, k, val in sorted(set(bad)))
        r.fail("verifier.reward_domain",
               f"a half-finished fix would score 0.5, but reward is pass/fail only — so this "
               f"task can record a score no consumer can interpret.\n"
               f"  where: {shown}\n"
               f"  allowed: reward and tests_passed are 0 or 1; rubric_passed is 1 (pass), "
               f"0 (fail) or -1 (not graded)\n"
               f"  fix: score it 0 — a partial fix is a fail, so floor it. Do not round to "
               f"the nearest and do not cap at 0.5:\n"
               f"         reward = 1.0 if all_f2p_pass else 0.0\n"
               f"  why: the counts (f2p_passed / f2p_total) already carry how close it got, "
               f"so nothing is lost by collapsing the middle. Leaving 0.5 in lets a half-fix "
               f"read as solved to pass@k")
    else:
        r.ok("verifier.reward_domain",
             "reward / tests_passed / rubric_passed only take values from their closed sets")


# ------------------------------------------------- the verifier phase must reach the judge
# The three EVAL_* names judge.py's API backend reads, and what [verifier.env] must map them
# from. Values are ${VAR} REFERENCES expanded by harbor at run time from its own environment --
# no credential is ever written into a bundle, which is what made this safe to require.
EVAL_ENV_KEYS = {
    "EVAL_API_KEY": "${OPENAI_API_KEY}",
    "EVAL_BASE_URL": "${OPENAI_API_BASE}",
    "EVAL_MODEL": '${EVAL_MODEL:-anthropic/claude-opus-4-5-20251101}',
}


def toml_section(txt, name):
    """Body of a top-level [name] table, or None. Good enough for the flat blocks we grade."""
    m = re.search(r"^\[" + re.escape(name) + r"\]\s*$(.*?)(?=^\[|\Z)", txt, re.M | re.S)
    return m.group(1) if m else None


def check_verifier_network_mode(r, task):
    """BOTH MODES: can the verifier phase reach the network at all?

    Two independent things need it, and only the first is about the rubric:

      1. THE JUDGE (Mode A). An API-backend judge dials the proxy from inside the container.
         Sealed, it cannot, and every run records rubric_passed = -1 -- the rubric is
         decorative in exactly the way an all-pass stub is.
      2. TEST DEPENDENCY INSTALLATION (both modes). test.sh routinely installs what the tests
         need at verify time: `npm install`, `pip install`, or a bare `npx <runner>` that
         resolves from the registry when the binary is not already in the project tree. Sealed,
         those fail, the f2p test fails with them, and a CORRECT submission records 0.0.

    THAT SECOND CASE IS WHY THIS IS NO LONGER MODE-GATED. The old reasoning -- "in Mode B there
    is no judge, so there is nothing to reach an endpoint" -- is true and irrelevant: a Mode B
    verifier that cannot install its test runner mis-scores every submission it grades, and the
    reward it writes looks entirely legitimate. A false negative is a mis-scored run, so it is
    blocking here on the same standard as the Mode A findings.

    Grading it in Mode B is NOT a return to the false failures this area was once pulled out
    for. Those came from demanding [verifier.env] of tasks with no judge to configure -- a
    requirement that made harbor demand host credentials for a keyless run. network_mode carries
    no such cost: it is a permission, it takes no host state, and a task that pre-stages its test
    dependencies at build time simply never exercises it.

    WHY "public" AND NOT AN ALLOWLIST. Verified against harbor 0.18:
    NetworkPolicy.validate_allowed_hosts rejects allowed_hosts unless network_mode ==
    "allowlist"; normalize_allowed_hosts validates LITERAL hostnames and never env-expands, so a
    run-time-injected endpoint cannot be named; and the CLI exposes allow_agent_hosts /
    allow_environment_hosts but NO allow_verifier_hosts, so there is no run-level override for
    this phase. "public" is not a preference, it is the only setting that works.

    WHAT IT COSTS: little, and nothing an agent can reach. The verifier runs AFTER the agent
    phase is over and test.sh restores the test files from harbor_base, so egress here cannot
    help a submission cheat. The agent phase stays sealed -- [agent] network_mode is
    qc_structure's, and this check never touches it.

    WHAT IT GIVES UP: a sealed verifier fails loudly at authoring time when a test accidentally
    depends on the registry, which is real. Pre-staging is still the better shape and the checks
    should keep saying so -- but the cure for an accidental dependency is not a permission that
    silently mis-scores every task with a deliberate one.
    """
    txt = read(os.path.join(task, "task.toml"))
    if txt is None:
        r.fail("verifier.phase", "task.toml missing; cannot confirm the verifier phase can "
                                 "install test dependencies or reach a judge endpoint")
        return

    body = toml_section(txt, "verifier")
    mode_m = re.search(r"^\s*network_mode\s*=\s*[\"']([^\"']*)[\"']", body or "", re.M)
    if mode_m and mode_m.group(1) == "public":
        r.ok("verifier.network_mode",
             'network_mode = "public" — the verifier can install test dependencies, and an '
             'API-backend judge can reach its endpoint')
    else:
        found = f"'{mode_m.group(1)}'" if mode_m else ("absent" if body is not None
                                                       else "no [verifier] section")
        r.fail("verifier.network_mode",
               f"[verifier] network_mode is {found}; it must be \"public\". Sealed, the verifier "
               f"cannot install what the tests need (npm/pip install, or npx resolving a runner "
               f"from the registry), so the f2p test fails and a CORRECT submission records 0.0 "
               f"— a false negative whose reward looks legitimate. On a rubric task it also "
               f"leaves the in-container judge unable to reach the proxy, so every run records "
               f"rubric_passed = -1. An allowlist cannot express it (harbor validates "
               f"allowed_hosts as literal hostnames and never env-expands them, and there is "
               f"no --allow-verifier-host), so \"public\" is the only working value. The AGENT "
               f"phase is unaffected and stays sealed")


def check_verifier_env(r, task):
    """MODE A ONLY: does task.toml pass the judge the endpoint and key it reads?

    WHY THIS IS GRADED AT ALL, having been explicitly out of scope before. The old position was
    that [verifier] / [verifier.env] "vary legitimately across tasks", which was true while BOTH
    judge backends were considered complete. Once in-band grading is required (see judge.backend)
    the variance collapses: an API-backend judge has exactly one working configuration, and any
    other is a task that ships a rubric it cannot grade.

    WHY THIS HALF STAYS MODE-GATED, unlike network_mode. In Mode B nothing reads EVAL_*, so the
    block is inert -- and not harmlessly so. EVAL_API_KEY / EVAL_BASE_URL are bare "${VAR}"
    references, which harbor treats as REQUIRED host vars: cli/jobs.py exits 1 with a "Missing
    Environment Variables" table before any container starts if they are unset. Writing them
    into a rubric-less task converts a keyless oracle/nop into one that cannot run without
    credentials it never uses. THIS is the false-failure class this area was pulled out for.
    """
    txt = read(os.path.join(task, "task.toml"))
    if txt is None:
        return                      # already reported by check_verifier_network_mode

    env_body = toml_section(txt, "verifier.env")
    if env_body is None:
        r.fail("verifier.env",
               f"no [verifier.env] block; judge.py's API backend reads "
               f"{sorted(EVAL_ENV_KEYS)} and gets nothing, so it falls back to the sub-agent "
               f"request on every run. These are ${{VAR}} references expanded by harbor at run "
               f"time — no credential is written into the bundle")
        return
    missing = [k for k in EVAL_ENV_KEYS if not re.search(r"^\s*" + k + r"\s*=", env_body, re.M)]
    if missing:
        r.fail("verifier.env",
               f"[verifier.env] does not map {sorted(missing)}; judge.py's API backend needs all "
               f"of {sorted(EVAL_ENV_KEYS)} and skips grading entirely if any one is empty")
    else:
        r.ok("verifier.env", f"maps all of {sorted(EVAL_ENV_KEYS)} from the host environment")


# --------------------------------------------------------------- shared gate checks
def check_gate(r, task, mode):
    """The --rubric gate lives in verifier.py + test.sh and should stay wired in BOTH modes.

    SEVERITY IS MODE-AWARE, and the dividing line is "can its absence mis-score a run?":

      Mode A - a rubric ships, so missing plumbing is a genuine scoring defect: the judge's
               `fail` verdict never reaches the gate, and a task that should record 0.0 records
               1.0 instead. FAIL, blocking.
      Mode B - no rubric ships, so there is no verdict to lose. Measured against golden 2's own
               _rubric_verdict(): `--rubric ""` (what its test.sh actually sends) and omitting the
               flag entirely BOTH yield verdict=None -> rubric_passed=-1. The wiring is inert, so
               its absence cannot change any reward. Reported as a CANDIDATE - still surfaced, so
               the corpus converges on one verifier shape and a task that later gains a rubric
               needs no verifier surgery, but it cannot block a correct rubric-less bundle.

    Everything else in this function stays FAIL in both modes, because those defects DO mis-score
    regardless of the rubric: partial credit, a non-canonical reward.json, hardcoded identifiers.
    """
    plumbing = r.fail if mode == "A" else r.warn
    inert = "" if mode == "A" else (" (inert in Mode B - no verdict to carry - but it keeps the "
                                    "verifier shape uniform and the task rubric-ready)")
    vp, tp = os.path.join(task, "tests", "verifier.py"), os.path.join(task, "tests", "test.sh")
    v, t = read(vp), read(tp)

    if v is None:
        r.fail("verifier.present", "tests/verifier.py missing")
    else:
        if not parses_rubric_flag(v):
            plumbing("verifier.gate", "verifier.py does not parse --rubric; the verdict cannot "
                                      "reach the gate" + inert)
        else:
            r.ok("verifier.gate", "parses --rubric")

        # The gate must zero a 1.0, not halve it. Scope note: this owns the GATE -- what a
        # failed rubric does to the reward. Out-of-domain values anywhere else in the verifier
        # belong to check_reward_domain, which runs unconditionally; the generic
        # `reward = 0.5` clause was removed from here so one 0.5 is not reported twice.
        if re.search(r"rubric\s*==\s*[\"']fail[\"']", v):
            if re.findall(r"rubric\s*==\s*[\"']fail[\"'][^\n]*\n?[^\n]*?=\s*0\.5", v):
                r.fail("verifier.gate.value",
                       "a submission that FAILS the rubric still scores 0.5 — it should score 0.\n"
                       "  where: the `rubric == \"fail\"` branch in tests/verifier.py sets 0.5\n"
                       "  fix:   set it to 0.0 — `if rubric == \"fail\": reward = 0.0`\n"
                       "  why:   half credit for failing the rubric means the rubric cannot "
                       "actually reject anything. It only nudges the score, so a submission the "
                       "judge rejected still counts as partly correct")
            else:
                r.ok("verifier.gate.value", "failed rubric zeroes the reward")
        else:
            r.warn("verifier.gate.value", "could not locate the `rubric == \"fail\"` gate; "
                                          "confirm by hand")

        check_reward_domain(r, task)

        # reward.json must be a FLAT {str: float|int}. These assignments are harbor-fatal.
        nested = re.findall(r"detail\[[\"'](f2p|p2p|rubric|rubric_failed)[\"']\]\s*=\s*"
                            r"(?!.*(?:len\(|sum\(|1\.0|0\.0|int\(|\{\"pass\"))", v)
        if nested:
            r.fail("verifier.reward_json",
                   f"assigns non-numeric value(s) {sorted(set(nested))} into reward.json. "
                   f"harbor parses it as dict[str, float|int] and aborts the trial before "
                   f"recording any reward")
        canon = [n for n in ("_canon_project", "_canon_policy", "_canon_capture") if n in v]
        if canon:
            r.ok("verifier.reward_json", f"canonicalised via {canon[0]}()")
        elif not nested:
            r.open_("verifier.reward_json", "no _canon_* helper found; confirm reward.json is a "
                                            "flat map of exactly the canonical 7 keys")

        # The exact key set both goldens emit. A missing key is not cosmetic: downstream
        # analysis reads these positionally across the corpus.
        gone = [k for k in CANON_REWARD_KEYS
                if f'"{k}"' not in v and f"'{k}'" not in v]
        if gone:
            migrating = ("rubric_passed" in gone and re.search(r"['\"]rubric_pass['\"]", v)
                         is not None)
            hint = ("  MIGRATION: this verifier still writes the OLD key `rubric_pass`. The "
                    "canonical name is now `rubric_passed`; rename it at the write site in "
                    "verifier.py. Runs recorded before the rename carry the old key and are not "
                    "retroactively wrong." if migrating else "")
            r.fail("verifier.reward_json.keys",
                   f"reward.json is missing canonical key(s) {gone}. The golden shape is exactly "
                   f"{CANON_REWARD_KEYS} — flat, all numeric, rubric_passed = 1 pass / 0 fail / "
                   f"-1 not graded.{hint}")
        else:
            r.ok("verifier.reward_json.keys", "emits all 7 canonical keys")

        # Identifiers belong in config.json, not duplicated in the verifier.
        if re.search(r"^\s*(F2P_IDENTIFIERS|P2P_IDENTIFIERS)\s*=\s*\[", v, re.M):
            r.fail("verifier.config", "hard-codes F2P/P2P identifier lists instead of reading "
                                      "tests/config.json — they drift from task.toml silently")
        elif "config.json" in v:
            r.ok("verifier.config", "reads f2p/p2p from config.json")
        else:
            r.open_("verifier.config", "cannot tell where f2p/p2p come from; confirm by hand")

    if t is None:
        r.fail("test_sh.present", "tests/test.sh missing")
        return
    tc = strip_sh_comments(t)          # a commented-out block wires nothing
    guarded = re.search(r"if\s+\[\s+-f\s+/tests/rubrics\.json\s+\]", tc) is not None
    invokes = "judge.py" in tc
    passes = re.search(r"verifier\.py[^\n|;&]*--rubric(?!s)", tc) is not None
    if not passes:
        plumbing("test_sh.gate", "test.sh does not pass --rubric to verifier.py "
                                 "(judge.py's own --rubrics does not count)" + inert)
    else:
        r.ok("test_sh.gate", "passes --rubric to verifier.py")
    if not invokes:
        plumbing("test_sh.judge", "test.sh never invokes judge.py" + inert)
    elif not guarded:
        # An UNGUARDED judge block stays a hard failure in both modes: in Mode B it would run
        # judge.py against a rubrics.json that does not exist on every single run.
        r.fail("test_sh.judge", "the judge block is not guarded by `[ -f /tests/rubrics.json ]`; "
                                "the same test.sh must work in both modes")
    else:
        r.ok("test_sh.judge", "judge block guarded by `[ -f /tests/rubrics.json ]`")
    if invokes and '|| echo ""' not in tc and "|| echo ''" not in tc:
        r.warn("test_sh.judge.safety", "the load-bearing `|| echo \"\"` is absent; the judge must "
                                       "never be able to fail the run")


# ------------------------------------------------------------------- mode A: rubric
def check_rubric_mode(r, task, doc, real, stubs):
    tid_toml = tid_conf = None
    toml = read(os.path.join(task, "task.toml")) or ""
    m = re.search(r'^\s*task_id\s*=\s*"([^"]+)"', toml, re.M)
    if m:
        tid_toml = m.group(1)
    conf, _ = load_json(os.path.join(task, "tests", "config.json"))
    if conf:
        tid_conf = conf.get("task_id")

    sch = doc.get("schema")
    if sch == CANONICAL_SCHEMA:
        r.ok("rubrics.schema", f"{CANONICAL_SCHEMA}")
    elif sch in LEGACY_SCHEMAS:
        r.warn("rubrics.schema", f"{sch!r} is legacy; {CANONICAL_SCHEMA!r} is canonical")
    else:
        r.fail("rubrics.schema", f"schema is {sch!r}; expected {CANONICAL_SCHEMA!r}")

    ids = {v for v in (doc.get("task"), tid_toml, tid_conf) if v}
    if len(ids) > 1:
        r.fail("rubrics.task_id", f"task id disagrees across files: rubrics={doc.get('task')!r} "
                                  f"task.toml={tid_toml!r} config={tid_conf!r}")
    else:
        r.ok("rubrics.task_id", f"consistent ({doc.get('task')!r})")

    desc = str(doc.get("description", "")).strip()
    if not desc:
        r.fail("rubrics.description", "empty; it must say what class of defect the rubric guards "
                                      "and why the behavioral suite cannot")
    elif STUB_TEXT.search(desc):
        r.fail("rubrics.description", f"still carries the stub wording {desc!r} alongside real "
                                      f"criteria")
    elif len(desc) < 80:
        r.warn("rubrics.description", f"only {len(desc)} chars; state the loophole the tests "
                                      f"leave open, not just a label")
    else:
        r.ok("rubrics.description", f"{len(desc)} chars, states the rubric's purpose")

    if stubs:
        r.fail("rubrics.stub", f"always-pass stub {stubs} ships alongside {len(real)} real "
                               f"criterion(s); remove the stub")

    changed = golden_changed_files(task)
    seen_ids = set()
    for c in real:
        cid, text = str(c.get("id", "?")), str(c.get("criterion", "")).strip()
        if not cid or cid == "?":
            r.fail("criterion.id", "a criterion has no id")
        elif cid in seen_ids:
            r.fail("criterion.id", f"duplicate id {cid!r}")
        elif not re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)*", cid):
            r.warn("criterion.id", f"{cid!r} is not snake_case")
        seen_ids.add(cid)

        if not text:
            r.fail("criterion.text", f"[{cid}] empty criterion")
            continue
        m = DEFERS.search(text)
        if m:
            r.fail("criterion.self_contained",
                   f"[{cid}] defers to {m.group(0)!r}; the judge never sees the prompt, the "
                   f"golden fix or the tests, so this scores 0 on a correct submission")
        m = UI_ONLY.search(text)
        if m and not FILEREF.search(text):
            r.fail("criterion.self_contained",
                   f"[{cid}] reads as a rendered-UI check ({m.group(0)!r}); rephrase around a "
                   f"code signal")
        m = VAGUE.search(text)
        if m:
            r.warn("criterion.measurable", f"[{cid}] unmeasurable qualifier {m.group(0)!r}")
        refs = set(FILEREF.findall(text))
        if not refs:
            r.warn("criterion.anchored", f"[{cid}] names no source file; anchor it to the file "
                                         f"the judge should read")
        elif changed is not None:
            for ref in refs:
                if not any(ref.lower() == os.path.basename(p).lower()
                           or p.lower().endswith(ref.lower()) for p in changed):
                    r.fail("criterion.source",
                           f"[{cid}] names {ref!r}, which the golden fix.patch does not touch "
                           f"({[os.path.basename(p) for p in changed]})")
    if not [row for row in r.rows if row[1].startswith("criterion.") and row[0] == "FAIL"]:
        r.ok("criterion.*", f"{len(real)} criterion(s) are self-contained and code-decidable")
    r.open_("criterion.semantics",
            "Overfitting / Underfitting / Incorrect / Missing / Contradiction / Overlapping are "
            "not statically decidable — grade them by reading (qc_rubrics.py --emit-graders)")

    # judge.py. THE API BACKEND IS REQUIRED (policy change, see check_verifier_env).
    jp = os.path.join(task, "tests", "judge.py")
    j = read(jp)
    api_backend = False
    if j is None:
        r.fail("judge.present", "tests/rubrics.json ships but tests/judge.py is missing; the "
                                "rubric is never graded")
    else:
        api_backend = JUDGE_API_MARKER in j
        if api_backend:
            r.ok("judge.backend", "API-capable (in-band grading, sub-agent fallback)")
        else:
            # This used to be an [ok]: both backends were legal. A sub-agent-only judge is
            # not WRONG, it is INCOMPLETE -- it cannot grade during the run, so every run
            # records rubric_passed = -1 until a human reads PROMPT.md, writes verdict.json
            # and reruns rescore. That step is routinely skipped, and a rubric that never
            # grades is decorative exactly as an all-pass stub is: the layer looks wired and
            # measures nothing. Same defect, different route, so the same blocking severity.
            r.fail("judge.backend",
                   "tests/judge.py has no API backend (no call_eval_api), so it cannot grade "
                   "IN-BAND: every run records rubric_passed = -1 until someone grades "
                   "PROMPT.md by hand and reruns rescore. A rubric that only grades on a "
                   "manual follow-up is decorative. Add the API backend (keep the sub-agent "
                   "path as its fallback) — see RUBRIC_MODES.md")
        for k, why in JUDGE_QUALITY_MARKERS.items():
            if k not in j:
                r.warn("judge.context", f"no {k}(); the judge gets {why}")

        # Only a defect if verifier.py actually reads a path judge.py never writes.
        v_src = read(os.path.join(task, "tests", "verifier.py")) or ""
        if "/logs/verifier/rubric.json" in v_src and "rubric.json" not in j:
            r.fail("judge.rubric_json",
                   "verifier.py reads /logs/verifier/rubric.json but judge.py never writes it — "
                   "that list is structurally always empty. Either write it in judge.py or drop "
                   "the read (the canonical reward.json does not need it)")
        blk = exclude_re_block(j)
        if blk is None:
            r.fail("judge.exclude", "judge.py has no EXCLUDE_RE; the graded tests are not "
                                    "stripped from the diff the judge reads")
        else:
            lost = [d for pat, d in JUDGE_EXCLUDE_MARKERS.items() if pat not in blk]
            if lost:
                r.warn("judge.exclude", f"EXCLUDE_RE does not strip {', '.join(lost)} from the "
                                        f"diff. Harmless if this repo has no such tests, but "
                                        f"harbor generates harbor_test.js itself, and a judge "
                                        f"that sees the graded tests grades similarity to them")
            else:
                r.ok("judge.exclude", "EXCLUDE_RE strips JS/TS, python, go and harbor test paths")
        if "return 0" not in j:
            r.warn("judge.never_fails", "confirm judge.py always exits 0 — it must never be able "
                                        "to fail the run")

    # config.json wiring
    if conf is None:
        r.fail("config.rubric_file", "tests/config.json missing or unparseable")
    elif conf.get("rubric_file") != "rubrics.json":
        r.fail("config.rubric_file",
               f'"rubric_file" is {conf.get("rubric_file")!r}; must be "rubrics.json" so the '
               f"rubric is picked up")
    else:
        r.ok("config.rubric_file", '"rubric_file": "rubrics.json"')

    # task.toml is not graded HERE, but both of its verifier blocks ARE graded: network_mode by
    # check_verifier_network_mode (every task, from check_task) and [verifier.env] by
    # check_verifier_env (Mode A only, from the branch below). This function owns the rubric
    # setup and reads task.toml only for the task_id cross-check above.


# ---------------------------------------------------------------- mode B: no rubric
def check_no_rubric_mode(r, task):
    j = os.path.join(task, "tests", "judge.py")
    if os.path.exists(j):
        r.fail("judge.absent", "tests/judge.py still ships with no tests/rubrics.json to grade; "
                               "strip it — a judge with no rubric is dead weight")
    else:
        r.ok("judge.absent", "tests/judge.py correctly absent")

    conf, err = load_json(os.path.join(task, "tests", "config.json"))
    if conf is None:
        r.fail("config.rubric_file", f"tests/config.json missing or unparseable ({err})")
    elif "rubric_file" in conf:
        r.fail("config.rubric_file",
               f'"rubric_file": {conf["rubric_file"]!r} points at a rubric that does not ship; '
               f"remove the key")
    else:
        r.ok("config.rubric_file", "no rubric_file key, as expected")

    # [verifier.env] is correctly NOT required of a Mode B task -- nothing reads EVAL_*, and its
    # bare "${VAR}" entries would make harbor demand host credentials for an otherwise keyless
    # run. [verifier] network_mode IS required, and is checked for every task in check_task():
    # a sealed verifier cannot install test dependencies, rubric or no rubric.


# ------------------------------------------------------------------------- dispatch
def check_task(task):
    r = Report(task)
    rp = os.path.join(task, "tests", "rubrics.json")

    # BOTH MODES, so it is called BEFORE the mode is decided -- one call site rather than a copy
    # in each of the five dispatch branches, which is how a branch gets missed. A sealed verifier
    # cannot install test dependencies whether or not the task ships a rubric.
    check_verifier_network_mode(r, task)

    if not os.path.exists(rp):
        r.mode = "B — NO_RUBRIC (rubric layer stripped)"
        check_no_rubric_mode(r, task)
        check_gate(r, task, "B")
        return r

    doc, err = load_json(rp)
    if doc is None:
        r.mode = "BROKEN"
        r.fail("rubrics.parse", f"tests/rubrics.json does not parse: {err}")
        check_gate(r, task, "A")
        return r

    criteria = [c for c in (doc.get("criteria") or []) if isinstance(c, dict)]
    stubs = [c.get("id") for c in criteria if is_stub(c, doc)]
    real = [c for c in criteria if not is_stub(c, doc)]

    if not criteria:
        r.mode = "BROKEN"
        r.fail("rubrics.criteria", "rubrics.json ships with no criteria; either write real "
                                   "criteria or strip the rubric layer")
        check_gate(r, task, "A")
        return r

    if not real:
        r.mode = "INVALID — all-pass stub only"
        r.fail("rubrics.stub_only",
               f"the only criterion is the all-pass stub {stubs} "
               f"({str(doc.get('description', ''))[:60]!r}). An all-pass rubric grades nothing: "
               f"it cannot fail any submission, and it makes rubric_passed read 1 as though a "
               f"real rubric had been satisfied. STRIP the rubric layer instead — delete "
               f"tests/rubrics.json and tests/judge.py, and drop \"rubric_file\" from "
               f"tests/config.json. Leave the --rubric gate in verifier.py and the guarded "
               f"judge block in test.sh untouched.")
        # Still report what else is mis-wired, so one pass gives the whole picture.
        check_no_rubric_mode(r, task)
        check_gate(r, task, "B")
        return r

    r.mode = f"A — RUBRIC ({len(real)} real criterion(s))"
    check_rubric_mode(r, task, doc, real, stubs)
    check_gate(r, task, "A")
    # Mode A ONLY, and this is the half that must stay that way: [verifier.env]'s bare "${VAR}"
    # entries are REQUIRED host vars to harbor, so demanding them of a rubric-less task breaks
    # its keyless oracle/nop for credentials no judge would ever read. network_mode has no such
    # cost and is checked for every task, above.
    check_verifier_env(r, task)
    return r


# ------------------------------------------------------------------ QC integration
# The rubric layer books against the reviewer's RUBRIC & JUDGE dimension. Format defects are
# reported as FAIL + blocking; heuristics as CANDIDATE; the semantic pass as OPEN.
RUBRIC_DIM = "Fail - Rubric Quality"
_SEV_MAP = {"FAIL": "FAIL", "WARN": "CANDIDATE", "OPEN": "OPEN", "OK": "OK"}


def finding_id(check):
    """`criterion.self_contained` -> `rubfmt_criterion_self_contained`.

    Derived, not table-driven, so a new check cannot silently emit an id nothing routes.
    """
    return "rubfmt_" + re.sub(r"[^a-z0-9]+", "_", check.lower()).strip("_")


def export_findings(reports, path):
    """Translate the report rows into the shared finding model.

    Rows are grouped BY CHECK, so five criteria failing one rule read as one defect with five
    pieces of evidence rather than five defects - the same convention qc_rubrics uses.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from qc_common import Finding, dump_findings, TIER_BUNDLE

    out = []
    for r in reports:
        groups = {}
        for sev, check, msg in r.rows:
            g = groups.setdefault((check, sev), [])
            g.append(msg)
        # MODE is worth stating even when everything passes: it is the one line that says which
        # of the two shapes the task was judged against.
        #
        # SEVERITY TRACKS THE MODE, NOT THE REPORT. This was `"FAIL" if r.failed else "OK"`,
        # which made the status line itself a blocking FAIL whenever ANY other check failed --
        # so a task whose shape was identified perfectly ("MODE A — RUBRIC (2 real criterion(s))")
        # was reported as a blocker carrying `action:decide`, telling a CB to decide something
        # about a non-problem and inflating the blocker count by one on every failing bundle.
        # `rubfmt_mode` means what the glossary says it means -- "the rubric layer is in neither
        # of the two valid shapes" -- so it fails only when the mode is genuinely un-shaped.
        mode_broken = r.mode.startswith(("BROKEN", "INVALID"))
        out.append(Finding("rubfmt_mode", f"rubric layer judged as MODE {r.mode}",
                           "FAIL" if mode_broken else "OK",
                           category="rubric_judge", rubric_dim=RUBRIC_DIM, tier=TIER_BUNDLE,
                           blocking=mode_broken,
                           evidence=[f"{os.path.basename(r.task)}: {r.mode}"],
                           source=["qc_rubric_format"]))
        for (check, sev), msgs in groups.items():
            mapped = _SEV_MAP.get(sev, "CANDIDATE")
            out.append(Finding(
                finding_id(check),
                f"{check}: {msgs[0]}" if len(msgs) == 1
                else f"{check} - {len(msgs)} finding(s)",
                mapped,
                category="rubric_judge", rubric_dim=RUBRIC_DIM, tier=TIER_BUNDLE,
                # A format defect voids the measurement, so it blocks. Only FAILs block:
                # a heuristic candidate must never gate the run.
                blocking=(mapped == "FAIL"),
                evidence=msgs[:6],
                needs=("a reading pass" if mapped == "OPEN" else None),
                # action is left to FIX_HINTS: it knows which of these are mechanical
                # (rubric_file, schema, task id) and which are authoring or a decision.
                source=["qc_rubric_format"]))
    dump_findings(out, path)
    return len(out)


def resolve_tasks(path):
    """Accept a deliverables root, a Tasks/ dir, or any dir holding task.toml.

    qc_all hands every check the ROOT, while a CB points at Tasks/ - guessing wrong is how a
    check ends up reporting on nothing and reading as clean.
    """
    path = os.path.abspath(path.rstrip("/"))
    if os.path.isfile(os.path.join(path, "task.toml")):
        return path
    for cand in ("Tasks", "project"):
        p = os.path.join(path, cand)
        if os.path.isfile(os.path.join(p, "task.toml")):
            return p
    # Nested Tasks/<any-name>/task.toml - see qc_layout.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from qc_layout import find_task_dir, AmbiguousLayout
    try:
        found = find_task_dir(path)
    except AmbiguousLayout as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    return found or path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks", nargs="+")
    ap.add_argument("--json", metavar="OUT")
    ap.add_argument("--emit-findings", metavar="OUT",
                    help="write findings in the shared qc_common model (for qc_all.py)")
    ap.add_argument("--quiet", action="store_true", help="emit findings only, print nothing")
    a = ap.parse_args()

    reports = []
    for t in a.tasks:
        t = resolve_tasks(t)
        if not os.path.isfile(os.path.join(t, "task.toml")):
            print(f"error: no task.toml under {t}", file=sys.stderr)
            return 2
        r = check_task(t)
        if not a.quiet:
            r.print()
        reports.append(r)

    if a.emit_findings:
        n = export_findings(reports, a.emit_findings)
        if not a.quiet:
            print(f"  wrote {n} finding(s) -> {a.emit_findings}")

    if not a.quiet:
        print(f"\n{'=' * 78}\nSUMMARY")
        for r in reports:
            print(f"  {'FAIL' if r.failed else 'PASS'}  {os.path.basename(r.task):24} {r.mode}")
    if a.json:
        json.dump([{"task": r.task, "mode": r.mode,
                    "verdict": "FAIL" if r.failed else "PASS",
                    "findings": [{"severity": s, "check": c, "message": m} for s, c, m in r.rows]}
                   for r in reports], open(a.json, "w"), indent=2)
        print(f"  wrote {a.json}")
    return 1 if any(r.failed for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
