#!/usr/bin/env python3
"""MM SWE QC - the shared finding model, category map, phase/tier logic and renderer.

WHY THIS EXISTS. The four checks grew independently and each invented its own severity
vocabulary (structure: a `[FAIL]` prefix; rubrics: Major/Moderate/Minor; judge:
FAIL/WARN/MANUAL/INFO; gate: a flat PROBLEMS list). A CB could not tell whether `[check]`
outranked `Moderate`. Worse, findings were grouped by the TOOL that found them rather than by
the defect class, so one defect reported by two checks read as two defects, and the reviewer's
own dimension tags - which the checks already carry - were buried mid-sentence in prose.

THE PHASE MODEL IS THE SPINE. QC has to be useful BEFORE the trial is spent, because the trial
is the only step that costs a real model call. So every check declares the TIER of artifact it
needs, and a finding whose tier is not available at the current phase becomes OPEN - never FAIL:

    bundle      Tasks/ only.                       free           <- the default
    gate        + Oracle/ + Nop/.                  keyless, docker only
    trial       + Trials/.                         a real model call
    submission  + the four .tar.gz at root.        packaging time

    bundle  <  gate  <  post-trial  <  submission        (cumulative)

THE HARD GUARANTEE: the verdict and exit code are computed over DECIDABLE findings only. An
OPEN or N/A finding can never make the exit code non-zero, so a sound bundle at phase `bundle`
exits 0 - while the verdict line still states plainly that the gate was not reproduced and the
trial was not run. "Nothing was checked" must never be able to read as "everything passed".

Stdlib only, no network - same guarantee as every check that imports this.
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qc_layout import deliverables_root, find_trial_dirs, run_path

# --------------------------------------------------------------------------- tiers
TIER_BUNDLE, TIER_GATE, TIER_TRIAL, TIER_SUBMISSION = "bundle", "gate", "trial", "submission"
TIER_ORDER = [TIER_BUNDLE, TIER_GATE, TIER_TRIAL, TIER_SUBMISSION]

# What would unlock a finding whose tier is not yet available. This is the `needs:` the report
# prints, and it is the difference between "we cannot tell yet" and "this failed".
TIER_NEEDS = {
    TIER_GATE: "oracle+nop",
    TIER_TRIAL: "trial",
    TIER_SUBMISSION: "packaging",
}

# Phases are cumulative: each includes every tier at or below it.
PHASES = ["bundle", "gate", "post-trial", "submission"]
PHASE_TIERS = {
    "bundle":     {TIER_BUNDLE},
    "gate":       {TIER_BUNDLE, TIER_GATE},
    "post-trial": {TIER_BUNDLE, TIER_GATE, TIER_TRIAL},
    "submission": {TIER_BUNDLE, TIER_GATE, TIER_TRIAL, TIER_SUBMISSION},
}
PHASE_LABEL = {
    "bundle":     "bundle (T0, no runs present)",
    "gate":       "gate (T1, oracle+nop present)",
    "post-trial": "post-trial (T2, a trial exists)",
    "submission": "submission (packaged)",
}


def detect_phase(deliv):
    """Infer the phase from what is actually on disk. Deliberately conservative: a run dir only
    counts if it holds a trial dir, so a leftover empty folder cannot promote the phase and make
    a trial-tier check fire against nothing."""
    def has_run(name):
        d = run_path(deliv, name)
        if not os.path.isdir(d):
            return False
        # Any trial dir, whatever its name: a nested task's trials are `<task-name>__*`, not
        # `Tasks__*`, and a timestamped job puts them one level further down.
        return bool(find_trial_dirs(d))
    oracle, nop, trials = has_run("Oracle"), has_run("Nop"), has_run("Trials")
    if oracle and nop and trials and all(
            os.path.exists(os.path.join(deliv, f"{n}.tar.gz"))
            for n in ("Tasks", "Trials", "Oracle", "Nop")):
        return "submission"
    if oracle and nop and trials:
        return "post-trial"
    if oracle and nop:
        return "gate"
    return "bundle"


def tier_available(tier, phase):
    return tier in PHASE_TIERS.get(phase, PHASE_TIERS["bundle"])


# ------------------------------------------------------------------------ severity
FAIL = "FAIL"              # trips a rubric Fail condition
NON_FAIL = "NON-FAIL"      # a real defect that trips no Fail condition (the v2 #6 case)
PENDING = "PENDING"        # proposed; the verdict needs a READ the script cannot perform
CANDIDATE = "CANDIDATE"    # heuristic hit; a human must confirm
OPEN = "OPEN"              # not decidable at this phase - see `needs`
NA = "N/A"                 # does not apply here
OK = "OK"

SEV_RANK = {FAIL: 6, NON_FAIL: 5, PENDING: 4, CANDIDATE: 3, OPEN: 2, NA: 1, OK: 0}
SEV_TAG = {FAIL: "FAIL", NON_FAIL: "NONFAIL", PENDING: "PEND", CANDIDATE: "CAND", OPEN: "OPEN",
           NA: "N/A", OK: "ok"}

# WHY `PENDING` IS A SEVERITY AND NOT A FLAG.
# check_F used to hardcode a verdict about a pattern its author had not seen: any identifier that
# was a SUBSTRING of another was an unconditional FAIL, decided without ever opening the verifier
# that does the matching. On a task matching with `k.endswith(ident)` that is wrong by
# construction, and the CB got a blocker the audit had no fix for.
#
# The repair is NOT a cleverer predicate -- the next unfamiliar matcher would break that one too.
# It is to split PROPOSING from DECIDING: the script gathers evidence and proposes, and the agent
# driving the skill reads `tests/verifier.py` and records the verdict (`--adjudicated`). PENDING is
# that middle state, and it needs to be a severity because the renderer, `dedup()` and the marker
# all key off severity -- a flag would be silently dropped by each of them.
#
# It is DECIDABLE (it describes something that WAS checked, unlike OPEN) but NOT exit-worthy: a
# defect nobody has confirmed must not fail a run. What it DOES block is the `.qc_passed` marker,
# because the alternative is worse than the false positive being fixed -- a headless audit with no
# agent to adjudicate would otherwise report a real collision as clean.
#
# OPEN and N/A stay excluded on purpose: they describe what was NOT checked, and letting them
# colour the verdict is exactly how "the trial has not run" became "the task fails".
DECIDABLE = {FAIL, NON_FAIL, PENDING, CANDIDATE, OK}
# Only a hard FAIL sets a non-zero exit code. A CANDIDATE is a heuristic, a PENDING is unadjudicated
# and a NON-FAIL is defined as not tripping a Fail condition, so none may fail the run - this
# matches what qc_structure and qc_judge already did with their own exit codes.
EXIT_WORTHY = {FAIL}
# The severities the renderer shows in full rather than collapsing into "N check(s) clean".
LOUD = (FAIL, NON_FAIL, PENDING, CANDIDATE)
# OK results that are NAMED on their category's line instead of vanishing into "N check(s) clean".
# A clean result is still a result the CB is told about: /run-check reports the instruction wording
# scan beside the "could this be fixed without the screenshots?" read every time, hit or clean, and
# it cannot report a clean scan the audit never printed.
# None pins the finding's own title, for a clean result whose wording depends on how it was reached
# (the instruction read names the model that made it, or says it fell back to the phrase scan).
PINNED_OK = {"instr_lint_clean": "instruction wording scan: clean",
             "instr_lint_symptom_clean": None}
# Advisory groups with no rubric dimension (group L) would otherwise print an empty dimension column.
NO_DIM_LABEL = (("instr_lint_", "Instruction wording · advisory"),)


def _pinned(fs):
    return [PINNED_OK[f.id] or f.title for f in fs if f.severity == OK and f.id in PINNED_OK]


# ---------------------------------------------------------------------- categories
# The category axis is the QC rubric v2 dimension set - the values a reviewer puts in the eval
# dropdown. The tags were already in the checks; they just were not the organizing principle.
CATEGORIES = [
    ("structure",    "STRUCTURE & PACKAGING",
     ["Fail - Broken Structure", "Fail - Deliverable Packaging"]),
    ("fix_tests",    "GOLDEN FIX & TESTS",
     ["Fail - Dirty Fix Scope", "Fail - Bad Test IDs", "Fail - Implementation Overfit"]),
    ("evidence",     "EVIDENCE & IMAGE",
     ["Fail - Evidence Mismatch", "Fail - Bad Evidence", "Fail - Wrong task_type"]),
    ("rubric_judge", "RUBRIC & JUDGE",
     ["Fail - Rubric Quality"]),
    ("gate",         "GATE & MEASUREMENT",
     ["Fail - Gate Broken", "Fail - Unauditable"]),
    ("hardening",    "HARDENING & DIFFICULTY",
     ["Fail - Not Hard Enough", "Fail - Unreal or Infeasible"]),
]
CATEGORY_TITLE = {k: t for k, t, _ in CATEGORIES}
CATEGORY_ORDER = [k for k, _, _ in CATEGORIES]
CATEGORY_NUM = {k: i + 1 for i, k in enumerate(CATEGORY_ORDER)}

# Two dimension names in the checks denote one dimension, and one differs only by case.
# Canonicalising here is what lets the router treat them as the same category.
DIM_ALIASES = {
    "fail - missing/broken rubrics": "Fail - Rubric Quality",
    "fail - unauditable": "Fail - Unauditable",
    "failure - unauditable": "Fail - Unauditable",
}
DIM_TO_CATEGORY = {}
for _k, _t, _dims in CATEGORIES:
    for _d in _dims:
        DIM_TO_CATEGORY[_d.lower()] = _k

# A defect that voids the measurement: until it is fixed, no other number means anything.
BLOCKING_DIMS = {"Fail - Gate Broken", "Fail - Unauditable"}

# Rubric FORMAT defects (qc_rubric_format) are blocking too, but the dimension they book against
# - "Fail - Rubric Quality" - also carries non-blocking CONTENT findings from qc_rubrics, so it
# cannot go in BLOCKING_DIMS wholesale. qc_rubric_format therefore sets `blocking=True` per
# finding instead. Recorded here because BLOCKING_DIMS is the first place anyone looks to ask
# "what blocks?", and the honest answer is now "these dimensions, plus any rubric-format FAIL".

_DIM_RE = re.compile(r"\[(Fail(?:URE)?|FAIL)\s*-\s*([^\]]+)\]", re.I)


def normalize_dim(text):
    """Pull a `[Fail - X]` tag out of a message and canonicalise it. Returns None if absent."""
    m = _DIM_RE.search(text or "")
    if not m:
        return None
    dim = f"Fail - {m.group(2).strip()}"
    return DIM_ALIASES.get(dim.lower(), dim)


def category_for_dim(dim, default=None):
    if not dim:
        return default
    return DIM_TO_CATEGORY.get(DIM_ALIASES.get(dim.lower(), dim).lower(), default)


def strip_dim(text):
    """Remove the inline `[Fail - X]` tag; the renderer shows it in its own column instead."""
    return re.sub(r"\s*\[(Fail(?:URE)?|FAIL)\s*-\s*[^\]]+\]\s*", " ", text or "").strip()


# ------------------------------------------------------- how does the verifier match identifiers?
# EVIDENCE, NEVER A VERDICT. Everything below reports what it saw in tests/verifier.py so a finding
# can cite `tests/verifier.py:118` and an agent can adjudicate from the actual line. It deliberately
# does not decide whether a collision is real: that is the mistake being repaired, and returning
# `unknown` is a legitimate, expected answer rather than a failure of the function.
#
# THE SCOPING IS THE WHOLE TRICK. A naive scan for `endswith` / ` in ` / `==` anywhere in the file
# misclassifies every verifier in the corpus, because load_junit() alone contains
# `if any(c.tag == 'skipped' for c in tc)` -- an `==` and a `for ... in` that have nothing to do
# with identifier matching. So the search is scoped to the RESOLUTION SITE: the loop or
# comprehension that walks the configured identifier list, found by looking for iteration over an
# identifier-ish source, then classifying only the comparisons that mention that loop variable.
MATCHER_SUFFIX, MATCHER_SUBSTRING, MATCHER_EXACT, MATCHER_UNKNOWN = (
    "suffix", "substring", "exact", "unknown")

# `for <var> in <source>` / `<expr> for <var> in <source>`. The source names are the ones the corpus
# actually uses for the configured identifier list.
_IDENT_ITER = re.compile(r"\bfor\s+([A-Za-z_]\w*)\s+in\s+([A-Za-z_]\w*)")
_IDENT_SOURCE = re.compile(
    r"^(?:idents?|ident_list|identifiers?|names?|tests?|testcases?|expected|f2p|p2p)$", re.I)
# Names a verifier gives the parsed JUnit map, for telling a LOOKUP from a WRITE.
_RESULTS_MAP = re.compile(r"^(?:\w*results?\w*|\w*outcomes?\w*|junit|report|cases|testcases|"
                          r"by_name|res)$", re.I)


def _matcher_ident_vars(src):
    """Loop variables that walk the configured identifier list, plus any `idents`-ish parameter."""
    vars_ = set()
    for var, source in _IDENT_ITER.findall(src):
        if _IDENT_SOURCE.match(source):
            vars_.add(var)
    # A verifier that resolves inside `def matched(idents, results)` without a for-loop (a dict
    # comprehension, say) still names the parameter, so accept those too.
    for params in re.findall(r"\bdef\s+\w+\s*\(([^)]*)\)", src):
        for p in params.split(","):
            p = p.split("=")[0].split(":")[0].strip()
            if p and _IDENT_SOURCE.match(p):
                vars_.add(p)
    return vars_


def matcher_kind(tasks):
    """(kind, evidence) for how tests/verifier.py resolves a configured identifier to a testcase.

    kind is one of MATCHER_{SUFFIX,SUBSTRING,EXACT,UNKNOWN}; evidence is a list of
    "tests/verifier.py:<lineno>  <source line>" strings for the lines that decided it. Several
    conflicting forms, or none, yield UNKNOWN together with whatever candidate lines were seen --
    which is what routes the finding to an agent instead of to a guess.
    """
    path = os.path.join(tasks or "", "tests/verifier.py")
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError:
        return MATCHER_UNKNOWN, []

    ident_vars = _matcher_ident_vars(src)
    if not ident_vars:
        return MATCHER_UNKNOWN, []

    found, evidence = {}, []
    for lineno, line in enumerate(src.splitlines(), 1):
        code = line.split("#", 1)[0]
        for var in ident_vars:
            v = re.escape(var)
            if not re.search(rf"\b{v}\b", code):
                continue
            kinds = set()
            if re.search(rf"\.endswith\s*\(\s*{v}\b", code):
                kinds.add(MATCHER_SUFFIX)
            if re.search(rf"\.startswith\s*\(\s*{v}\b", code):
                kinds.add(MATCHER_SUBSTRING)      # prefix matching collides the same way
            # Containment, excluding the `for x in y` that introduced the variable.
            if re.search(rf"\b{v}\s+in\s+\w", code) and not re.search(rf"\bfor\s+{v}\s+in\b", code):
                kinds.add(MATCHER_SUBSTRING)
            # Exact match: an equality test, or a LOOKUP INTO THE RESULTS MAP. Both guards on the
            # lookup form are load-bearing. A bare `\[ident\]` also matches `out[ident] = hit`,
            # which is how the verifier WRITES its answer, not how it finds it -- counting that
            # classified the reference task as {suffix, exact} and therefore `unknown`, throwing
            # away a matcher that had been read correctly. So the receiver must look like a results
            # mapping, and the subscript must not be an assignment target.
            subscript = re.search(rf"\b(\w+)\s*\[\s*{v}\s*\]\s*(=(?!=))?", code)
            lookup = (subscript and _RESULTS_MAP.match(subscript.group(1))
                      and not subscript.group(2))
            if (re.search(rf"==\s*{v}\b", code) or re.search(rf"\b{v}\s*==", code) or lookup
                    or re.search(rf"\b(?:\w*result\w*|\w*outcome\w*|junit|report|cases?|"
                                 rf"testcases?)\s*\.get\s*\(\s*{v}\b", code)):
                kinds.add(MATCHER_EXACT)
            for k in kinds:
                found.setdefault(k, []).append(lineno)
                evidence.append(f"tests/verifier.py:{lineno}  {code.strip()}")

    if len(found) == 1:
        return next(iter(found)), list(dict.fromkeys(evidence))
    # Nothing recognised, or more than one form -- both are honestly "I cannot tell".
    return MATCHER_UNKNOWN, list(dict.fromkeys(evidence))


# ------------------------------------------------------------------- adjudicated verdicts
# `--adjudicated <id>=cleared|confirmed:"reason"`. Naming the verdict on the command line is the
# same idiom `--approve <id>` already uses, and it lands in qc_report.json so the decision is
# auditable from the transcript.
#
# THIS PAIR IS STILL STATELESS - it is handed a dict and knows nothing about where one comes from -
# but the SKILL no longer is, and the comment that used to sit here said otherwise. It argued that
# an on-disk verdict store would have "a structurally zero hit rate" because every task gets a
# fresh container. That is true of the case it was written for and false of the one that mattered:
# mm_run.sh's qc_gate() re-invokes `fix.py qc` with a fixed argument list, same container, same
# bundle, seconds later. With no store, that re-invocation recomputed the ruled finding as PENDING
# and deleted the QC pass the ruling had just earned, so a task with a legitimately cleared finding
# could never satisfy the gate. fix.py now records rulings and replays them; see
# qc_digest.load_rulings for what a replayed ruling may and may not do.
CLEARED, CONFIRMED = "cleared", "confirmed"


def parse_adjudications(values):
    """['id=cleared:reason', ...] -> {id: (verdict, reason)}. Raises ValueError on a bad spec."""
    out = {}
    for raw in values or []:
        for chunk in [c for c in raw.split(",") if c.strip()] if "=" not in raw else [raw]:
            spec = chunk.strip()
            if "=" not in spec:
                raise ValueError(f"--adjudicated {spec!r}: expected <id>=cleared|confirmed:\"why\"")
            fid, _, rest = spec.partition("=")
            verdict_, _, reason = rest.partition(":")
            verdict_, reason = verdict_.strip().lower(), reason.strip().strip('"').strip("'")
            if verdict_ not in (CLEARED, CONFIRMED):
                raise ValueError(f"--adjudicated {spec!r}: verdict must be "
                                 f"`{CLEARED}` or `{CONFIRMED}`, got {verdict_!r}")
            # A verdict with no reason is not auditable, and an unexplained dismissal of a possible
            # collision is exactly what this mechanism exists to prevent.
            if not reason:
                raise ValueError(f"--adjudicated {spec!r}: a reason is required "
                                 f"(<id>={verdict_}:\"why\")")
            out[fid.strip()] = (verdict_, reason)
    return out


def apply_adjudications(findings, verdicts):
    """Resolve PENDING findings the agent has ruled on. Returns (findings, unused_ids).

    `confirmed` promotes to FAIL - the collision is real and must block. `cleared` drops to OK with
    the reason recorded, so the report shows it was adjudicated rather than silently absent.
    Anything not named stays PENDING.
    """
    used = set()
    for f in findings:
        if f.severity != PENDING or f.id not in (verdicts or {}):
            continue
        verdict_, reason = verdicts[f.id]
        used.add(f.id)
        f.adjudication = (verdict_, reason)
        if verdict_ == CONFIRMED:
            f.severity = FAIL
            f.evidence = list(f.evidence) + [f"adjudicated CONFIRMED: {reason}"]
        else:
            f.severity = OK
            f.title = f"{f.title} — adjudicated CLEARED: {reason}"
    return findings, [i for i in (verdicts or {}) if i not in used]


# ----------------------------------------------------------------------- fix hints
# The join table `fix.py` will own. Keeping it here means the report can already say whether a
# finding is mechanically fixable, and stage 2 replaces this dict with a real join on finding id
# rather than fix.py re-deriving the same findings a second time in its own wording.
#   auto      mechanical, no judgment
#   agent     ONE correct repair that a script must not write; the agent makes it and proves it,
#             inside the same approval as `auto` - see RUBRIC_MODES.md 2c
#   decide    a human must decide first (assets always land here)
#   authoring rewriting it changes what the task grades - never auto-patched
#   re-run    the artifact must be produced again
#   grade     needs a grader pass
FIX_HINTS = {
    "junk":                   ("auto", "A"),
    "debris":                 ("auto", "A"),
    "empty_noncanon":         ("auto", "A"),
    "stray_files":            ("decide", "C"),
    # "legacy_creds" removed with qc_judge.check_creds and fix.py's fix of the same name: nothing
    # emits it, and it described the SUPERSEDED rule (strip [verifier.env]) that Mode A now
    # requires the opposite of.
    # additive and a no-op on a normal daemon, so it needs no question; class A because it changes
    # nothing the agent can see (same uid, same command) - it only lets the image build at all.
    "nonroot_privilege_drop": ("auto", "A"),
    "nonroot_manual":         ("authoring", "A"),
    "rubric_file":            ("auto", "A"),
    "judge_missing":          ("auto", "B"),
    # judge_drift is a QUESTION, not a repair: the two valid judge backends mean a hash mismatch
    # against the bundled template usually says "the other backend", and overwriting would replace
    # a working judge. Was ("auto", "B").
    "judge_drift":            ("decide", "B"),
    "rubric_task_id":         ("auto", "B"),
    "test_sh_judge":          ("auto", "B"),
    "rubrics_shape":          ("auto", "B"),
    "unused_assets":          ("decide", "C"),
    # Writing the missing reference into instruction.md is authoring task prose, and deciding the
    # poster does not belong is deciding what evidence the task IS - no script does either.
    "asset_not_in_instruction": ("authoring", "C"),
    # verifier.py carries TASK-SPECIFIC scoring logic, so no SCRIPT patches it. That is not the
    # same as nobody fixing it: the first three are `agent` -- one correct repair each, made by the
    # agent under the CB's single approval and proven against qc_rubric_format.
    "reward_json_nonnumeric": ("agent", "B"),
    "verifier_rubric":        ("agent", "B"),
    "verifier_reward_domain": ("agent", "B"),
    "judge_backend":          ("agent", "B"),
    # rubric CONTENT stays authoring: rewriting a criterion changes what the task grades, and
    # unlike the three above there is no single correct answer to point the agent at.
    "rubric_quality":         ("authoring", "B"),
    # --- rubric FORMAT (qc_rubric_format) ------------------------------------------------
    # Choosing between the two legal shapes is a judgement, and stripping the layer DELETES
    # files, so nothing here is ever auto-applied except the two genuinely mechanical edits.
    "rubfmt_mode":                        ("decide", "B"),
    "rubfmt_rubrics_stub_only":           ("decide", "B"),
    "rubfmt_rubrics_criteria":            ("decide", "B"),
    "rubfmt_judge_absent":                ("decide", "B"),
    "rubfmt_judge_present":               ("decide", "B"),
    "rubfmt_config_rubric_file":          ("auto", "A"),
    "rubfmt_rubrics_schema":              ("auto", "B"),
    "rubfmt_rubrics_task_id":             ("auto", "B"),
    "rubfmt_test_sh_gate":                ("auto", "B"),
    "rubfmt_test_sh_judge":               ("auto", "B"),
    # verifier.py carries TASK-SPECIFIC scoring logic; a blind insert could change what the task
    # grades, so no script writes it -- the AGENT merges the canonical reward block and proves it.
    "rubfmt_verifier_gate":               ("agent", "B"),
    "rubfmt_verifier_gate_value":         ("agent", "B"),
    "rubfmt_verifier_reward_json":        ("agent", "B"),
    # The 0.5 ladder. Its own fix now, split out of the whole-block merge: it has exact AST-located
    # sites the agent can edit, so pointing at a block-merge for it was needless scope.
    "rubfmt_verifier_reward_domain":      ("agent", "B"),
    # AUTO. The whole-block merges above rewrite scoring LOGIC, but the common case behind this
    # finding is a pure key RENAME (`rubric_pass` -> `rubric_passed`): the same value under the
    # name every consumer reads, no grading change. It was `decide` so a bulk apply would not
    # quietly rewrite five verifiers -- but the report shows it either way, so withholding it
    # bought no visibility and cost a round trip. rubric_key_rename declines to offer itself when
    # other canonical keys are missing, which is what keeps a rename from masking a larger hole.
    "rubfmt_verifier_reward_json_keys":   ("auto", "B"),
    "rubfmt_verifier_config":             ("authoring", "B"),
    "rubfmt_rubrics_description":         ("authoring", "B"),
    "rubfmt_rubrics_stub":                ("authoring", "B"),
    # Both are closed by one file copy: reference/judge.py has the API backend AND writes
    # /logs/verifier/rubric.json at the path verifier.py reads. The live fix decides auto vs agent
    # on the shipped judge's sha (stock stub -> auto), and join_fixes overwrites this hint with
    # that real kind; `agent` is only the fallback for when detect() produced no fix at all.
    "rubfmt_judge_backend":               ("agent", "B"),
    "rubfmt_judge_rubric_json":           ("agent", "B"),
}


# --------------------------------------------------------- joining checks to fixes
# THE ONLY PLACE THE TWO VOCABULARIES MEET. The checks in checks/ and fix.py's own detect() grew
# separately, so the same defect can carry different ids. Aliasing them here lets one report show
# a finding alongside the LIVE fix that repairs it, instead of the static FIX_HINTS guess.
#
# A missing entry degrades gracefully: the finding simply keeps its FIX_HINTS action and is not
# linked to an action. So this table can be incomplete without being wrong.
FIX_ID_ALIASES = {
    # three separate gaps in verifier.py, one hand-merge fixes all of them
    "verifier_no_rubric_flag": "verifier_rubric",
    "verifier_no_reward_json": "verifier_rubric",
    "verifier_no_gate_value":  "verifier_rubric",
    # The three verifier.py rubric-format gaps are the same hand-merge as verifier_rubric: one
    # canonical reward block fixes the gate, the nested reward.json and the missing keys together.
    "rubfmt_verifier_gate":             "verifier_rubric",
    "rubfmt_verifier_gate_value":       "verifier_rubric",
    "rubfmt_verifier_reward_json":      "verifier_rubric",
    # NOT verifier_rubric: the 0.5 ladder has exact AST-located sites, so it gets a targeted repair
    # instead of the whole-block merge. Keeping it aliased to verifier_rubric is what produced one
    # defect reported twice with contradictory advice.
    "rubfmt_verifier_reward_domain":    "verifier_reward_domain",
    # One file copy closes both: the reference judge has the API backend and writes rubric.json.
    "rubfmt_judge_backend":             "judge_backend",
    "rubfmt_judge_rubric_json":         "judge_backend",
    # NOT verifier_rubric (the whole-block hand-merge): when the only thing wrong is the legacy
    # key name, a targeted rename fixes it and the merge is overkill. rubric_key_rename detects
    # exactly that case and declines to offer itself when anything else is missing.
    "rubfmt_verifier_reward_json_keys": "rubric_key_rename",
    # the verifier PHASE wiring: each has one correct value and its own auto-fix, so they map
    # 1:1 rather than collapsing into a hand-merge like the verifier.py gaps above
    "rubfmt_verifier_network_mode": "verifier_network_mode",
    "rubfmt_verifier_env":          "verifier_env",
    # One Dockerfile edit un-strips every harness binary the anti-cheat removed, so all six
    # per-binary findings from qc_structure's group E join the same fix. The ids are generated
    # (`env_harness_bin_<name>`) so they are enumerated rather than pattern-matched - a new entry in
    # _HARNESS_BINS needs a line here too, which is the point: an unaliased finding degrades to its
    # static hint instead of silently claiming a fix that does not exist.
    # One rewrite closes all three BuildKit-portability findings: the heredoc becomes a portable
    # `RUN printf`, and the `# syntax=` directive that existed to enable it goes with it.
    "env_buildkit_heredoc":     "heredoc_to_run",
    "env_heredoc_unterminated": "heredoc_to_run",
    "env_syntax_directive":     "heredoc_to_run",
    # One additive Dockerfile edit closes both privilege-drop findings: the same `chmod a+rx /` goes
    # into the dropping RUNs and into the script they generate. `env_user_directive` is deliberately
    # NOT aliased - a USER stanza has no in-image repair, so linking it to a fix would promise one
    # that does not exist; it keeps its static hint instead.
    "env_nonroot_build":  "nonroot_privilege_drop",
    "env_nonroot_verify": "nonroot_privilege_drop",
    "env_harness_bin_curl": "agent_runtime_blocked",
    "env_harness_bin_wget": "agent_runtime_blocked",
    "env_harness_bin_git":  "agent_runtime_blocked",
    "env_harness_bin_bash": "agent_runtime_blocked",
    "env_harness_bin_node": "agent_runtime_blocked",
    "env_harness_bin_npm":  "agent_runtime_blocked",
    # every rubric-content issue, and the threshold verdict they produce, is the same authoring job
    "rubric_thresholds":         "rubric_quality",
    "rubric_not_self_contained": "rubric_quality",
    "rubric_incorrect":          "rubric_quality",
    "rubric_inaccurate_source":  "rubric_quality",
    "rubric_contradiction":      "rubric_quality",
    "rubric_overfitting":        "rubric_quality",
    "rubric_not_atomic":         "rubric_quality",
    "rubric_underfitting":       "rubric_quality",
    "rubric_negative_framing":   "rubric_quality",
    "rubric_missing":            "rubric_quality",
    "rubric_vague":              "rubric_quality",
    "rubric_overlapping":        "rubric_quality",
}

# fix.py's four kinds -> the action vocabulary the report prints.
# `agent` is its own action, not a flavour of "authoring": authoring means nobody may safely change
# it, whereas an agent repair has ONE correct answer and is already authorized. Collapsing them
# would put the three blockers back in the dead end the kind exists to remove.
KIND_TO_ACTION = {"auto": "auto", "agent": "agent", "ask": "decide", "never": "authoring"}

# Fixes that NO check detects, so without this they never appear in the report at all. A CB who
# read only the audit would never learn about an unreferenced asset.
FIX_ONLY_DIMENSION = {
    "debris":         ("structure", "Fail - Broken Structure", FAIL),
    "empty_noncanon": ("structure", "Fail - Broken Structure", FAIL),
    "stray_files":    ("structure", "Fail - Broken Structure", CANDIDATE),
    "unused_assets":  ("evidence",  "Fail - Evidence Mismatch", CANDIDATE),
    # Documented in the evidence files but absent from instruction.md. CANDIDATE, not FAIL: the
    # reference may be implicit in prose a filename grep cannot see, and this skill never hard-FAILs
    # on a term missing from instruction.md. The runner's integrity gate blocks on its own
    # asset-referenced-in-instruction check, which reads the container path as well as the filename.
    "asset_not_in_instruction": ("evidence", "Fail - Evidence Mismatch", CANDIDATE),
    "junk":           ("structure", "Fail - Broken Structure", FAIL),
    # Normally this DOES match group E's findings and the table is not consulted; it is the floor
    # for a forced --phase or an unreadable Dockerfile. FAIL, and blocking is set on the group E
    # findings themselves - an image the agent cannot be installed into voids the trial.
    "agent_runtime_blocked": ("hardening", "Fail - Unreal or Infeasible", FAIL),
    "heredoc_to_run":  ("hardening", "Fail - Unreal or Infeasible", FAIL),
    # Normally matched by group P's own findings; this is the floor for a forced --phase or an
    # unreadable Dockerfile. Blocking is set on the group P findings themselves.
    "nonroot_privilege_drop": ("hardening", "Fail - Unreal or Infeasible", FAIL),
    # `never`: a drop the injector declines (exec-form RUN, CMD/ENTRYPOINT, a script built some other
    # way, a USER stanza). Still a FAIL - it just has no auto-fix, exactly like heredoc_manual.
    "nonroot_manual":  ("hardening", "Fail - Unreal or Infeasible", FAIL),
    # `never`: a heredoc the rewriter declines to convert (unquoted tag, RUN heredoc). The build
    # still fails on a builder without heredoc support, so it is a FAIL - it just has no auto-fix.
    "heredoc_manual":  ("hardening", "Fail - Unreal or Infeasible", FAIL),
    "rubric_file":    ("rubric_judge", "Fail - Rubric Quality", FAIL),
    "judge_missing":  ("rubric_judge", "Fail - Rubric Quality", FAIL),
    "judge_drift":    ("rubric_judge", "Fail - Rubric Quality", FAIL),
    "rubric_task_id": ("rubric_judge", "Fail - Rubric Quality", FAIL),
    "test_sh_judge":  ("rubric_judge", "Fail - Rubric Quality", FAIL),
    "rubrics_shape":  ("rubric_judge", "Fail - Rubric Quality", FAIL),
    "rubric_quality": ("rubric_judge", "Fail - Rubric Quality", CANDIDATE),
    "verifier_rubric": ("gate", "Fail - Gate Broken", FAIL),
    # Normally these two DO match a check finding (rubfmt_verifier_reward_domain /
    # rubfmt_judge_backend) and this table is not consulted. It is the floor for when the check
    # could not run -- a verifier.py that does not parse, or a forced --phase. FAIL, not the
    # CANDIDATE default: both are blocking, and a blocker that silently stops counting toward the
    # exit code is the failure mode this whole skill exists to prevent.
    "verifier_reward_domain": ("gate", "Fail - Gate Broken", FAIL),
    "judge_backend":  ("rubric_judge", "Fail - Rubric Quality", FAIL),
}


def fix_id_for(finding):
    return FIX_ID_ALIASES.get(finding.id, finding.id)


def join_fixes(findings, fixes):
    """Attach each live fix to the finding(s) it repairs, and surface fixes nothing reported.

    `fixes` is {fix_id: Fix} from fix.py's detect(). Two things happen:
      * a finding whose id maps to a real fix gets that fix's ACTUAL action and trial class,
        replacing the FIX_HINTS guess - so `action:auto` now means "an action exists and applies
        to this bundle", not "findings of this kind are usually fixable";
      * a fix with no matching finding is added as a finding, because otherwise the audit is
        silently narrower than the repair plan.
    """
    matched = {}
    for f in findings:
        fid = fix_id_for(f)
        fx = fixes.get(fid)
        if not fx:
            continue
        f.action = KIND_TO_ACTION.get(fx.kind, fx.kind)
        f.trial_class = fx.trial_class
        matched.setdefault(fid, []).append(f)

    for fid, fx in fixes.items():
        if fid in matched:
            continue
        cat, dim, sev = FIX_ONLY_DIMENSION.get(fid, ("structure", None, CANDIDATE))
        findings.append(Finding(
            fid, fx.title, sev, category=cat, rubric_dim=dim, tier=TIER_BUNDLE,
            evidence=list(fx.evidence or [])[:6], why=fx.why,
            action=KIND_TO_ACTION.get(fx.kind, fx.kind), trial_class=fx.trial_class,
            source=["fix.py detect()"]))
    return findings, matched


# ------------------------------------------------------------------------- finding
class Finding:
    """One defect, in one vocabulary, routed to one category."""

    __slots__ = ("id", "category", "rubric_dim", "severity", "tier", "needs", "blocking",
                 "action", "trial_class", "source", "title", "evidence", "why",
                 "rubric_severity", "from_run", "suppressed", "adjudication")

    def __init__(self, fid, title, severity, category=None, rubric_dim=None,
                 tier=TIER_BUNDLE, needs=None, evidence=None, why=None, source=None,
                 action=None, trial_class=None, rubric_severity=None, blocking=None,
                 from_run=None):
        # A tag inside the message is authoritative for routing when the caller gave no category.
        dim = rubric_dim or normalize_dim(title)
        self.id = fid
        self.title = strip_dim(title)
        self.severity = severity
        self.rubric_dim = dim
        self.category = category or category_for_dim(dim, "structure")
        self.tier = tier
        self.needs = needs or (TIER_NEEDS.get(tier) if tier != TIER_BUNDLE else None)
        self.evidence = list(evidence or [])
        self.why = why
        self.source = list(source or [])
        hint = FIX_HINTS.get(fid, (None, None))
        self.action = action or hint[0]
        self.trial_class = trial_class or hint[1]
        self.rubric_severity = rubric_severity
        self.blocking = blocking if blocking is not None else (dim in BLOCKING_DIMS)
        # Which run's OUTPUT this was read from, if any. A finding read out of Oracle/Nop/Trials
        # describes those files, so it stops being true the moment that run goes stale.
        # A bare string is ONE run name, not a sequence of characters - list("Oracle") would
        # quietly produce ['O','r','a','c','l','e'] and every membership test would then fail.
        if from_run is None:
            self.from_run = []
        elif isinstance(from_run, str):
            self.from_run = [from_run]
        else:
            self.from_run = list(from_run)
        self.suppressed = None
        # (verdict, reason) once an agent has ruled on a PENDING finding; None while unadjudicated.
        # Recorded even after the severity changes, so the report can show WHY a possible collision
        # was dismissed instead of it simply vanishing from the output.
        self.adjudication = None

    def as_dict(self):
        return {"id": self.id, "title": self.title, "severity": self.severity,
                "category": self.category, "rubric_dim": self.rubric_dim,
                "tier": self.tier, "needs": self.needs, "blocking": self.blocking,
                "action": self.action, "trial_class": self.trial_class,
                "source": self.source, "evidence": self.evidence, "why": self.why,
                "rubric_severity": self.rubric_severity, "from_run": self.from_run,
                "suppressed": self.suppressed,
                "adjudication": (list(self.adjudication) if self.adjudication else None)}

    @classmethod
    def from_dict(cls, d):
        f = cls(d.get("id") or "?", d.get("title") or "", d.get("severity") or CANDIDATE,
                category=d.get("category"), rubric_dim=d.get("rubric_dim"),
                tier=d.get("tier") or TIER_BUNDLE, needs=d.get("needs"),
                evidence=d.get("evidence"), why=d.get("why"), source=d.get("source"),
                action=d.get("action"), trial_class=d.get("trial_class"),
                rubric_severity=d.get("rubric_severity"), blocking=d.get("blocking"),
                from_run=d.get("from_run"))
        f.suppressed = d.get("suppressed")
        adj = d.get("adjudication")
        f.adjudication = tuple(adj) if adj else None
        return f


def dump_findings(findings, path):
    with open(path, "w") as fh:
        json.dump([f.as_dict() for f in findings], fh, indent=2)


def load_findings(path):
    try:
        with open(path) as fh:
            return [Finding.from_dict(d) for d in json.load(fh)]
    except Exception:
        return []


# -------------------------------------------------------------- phase gating + dedup
def apply_phase(findings, phase):
    """Demote any finding whose tier is unavailable at `phase` to OPEN (or N/A for packaging).

    This is the single place the pre-trial guarantee is enforced. Before it existed, a bundle
    with no runs yet produced 9 phantom [FAIL]s - `Trials/ folder missing` and friends - and a
    VERDICT of FAIL on a sound task."""
    out = []
    for f in findings:
        if tier_available(f.tier, phase) or f.severity == OK:
            out.append(f)
            continue
        # Packaging genuinely does not apply before packaging; the rest is merely not yet known.
        f.severity = NA if f.tier == TIER_SUBMISSION else OPEN
        f.needs = f.needs or TIER_NEEDS.get(f.tier)
        out.append(f)
    return out


def suppress_stale(findings):
    """Demote findings whose only evidence came from a run that is already known to be stale.

    THE BUG THIS FIXES. `qc_gate` reads Oracle/Nop/Trials output. If a run predates the current
    bundle, everything read out of it describes files that no longer exist - yet each of those
    readings was still reported as a full FAIL. On a real task that turned "your three runs are
    stale, re-run them" into nine separate failures, one of which (`reward_json_nonnumeric`) had
    already been FIXED in the source and was being kept alive purely by the old run output.

    WHY THE TIER TEST IS THE WHOLE TRICK. A finding is only suppressed when its tier is `gate` or
    `trial`. `dedup()` keeps the EARLIEST tier across witnesses, so a defect that ALSO has a
    static, bundle-tier witness (qc_judge reading verifier.py) lands at tier `bundle` and is left
    alone. That is exactly right: the static reading is still true regardless of any run. Only a
    finding whose every witness was a stale run loses its standing.

    The staleness findings themselves are never suppressed - they become the single accurate
    statement, and `suppressed` records what each one accounts for so nothing vanishes silently.
    """
    stale_runs = {f.id[: -len("_stale")].capitalize()
                  for f in findings if f.id.endswith("_stale") and f.severity == FAIL}
    if not stale_runs:
        return findings, {}
    accounted = {}
    for f in findings:
        if f.id.endswith("_stale") or f.severity not in (FAIL, NON_FAIL, CANDIDATE):
            continue
        if f.tier not in (TIER_GATE, TIER_TRIAL):
            continue                      # a bundle-tier witness exists - still decidable
        if not f.from_run or not all(r in stale_runs for r in f.from_run):
            continue                      # not read from a run, or not from a stale one
        f.suppressed = (f"evidence comes only from {', '.join(sorted(f.from_run))}, which "
                        f"predates the current bundle")
        f.severity = OPEN
        f.needs = "a re-run"
        accounted.setdefault(tuple(sorted(f.from_run)), []).append(f.id)
    return findings, accounted


def dedup(findings):
    """Merge findings that are the same defect seen by more than one check.

    Identity is (id, category). The `reward.json` shape defect is the motivating case: qc_judge
    reads it statically out of verifier.py and qc_gate meets it again as a nested map in the
    run output. One defect, two witnesses - so the sources merge rather than the finding
    duplicating, and the worst severity and the lowest (earliest-decidable) tier win."""
    merged, order = {}, []
    for f in findings:
        key = (f.id, f.category)
        if key not in merged:
            merged[key] = f
            order.append(key)
            continue
        keep = merged[key]
        if SEV_RANK[f.severity] > SEV_RANK[keep.severity]:
            f.source = list(dict.fromkeys(keep.source + f.source))
            f.evidence = list(dict.fromkeys(keep.evidence + f.evidence))
            f.from_run = list(dict.fromkeys(keep.from_run + f.from_run))
            merged[key] = f
            keep = f
        else:
            keep.source = list(dict.fromkeys(keep.source + f.source))
            keep.evidence = list(dict.fromkeys(keep.evidence + f.evidence))
            keep.from_run = list(dict.fromkeys(keep.from_run + f.from_run))
        # Report the earliest phase at which this is knowable, so a statically-decidable defect
        # is never presented as something you must run a trial to discover.
        if TIER_ORDER.index(f.tier) < TIER_ORDER.index(keep.tier):
            keep.tier, keep.needs = f.tier, f.needs
    return [merged[k] for k in order]


# ------------------------------------------------------------------------- verdict
def verdict(findings, phase):
    """(triple, exit_code). The triple always names what was NOT checked."""
    dec = [f for f in findings if f.severity in DECIDABLE]
    n_fail = sum(1 for f in dec if f.severity == FAIL)
    n_block = sum(1 for f in dec if f.severity == FAIL and f.blocking)
    n_pend = sum(1 for f in dec if f.severity == PENDING)

    # A bare "PASS" printed while a collision proposal is outstanding would be the same mistake the
    # marker gate exists to prevent, one line higher up: the headline reading clean because nobody
    # has adjudicated yet. PASS is still accurate (nothing FAILED and the exit code is 0), so the
    # count is appended rather than the verdict downgraded.
    bundle = (f"FAIL ({n_fail})" if n_fail else "PASS")
    if n_pend:
        bundle += f" · {n_pend} awaiting adjudication"
    if tier_available(TIER_GATE, phase):
        gate_f = [f for f in findings
                  if f.tier == TIER_GATE and f.severity in (FAIL, NON_FAIL)]
        gate = f"FAIL ({len(gate_f)})" if gate_f else "holds"
    else:
        gate = "not reproduced"
    if tier_available(TIER_TRIAL, phase):
        trial_f = [f for f in findings
                   if f.tier == TIER_TRIAL and f.severity in (FAIL, NON_FAIL)]
        trial = f"FAIL ({len(trial_f)})" if trial_f else "OK"
    else:
        trial = "n/a (pre-trial)"

    code = 1 if any(f.severity in EXIT_WORTHY for f in dec) else 0
    return {"bundle": bundle, "gate": gate, "trial": trial,
            "n_fail": n_fail, "n_blocking": n_block, "n_pending": n_pend}, code


# -------------------------------------------------------------------------- render
def _cat_worst(fs):
    return max((SEV_RANK[f.severity] for f in fs), default=0)


def render_proposals(fixes, phase, root, width=78):
    """The repair plan: the authoritative preview of what --apply would touch.

    This is what used to require a second command (`fix.py auto`). It lives in the one report now,
    because there was never a safety reason to split them - both are read-only - and splitting them
    meant a CB could read the audit and never see that four of the fixes exist at all.
    """
    out, w = [], None
    w = out.append
    if not fixes:
        w("PROPOSED FIXES — none. Nothing here is mechanically repairable.")
        return "\n".join(out)
    order = {"auto": 0, "agent": 1, "ask": 2, "never": 3}
    fs = sorted(fixes.values(), key=lambda f: (order.get(f.kind, 4), f.id))
    n_auto = sum(1 for f in fs if f.kind == "auto")
    n_agent = sum(1 for f in fs if f.kind == "agent")
    n_ask = sum(1 for f in fs if f.kind == "ask")
    n_never = sum(1 for f in fs if f.kind == "never")
    bits = " · ".join(x for x in (f"{n_auto} mechanical" if n_auto else "",
                                 f"{n_agent} for the agent" if n_agent else "",
                                 f"{n_ask} need your decision" if n_ask else "",
                                 f"{n_never} authoring" if n_never else "") if x)
    w(f"PROPOSED FIXES — nothing applied ({bits})")
    tag = {"auto": "auto ", "agent": "agent", "ask": "ask  ", "never": "never"}
    for f in fs:
        w(f"  [{tag.get(f.kind, f.kind)}] [{f.trial_class}] {f.id:22} {_clip(f.title, 36)}")
        for e in list(f.evidence or [])[:3]:
            w(f"              → {_clip(str(e), 58)}")
    if tier_available(TIER_TRIAL, phase):
        # The mechanical fixes and the agent repairs land under ONE approval, so the trial verdict
        # for that approval is the worst of both. Reporting only the auto class understated it.
        worst = max([f.trial_class for f in fs if f.kind in ("auto", "agent")] or ["A"])
        verdicts = {"A": "keep the existing trial as-is",
                    "B": "keep the trajectory, then rescore (no container run)",
                    "C": "the trial is INVALID and must be re-run"}
        w(f"\n  approving the mechanical fixes + agent repairs → class {worst}: {verdicts[worst]}")
    else:
        w("\n  no trial exists yet, so no trajectory is at risk — these fixes cost nothing")
    if n_agent:
        w("  agent items are covered by the SAME approval as the mechanical ones — the agent makes")
        w("  those edits itself and proves them; they are not a second question")
    if n_never:
        w("  authoring items are never auto-patched: editing them changes what the task grades")
    return "\n".join(out)


def render(findings, phase, tasks_dir, deliv=None, verbose=False, width=78, detected=None,
           proposals=None):
    """The report. Sections sort by worst severity so the blocking defect is line 4, not 62."""
    out = []
    w = out.append
    findings = dedup(findings)
    v, code = verdict(findings, phase)

    w(f"MM SWE QC — {tasks_dir}")
    label = PHASE_LABEL.get(phase, phase)
    if detected and detected != phase:
        # Saying "no runs present" when runs exist and are being deliberately ignored would be a
        # lie about the input, which is the one thing a QC report cannot afford.
        label = f"{phase} — FORCED (detected: {detected}; higher-tier artifacts ignored)"
    w(f"phase: {label}")
    w("")
    w(f"VERDICT   BUNDLE: {v['bundle']}  ·  GATE: {v['gate']}  ·  TRIAL: {v['trial']}")
    if v["n_blocking"]:
        w(f"          {v['n_blocking']} blocking defect(s) — until fixed, no reward means anything")
    if not tier_available(TIER_TRIAL, phase):
        # Pre-trial there is no trajectory to preserve, so an A/B/C verdict would be worse than
        # useless: it implies a run exists that a fix could invalidate.
        w("          no trial yet — fixes cost nothing")
    w("")

    by_cat = {k: [] for k in CATEGORY_ORDER}
    for f in findings:
        by_cat.setdefault(f.category, []).append(f)

    # Blocking first, then loudest, then canonical order. A blocking defect voids the measurement,
    # so it outranks an equally-severe defect that merely fails a dimension.
    def _blocking(fs):
        return any(f.blocking and f.severity == FAIL for f in fs)

    ranked = sorted(by_cat.items(),
                    key=lambda kv: (not _blocking(kv[1]), -_cat_worst(kv[1]),
                                    CATEGORY_ORDER.index(kv[0])
                                    if kv[0] in CATEGORY_ORDER else 99))

    quiet = []
    for key, fs in ranked:
        loud = [f for f in fs if f.severity in LOUD]
        if not loud and not verbose:
            quiet.append((key, fs))
            continue
        _render_category(w, key, fs, loud, phase, width, verbose)
        w("")

    if quiet:
        for key, fs in sorted(quiet, key=lambda kv: CATEGORY_ORDER.index(kv[0])
                              if kv[0] in CATEGORY_ORDER else 99):
            n_ok = sum(1 for f in fs if f.severity == OK)
            na = [f for f in fs if f.severity == NA]
            bits = [f"{n_ok} check(s) clean" if n_ok else "nothing to check"] + _pinned(fs)
            if na:
                bits.append(f"{len(na)} N/A [{na[0].needs or 'n/a'}]")
            w(f"  {CATEGORY_NUM.get(key, '?')}. {CATEGORY_TITLE.get(key, key):<24} "
              f"OK — {' · '.join(bits)}")
        w("        (`--verbose` to expand clean categories)")
        w("")

    _render_open(w, findings, phase)
    if proposals is not None:
        w(render_proposals(proposals, phase, deliverables_root(tasks_dir), width))
        w("")
    _render_next(w, findings, phase, tasks_dir)
    return "\n".join(out), code


def _render_category(w, key, fs, loud, phase, width, verbose):
    worst = max(loud, key=lambda f: SEV_RANK[f.severity], default=None)
    n_fail = sum(1 for f in loud if f.severity == FAIL)
    n_cand = sum(1 for f in loud if f.severity == CANDIDATE)
    n_nf = sum(1 for f in loud if f.severity == NON_FAIL)
    n_pend = sum(1 for f in loud if f.severity == PENDING)
    tally = " · ".join(x for x in (f"{n_fail} FAIL" if n_fail else "",
                                   f"{n_nf} non-fail" if n_nf else "",
                                   f"{n_pend} pending" if n_pend else "",
                                   f"{n_cand} candidate(s)" if n_cand else "") if x)
    blocking = any(f.blocking and f.severity == FAIL for f in loud)
    head = (f"┌─ {CATEGORY_NUM.get(key, '?')}. {CATEGORY_TITLE.get(key, key)} ")
    tail = f" {tally or 'clean'}" + ("  ⛔ blocking" if blocking else "")
    w(head + "─" * max(1, width - len(head) - len(tail)) + tail)

    for f in sorted(loud, key=lambda f: -SEV_RANK[f.severity]):
        tags = [SEV_TAG[f.severity]]
        line = f"│ [{SEV_TAG[f.severity]}] {f.id}"
        meta = []
        if f.rubric_dim:
            meta.append(f.rubric_dim.replace("Fail - ", ""))
        else:
            meta.extend(lbl for pre, lbl in NO_DIM_LABEL if f.id.startswith(pre))
        if f.action:
            meta.append(f"action:{f.action}")
        if f.trial_class and tier_available(TIER_TRIAL, phase):
            meta.append(f"class {f.trial_class}")
        if f.rubric_severity:
            meta.append(f.rubric_severity)
        pad = max(1, 46 - len(line))
        w(line + " " * pad + "  ".join(meta))
        for ln in _wrap(f.title, width - 9):
            w(f"│        {ln}")
        for e in f.evidence[:6]:
            for ln in _wrap(f"→ {e}", width - 11):
                w(f"│          {ln}")
        if f.why:
            for ln in _wrap(f.why, width - 9):
                w(f"│        {ln}")
        if f.tier == TIER_BUNDLE and f.category == "gate":
            w("│        ⚠ decidable now, statically — fix before spending a trial")
        if len(f.source) > 1:
            w(f"│        ↳ also seen by: {', '.join(f.source[1:])}")

    footer = [f for f in fs if f.severity in (OPEN, NA)]
    n_ok = sum(1 for f in fs if f.severity == OK)
    bits = []
    if footer:
        bits.append(" · ".join(dict.fromkeys(
            f"{f.id} → {f.severity} [{f.needs or 'n/a'}]" for f in footer[:3])))
    bits.extend(_pinned(fs))
    if n_ok:
        bits.append(f"{n_ok} check(s) clean")
    w("└─ " + ("  ".join(bits) if bits else "—"))


def _render_open(w, findings, phase):
    opens = [f for f in findings if f.severity in (OPEN, NA)]
    if not opens:
        return
    n_na = sum(1 for f in opens if f.severity == NA)
    head = f"OPEN — not decidable at this phase ({len(opens) - n_na}"
    head += f", plus {n_na} N/A)" if n_na else ")"
    w(head + "   none of these affect the verdict or exit code")
    groups = {}
    for f in opens:
        groups.setdefault(f.needs or "n/a", []).append(f)
    for needs in sorted(groups, key=lambda n: (n == "n/a", n)):
        fs = groups[needs]
        names = " · ".join(dict.fromkeys(f.id for f in fs))
        # ljust alone silently collapses the gap when the label is longer than the column, so the
        # separating space is explicit rather than a side effect of padding.
        w(f"  [needs {needs}]".ljust(21) + " " + _clip(names, 54))
    # Suppression must be VISIBLE. Silently dropping findings would trade one wrong impression
    # ("nine things are broken") for a worse one ("we checked and they were fine").
    sup = [f for f in opens if f.suppressed]
    if sup:
        w("")
        w(f"  {len(sup)} of the above were DOWNGRADED from FAIL, not dismissed:")
        for f in sup[:6]:
            w(f"    {f.id:26} {_clip(f.suppressed, 46)}")
        if len(sup) > 6:
            w(f"    … and {len(sup) - 6} more")
        w("    Re-run the stale run(s) and they will be judged against the current bundle.")
    w("")


def _render_next(w, findings, phase, tasks_dir):
    root = deliverables_root(tasks_dir)
    auto = [f for f in findings
            if f.action == "auto" and f.severity in (FAIL, NON_FAIL, CANDIDATE)]
    hand = [f for f in findings
            if f.action in ("authoring", "decide") and f.severity in (FAIL, NON_FAIL)]
    w("NEXT")
    if auto:
        w(f"  fix.py auto {root}".ljust(46)
          + f"{len(auto)} auto-fix(es), then reproduces oracle+nop")
    if hand:
        for f in hand:
            verb = "decide" if f.action == "decide" else "edit by hand"
            w(f"  {verb}: {f.id}".ljust(46) + "(never auto-patched)")
    if not tier_available(TIER_GATE, phase):
        w(f"  fix.py verify {root}".ljust(46) + "reproduce the gate (keyless) → phase gate")
    if not auto and not hand and tier_available(TIER_GATE, phase):
        w("  nothing to fix at this phase.")
    w("  `--next-steps` prints the harbor command block")


def _wrap(text, width):
    """Wrap to `width`, PRESERVING author-inserted newlines and their indentation.

    `.split()` on the whole string used to flatten embedded newlines into spaces, so a message
    written as a labelled block --

        a half-finished fix would score 0.5 ...
          where: line 250: tests_passed = 0.5
          fix:   reward = 1.0 if all_f2p_pass else 0.0

    -- rendered as one unbroken paragraph, with `where:` and `fix:` buried mid-sentence. The
    labels are the readable part, so the line structure is load-bearing rather than cosmetic.
    Each line is wrapped independently and continuations keep the original indent, so a long
    `fix:` value still lines up under its label instead of resetting to the left margin.
    """
    out = []
    for raw in str(text or "").split("\n"):
        indent = raw[: len(raw) - len(raw.lstrip())]
        # A continuation deeper than its label would collide with the box gutter on a narrow
        # terminal, so cap it well inside the width and let the text wrap instead.
        indent = indent[: max(0, width // 3)]
        words = raw.split()
        if not words:
            out.append("")
            continue
        line = indent + words[0]
        for word in words[1:]:
            if len(line) + 1 + len(word) > width:
                out.append(line)
                line = indent + word
            else:
                line = f"{line} {word}"
        out.append(line)
    return out or [""]


def _clip(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"
