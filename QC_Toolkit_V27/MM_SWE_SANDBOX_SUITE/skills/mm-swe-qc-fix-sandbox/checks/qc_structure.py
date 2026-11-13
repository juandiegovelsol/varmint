#!/usr/bin/env python3
"""Step 0.5 - static mechanical pre-checks for a Varmint Sheriffs deliverable bundle (v3).

Usage:
    python3 review_checks.py "task_<taskId>/deliverables"     # the four-folder root
    python3 review_checks.py "path/to/Tasks"                  # a bare Tasks/ (partial checks)

Aligned to **QC rubric v2** (16 scored dims + Unauditable) plus the **v3 rubric layer**
(`tests/rubrics.json`, Guidelines V3 Step III-C). This script covers ONLY the
statically-checkable dimensions; it NEVER runs the verifier (Step 0.6 / check_gate.py) or the
rubric judge. Every finding is a CANDIDATE unless marked [FAIL]; confirm by hand before scoring.
Standard library only.

  * Group R here is a light *presence/parse* check on `tests/rubrics.json`. The full rubric
    verification (schema, task-id consistency, and the six "Rules for rubrics") is the v3
    component `check_rubrics.py` (Step 0.55), and the rubric *judge mechanics* (the rubric-template
    wiring in tests/) are audited by the v3.1 component `check_judge.py` (Step 7.6) - run both too.

Groups -> rubric items:
  A  ->  v2 #2  Structure - Deliverables & Packaging      [Fail - Deliverable Packaging]
  B  ->  v2 #1  Structure - Task Bundle Files             [Fail - Broken Structure]
              (+ poster decode feeds v2 #4 Image - Evidence Quality [Fail - Bad Evidence])
  D  ->  v2 #8  Golden Fix - Source-Only Scope            [Fail - Dirty Fix Scope]
  E  ->  v2     Hardening - can the harness still RUN?    [Fail - Unreal or Infeasible]
              (BLOCKING. Does environment/Dockerfile destroy something harbor itself needs -
               the curl/npm path the agent CLI is installed over, the git the verifier diffs
               with, the bash every phase is spawned under? Anti-cheat that strips these makes
               the trial die at startup, and oracle+nop cannot see it: they install no agent,
               so the gate passes and the failure only appears once the trial is spent.)
  F  ->  v2 #10 Tests - f2p/p2p Identifier Validity       [Fail - Bad Test IDs]
  H  ->  v2 #5  Metadata - task_type Accuracy (value)     [Fail - Wrong task_type]
  I  ->  v2 #6  Evidence - Chain Consistency              [Fail - Evidence Mismatch]
  K  ->  v2 #1  Structure - task.toml identity block      [Fail - Broken Structure]
              ([task] name = "scale-ai/<task_id>"; [metadata] task_id, title, repository_name)
  P  ->  v2     Hardening - can a NON-ROOT process run?   [Fail - Unreal or Infeasible]
              (BLOCKING. The sandbox daemon's rootfs has `/` at 0750, so every `su`/`gosu`/
               `setpriv`/`USER` privilege drop dies before main() with a libc "Permission
               denied" that reads as a corrupt base image. The build DOES fail loudly, so
               unlike group E the gate is not blind - what is missing is the diagnosis, and
               the verify-time half (a generated starter script) fails later, not at build.)
  N  ->  v2     Hardening - is the AGENT phase sealed?    [Fail - Unreal or Infeasible]
              ([agent] network_mode. The ONE network setting nothing else can catch: oracle
               and nop run no agent so the gate is blind to it, and the runner only warns at
               run time, after the trial is already committed to.)
  R  ->  v3     Rubrics - rubrics.json present & parses    [Fail - Missing/Broken Rubrics]
              (structure only; run check_rubrics.py for the full rule-by-rule audit)
  S  ->  v2 #15 Hardening - Real & Feasible (ADVISORY)    [Fail - Unreal or Infeasible]
              (is every f2p behaviour perceivable from instruction.md or the posters?
               derived from the f2p TESTS, not from solution/fix.patch - the golden patch's
               file spread is one author's structuring, not the task's scope)
"""
import json, sys, os, re, glob, hashlib, py_compile, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qc_common import (matcher_kind, MATCHER_SUFFIX, MATCHER_SUBSTRING, MATCHER_EXACT,
                       MATCHER_UNKNOWN)
from qc_layout import resolve_layout, find_task_dir, AmbiguousLayout

SEVEN_TYPES = {
    "visual_bug_fix", "visual_regression", "design_reference", "build_render_repair",
    "temporal_interaction", "accessibility_visual", "data_viz_correctness",
}
REQUIRED_TASK_FILES = [
    "task.toml", "instruction.md", "evidence_bundle.json",
    "environment/Dockerfile", "environment/assets/ASSET_MANIFEST.json",
    "solution/fix.patch", "solution/solve.sh",
    "tests/config.json", "tests/test.patch", "tests/test.sh", "tests/verifier.py",
    # tests/rubrics.json and tests/judge.py are deliberately NOT required. The rubric layer has
    # two legal shapes and "absent" is one of them (Mode B), so requiring the file here failed
    # correct bundles. qc_rubric_format.py decides which shape a task should be in.
]
DIRTY_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|docs?|CHANGELOG|changelog|"
                        r".*\.lock|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|\.changeset)(/|$|\.)",
                        re.I)


# ----------------------------------------------------------------- helpers
def read(path):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def load_json(path):
    txt = read(path)
    if txt is None:
        return None, "missing"
    try:
        return json.loads(txt), None
    except Exception as e:
        return None, str(e)


# TOML bare keys are [A-Za-z0-9_-]+. This used to be spelled `[a-z_]+`, WITH NO DIGITS, so the two
# keys whose whole job is to name tests - `f2p` and `p2p` - were the only two in task.toml the
# fallback could not read, and `md["f2p"]` came back None on every bundle. That is not a visible
# failure: check_F's "config.json f2p == task.toml f2p" comparison is guarded by `if t`, so an
# unreadable list SKIPS the check instead of failing it, and a real divergence between the two
# files went unreported. Only reachable below Python 3.11, where tomllib does not exist - which is
# exactly where the sandbox runs.
_TOML_KEY = r"[A-Za-z0-9_-]+"
# Escapes TOML basic strings define. \u/\U are left as written: they do not occur in test ids, and
# emitting the sequence verbatim is a visible non-match rather than a silent wrong character.
_TOML_ESC = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r",
             '"': '"', "\\": "\\", "/": "/"}


def _toml_unescape(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(_TOML_ESC.get(s[i + 1], s[i:i + 2])); i += 2
        else:
            out.append(s[i]); i += 1
    return "".join(out)


def _toml_str_array(txt, open_idx):
    r"""Parse the TOML string array whose `[` sits at `open_idx` -> (items, index_of_closing_]).

    A SCANNER, NOT A REGEX, for two reasons the regex got wrong. `\[(.*?)\]` is non-greedy, so the
    array ended at the FIRST `]` in the text - and a pytest id like `test_x[1-2]`, or any prose
    name containing a bracket, puts one INSIDE the first element, silently truncating the list.
    And `"([^"]*)"` treats the `"` of an escaped `\"` as a terminator, so an id like
    `renders with scope=\"col\"` came back as a fragment plus an empty string. Tracking depth and
    quoting together is the only way both stay right; strings are consumed whole, so a bracket
    inside one cannot close the array.
    """
    items, i, depth, n = [], open_idx + 1, 1, len(txt)
    while i < n:
        c = txt[i]
        if c in '"\'':
            # Literal strings ('...') define NO escapes; basic strings ("...") do.
            esc, j, buf = (c == '"'), i + 1, []
            while j < n:
                d = txt[j]
                if esc and d == "\\" and j + 1 < n:
                    buf.append(txt[j:j + 2]); j += 2; continue
                if d == c:
                    break
                buf.append(d); j += 1
            if j >= n:
                return None, None
            items.append(_toml_unescape("".join(buf)) if esc else "".join(buf))
            i = j + 1
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return items, i
        i += 1
    return None, None


def parse_toml(path):
    """Prefer tomllib; else a small regex fallback for the [metadata] keys we need."""
    txt = read(path)
    if txt is None:
        return None
    try:
        import tomllib
        return tomllib.loads(txt)
    except Exception:
        pass
    md = {}
    # `[^"\\\n]|\\.` so an escaped quote inside the value does not end it, and the newline
    # exclusion keeps a greedy match from running to the next quoted value further down the file.
    for k, v in re.findall(r'^[ \t]*(' + _TOML_KEY + r')[ \t]*=[ \t]*"((?:[^"\\\n]|\\.)*)"', txt, re.M):
        md[k] = _toml_unescape(v)
    for k, v in re.findall(r'^[ \t]*(' + _TOML_KEY + r')[ \t]*=[ \t]*(\d+)[ \t]*$', txt, re.M):
        md.setdefault(k, int(v))
    for k, v in re.findall(r'^[ \t]*(' + _TOML_KEY + r')[ \t]*=[ \t]*(true|false)[ \t]*$', txt, re.M):
        md.setdefault(k, v == "true")
    for m in re.finditer(r'^[ \t]*(' + _TOML_KEY + r')[ \t]*=[ \t]*\[', txt, re.M):
        items, _end = _toml_str_array(txt, m.end() - 1)
        if items is not None:
            md.setdefault(m.group(1), items)
    return {"metadata": md}


def diff_paths(patch_text):
    """Return the set of file paths from `diff --git a/... b/...` headers."""
    if not patch_text:
        return set()
    a = re.findall(r"^diff --git a/(.*?) b/", patch_text, re.M)
    b = re.findall(r"^diff --git a/.*? b/(.*)$", patch_text, re.M)
    return {p.strip() for p in (a + b) if p.strip()}


def find_tasks_root(root):
    """Return (deliverables_root, tasks_dir).

    Flat (Tasks/task.toml) and nested (Tasks/<any-name>/task.toml) layouts both resolve to the
    same root - the folder the run dirs sit in - via qc_layout, so group A never mistakes Tasks/
    itself for the deliverables root.
    """
    try:
        deliv, tasks = resolve_layout(root)
    except AmbiguousLayout as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    if tasks is None and os.path.isdir(os.path.join(deliv, "Tasks")):
        tasks = os.path.join(deliv, "Tasks")
    return deliv, tasks


GROUPS = "ABDEFOHIKMLNPRST"
findings = {g: [] for g in GROUPS}
fails = {g: 0 for g in GROUPS}
records = []            # structured mirror of `findings`, for --emit-findings

# Group -> (category, tier) for the shared finding model. The tier is the important half.
#
# GROUP A IS TIER `submission`, NOT `bundle`. It checks that Tasks/Trials/Oracle/Nop and their
# four .tar.gz sit as siblings at the root - which is a PACKAGING-AT-SUBMISSION property, not a
# property of the task bundle. Tiering it as `bundle` is what made a perfectly sound task emit
# three hard [FAIL]s ("deliverable folder `Trials/` missing at root") when QC ran before the
# trial - i.e. in the case QC is most useful.
GROUP_MAP = {
    "A": ("structure",    "submission"),
    "B": ("structure",    "bundle"),
    "D": ("fix_tests",    "bundle"),
    "E": ("hardening",    "bundle"),
    "F": ("fix_tests",    "bundle"),
    "H": ("evidence",     "bundle"),
    "I": ("evidence",     "bundle"),
    "K": ("structure",    "bundle"),
    "M": ("hardening",    "bundle"),
    # L, like T, carries NO entry in GROUP_DIM: it is an advisory wording lint, not a rubric Fail
    # condition, so it cannot block the marker however it is worded.
    "L": ("evidence",     "bundle"),
    "N": ("hardening",    "bundle"),
    "O": ("fix_tests",    "bundle"),
    "P": ("hardening",    "bundle"),
    "R": ("rubric_judge", "bundle"),
    # T carries NO entry in GROUP_DIM, deliberately. Every dimension is a rubric Fail condition
    # and this is not one: a task without submission capture is correct, gradeable and shippable
    # -- it just cannot be pseudo-trialled later. No dim also means `dim in BLOCKING_DIMS` is
    # False by construction, so this group cannot block the marker however it is worded.
    "T": ("structure",    "bundle"),
    "S": ("hardening",    "bundle"),
}


def _slug(msg, g):
    words = re.findall(r"[a-z0-9]+", msg.lower())
    skip = {"the", "a", "an", "is", "at", "in", "of", "to", "not", "no"}
    keep = [w for w in words if w not in skip][:4]
    return f"{g.lower()}_" + "_".join(keep or ["finding"])


def add(g, msg, fail=False, ok=False, fid=None, tier=None, category=None, evidence=None,
        blocking=None, pending=False):
    """`blocking` is per-finding, like qc_rubric_format's, and for the same reason: the dimension
    it books against carries non-blocking findings too. Group E's dimension
    ("Fail - Unreal or Infeasible") is shared with the advisory groups M and S, so it cannot go in
    BLOCKING_DIMS wholesale - but an image that cannot host the agent voids the trial exactly the
    way a broken gate voids the reward, and must sort to the top of the report.

    `pending` is the third state check_F needs: PROPOSED, not decided. It is deliberately NOT
    counted in `fails[g]`, so it cannot change this script's exit code - an unadjudicated finding
    must never fail a run. What it does do is survive into the shared model as severity PENDING,
    where the marker gate picks it up. See qc_common's PENDING commentary for why."""
    prefix = "[FAIL] " if fail else ("[PEND] " if pending else "")
    findings[g].append(prefix + msg)
    for e in evidence or []:                     # text output keeps them as indented lines
        findings[g].append("  " + str(e))
    if fail:
        fails[g] += 1
    cat, dflt_tier = GROUP_MAP.get(g, ("structure", "bundle"))
    records.append({"group": g, "msg": msg, "fail": fail, "ok": ok, "pending": pending,
                    "id": fid or _slug(msg, g), "tier": tier or dflt_tier,
                    "category": category or cat, "evidence": list(evidence or []),
                    "blocking": blocking})


# ------------------------------------------------------------------ checks
def check_A(deliv):
    """v2 #2 - Structure: Deliverables & Packaging."""
    for req in ("Tasks", "Trials", "Oracle", "Nop"):
        d = os.path.join(deliv, req)
        if not os.path.isdir(d):
            add("A", f"deliverable folder `{req}/` missing at root", fail=True)
        tgz = os.path.join(deliv, req + ".tar.gz")
        if not os.path.exists(tgz):
            add("A", f"archive `{req}.tar.gz` missing at root")
    _bundle = find_task_dir(deliv) if os.path.isdir(os.path.join(deliv, "Tasks")) else None
    for _where in {os.path.join(deliv, "Tasks"), _bundle or os.path.join(deliv, "Tasks")}:
        for nested in ("Trials", "Oracle", "Nop"):
            if os.path.isdir(os.path.join(_where, nested)):
                # Tier `bundle`, unlike the rest of group A: a run dir INSIDE Tasks/ is a defect
                # in the bundle itself and would ship with it, so it is knowable pre-trial.
                add("A", f"`{nested}/` is nested inside `Tasks/` (must be a root sibling)",
                    fail=True, tier="bundle")
    for name in os.listdir(deliv) if os.path.isdir(deliv) else []:
        if name.lower() == "tasks" and name != "Tasks":
            add("A", f"folder `{name}` is mis-cased (must be capital-T `Tasks`)", fail=True)
    if not any(findings["A"]):
        add("A", "four deliverables present, sibling, correctly named", ok=True)


def check_B(tasks):
    """v2 #1 - Structure: Task Bundle Files (+ poster decode feeds v2 #4)."""
    if not tasks:
        add("B", "no Tasks/ dir found - cannot check bundle files", fail=True)
        return
    for rel in REQUIRED_TASK_FILES:
        p = os.path.join(tasks, rel)
        if not os.path.exists(p):
            add("B", f"required file `{rel}` missing", fail=True)
        elif os.path.getsize(p) == 0:
            add("B", f"required file `{rel}` is EMPTY", fail=True)
    for rel in ("evidence_bundle.json", "environment/assets/ASSET_MANIFEST.json",
                "tests/config.json"):
        p = os.path.join(tasks, rel)
        if os.path.exists(p):
            _, err = load_json(p)
            if err and err != "missing":
                add("B", f"`{rel}` does not parse as JSON: {err}", fail=True)
    vp = os.path.join(tasks, "tests/verifier.py")
    if os.path.exists(vp):
        try:
            py_compile.compile(vp, cfile=os.path.join(tempfile.gettempdir(), "qc_struct_check.pyc"), doraise=True)
        except Exception as e:
            add("B", f"tests/verifier.py fails to compile: {e}", fail=True)
    # posters decode (PNG/JPEG/GIF/WEBP signature) -> also feeds v2 #4
    adir = os.path.join(tasks, "environment/assets")
    if os.path.isdir(adir):
        for f in os.listdir(adir):
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                with open(os.path.join(adir, f), "rb") as fh:
                    head = fh.read(12)
                ok = (head.startswith(b"\x89PNG") or head[:2] == b"\xff\xd8" or
                      head[:6] in (b"GIF87a", b"GIF89a") or head[8:12] == b"WEBP")
                if not ok:
                    # feeds v2 #4 Image - Evidence Quality, so it books against EVIDENCE
                    add("B", f"poster `{f}` does not decode (bad signature) [feeds v2 #4]",
                        fail=True, category="evidence")
    if not any(x for x in findings["B"] if x.startswith("[FAIL]")):
        add("B", "all required bundle files present, non-empty, valid; posters decode", ok=True)


def check_D(tasks, md):
    """v2 #8 - Golden Fix: Source-Only Scope."""
    if not tasks:
        return
    patch = read(os.path.join(tasks, "solution/fix.patch"))
    paths = diff_paths(patch)
    if not paths:
        add("D", "no diff --git paths found in fix.patch", fail=True)
        return
    dirty = [p for p in paths if DIRTY_PATH.search(p)]
    for p in dirty:
        add("D", f"fix.patch edits a non-source path `{p}` (test/doc/lock/changeset)", fail=True)
    fe = set(md.get("files_edited") or [])
    if fe and fe != paths:
        add("D", f"fix.patch paths {sorted(paths)} != task.toml files_edited {sorted(fe)}",
            fail=True)
    if not any(x for x in findings["D"] if x.startswith("[FAIL]")):
        add("D", f"fix.patch touches source-only paths, equal to files_edited ({sorted(paths)})",
            ok=True)


def collect_test_source(tasks, conf, include_context=False):
    """Test source text = existing test files + added lines of test.patch.

    `include_context` additionally keeps the diff's CONTEXT lines (leading space). Those are
    existing source the diff hands over for free, and discarding them threw away real evidence:
    on the Cesium pickModel bundle one context line declares
    `it("returns position of intersection with instanced model", ...)` - a declared p2p name that
    check_F was reporting as "not found in test source".

    DEFAULT OFF, and that matters. check_O shares this helper to reason about what test.patch
    INTRODUCES; feeding it pre-existing context lines would change what that check means. Only
    check_F, which asks "does this identifier exist anywhere at all", opts in.
    """
    text = ""
    for tf in (conf or {}).get("test_files") or []:
        t = read(os.path.join(tasks, tf))
        if t:
            text += "\n" + t
    patch = read(os.path.join(tasks, "tests/test.patch")) or ""
    keep = []
    for l in patch.splitlines():
        if l.startswith("+") and not l.startswith("+++"):
            keep.append(l[1:])
        elif include_context and l.startswith(" "):
            keep.append(l[1:])
    text += "\n" + "\n".join(keep)
    return text


def missing_test_files(tasks, conf):
    """Declared test_files that are NOT in the bundle.

    Bundles do not ship the repo, so this is the normal case, not a defect - and it is the reason
    check_F cannot validate pre-existing p2p identifiers statically. Naming them is what lets the
    report say "unverifiable here" instead of "not found", which is the difference between a
    candidate a CB can act on and eighteen phantom defects.
    """
    created = _patch_targets(tasks)
    out = []
    for tf in (conf or {}).get("test_files") or []:
        if os.path.exists(os.path.join(tasks or "", tf)):
            continue
        # A file test.patch CREATES (`--- /dev/null`) ships in full inside the patch, so the
        # bundle does answer every question about it. Treating it as absent was reporting
        # "the bundle does not ship this" about 397 lines of source sitting in tests/test.patch,
        # and suppressing per-identifier resolution for every test in the task.
        if created.get(tf):
            continue
        out.append(tf)
    return out


def _patch_targets(tasks):
    """{path: was it CREATED whole?} for every file tests/test.patch touches."""
    patch = read(os.path.join(tasks or "", "tests/test.patch")) or ""
    out, from_null = {}, False
    for line in patch.splitlines():
        if line.startswith("--- "):
            from_null = line[4:].strip() == "/dev/null"
        elif line.startswith("+++ "):
            p = line[4:].strip()
            if p.startswith("b/"):
                p = p[2:]
            if p and p != "/dev/null":
                out[p] = from_null
    return out


def _ident_leaf(ident):
    """The bare test name inside a declared identifier.

    Declared f2p/p2p ids are written in whatever notation the task's runner uses, and only the
    LAST segment is a name the source actually contains:

        pytest      tests/test_x.py::Class::test_method
        unittest    tests.test_x.Class::test_method          <- separators AND dots
        JS / Dart   a prose sentence, with no separators at all

    Everything downstream used to search for the identifier verbatim, which resolves for the prose
    notation and for nothing else. On a unittest bundle that meant 0 of 7 f2p located, an overfit
    check that inspected nothing, and 16 identifiers reported unverifiable.
    """
    parts = [p for p in re.split(r"::|#|\s>\s", ident) if p.strip()]
    leaf = (parts[-1] if parts else ident).strip()
    # Dotted module paths only - never a prose name like `IconButton.fill defaults - M3`, which
    # contains spaces, nor a bare filename.
    #
    # THE STRIP IS A RESOLUTION AID, NOT A CLAIM ABOUT THE NAME. It has to stay unconditional: a
    # C#/NUnit id reads `tests/X.cs::ClassName.MethodName` while the source declares only
    # `MethodName`, so without stripping the dotted owner the test body is never located at all.
    # Restricting it to separator-less ids (an attempt at the vitest bug below) silently lost the
    # f2p block on every such bundle - no block, no findings, a clean report about a test nobody
    # read.
    #
    # So a leaf that came out SHORTER than the name the identifier actually carries is expected
    # here, and must not be mistaken for a truncated identifier. That is settled in
    # truncated_identifiers, which drops any candidate name the identifier already spells out in
    # full - the vitest test genuinely called `TableCellNode.constructor` used to be "repaired"
    # into `TableCellNode.TableCellNode.constructor` in task.toml AND tests/config.json.
    if leaf and " " not in leaf and "." in leaf and not leaf.endswith(".py"):
        leaf = leaf.rsplit(".", 1)[-1]
    return leaf


def _ident_owner(ident):
    """The class/suite the identifier names, if it names one."""
    parts = [p for p in re.split(r"::|#|\s>\s", ident) if p.strip()]
    if len(parts) < 2:
        return None
    owner = parts[-2].strip().rsplit(".", 1)[-1]
    return owner or None


def _word_bounded(leaf):
    r"""`leaf` as a regex, with \b only on the ends that can actually carry one.

    An unconditional \b...\b assumes the name starts and ends with a word character. Test names
    routinely do not - `treats a missing confidenceFloor as 0 (config.confidenceFloor ?? 0)` ends
    in `)`, and \b after `)` demands a word character NEXT, which in source is the closing quote.
    So the name sat in the file and _locate() reported it absent, and the identifier that names it
    was filed as "not found verbatim - likely a DYNAMIC test name".
    """
    pat = re.escape(leaf)
    head = r"\b" if leaf[:1].isalnum() or leaf[:1] == "_" else ""
    tail = r"\b" if leaf[-1:].isalnum() or leaf[-1:] == "_" else ""
    return head + pat + tail


def _locate(src, ident):
    """Offset in `src` just past the declaration of `ident`, or -1.

    Verbatim first, so prose identifiers keep their exact previous behaviour. Only if that fails
    does it fall back to the leaf name, anchored at the enclosing class when the identifier names
    one - two classes in one file may well declare the same method name."""
    i = src.find(ident)
    if i >= 0:
        return i + len(ident)
    leaf = _ident_leaf(ident)
    if not leaf or leaf == ident:
        return -1
    owner = _ident_owner(ident)
    if owner:
        m = re.search(rf"\bclass\s+{re.escape(owner)}\b", src)
        if m:
            hit = re.search(_word_bounded(leaf), src[m.end():])
            if hit:
                return m.end() + hit.end()
    hit = re.search(_word_bounded(leaf), src)
    return hit.end() if hit else -1


# Test declarations, for the collision check that actually has teeth. Covers Jasmine/Jest/Mocha
# (`it`/`test`/`specify` + focus/skip prefixes) and the `describe` suites they nest in.
_TEST_DECL = re.compile(
    r"\b(?:x|f)?(?:it|test|specify)(?:\.(?:only|skip))?\s*\(\s*(['\"`])(.+?)\1", re.S)
_SUITE_DECL = re.compile(r"\b(?:x|f)?describe(?:\.(?:only|skip))?\s*\(\s*(['\"`])(.+?)\1", re.S)
# A name built at run time: `${...}` interpolation, or a table/loop driving the declaration.
_DYNAMIC_NAME = re.compile(r"\$\{")
_PARAM_LOOP = re.compile(
    r"\.forEach\s*\(|\bfor\s*\(|\.each\s*[(`]|\bit\.each\b|\btest\.each\b|"
    r"@pytest\.mark\.parametrize|\bparameterized\b", re.I)
# `[ "a", "b" ].forEach(` / `it.each([...])` - a literal iterable we can expand exactly.
_LITERAL_ITERABLE = re.compile(r"\[\s*((?:['\"][^'\"]*['\"]\s*,?\s*)+)\]")


def _test_names(src):
    """Declared test names, plus whether each looks dynamically constructed."""
    return [(m.group(2), bool(_DYNAMIC_NAME.search(m.group(2)))) for m in _TEST_DECL.finditer(src)]


def _expand_literal_params(src, name):
    """Concrete names for a `${...}` template whose parameter list is a LITERAL, else [].

    Scope is deliberately narrow: a literal array of string literals somewhere in the enclosing
    source. Anything else - a variable, an import, a .map chain, a nested loop, a computed
    expression - returns [] and the finding goes to an agent instead.

    THE NARROWNESS IS THE POINT. Guessing at a name this check then compares for collisions would
    reintroduce exactly the over-claiming being repaired here, one layer deeper and harder to see.
    """
    if not _DYNAMIC_NAME.search(name):
        return []
    lits = _LITERAL_ITERABLE.search(src)
    if not lits:
        return []
    values = re.findall(r"['\"]([^'\"]*)['\"]", lits.group(1))
    if not values:
        return []
    # One placeholder only. Two independent placeholders need the cross product of two resolved
    # lists, which is past what a literal scan can claim to know.
    if len(re.findall(r"\$\{[^}]*\}", name)) != 1:
        return []
    return [re.sub(r"\$\{[^}]*\}", v, name) for v in values]


def _collides(ident, other, kind):
    """Would `other` (a runtime key or another identifier) also match `ident` under this matcher?

    This is the predicate the old code got wrong. It tested `ident in other` unconditionally, which
    is right ONLY for a substring matcher. Under `endswith` a strict PREFIX cannot collide - the
    keys differ at the tail - and that is the false positive this whole change exists to fix.
    """
    if ident == other:
        return False
    if kind == MATCHER_SUFFIX:
        return other.endswith(ident)
    if kind == MATCHER_SUBSTRING:
        return ident in other
    if kind == MATCHER_EXACT:
        return False
    return ident in other        # unknown: report the widest relation, but never as a FAIL


def _ident_fid(prefix, ident):
    """A per-identifier finding id that cannot collide with another identifier's.

    `_slug()` keeps the first four non-stopword tokens, so "returns undefined if model is not
    ready" and "returns undefined if ray does not intersect model surface" both became
    `f_identifier_returns_undefined_if` and dedup() merged them - which is why eighteen unfound
    identifiers were reported as ten. The hash suffix is what makes each one distinct.
    """
    toks = [t for t in re.findall(r"[a-z0-9]+", ident.lower()) if t not in
            {"the", "a", "an", "is", "at", "in", "of", "to", "not", "no"}][:3]
    h = hashlib.sha1(ident.encode("utf-8")).hexdigest()[:6]
    return f"{prefix}_" + "_".join(toks or ["ident"]) + f"_{h}"


# ----------------------------------------- ground truth for PRE-EXISTING tests (upstream repo)
# WHY THIS REACHES THE NETWORK. A bundle ships tests/test.patch and no other part of the suite, so
# the only test names it can prove are the ones the patch ADDS - every f2p, and not one
# pre-existing p2p. That gap is what let a TRUNCATED identifier ship undetected: a p2p declared as
# "... treats a missing confidenceFloor as 0" against a test actually named
# "... treats a missing confidenceFloor as 0 (config.confidenceFloor ?? 0)". It resolved, it
# scored, and the reward said 1.0 forever, because tests/verifier.py matched by containment.
#
# The missing half is not unknowable - it is one HTTP GET away. task.toml pins `repo_url` and
# `base_commit`, tests/config.json names the files, and it is the same repository
# environment/Dockerfile git-clones at image build time. A task whose repo this cannot reach
# cannot build its own image either, so the check adds no dependency the task does not already
# have - and it needs no key, no image and no run, which is what puts it at BUNDLE phase instead
# of behind the oracle.
#
# IT CAN NEVER FAIL ON ITS OWN. No network, a private repo, a non-GitHub host, a moving ref - all
# of it degrades to "not fetched", which leaves the pre-existing `absent` path and its OPEN
# finding exactly as they were. MM_QC_NO_NETWORK=1 skips the fetch entirely.
_UPSTREAM_CACHE = {}


def _raw_url(repo_url, sha, path):
    """The raw-content URL for one file at one commit, or None if the host has no known endpoint."""
    m = re.match(r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$",
                 (repo_url or "").strip())
    if not m:
        return None
    return "https://raw.githubusercontent.com/%s/%s/%s/%s" % (
        m.group(1), m.group(2), sha, path.lstrip("/"))


# Transient-failure retry. A public raw.githubusercontent GET normally answers first time, so a
# failure here is usually a blip - a timeout, a 429, a 502 from the CDN - and giving up on the first
# one turns a decidable identifier check into "not checked" for no reason. What must NOT be retried
# is a definitive answer: 404 means the file is not at that commit, and re-asking cannot change it.
#
# BOUNDED, because this runs inside an audit advertised as fast and free. Per-attempt timeout is
# small, backoff is short, and a single deadline covers the WHOLE fetch across every file - so the
# worst case is one deadline, not one deadline per file. Past it, the check degrades exactly as it
# does with no network at all.
_RETRY_CODES = {403, 408, 425, 429, 500, 502, 503, 504}
_FETCH_ATTEMPTS = 3
_FETCH_TIMEOUT = 8.0            # seconds, per attempt
_FETCH_BUDGET = 45.0            # seconds, for every file together
_BACKOFF = (0.6, 1.8)           # after attempt 1, after attempt 2


def _http_get(url, deadline, notes, label, attempts=_FETCH_ATTEMPTS,
              timeout=_FETCH_TIMEOUT, sleep=None):
    """(body, definitive). body is str on success, "" on a definitive 404, None on failure.

    `definitive` says whether the answer is worth caching. `sleep` is injectable so the retry path
    is testable without spending real seconds.
    """
    import time, urllib.error, urllib.request
    sleep = sleep or time.sleep
    last = None
    for attempt in range(1, attempts + 1):
        if time.monotonic() > deadline:
            notes.append("%s: fetch budget exhausted after %d attempt(s)" % (label, attempt - 1))
            return None, False
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace"), True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "", True                      # definitive: not at this commit
            last = "HTTP %s" % e.code
            if e.code not in _RETRY_CODES:
                notes.append("%s: %s" % (label, last))
                return None, False
            # A server that says when to come back is worth obeying, within budget.
            ra = (e.headers or {}).get("Retry-After") if hasattr(e, "headers") else None
            try:
                wait = min(float(ra), max(0.0, deadline - time.monotonic())) if ra else None
            except (TypeError, ValueError):
                wait = None
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
            wait = None
        if attempt < attempts:
            delay = wait if wait is not None else _BACKOFF[min(attempt, len(_BACKOFF)) - 1]
            if time.monotonic() + delay > deadline:
                notes.append("%s: %s, and the fetch budget leaves no room to retry" % (label, last))
                return None, False
            sleep(delay)
    notes.append("%s: %s (gave up after %d attempts)" % (label, last, attempts))
    return None, False


def _fetch_upstream_tests(tasks, conf, md, timeout=15):
    """(source_text, fetched_paths, notes) - the pre-existing test files, read at base_commit.

    `fetched_paths` is the subset of missing_test_files() that actually arrived. check_F treats the
    source as complete ONLY when that covers all of them: a half-fetched suite is still a suite
    with holes, and calling it complete would be the same over-claim this check exists to catch.
    """
    want = missing_test_files(tasks, conf)
    if not want:
        return "", [], []
    if os.environ.get("MM_QC_NO_NETWORK"):
        return "", [], ["MM_QC_NO_NETWORK is set - the pre-existing test files were not fetched"]
    repo = ((md or {}).get("repo_url") or "").strip()
    sha = ((md or {}).get("base_commit") or "").strip()
    lacks = [k for k, v in (("repo_url", repo), ("base_commit", sha)) if not v]
    if lacks:
        return "", [], ["task.toml declares no " + " and no ".join(lacks)
                        + ", so the pre-existing tests cannot be located upstream"]
    # A branch or tag would compare the identifiers against whatever upstream says TODAY, which is
    # not what the task runs. Only a pinned sha answers the question that was asked.
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        return "", [], ["base_commit `%s` is not a commit sha - refusing to resolve identifiers "
                        "against a moving ref" % sha]
    import time
    deadline = time.monotonic() + _FETCH_BUDGET
    text, got, notes = "", [], []
    for tf in want:
        url = _raw_url(repo, sha, tf)
        if not url:
            notes.append("%s: `%s` is not a github.com URL and no raw endpoint is known for it"
                         % (tf, repo))
            continue
        if url in _UPSTREAM_CACHE:
            body = _UPSTREAM_CACHE[url]
        else:
            body, definitive = _http_get(url, deadline, notes, tf)
            if body == "":
                # missing_test_files() already drops anything test.patch CREATES, so a 404 is a
                # real inconsistency: tests/config.json names a test file that is in neither the
                # repo at base_commit nor the patch.
                notes.append("%s: HTTP 404 at %s - in neither the repo at base_commit nor "
                             "tests/test.patch" % (tf, sha[:7]))
            if definitive:
                _UPSTREAM_CACHE[url] = body
        if body:
            text += "\n" + body
            got.append(tf)
    return text, got, notes


_PY_TEST_DECL = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+(test\w*)[ \t]*\(", re.M)


def truncated_identifiers(tasks, conf, md):
    """([(ident, leaf, [real names it is a strict substring of])], source_was_complete).

    ONE implementation, called by check_F (which reports this) and by fix.py (which repairs it),
    so the finding and the rewrite can never disagree about which identifier is wrong or what the
    test is really called. Returns ([], False) whenever the suite could not be assembled in full -
    a partial view can prove an identifier RIGHT but never wrong, because the name it was meant to
    carry may sit in the half that is missing.
    """
    src = collect_test_source(tasks, conf, include_context=True)
    absent = missing_test_files(tasks, conf)
    up_src, up_got, _notes = _fetch_upstream_tests(tasks, conf, md)
    if up_src:
        src += "\n" + up_src
    if (absent and len(up_got) != len(absent)) or not src.strip():
        return [], False
    names = set()
    for name, dyn in _test_names(src):
        names.add(name)
        if dyn:
            names.update(_expand_literal_params(src, name))
    # _test_names reads JS-style declarations only. On a pytest/unittest bundle it returns nothing,
    # which made this pass report "complete truth, no truncation" - a FALSE CLEAR of exactly the
    # kind this check exists to remove. Python test functions are added here rather than inside
    # _test_names because the collision sections consume that helper and reason about quoted prose
    # names; widening it would change what they mean.
    names.update(_PY_TEST_DECL.findall(src))
    # Identifiers to check but not one declaration recognised: the notation is one this cannot
    # read. Say so by declining, so the OK line never claims resolution it did not perform.
    if not names:
        return [], False
    out = []
    for ident in list((conf or {}).get("f2p") or []) + list((conf or {}).get("p2p") or []):
        leaf = _ident_leaf(ident)
        # AN EXACT MATCH ALWAYS WINS. A short-but-correct name that happens to sit inside a longer
        # sibling (`renders` beside `renders empty`) is resolved here and never reported.
        if not leaf or leaf in names:
            continue
        longer = sorted(n for n in names if n != leaf and leaf in n)
        # A SECOND BELT ON THE SAME STRAP. If the identifier already spells one of those longer
        # names out in full, it is not truncated - the leaf is just a shorter substring of a name
        # the id carries. Reported truncation here becomes a bundle REWRITE in fix.py, so this
        # stays even though _ident_leaf no longer over-strips: the cost of a wrong finding is two
        # corrupted files, and the cost of this guard is nothing a real truncation can trip.
        longer = [n for n in longer if n not in ident]
        if longer:
            out.append((ident, leaf, longer))
    return out, True


def check_F(tasks, conf, md):
    """v2 #10 - Tests: f2p/p2p Identifier Validity.

    WHAT THIS CHECK USED TO GET WRONG, because the shape of the fix follows from it.

    It asserted that any identifier which is a SUBSTRING of another would collide, and booked it as
    a hard FAIL - without ever opening the verifier that does the matching. On a task whose
    verifier resolves with `k.endswith(ident)`, a strict PREFIX of a longer sibling cannot collide:
    the keys differ at the tail. So a sound bundle got a blocker, and because no script can repair
    a defect that is not there, the report simultaneously said "1 blocking defect(s) must be fixed
    first" and "nothing to fix at this phase".

    The repair is not a better predicate - the next unfamiliar matcher would defeat that too. It is
    to stop DECIDING what needs a reading:

      * `matcher_kind()` reads tests/verifier.py and reports how it matches, as evidence;
      * a possible collision is PROPOSED (severity PENDING) with that evidence attached;
      * the agent driving the skill reads the matcher and records a verdict via `--adjudicated`,
        which promotes it to FAIL or clears it with a reason.

    Nothing here can produce a collision FAIL on its own, and PENDING never touches the exit code.
    """
    if not tasks:
        return
    # include_context: the diff's context lines are existing source, and pre-existing p2p tests are
    # exactly what they show. See collect_test_source.
    src = collect_test_source(tasks, conf, include_context=True)
    ids = list((conf or {}).get("f2p") or []) + list((conf or {}).get("p2p") or [])
    absent = missing_test_files(tasks, conf)
    # The half of the suite a bundle cannot carry, read from the repo at base_commit. When it
    # arrives in FULL the test source is complete, so `absent` is cleared and every section below
    # answers for real instead of declining: per-identifier resolution, the runtime-collision
    # pass, and the truncation pass that section 1 cannot perform on its own.
    up_src, up_got, up_notes = _fetch_upstream_tests(tasks, conf, md)
    if up_src:
        src += "\n" + up_src
    upstream_complete = bool(absent) and len(up_got) == len(absent)
    if upstream_complete:
        absent = []
    kind, matcher_ev = matcher_kind(tasks)
    kind_note = {
        MATCHER_SUFFIX:    "verifier.py matches on the key's SUFFIX",
        MATCHER_SUBSTRING: "verifier.py matches by CONTAINMENT",
        MATCHER_EXACT:     "verifier.py matches EXACTLY",
        MATCHER_UNKNOWN:   "verifier.py's matching could not be classified",
    }[kind]

    # Declared test names, with literal parametrization expanded. Built before the existence check
    # because an expansion is PROOF the identifier exists: a name assembled from `${mode}` never
    # appears verbatim in the source, so without this an expandable-and-correct identifier was
    # reported as "not found verbatim", which is noise the CB then has to dismiss by hand.
    declared_names = _test_names(src) if src.strip() else []
    resolved_names, unexpandable = set(), []
    for _name, _dyn in declared_names:
        resolved_names.add(_name)
        _exp = _expand_literal_params(src, _name) if _dyn else []
        resolved_names.update(_exp)
        if _dyn and not _exp:
            unexpandable.append(_name)
    # Section 3 reports these with the loop source attached and a verdict to record. Without this
    # flag section 1 ALSO reports each one as "not found verbatim - likely dynamic", so one
    # unexpandable loop produced two findings per identifier saying the same thing.
    defer_to_parametrized = bool(unexpandable) and bool(_PARAM_LOOP.search(src))

    # ---------------------------------------------------------------- 1. does each identifier exist
    # Resolution accepts the identifier's LEAF name too - see _ident_leaf. Without it every
    # pytest/unittest-notation identifier is 'not found verbatim', which is the notation and
    # not a defect.
    unfound = [i for i in ids
               if src.count(i) == 0 and i not in resolved_names
               and _locate(src, i) < 0]
    if absent and unfound:
        # THE BUNDLE CANNOT ANSWER THIS. Only test.patch was searchable, and a pre-existing p2p test
        # lives in the repo file, so its absence here is not evidence of anything. One finding, not
        # one per identifier: eighteen copies of "cannot tell" is not eighteen defects.
        add("F", f"{len(unfound)} of {len(ids)} f2p/p2p identifier(s) could not be checked against "
                 f"test source: tests/config.json declares test_files {absent}, which the bundle "
                 f"does not ship (bundles carry no repo checkout), so only tests/test.patch was "
                 f"searchable. Pre-existing p2p tests live in the repo file and CANNOT appear "
                 f"there, so this is NOT evidence the identifiers are wrong. UNCHECKED as a "
                 f"result: per-identifier resolution, and duplicate-leaf/parametrization "
                 f"collisions. The pre-existing tests were fetched from the repository at "
                 f"base_commit instead, and that did not complete either (see evidence). Note that "
                 f"the Oracle run does NOT settle this: "
                 f"`p2p_passed == p2p_total` counts identifiers that "
                 f"RESOLVED, and under a containment matcher an identifier resolves just as "
                 f"happily to a test whose name it only partly carries.",
            fid="tests_ident_source_unavailable",
            evidence=[f"searched: tests/test.patch added + context lines only"]
                     + [f"upstream: {n}" for n in up_notes[:4]]
                     + [f"unchecked: {i}" for i in unfound[:5]]
                     + ([f"... and {len(unfound) - 5} more"] if len(unfound) > 5 else []))
    elif unfound:
        # The source WAS available, so absence is a real signal. Per-identifier, with distinct ids.
        for ident in unfound:
            toks = [t for t in re.split(r"[-_\s]", ident) if len(t) > 1]
            present = [t for t in toks if t in src]
            if defer_to_parametrized:
                continue                     # section 3 owns this one, with the loop as evidence
            if len(present) >= max(2, len(toks) - 2):
                add("F", f"identifier `{ident}` not found verbatim but its tokens {present[:6]} "
                         f"appear - likely a DYNAMIC test name; confirm it resolves to exactly "
                         f"one test", fid=_ident_fid("tests_ident_dynamic", ident))
            else:
                add("F", f"identifier `{ident}` not found in test source (tokens present: "
                         f"{present[:6]}) - confirm it resolves to exactly one test",
                    fid=_ident_fid("tests_ident_missing", ident))

    # ------------------------- 1b. an identifier that is a strict SUBSTRING of a real test name
    # THE DEFECT SECTION 1 CANNOT SEE, and the reason this check reaches the network at all.
    # `_locate` resolves an identifier by searching for its leaf, so a declaration that drops the
    # tail of a test's name - "... as 0" against a test named "... as 0 (config.confidenceFloor ??
    # 0)" - is found, reads as present, and then scores through the verifier's containment match
    # against a test whose name it does not carry. Nothing downstream notices: the oracle reads
    # 1.0, `p2p_passed == p2p_total`, and the identifier is still wrong.
    #
    # Section 2 cannot see it either. That one compares declared identifiers to EACH OTHER, and
    # the name being truncated is declared nowhere - it exists only in the repository.
    #
    # The comparison itself lives in truncated_identifiers() because fix.py repairs what this
    # reports, and a repair derived from a second implementation is a repair that can disagree
    # with the finding. Everything below is severity and wording.
    truncated, truth_complete = truncated_identifiers(tasks, conf, md)
    if truth_complete:
        # Severity varies with the matcher, but the OK line's claim does not: a CANDIDATE
        # truncation is still an identifier that carries no test's name, and printing "every
        # identifier carries a real test's name in full" beside it contradicts the finding
        # directly above it.
        for ident, leaf, longer in truncated:
            real = longer[0]
            head, _sep, tail = real.partition(leaf)
            dropped = ", ".join(p for p in (
                ("%r from the front" % head) if head else "",
                ("%r from the end" % tail) if tail else "") if p)
            # Does the truncation SCORE, or does it merely fail loudly? That decides the
            # severity - a loud break costs one debugging session, a silent one ships - and it
            # has to be asked of the RUNTIME KEY, not of the bare names.
            #
            # The first version compared `leaf` against the test name and got this wrong whenever
            # the identifier carries a `file > suite > ` prefix, which most do. The verifier
            # matches the WHOLE declared identifier against the whole key, so the prefix is part
            # of both sides: under `endswith`, `a.ts > s > total count` is not a suffix of
            # `a.ts > s > shows the total count` - the prefix reappears in the middle and blocks
            # it - so that truncation resolves to `missing` and is loud, not silent. Same reason
            # kills a dropped HEAD under containment. Reconstructing the key and asking the
            # matcher's own question is the only version that stays right for every notation,
            # including bare-name identifiers where the prefix is empty.
            keys = [ident[:len(ident) - len(leaf)] + n for n in longer]
            if kind == MATCHER_SUBSTRING:
                silent = any(ident in k for k in keys)
            elif kind == MATCHER_SUFFIX:
                silent = any(k.endswith(ident) for k in keys)
            elif kind == MATCHER_EXACT:
                silent = False
            else:
                silent = None
            ev = ["declared: %s" % leaf,
                  "actual:   %s" % real,
                  "dropped:  %s" % (dropped or "(nothing - the names differ elsewhere)"),
                  "source:   %s" % ("the repository at %s" % ((md or {}).get("base_commit") or "")[:7]
                                    if upstream_complete else "tests/ in the bundle")]
            fix = ("Replace it in tests/config.json AND task.toml - both, or section 4 below "
                   "fails on the mismatch.")
            if len(longer) > 1:
                add("F", f"identifier `{ident}` carries no test's name, and is a strict SUBSTRING "
                         f"of {len(longer)} of them, and {kind_note} - the verifier's `next(...)` "
                         f"takes whichever comes first in iteration order. READ the matcher and "
                         f"decide which test this was meant to name.",
                    pending=True, fid=_ident_fid("tests_ident_truncated_ambiguous", ident),
                    evidence=ev[:3] + ["also matches: %s" % n for n in longer[1:4]] + matcher_ev[:2])
            elif silent is None:
                add("F", f"identifier `{ident}` carries no test's name - it is a strict SUBSTRING "
                         f"of `{real}`. {kind_note}, so whether it silently scores that test or "
                         f"resolves to nothing cannot be decided from here. READ tests/verifier.py "
                         f"and record the verdict.",
                    pending=True, fid=_ident_fid("tests_ident_truncated", ident),
                    evidence=ev + matcher_ev[:2])
            elif silent:
                add("F", f"identifier `{ident}` carries no test's name. The only test it matches "
                         f"is `{real}`, which it is a strict SUBSTRING of - the declaration drops "
                         f"{dropped}. {kind_note}, so it SCORES that test anyway and the "
                         f"truncation never surfaces: the reward reads 1.0 and p2p_passed == "
                         f"p2p_total while the identifier names nothing. {fix}",
                    fail=True, fid=_ident_fid("tests_ident_truncated", ident),
                    evidence=ev + matcher_ev[:2])
            else:
                add("F", f"identifier `{ident}` carries no test's name - the closest is `{real}`, "
                         f"which it is a strict SUBSTRING of (it drops {dropped}). {kind_note}, so "
                         f"it resolves to nothing and the test is scored `missing`. This one is "
                         f"self-revealing rather than silent - a p2p declared this way holds the "
                         f"oracle below 1.0 - but it is still the wrong name. {fix}",
                    fid=_ident_fid("tests_ident_truncated", ident),
                    evidence=ev + matcher_ev[:2])

    # ONE COLLISION, TWO FINDINGS - AND RULING ON ONE OF THEM SETTLES NOTHING. Sections 2 and 3
    # below ask the same question ("can these resolve to the same key?") about the same
    # identifier, from two angles, so a single genuinely-duplicated test name raises BOTH
    # `tests_ident_collision_<ident>` and `tests_ident_collision_runtime_<ident>`. Their ids
    # differ by one word and a hash.
    #
    # A reviewer reads verifier.py once, decides the collision is harmless, clears "the finding",
    # and sees "ADJUDICATED THIS RUN: 1 cleared" - then no QC pass appears, because the twin is
    # still PENDING and withholding it. That was reported as "adjudication does not write the
    # marker". The findings are not merged (they cite different evidence and a reviewer may
    # legitimately answer them differently), so each one has to SAY that the other exists.
    sibling_ids = {}
    def _sib(ident, fid):
        sibling_ids.setdefault(ident, []).append(fid)
        return fid

    # ------------------------------------------- 2. collisions between two DECLARED identifiers
    seen_pairs = set()
    for ident in ids:
        for other in ids:
            if not _collides(ident, other, kind) or (ident, other) in seen_pairs:
                continue
            seen_pairs.add((ident, other))
            rel = ("a SUFFIX" if other.endswith(ident) else
                   "a PREFIX" if other.startswith(ident) else "a SUBSTRING")
            add("F", f"identifier `{ident}` is {rel} of `{other}`, and {kind_note} — so both may "
                     f"resolve to the same testcase, in which case the verifier's `next(...)` "
                     f"silently takes whichever comes first in iteration order and the task scores "
                     f"an arbitrary one of them. READ the matcher and decide: can these two "
                     f"resolve to the same key? "
                     f"LEAN: {'a real collision' if kind == MATCHER_SUBSTRING else 'probably NOT a collision — the leaf names differ' if kind == MATCHER_SUFFIX else 'undetermined'}. "
                     f"Record it with `--adjudicated <id>=confirmed:\"why\"` or "
                     f"`=cleared:\"why\"`.",
                pending=True, fid=_sib(ident, _ident_fid("tests_ident_collision", ident + "\x00" + other)),
                evidence=matcher_ev[:4] or ["no candidate matcher line found in tests/verifier.py"])

    # --------------------- 3. the case with teeth: several RUNTIME keys ending in one identifier
    # Only possible when the test source is present. (2) compares declared identifiers to each
    # other, which cannot see a shared leaf name under two describe blocks, or a loop that appends
    # a suffix - in both of those only ONE name need be declared.
    if not absent and src.strip():
        suites = [m.group(2) for m in _SUITE_DECL.finditer(src)]
        for ident in ids:
            hits, dynamic = [], []
            for name, is_dyn in declared_names:
                expanded = _expand_literal_params(src, name) if is_dyn else []
                for candidate in (expanded or [name]):
                    if candidate == ident or _collides(ident, candidate, kind):
                        hits.append(candidate)
                if is_dyn and not expanded and _PARAM_LOOP.search(src):
                    dynamic.append(name)
            if len(hits) > 1:
                add("F", f"identifier `{ident}` matches {len(hits)} declared test names, and "
                         f"{kind_note} — the verifier's `next(...)` resolves to whichever comes "
                         f"first in iteration order, so the task scores an arbitrary one. "
                         f"{'Two suites declare the same leaf name. ' if len(suites) > 1 else ''}"
                         f"READ the matcher and decide. LEAN: a real collision.",
                    pending=True, fid=_sib(ident, _ident_fid("tests_ident_collision_runtime", ident)),
                    evidence=[f"matches: {h}" for h in hits[:5]] + matcher_ev[:2])
            elif dynamic:
                add("F", f"identifier `{ident}` sits alongside test name(s) built at run time whose "
                         f"parameter list is not a literal, so the set of keys cannot be enumerated "
                         f"statically and it is unknown whether more than one ends with this "
                         f"identifier. READ the loop and decide.",
                    pending=True, fid=_sib(ident, _ident_fid("tests_ident_parametrized", ident)),
                    evidence=[f"dynamic name: {d}" for d in dynamic[:4]] + matcher_ev[:2])

    # Cross-reference the twins, now that both sections have run. Written into evidence rather
    # than the message so it renders under the finding it belongs to, and stated as the
    # CONSEQUENCE ("the pass stays withheld"), because that is the part a reviewer got wrong.
    _by_id = {r["id"]: r for r in records}
    for _ident, _fids in sibling_ids.items():
        if len(_fids) < 2:
            continue
        for _fid in _fids:
            _rec = _by_id.get(_fid)
            if not _rec:
                continue
            _others = [f for f in _fids if f != _fid]
            _rec["evidence"] = list(_rec.get("evidence") or []) + [
                f"SAME IDENTIFIER is also reported as {', '.join(_others)} — one ruling does "
                f"NOT settle the other(s); until every one of them is ruled on, no QC pass is "
                f"recorded."]

    # ------------------------------------ 4. config.json f2p/p2p must equal task.toml f2p/p2p
    # Unchanged, and deliberately still a hard FAIL: two sets are equal or they are not, which
    # needs no reading and no adjudication.
    for key in ("f2p", "p2p"):
        c = set((conf or {}).get(key) or [])
        t = set(md.get(key) or [])
        if t and c != t:
            add("F", f"{key}: config.json {sorted(c)} != task.toml {sorted(t)}", fail=True)
    if not truncated and not any(x for x in findings["F"]
                                 if x.startswith("[FAIL]") or x.startswith("[PEND]")):
        # The OK line must not claim more than was actually checked. When the test source was not
        # in the bundle it says so, because an unqualified "all identifiers resolve" printed beside
        # a candidate reporting 17 unchecked names is the kind of reassurance that stops a CB
        # reading the candidate at all.
        scope = ("the declared lists agree and no collision is possible among them"
                 if absent else
                 "every identifier carries a real test's name in full, resolves to exactly one "
                 "test and none collide"
                 + (" (pre-existing tests read from the repository at %s)"
                    % ((md or {}).get("base_commit") or "")[:7] if upstream_complete else ""))
        add("F", f"f2p/p2p identifiers: {scope}, under the matcher in tests/verifier.py ({kind})"
                 + (" — resolution against the real test files was NOT checked, see "
                    "tests_ident_source_unavailable" if absent else ""),
            ok=True, fid="tests_ident_ok")


def check_H(md):
    """v2 #5 - Metadata: task_type Accuracy (value only; poster match is manual)."""
    tt = md.get("task_type")
    if not tt:
        add("H", "task_type missing from task.toml", fail=True)
    elif tt not in SEVEN_TYPES:
        add("H", f"task_type `{tt}` not one of the seven allowed values", fail=True)
    else:
        add("H", f"task_type `{tt}` is a valid value (confirm it MATCHES the image in Step 5)",
            ok=True)


def check_I(tasks):
    """v2 #6 - Evidence: Chain Consistency."""
    if not tasks:
        return
    man, _ = load_json(os.path.join(tasks, "environment/assets/ASSET_MANIFEST.json"))
    ev, _ = load_json(os.path.join(tasks, "evidence_bundle.json"))
    instr = read(os.path.join(tasks, "instruction.md")) or ""
    man = man or []
    ev = ev or []
    ev_by_path = {e.get("local_path"): e for e in ev if isinstance(e, dict)}
    for entry in man if isinstance(man, list) else []:
        f = entry.get("file")
        cpath = entry.get("container_path")
        if f and not os.path.exists(os.path.join(tasks, "environment/assets", f)):
            add("I", f"asset `{f}` in manifest not present in environment/assets/", fail=True)
        if cpath and not cpath.startswith("/app/.harbor_assets/"):
            add("I", f"asset `{f}` container_path `{cpath}` not under /app/.harbor_assets/",
                fail=True)
        # evidence_bundle divergence is only a NON-FAIL in v2 (#6) -> warn, don't hard-fail
        e = ev_by_path.get(cpath)
        if cpath and not e:
            add("I", f"asset `{f}` container_path `{cpath}` has no evidence_bundle.json entry "
                     f"[v2 #6 Non-Fail candidate: evidence_bundle diverges]")
        if cpath and cpath not in instr and (f and f not in instr):
            add("I", f"asset `{f}` ({cpath}) is not referenced in instruction.md", fail=True)
    man_paths = {e.get("container_path") for e in man} if isinstance(man, list) else set()
    for e in ev if isinstance(ev, list) else []:
        lp = e.get("local_path")
        if lp and lp not in man_paths:
            add("I", f"evidence_bundle entry `{lp}` has no ASSET_MANIFEST.json match "
                     f"[v2 #6 Non-Fail candidate]")
    if not any(x for x in findings["I"] if x.startswith("[FAIL]")):
        add("I", "evidence chain (assets <-> manifest <-> instruction) agrees "
                 "(confirm evidence_bundle too - a lone mismatch there is a v2 #6 Non-Fail)",
            ok=True)


def check_T(tasks):
    """mm - Tooling: does tests/test.sh save the agent's submission?

    WHY THIS IS ADVISORY AND NOT A FAIL. A task without the capture block is completely correct:
    it builds, it grades, oracle and nop and the trial all behave. What it cannot do is be
    RE-SCORED later without paying for another agent call -- editing tests/ invalidates a
    recorded trial reward, and with no saved submission the only way back is to re-run the agent.
    So this is a missing capability, not a defect, and it must never stand between a CB and a
    check run. It is reported every time because the cost of noticing late is a wasted trial.

    DETECTED BY THE OUTPUT PATH, not by a version marker. `/logs/verifier/submission.patch` is
    what the runner and any pseudo-trial actually look for, so a task that writes it by some other
    means is correctly reported as wired -- the check tracks the contract, not one implementation.
    """
    if not tasks:
        return
    ts = os.path.join(tasks, "tests/test.sh")
    body = read(ts) or ""
    if not body:
        return                      # a missing/unreadable test.sh is group B's finding, not ours
    if "/logs/verifier/submission.patch" in body:
        # Wired -- but placement is the half that decides whether it captures the agent or the
        # tests. test.patch is applied part-way down; a capture below that point records the
        # bundle's own tests as though the agent had written them.
        cap = body.index("/logs/verifier/submission.patch")
        applied = body.find("/tests/test.patch")
        if applied != -1 and cap > applied:
            add("T", "tests/test.sh writes submission.patch AFTER test.patch is applied, so the "
                     "saved submission includes the task's own tests and is not what the agent "
                     "produced. Move the capture block above the restore loop. "
                     "[Non-Fail: the reward is unaffected; only the saved submission is wrong]",
                fid="submission_capture_late")
        else:
            add("T", "tests/test.sh saves the agent's submission to /logs/verifier/"
                     "submission.patch before applying test.patch", ok=True,
                fid="submission_capture_ok")
        return
    add("T", "tests/test.sh does not save the agent's submission, so a recorded trial cannot be "
             "re-scored against edited tests without paying for another agent run. fix.py wires "
             "the canonical block in mechanically. "
             "[Non-Fail: the task is correct and gradeable as it stands]",
        fid="submission_capture_missing")


def check_N(tasks):
    """v2 Hardening - is the AGENT phase sealed?

    Scope is deliberately ONE value. [verifier] network_mode and [verifier.env] are graded by
    qc_rubric_format (the judge needs egress); [environment] is not graded at all, because a
    wrong value there fails the build loudly and the oracle catches it; and allowlist CONTENTS
    are not graded because no task in the corpus uses allowlist, so any rule would be written
    against a guess rather than evidence.

    This one is different on both counts. Both reference tasks set "no-network" unanimously, so
    there is a known-good constant to compare against rather than a judgement to make. And it is
    the only network setting NOTHING else can catch: oracle and nop run no agent, so the gate is
    structurally blind to it, and the runner only warns at run time - after the trial has already
    been committed to. QC runs pre-trial, so this is the last point where the cost is avoidable.

    An unsealed agent can fetch the answer during the trial, so the reward measures nothing.
    """
    if not tasks:
        return
    txt = read(os.path.join(tasks, "task.toml"))
    if txt is None:
        return                                   # missing task.toml is already group B's finding
    m = re.search(r"^\[agent\]\s*$(.*?)(?=^\[|\Z)", txt, re.M | re.S)
    nm = re.search(r"^\s*network_mode\s*=\s*[\"']([^\"']*)[\"']", m.group(1) if m else "", re.M)
    val = nm.group(1) if nm else None
    if val in ("no-network", "no_network", "none"):
        add("N", f'[agent] network_mode = "{val}" - the agent phase is sealed', ok=True,
            fid="agent_sealed")
    elif val == "public":
        add("N", '[agent] network_mode = "public" - the agent phase is deliberately UNSEALED, '
                 'so the agent can fetch or install the answer during the trial and any reward '
                 'it produces is unverified. Set "no-network" unless the task genuinely needs '
                 'egress at solve time.', fail=True, fid="agent_unsealed")
    elif val is None:
        add("N", 'task.toml declares no [agent] network_mode, so harbor applies NO egress '
                 'control during the agent phase - the trial is not sealed and the agent can '
                 'fetch the answer. Add [agent] network_mode = "no-network".',
            fail=True, fid="agent_seal_absent")
    else:
        add("N", f'[agent] network_mode = "{val}" - sealed, but not the "no-network" both '
                 f'reference tasks use; confirm the allowance is needed at solve time',
            fid="agent_seal_nonstandard")


TASK_NAME_PREFIX = "scale-ai/"
_REPO_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _toml_section_strings(txt, section):
    """String keys of ONE top-level table -> {key: value}, or None when the table is absent.

    Section-aware on purpose: parse_toml's fallback (the path the sandbox's Python 3.10 takes)
    flattens every table into one dict, so a `name` under [task] and a `name` anywhere else would
    be indistinguishable. Only `[section]` itself is read - `[section.sub]` is a different table.
    """
    # `#[^\n]*`, not `#.*`: under re.S a header comment would otherwise swallow the whole table.
    m = re.search(r"^[ \t]*\[" + re.escape(section) + r"\][ \t]*(?:#[^\n]*)?$(.*?)(?=^[ \t]*\[|\Z)",
                  txt, re.M | re.S)
    if not m:
        return None
    out = {}
    # Multi-line forms first, or `"""x"""` reads as the empty string `""` followed by junk.
    val = (r'"""(?P<mb>.*?)"""|' r"'''(?P<ml>.*?)'''|"
           r'"(?P<b>(?:[^"\\\n]|\\.)*)"|' r"'(?P<l>[^'\n]*)'")
    for v in re.finditer(r'^[ \t]*(?P<k>' + _TOML_KEY + r')[ \t]*=[ \t]*(?:' + val + ')',
                         m.group(1), re.M | re.S):
        if v.group("mb") is not None:
            # TOML trims the newline right after the opening delimiter
            s = _toml_unescape(re.sub(r"\\\s*\n\s*", "", v.group("mb"))).removeprefix("\n")
        elif v.group("ml") is not None:
            s = v.group("ml").removeprefix("\n")
        elif v.group("b") is not None:
            s = _toml_unescape(v.group("b"))
        else:
            s = v.group("l")
        out.setdefault(v.group("k"), s)
    return out


def check_K(tasks):
    """v2 #1 - Structure: task.toml identity block.

    Every bundle must carry

        [task]
        name = "scale-ai/<task_id>"

        [metadata]
        task_id = "<task_id>"
        title = "..."
        repository_name = "<owner>/<repo>"

    with [task].name derived from [metadata].task_id, so the two can never name different tasks.
    repository_name is cross-checked against repo_url when that is present, because the two are
    written by hand in different places and drift silently.
    """
    if not tasks:
        return
    txt = read(os.path.join(tasks, "task.toml"))
    if txt is None:
        return                                   # missing task.toml is already group B's finding
    task = _toml_section_strings(txt, "task")
    meta = _toml_section_strings(txt, "metadata")
    if meta is None:
        add("K", "task.toml has no [metadata] table (needs task_id, title, repository_name)",
            fail=True, fid="toml_metadata_missing")
        meta = {}
    for key in ("task_id", "title", "repository_name"):
        if meta and not (meta.get(key) or "").strip():
            add("K", f"[metadata] {key} is missing or empty in task.toml", fail=True,
                fid=f"toml_metadata_{key}_missing")
    tid = (meta.get("task_id") or "").strip()
    want = f'{TASK_NAME_PREFIX}{tid or "<task_id>"}'
    if task is None:
        add("K", f'task.toml has no [task] table. Add it with name = "{want}"',
            fail=True, fid="toml_task_missing")
    elif not task.get("name"):
        add("K", f'[task] has no name in task.toml. Set name = "{want}"',
            fail=True, fid="toml_task_name_missing")
    elif tid and task["name"] != want:
        add("K", f'[task] name = "{task["name"]}" does not match [metadata] task_id; '
                 f'expected "{want}"', fail=True, fid="toml_task_name_mismatch")
    repo = (meta.get("repository_name") or "").strip()
    if repo and not _REPO_NAME.match(repo):
        add("K", f'[metadata] repository_name = "{repo}" is not in "<owner>/<repo>" form',
            fail=True, fid="toml_repository_name_format")
    url = (meta.get("repo_url") or "").strip()
    if repo and url:
        # https://host/o/r(.git)  and  git@host:o/r(.git)
        tail = re.sub(r"(\.git)?/*$", "", re.sub(r"^(?:[a-z+]+://[^/]+/|[^@/]+@[^:/]+:)", "", url))
        if tail.lower() != repo.lower():
            add("K", f'[metadata] repository_name = "{repo}" disagrees with repo_url = "{url}"',
                fail=True, fid="toml_repository_name_mismatch")
    if not findings["K"]:
        add("K", f'task.toml identity block present: [task] name = "{want}", '
                 f'[metadata] task_id/title/repository_name set', ok=True, fid="toml_identity_ok")


# ------------------- v2 Hardening - does the image still let the HARNESS run? (group E)
#
# THE FAILURE THIS EXISTS FOR:
#
#   NonZeroAgentExitCodeError: Command failed (exit 127):
#     if command -v apk; then npm install -g @anthropic-ai/claude-code;
#     else curl -fsSL https://downloads.claude.ai/.../bootstrap.sh | bash -s --; fi
#     && ... && claude --version
#   stderr: bash: line 1: curl: command not found
#
# The Dockerfile had hardened itself against exfiltration by deleting curl/wget and pointing npm
# at a dead registry. But harbor installs the agent CLI *into this image*, over exactly those two
# paths - curl on glibc bases, `npm install -g` on apk ones - so the anti-cheat removed the only
# two ways the agent can be installed, and the trial died before the model was ever called.
#
# WHY NOTHING ELSE CATCHES IT. Same structural blindness as check_N, one step further out: oracle
# and nop install no agent, so the gate is 1.0/0.0 on an image no agent can run in. `harbor check`
# reads the bundle, not the built image. The build itself succeeds - `rm -f` is a legal RUN. So the
# first observation is the trial, which is the one step that costs a real model call.
#
# WHY IT IS DECIDABLE STATICALLY. This is not a judgement like M or S. The Dockerfile either
# removes a binary the harness invokes or it does not, and both the removal and harbor's
# dependency on it are fixed text. So group E hard-FAILs, and marks itself blocking.
#
# WHY THE HARDENING IS REDUNDANT ANYWAY. `[agent] network_mode = "no-network"` (group N) already
# seals the agent phase at the harness level, which is strictly stronger than deleting clients
# inside the image: it also covers python's urllib, node's fetch, and git-over-ssh, none of which
# an `rm -f /usr/bin/curl` touches. So the in-image blackholing buys no protection the seal does
# not already give, and costs the trial. When the seal is present the repair is pure subtraction.

# What harbor needs to survive the build, and what breaks when it does not.
_HARNESS_BINS = {
    "curl":  ("harbor installs the agent CLI with "
              "`curl -fsSL https://downloads.claude.ai/.../bootstrap.sh | bash` on every non-apk "
              "base image. Deleting it is the exact 'exit 127: curl: command not found' failure."),
    "bash":  ("every harbor phase is spawned as `bash -c 'set -euo pipefail; ...'` and the "
              "bootstrap pipes into `bash -s --`. Without it nothing runs at all."),
    "git":   ("the verifier diffs the candidate against the `harbor_base` tag with git to build "
              "source.txt/changed_files.txt. Without it the diff is empty and the run is "
              "unauditable."),
    "node":  ("the apk install path is `npm install -g @anthropic-ai/claude-code`, and a JS/TS "
              "task's test runner needs the runtime regardless."),
    "npm":   ("the apk install path for the agent CLI, and the usual test-runner entry point."),
    "wget":  ("the fallback fetcher when curl is absent; some bootstrap paths and base-image "
              "tooling reach for it."),
}
# Hosts the harness itself must reach while it is setting the container up. Blackholing these in
# /etc/hosts is the same defect as deleting curl, one layer down.
_HARNESS_HOSTS = {
    "downloads.claude.ai": "the agent CLI bootstrap script is fetched from here",
    "claude.ai":           "parent domain of the agent CLI download host",
    "api.anthropic.com":   "the agent's own model endpoint during the trial",
    "registry.npmjs.org":  "the `npm install -g @anthropic-ai/claude-code` install path (apk "
                           "bases), and any test-time dependency the build did not vendor",
}
# Removal is graded per `&&`/`;`-separated FRAGMENT rather than per whole RUN, because one command
# takes many targets: `rm -f /usr/bin/curl /usr/bin/wget` is two defects in one fragment, and a
# single regex over the RUN reports only the first.
_FRAG_SPLIT = re.compile(r"&&|\|\||;|\|")
_REMOVERS = (
    (re.compile(r"^\s*(?:rm|unlink)\b"),                            "deletes"),
    (re.compile(r"^\s*(?:apt-get|apt)\s+(?:remove|purge)\b"),       "uninstalls"),
    (re.compile(r"^\s*apk\s+del\b"),                                "uninstalls"),
    (re.compile(r"^\s*dpkg\s+(?:-P|--purge)\b"),                    "uninstalls"),
    (re.compile(r"^\s*(?:yum|dnf)\s+(?:remove|erase)\b"),           "uninstalls"),
    (re.compile(r"^\s*chmod\s+(?:000|0000|a-x|-x|u-x)\b"),          "makes unexecutable"),
    (re.compile(r"^\s*(?:mv|truncate)\b"),                          "moves aside"),
)
# THE PREFIX AND SUFFIX GUARDS ARE LOAD-BEARING, not defensive noise. The name must be either a
# bare argument (whitespace before it) or an entry in a bin dir, and must not continue into another
# token. Without the prefix guard, `rm -rf /app/.git` - the .git strip EVERY MM SWE Dockerfile
# performs, and MUST perform, as anti-cheat - reads as "deletes git", and the check hard-FAILs a
# correct bundle on its most universal line. Without the suffix guard, `.bin/curl-wrapper` or a
# `git-lfs` path does the same.
_BIN_DIR = r"(?:/usr/local/bin/|/usr/bin/|/bin/|/usr/sbin/|/sbin/)"
_BIN_TOKEN = re.compile(rf"(?:(?<=\s)|^)(?:{_BIN_DIR})?(" + "|".join(_HARNESS_BINS)
                        + r")(?![\w./-])")


# ---- BuildKit-only Dockerfile syntax -------------------------------------------------------------
#
# THE FAILURE THIS EXISTS FOR (a second task, same family as the deleted curl):
#
#   # syntax=docker/dockerfile:1.4
#   COPY <<'PYEOF' /tmp/obfuscate_harbor.py
#   ...
#   PYEOF
#
# It was the only task of 66 using heredoc syntax and the only one whose build failed - twice,
# independently, which is what a capability mismatch looks like and is not what a flake looks like.
# MEASURED here on docker 29.6, all three cases:
#
#   classic builder (DOCKER_BUILDKIT=0)  -> `COPY failed: no source files were specified`
#   BuildKit + `# syntax=` directive     -> works, but FIRST does `resolve image config for
#                                           docker-image://docker.io/docker/dockerfile:1.4`
#   BuildKit, directive deleted          -> works; the bundled frontend already does heredocs
#
# A heredoc COPY does not copy a file, it CREATES one from the inline body - and that is a frontend
# feature, not core docker. Where the frontend does not support it, COPY falls back to its ordinary
# meaning ("copy these paths from the build context"), `<<'PYEOF'` is not a path, and the build dies
# before any layer exists. That is the "it could not find that file" symptom: nothing was mislocated,
# the file never existed, because the instruction that was supposed to create it was not understood.
#
# The `# syntax=` line is not the cure and is its own defect: the classic builder IGNORES it (it is
# a BuildKit feature), so it buys nothing on the one builder that needs help - while on BuildKit it
# adds a docker.io round-trip before instruction one (a proxy, a rate limit, an air-gapped builder
# or a pinned mirror each turn that into a build failure) against a FLOATING tag, so the parser
# itself can change under a task whose whole purpose is to be reproducible.
_SYNTAX_DIRECTIVE = re.compile(r"^\s*#\s*syntax\s*=\s*(\S+)", re.I)
# Each of these is a hard parse error or a silent no-op on the classic builder.
_BUILDKIT_ONLY = (
    (re.compile(r"^\s*RUN\b[^\n]*--mount="),            "RUN --mount",
     "rejected as an unknown flag by the classic builder"),
    (re.compile(r"^\s*(?:COPY|ADD)\b[^\n]*--link\b"),   "COPY --link",
     "rejected as an unknown flag by the classic builder"),
    (re.compile(r"^\s*(?:COPY|ADD)\b[^\n]*--parents\b"), "COPY --parents",
     "BuildKit-only, and newer than many pinned frontends"),
    (re.compile(r"^\s*ADD\b[^\n]*--checksum="),         "ADD --checksum",
     "rejected as an unknown flag by the classic builder"),
    (re.compile(r"^\s*RUN\b[^\n]*--network="),          "RUN --network",
     "BuildKit-only, and it silently changes the build's egress posture"),
)
# `<<TAG`, `<<'TAG'`, `<<-TAG`: the tag, whether it was quoted (a quoted tag means the body is
# LITERAL - no expansion), and whether `-` strips leading tabs. All three matter to a rewrite.
_HEREDOC = re.compile(r"<<(?P<dash>[-~]?)(?P<q>[\"']?)(?P<tag>\w+)(?P=q)")


def heredocs(txt):
    """[dict] for every heredoc instruction in a Dockerfile, with its body.

    `_logical_lines` joins `\\` continuations but knows nothing about heredocs, so on its own it
    scans the BODY as if each line were an instruction - which is how the classic builder misreads
    the file, and not how a check should. Returned per instruction:

        line     1-based lineno of the instruction
        instr    COPY | ADD | RUN
        tag      the terminator word
        quoted   True when written <<'TAG' - body is literal, so a printf rewrite is exact
        dash     True when written <<-TAG - leading tabs are stripped by the frontend
        head     the instruction line with the heredoc token(s) removed (dest for COPY)
        body     [str] body lines, verbatim
        end      1-based lineno of the terminator, or None when it is unterminated
        n_docs   how many heredocs this one instruction opens (>1 is not auto-fixable)
    """
    lines = txt.splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not re.match(r"\s*(?:COPY|ADD|RUN)\b", line, re.I):
            i += 1
            continue
        ms = list(_HEREDOC.finditer(line))
        if not ms:
            i += 1
            continue
        m = ms[0]
        tag = m.group("tag")
        body, j = [], i + 1
        while j < len(lines) and lines[j].strip() != tag:
            body.append(lines[j])
            j += 1
        out.append({
            "line": i + 1,
            "instr": re.match(r"\s*(\w+)", line).group(1).upper(),
            "tag": tag,
            "quoted": bool(m.group("q")),
            "dash": bool(m.group("dash")),
            "head": _HEREDOC.sub("", line).rstrip(),
            "body": body,
            "end": (j + 1) if j < len(lines) else None,
            "n_docs": len(ms),
        })
        i = (j + 1) if j < len(lines) else j
    return out


def _copy_sources(text):
    """[(source, dest)] for a COPY/ADD. [] when the sources do not come from the build context."""
    m = re.match(r"\s*(?:COPY|ADD)\s+(.*)$", text, re.I | re.S)
    if not m:
        return []
    rest = m.group(1)
    if re.search(r"--from=", rest, re.I):
        return []                            # source is another build STAGE, not the context
    rest = re.sub(r"--[\w-]+(?:=\S+)?\s*", "", rest)       # --chown=, --chmod=, --link, ...
    if rest.lstrip().startswith("["):                       # JSON form: ["src", "dst"]
        try:
            toks = json.loads(rest.strip())
        except Exception:
            return []
    else:
        toks = rest.split()
    if len(toks) < 2:
        return []
    return [(s, toks[-1]) for s in toks[:-1]]


def _removed_bins(text):
    """[(binary, how, fragment)] for every harness binary this instruction disables."""
    out = []
    for frag in _FRAG_SPLIT.split(text):
        frag = re.sub(r"^\s*(?:RUN|ENV)\s+", "", frag, flags=re.I)
        how = next((h for rx, h in _REMOVERS if rx.search(frag)), None)
        if not how:
            continue
        for m in _BIN_TOKEN.finditer(frag):
            out.append((m.group(1), how, frag.strip()))
    return out
# a registry pointed at a black hole: loopback, a reserved port, or an unroutable address
_DEAD_REGISTRY = re.compile(
    r"(?:npm|yarn|pnpm)\s+config\s+set\s+registry\s+(\S+)|registry\s*=\s*(\S+)", re.I)
_BLACKHOLE_HOST = re.compile(r"^(?:127\.|0\.0\.0\.0|localhost|::1|\[::1\]|10\.255\.255\.|"
                             r"192\.0\.2\.|198\.51\.100\.|203\.0\.113\.|invalid\b)", re.I)
# a load-bearing build step whose failure is swallowed, so the image ships half-built
_SWALLOWED = re.compile(r"\b(npm|yarn|pnpm)\s+(?:ci|install|i)\b[^\n]*?(?:\|\|\s*true|2>\s*/dev/null)")
# `|| true` on a MULTI-LINK chain: the RUN reports success no matter which link aborted it, so
# "the build passed" stops being evidence that any of it ran. This is the mechanism that hid the
# read-only-/etc/hosts abort, and it is worth flagging independently of what the links do.
_CHAIN_SWALLOWED = re.compile(r"\|\|\s*true\s*$")


def _logical_lines(txt):
    """[(first_lineno, joined_text)] - Dockerfile instructions with `\\` continuations joined.

    Every pattern below is anchored on `&&`/`;`-separated fragments, and a hardening RUN is
    routinely spread over ten physical lines (this is how the real defect was written). Matching
    per physical line would miss all of them.
    """
    out, buf, start = [], [], None
    for i, raw in enumerate(txt.splitlines(), 1):
        line = raw.rstrip()
        if line.lstrip().startswith("#") and not buf:
            continue
        if start is None:
            start = i
        if line.endswith("\\"):
            buf.append(line[:-1])
            continue
        buf.append(line)
        joined = " ".join(x.strip() for x in buf).strip()
        if joined:
            out.append((start, joined))
        buf, start = [], None
    if buf:
        out.append((start or 1, " ".join(x.strip() for x in buf).strip()))
    return out


def _hosts_blackholed(logical):
    """{hostname: lineno} for names the Dockerfile appends to /etc/hosts pointing at a black hole."""
    found = {}
    for ln, text in logical:
        if "/etc/hosts" not in text:
            continue
        for ip, host in re.findall(r"['\"]?(\d+\.\d+\.\d+\.\d+)\s+([A-Za-z0-9.\-]+)['\"]?", text):
            if _BLACKHOLE_HOST.match(ip):
                found.setdefault(host.lower(), ln)
    return found


def check_E(tasks, md):
    """v2 Hardening (BLOCKING) - does environment/Dockerfile leave the harness able to run?"""
    if not tasks:
        return
    dpath = os.path.join(tasks, "environment", "Dockerfile")
    txt = read(dpath)
    if txt is None:
        return                                # missing Dockerfile is already group B's finding
    # A heredoc BODY is data, not instructions. `_logical_lines` cannot know that, so its output is
    # filtered here before any rule runs over it - otherwise a python line like
    # `os.system("rm -f /usr/bin/curl")` inside a body could book a harness-binary removal against a
    # Dockerfile that removes nothing. Reading the body as instructions is precisely the mistake the
    # classic builder makes; the check must not repeat it.
    docs = heredocs(txt)
    body_lines = {n for hd in docs
                  for n in range(hd["line"] + 1, (hd["end"] or len(txt.splitlines()) + 1))}
    logical = [(ln, t) for ln, t in _logical_lines(txt) if ln not in body_lines]
    joined_all = "\n".join(t for _, t in logical)
    base = ([t for _, t in logical if t.upper().startswith("FROM ")] or [""])[-1]
    apk_base = bool(re.search(r"\balpine\b", base, re.I) or re.search(r"\bapk\s+add\b", joined_all))

    # The seal decides whether the repair is pure subtraction or a trade-off, so it is read here
    # too (group N grades the value itself).
    ttxt = read(os.path.join(tasks, "task.toml")) or ""
    am = re.search(r"^\[agent\]\s*$(.*?)(?=^\[|\Z)", ttxt, re.M | re.S)
    anm = re.search(r"^\s*network_mode\s*=\s*[\"']([^\"']*)[\"']", am.group(1) if am else "", re.M)
    sealed = (anm.group(1) if anm else None) in ("no-network", "no_network", "none")
    seal_note = (" `[agent] network_mode` already seals the agent phase at the harness level - "
                 "which also covers urllib, node fetch and git-over-ssh, none of which deleting a "
                 "binary touches - so this line buys no protection and can simply be dropped."
                 if sealed else
                 " NOTE: `[agent] network_mode` is NOT sealed (see group N), so this line is the "
                 "only egress control there is. Seal the agent phase FIRST, then drop this line - "
                 "do not just delete it.")

    hit = False
    for ln, text in logical:
        if not re.match(r"(?:RUN|ENV)\b", text, re.I):
            continue
        for bin_, how, frag in _removed_bins(text):
            add("E", f"Dockerfile:{ln} {how} `{bin_}`, which the HARNESS needs: "
                     f"{_HARNESS_BINS[bin_]} The build succeeds and oracle/nop still score "
                     f"1.0/0.0 (they install no agent), so this surfaces only as the trial "
                     f"dying at startup - after the model call is paid for.{seal_note}"
                     f"  [fragment: {frag!r}]",
                fail=True, blocking=True, fid=f"env_harness_bin_{bin_}")
            hit = True

        # A DEAD REGISTRY IS DECIDED, NOT HEDGED. This used to emit a CANDIDATE on every non-apk
        # base - "confirm no test-time npm install needs it" - which is a question the bundle already
        # answers: tests/test.sh and tests/verifier.py are right there, and either they invoke a
        # registry-touching install or they do not. A check that can read the answer and asks the
        # reviewer instead is spending their attention to save its own effort, and a group whose
        # findings are mostly hedges gets skimmed - which costs the FAILs sitting next to them.
        #
        # So it fires only where it can point at the consumer: the apk install path for the agent
        # CLI, or a verify-time install that would hit the dead address. Otherwise it stays silent.
        for m in _DEAD_REGISTRY.finditer(text):
            url = (m.group(1) or m.group(2) or "").strip("'\"")
            host = re.sub(r"^\w+://", "", url).split("/")[0].split(":")[0]
            if not host or not _BLACKHOLE_HOST.match(host):
                continue
            verify_src = "\n".join(read(os.path.join(tasks, "tests", f)) or ""
                                   for f in ("test.sh", "verifier.py"))
            v = re.search(r"\b(?:npm\s+(?:ci|install|i|exec)|npx|yarn\s+(?:add|install)|"
                          r"pnpm\s+(?:add|install))\b", verify_src)
            if not (apk_base or v):
                continue          # nothing on any path reaches the registry - saying so adds noise
            add("E", f"Dockerfile:{ln} points the npm registry at the black hole `{url}`, and "
                     + ("this base image is apk-based, so harbor installs the agent CLI with "
                        "`npm install -g @anthropic-ai/claude-code` over exactly that registry - "
                        "the trial dies at startup." if apk_base else
                        f"the verify path reaches the registry ({v.group(0)!r} in tests/), so the "
                        f"verifier fails against a dead address and a CORRECT submission records "
                        f"0.0.") + seal_note,
                fail=True, blocking=True, fid="env_npm_registry_blackhole")
            hit = True

        # `npm install ... || true` and `|| true` on a long chain: BOTH DELETED, and the deletion is
        # the same rule that justifies this group existing. Group E is only entitled to report what
        # nothing downstream can catch - that is why check_N grades one value and why
        # `[environment]` is not graded at all ("a wrong value there fails the build loudly and the
        # oracle catches it").
        #
        # A swallowed `npm install` does not clear that bar. If dependencies fail to resolve, the
        # test runner cannot run, and the ORACLE reports 0.0 instead of 1.0 - loudly, before any
        # trial, at the step the CB is already required to perform. So the finding could only ever
        # repeat what the gate says better, and on a task whose oracle is 1.0 it is not merely noise
        # but WRONG: a green oracle is positive proof the deps resolved.
        #
        # `|| true` on a multi-link chain is real, but it is not a defect on its own - it is the
        # MECHANISM by which a defect hides, and the only defect it hides here (the read-only
        # /etc/hosts abort) is already reported by env_hosts_build_write, which explains the
        # swallowing in the same breath. Emitting it separately turned one defect into three
        # findings on one line, which is how a reviewer learns to skim past group E.

    # ---- /etc/hosts anti-cheat: ineffective, AND it makes the rest of its chain builder-dependent
    #
    # MEASURED, not reasoned about (docker 29.6, BuildKit):
    #   1. During a BuildKit build /etc/hosts is READ-ONLY:
    #        #7 0.250 /bin/sh: 1: cannot create /etc/hosts: Read-only file system
    #      The RUN is written as `printf ... >> /etc/hosts && npm config set ... && rm -f curl`, so
    #      that first failure SHORT-CIRCUITS the chain: npm config set never runs, curl is never
    #      deleted - and a trailing `|| true` makes the whole RUN exit 0, so the build looks clean.
    #   2. Even where the write DOES land in a layer, docker regenerates /etc/hosts for every
    #      container, so the entry is gone at run time. Verified by commit+run: the appended line is
    #      absent and registry.npmjs.org resolves normally.
    #
    # BOTH WAYS, THE HOSTS ANTI-CHEAT PROTECTS NOTHING. And the combination is what produces the
    # confusing failure this check was written for: under one builder the chain aborts at link 1 and
    # curl survives (the image looks fine, and a local probe PASSES); under another the write
    # succeeds, the chain continues, curl is deleted, and the trial dies with exit 127. The SAME
    # Dockerfile, different builders. That is why this stays a static FAIL even when a local docker
    # probe is green.
    writes_hosts = [ln for ln, t in logical
                    if re.search(r">>?\s*/etc/hosts|tee\s+(?:-a\s+)?/etc/hosts", t)]
    blackholed = _hosts_blackholed(logical)
    for ln in writes_hosts:
        chain_bins = sorted({b for _l, t in logical if _l == ln for b, _h, _f in _removed_bins(t)})
        # Which harness hosts this write MEANT to blackhole rides along as evidence rather than as
        # its own finding. It is the same line and the same defect, and the standalone version had to
        # open by explaining it was not a live break - a finding that argues for its own irrelevance
        # is one the reviewer should not have been handed.
        intent = [f"would blackhole `{h}` ({_HARNESS_HOSTS[h]}) - harmless only because the write "
                  f"never lands; do NOT relocate it somewhere that works"
                  for h, hl in sorted(blackholed.items()) if hl == ln and h in _HARNESS_HOSTS]
        add("E", f"Dockerfile:{ln} writes /etc/hosts from a RUN. This does not work, in two "
                 f"independent ways: /etc/hosts is READ-ONLY during a BuildKit build (`cannot "
                 f"create /etc/hosts: Read-only file system`), and docker regenerates the file for "
                 f"every container anyway, so a write that does land in a layer is discarded at run "
                 f"time. The blackhole therefore never takes effect on any builder."
                 + (f" WORSE: the same `&&` chain then {'deletes' if chain_bins else 'continues'}"
                    f" {', '.join(chain_bins)} - so whether the harness survives depends on whether "
                    f"THIS builder let the first link run. Under BuildKit the chain aborts here and "
                    f"the image looks fine (a local docker probe PASSES); under a builder that "
                    f"permits the write, the chain continues and the trial dies with exit 127. That "
                    f"is the same Dockerfile behaving two different ways, and it is why this is a "
                    f"static FAIL even when a local probe is green." if chain_bins else
                    " Put the egress control in task.toml `[agent] network_mode` instead, which is "
                    "enforced by harbor rather than by the image.")
                 + seal_note,
            fail=True, blocking=bool(chain_bins) or None, fid="env_hosts_build_write",
            evidence=intent)
        hit = True

    # ---- BuildKit-only syntax: the build dies before any layer exists ----------------------------
    for hd in docs:
        why = (f"A heredoc {hd['instr']} does not copy a file, it CREATES one from the inline body - "
               f"a frontend feature, not core docker. Where the frontend does not support it, "
               f"`<<{hd['tag']}` is read as an ordinary source path, no such path exists, and the "
               f"build dies with `COPY failed: no source files were specified` before a single layer "
               f"is produced (measured on docker 29.6 with DOCKER_BUILDKIT=0). Nothing is "
               f"mislocated - the file never exists, because the instruction meant to create it was "
               f"not understood. Rewrite it as a portable `RUN printf ... > dest`, which needs no "
               f"frontend feature and no extra file in the bundle.")
        if hd["end"] is None:
            add("E", f"Dockerfile:{hd['line']} opens a heredoc `<<{hd['tag']}` that is never "
                     f"terminated - the rest of the file is swallowed as its body. {why}",
                fail=True, blocking=True, fid="env_heredoc_unterminated")
        else:
            add("E", f"Dockerfile:{hd['line']} uses a BuildKit-only heredoc "
                     f"(`{hd['instr']} <<{hd['tag']}`, body lines {hd['line'] + 1}-{hd['end'] - 1}). "
                     + why,
                fail=True, blocking=True, fid="env_buildkit_heredoc",
                evidence=[f"writes: {hd['head'].split()[-1] if hd['head'].split() else '?'}",
                          f"body: {len(hd['body'])} line(s), "
                          f"{'literal (quoted tag)' if hd['quoted'] else 'EXPANDED (unquoted tag)'}"])
        hit = True

    for ln, text in logical:
        for rx, feat, note in _BUILDKIT_ONLY:
            if rx.search(text):
                add("E", f"Dockerfile:{ln} uses the BuildKit-only feature `{feat}` - {note}. The "
                         f"build then fails outright on a builder without it, which produces a "
                         f"reward of 0 for reasons that have nothing to do with the task.",
                    fail=True, blocking=True, fid=f"env_buildkit_{feat.split()[-1].strip('-')}")
                hit = True

    # A PARSER DIRECTIVE ONLY COUNTS BEFORE THE FIRST INSTRUCTION - that is docker's own rule, and
    # obeying it is also what stops the check reading heredoc CONTENT as configuration. A fixture
    # whose python body contained the line `# syntax=docker/dockerfile:1.4` was reported as declaring
    # the directive twice, once for the real line 1 and once for a string of data on line 7. Scanning
    # a fixed window of leading lines was wrong twice over: it could reach into a body, and it could
    # miss nothing useful, since a directive after the first instruction is just a comment.
    for i, raw in enumerate(txt.splitlines(), 1):
        if re.match(r"\s*(?:FROM|ARG|RUN|COPY|ADD|ENV|WORKDIR|CMD|ENTRYPOINT|LABEL|USER|EXPOSE|"
                    r"VOLUME|SHELL|HEALTHCHECK|ONBUILD|STOPSIGNAL)\b", raw, re.I):
            break                       # first instruction reached; anything later is a comment
        m = _SYNTAX_DIRECTIVE.match(raw)
        if not m:
            continue
        ref = m.group(1)
        floating = not re.search(r"@sha256:", ref)
        add("E", f"Dockerfile:{i} declares `# syntax={ref}`, which makes BuildKit FETCH a parser "
                 f"from a registry before instruction one (`resolve image config for "
                 f"docker-image://docker.io/{ref}` - measured). That is a build-time network "
                 f"dependency on Docker Hub: a proxy, a rate limit, an air-gapped builder or a "
                 f"pinned mirror each turn it into a build failure."
                 + (f" The reference is also FLOATING (no @sha256:), so the parser itself can change "
                    f"under a task whose entire purpose is to be reproducible." if floating else "")
                 + " And it does not do what it looks like it does: the classic builder IGNORES the "
                   "directive entirely, so it cannot rescue the heredoc it was added for, while a "
                   "modern BuildKit already supports heredocs without it (verified by deleting the "
                   "line and rebuilding). Remove it once the BuildKit-only syntax is gone.",
            fail=True, fid="env_syntax_directive")
        hit = True

    # ---- every COPY/ADD source must actually resolve inside the build context --------------------
    # THE GENERALIZATION, and the reason it earns its place next to the heredoc rule: harbor builds
    # with the context set to `Tasks/environment/` (that is why `COPY assets/ ...` works). So every
    # local COPY source is a path this check can resolve on disk, right now, with no docker at all.
    # It catches the heredoc case, a `../` that escapes the context, and a plain typo - i.e. the
    # whole "cannot find that file at build time" class rather than the one syntax that produced it.
    heredoc_lines = {hd["line"] for hd in docs}
    for ln, text in logical:
        if ln in heredoc_lines:
            continue                       # already reported as env_buildkit_heredoc
        for src, dest in _copy_sources(text):
            if re.match(r"https?://|git@", src):
                continue                   # ADD <url> is fetched, not read from the context
            if src.startswith("/") or ".." in src.split("/"):
                add("E", f"Dockerfile:{ln} copies `{src}`, which is outside the build context. "
                         f"harbor builds with the context set to `environment/`, and COPY cannot "
                         f"escape it - an absolute or `../` source fails with `not found in build "
                         f"context` no matter what exists on the authoring machine.",
                    fail=True, blocking=True, fid="env_copy_escapes_context")
                hit = True
                continue
            base = os.path.join(tasks, "environment")
            if not glob.glob(os.path.join(base, src)) and not os.path.exists(
                    os.path.join(base, src)):
                add("E", f"Dockerfile:{ln} copies `{src}` -> `{dest}`, but no such path exists under "
                         f"`environment/` (the build context). The build fails with `not found in "
                         f"build context` and no layer is produced.",
                    fail=True, blocking=True, fid="env_copy_source_missing")
                hit = True

    # REMOVAL IS ONLY HALF THE QUESTION. A binary that was never there fails identically: on
    # `node:18-slim`, `python:3.12-slim` or a distroless base, `curl` simply does not exist, nothing
    # in the Dockerfile removes it, and the bootstrap still dies with the same 127. So the fetcher
    # is checked for PRESENCE, not just for survival. Scoped to bases whose minimality is knowable
    # from the tag - on a full base the check would be guessing at the image's contents, and a
    # confident wrong FAIL is worse than the CANDIDATE it would replace.
    _MINIMAL = re.compile(r"(?:-slim|-alpine|alpine:|distroless|:minimal|busybox|scratch|"
                          r"-slim-|wolfi|chainguard)", re.I)
    installs_fetcher = re.search(
        r"\b(?:apt-get|apt|apk|yum|dnf|microdnf)\s+(?:add|install)\b[^&|;]*\b(?:curl|wget)\b",
        joined_all)
    if not installs_fetcher and not any(b in ("curl", "wget")
                                        for _, t in logical for b, _, _ in _removed_bins(t)):
        minimal = _MINIMAL.search(base)
        add("E", f"no `curl`/`wget` is installed anywhere in the Dockerfile"
                 + (f", and the base `{base[5:].strip()[:40]}` is a minimal image that does not "
                    f"ship one. harbor installs the agent CLI with `curl -fsSL "
                    f"https://downloads.claude.ai/... | bash` on non-apk bases, so the trial dies "
                    f"at startup with the same 'exit 127: curl: command not found' as an image "
                    f"that deleted it - REMOVAL IS NOT THE ONLY WAY TO BE MISSING. Add curl to the "
                    f"install list." if minimal else
                    f". Confirm the base `{base[5:].strip()[:40]}` ships one: harbor installs the "
                    f"agent CLI over `curl -fsSL https://downloads.claude.ai/... | bash` on "
                    f"non-apk bases, and a base without it fails the trial at startup. Full "
                    f"debian/ubuntu/node bases normally do, which is why this is not a FAIL."),
            fail=bool(minimal) and not apk_base, blocking=bool(minimal) and not apk_base or None,
            fid="env_no_fetcher")
        hit = True

    if apk_base and not re.search(r"\bapk\s+add\b[^&|;]*\bbash\b", joined_all):
        add("E", "apk-based image with no `apk add bash`. harbor spawns every phase as "
                 "`bash -c 'set -euo pipefail; ...'` and the CLI bootstrap pipes into `bash -s --`, "
                 "neither of which busybox ash provides. Add bash to the install list.",
            fail=True, blocking=True, fid="env_no_bash")
        hit = True

    if not hit:
        add("E", f"Dockerfile leaves the harness intact: nothing removes, masks or blackholes the "
                 f"curl/npm install path for the agent CLI, the git the verifier diffs with, or "
                 f"bash ({'apk' if apk_base else 'glibc'} base assumed from `{base[:48]}`). "
                 f"Anti-cheat belongs in `[agent] network_mode`, which is "
                 f"{'set' if sealed else 'NOT set - see group N'}.", ok=True,
            fid="env_harness_intact")


# ------------------- v2 Hardening - can a NON-ROOT process run in this image? (group P)
#
# THE FAILURE THIS EXISTS FOR:
#
#   RUN mkdir -p /logs "$PGDATA" ... \
#    && su postgres -c "$(ls -d /usr/lib/postgresql/*/bin)/initdb -D $PGDATA -A trust ..."
#   /bin/sh: error while loading shared libraries: libc.so.6:
#            cannot open shared object file: Permission denied
#   su: failed to execute /bin/bash: Permission denied
#
# THE MEASURED ENVIRONMENT FACT. The sandbox's docker daemon hands the build a rootfs whose ROOT
# DIRECTORY is 0750 - `drwxr-x---  /`. Nothing running as a non-root uid can traverse `/`, so the
# dynamic loader cannot open /lib/.../libc.so.6 and the process dies before main(). It is not a PATH
# problem, not a missing package, and not a corrupt base image - which is exactly why it costs a
# debugging session rather than a minute: the message names libc, and libc is fine.
#
# WHY THIS IS ITS OWN GROUP AND NOT PART OF E. Group E asks whether the image still contains the
# binaries HARBOR invokes. This asks whether a non-root process can execute at all, which is a
# property of the daemon's rootfs rather than of the Dockerfile's package list. There is also a
# mechanical reason: check_E ends with `if not hit: add(... env_harness_intact, ok=True)`, so a
# privilege finding routed through that function would silence a TRUE statement about the harness
# binaries on every task that uses `su`. A new claim must not cost an existing one.
#
# WHAT THE ORACLE DOES AND DOES NOT CATCH - and why this still earns a check. Group E's defects are
# invisible to the gate (oracle and nop install no agent, so they score 1.0/0.0 on an image no agent
# can run in). This one is NOT invisible: the build fails, so `oracle` fails too. What the oracle
# does not deliver is the DIAGNOSIS. `cannot open shared object file: Permission denied` on libc
# reads as a broken base image or a bad apt layer, and the site it dies at is an ordinary-looking
# `initdb` line, so the reading that fits the evidence is the wrong one. That is the difference from
# the findings this group deliberately does NOT carry (a swallowed `npm install` is caught by a 0.0
# oracle and needs no explaining). The check converts an unbounded hunt into a named, one-line
# repair, and it costs a text scan against a build that can take the better part of an hour.
#
# THE REPAIR IS TWO-PART, AND THE SECOND HALF IS THE ONE THAT GETS FORGOTTEN.
#   1. BUILD TIME: `chmod a+rx /` must run in the SAME `RUN` as the privilege drop. A mode change on
#      `/` is not captured in a layer diff, so it reverts at the next instruction and never ships in
#      the image. One RUN doing both is the only shape that works.
#   2. VERIFY TIME: the shipped image still has `/` at 0750, so a starter script or entrypoint that
#      drops privileges must repeat `chmod a+rx /` (as root) before it does. Fixing only the build
#      moves the same failure from `docker build` to the first `test.sh`.
# `chmod a+rx /` is a no-op on a normal daemon, so it is safe to apply unconditionally, and it does
# not change what the tests measure: the same uid runs the same command.
#
# WHY `USER <non-root>` IS REPORTED BUT NEVER AUTO-REPAIRED. Once PID 1 is non-root there is no root
# process left to fix `/` with, so no in-image repair exists - and dropping the directive changes
# which uid the tests run as, which is a task decision rather than a mechanical one.
_PRIV_TOOLS = (
    # `(?=\s)` is what keeps `su` from matching `sudo`, `su-exec` or `su_helper`, and the leading
    # class is what keeps it from matching the tail of a path like `/opt/bin/issu`. Same lesson as
    # _BIN_TOKEN's prefix/suffix guards in group E: an unanchored tool name FAILs correct bundles.
    #
    # THE QUOTE CHARACTERS IN THAT CLASS ARE LOAD-BEARING. A generated starter script is written as
    # `printf "%s\n" "su postgres -c ..."`, so the drop's first character is preceded by the opening
    # `"` of a printf argument and by nothing else. Omitting `"'` from the class silently skipped
    # every verify-time site while still finding the build-time ones - the exact half of this defect
    # that no build failure can reveal.
    ("su",       re.compile(r"""(?:^|[\s;&|(`"'])su(?=\s)""")),
    ("sudo",     re.compile(r"""(?:^|[\s;&|(`"'])sudo(?=\s)""")),
    ("gosu",     re.compile(r"""(?:^|[\s;&|(`"'])gosu(?=\s)""")),
    ("runuser",  re.compile(r"""(?:^|[\s;&|(`"'])runuser(?=\s)""")),
    ("setpriv",  re.compile(r"""(?:^|[\s;&|(`"'])setpriv(?=\s)""")),
    ("su-exec",  re.compile(r"""(?:^|[\s;&|(`"'])su-exec(?=\s)""")),
    ("chroot",   re.compile(r"""(?:^|[\s;&|(`"'])chroot(?=\s+--userspec)""")),
)
# Services that refuse to run as root, so "just drop the privilege drop" is NOT among the repairs.
# The distinction is load-bearing: for PostgreSQL the `su` has to stay and only the chmod can fix
# it, while MariaDB accepts `--user=root` and can lose the drop entirely.
_ROOT_REFUSERS = {
    "initdb":  ("PostgreSQL", False), "pg_ctl": ("PostgreSQL", False),
    "pg_isready": ("PostgreSQL", False), "postgres": ("PostgreSQL", False),
    "pg_createcluster": ("PostgreSQL", False),
    "mysqld": ("MySQL/MariaDB", True), "mysqld_safe": ("MySQL/MariaDB", True),
    "mariadb-install-db": ("MySQL/MariaDB", True), "mysql_install_db": ("MySQL/MariaDB", True),
    "elasticsearch": ("Elasticsearch", False),
}
_ROOT_UIDS = {"root", "0", "#0"}
# The REPAIR, so the check can grade its absence rather than the mere presence of a `su`. A task
# whose every drop is already preceded by `chmod a+rx /` in the same layer is CORRECT here, and
# saying otherwise would leave a repaired bundle permanently red - which under this skill's own
# contract ("the price of that permission is proof") means the fix can never be shown to have worked.
# The target must be `/` exactly: `chmod 777 /logs`, which this Dockerfile also does, is not it.
_CHMOD_ROOT = re.compile(r"""chmod\s+(?P<mode>[0-7]{3,4}|[ugoa]*[+=][rwxXst]+)\s+/(?=[\s"';\\]|$)""")


def _grants_traverse(mode):
    """Does this chmod mode let a NON-root uid traverse the directory? (the `o+x` bit, nothing more)"""
    if re.fullmatch(r"[0-7]{3,4}", mode):
        return bool(int(mode[-1]) & 1)
    m = re.match(r"([ugoa]*)([+=])([rwxXst]+)", mode)
    if not m:
        return False
    who, op, perms = m.groups()
    return ("x" in perms or "X" in perms) and (who == "" or "a" in who or "o" in who)


def _sh_tokens(s):
    """Whitespace-split `s`, keeping a quoted run as ONE token (quotes and escapes stripped).

    `str.split()` is wrong here and it fails SILENTLY. On
    `su -c "psql -h 127.0.0.1 -U postgres" postgres` a parser that splits naively and skips `-c`
    plus one token lands INSIDE the command, walks past its `-h`, and reports `127.0.0.1` as the
    target uid. Grouping quoted runs is what makes the uid extraction below trustworthy.
    """
    out, buf, q, esc = [], "", None, False
    for ch in s:
        if esc:
            buf += ch
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if q:
            if ch == q:
                q = None
            else:
                buf += ch
            continue
        if ch in "\"'":
            q = ch
            continue
        if ch.isspace():
            if buf:
                out.append(buf)
                buf = ""
            continue
        buf += ch
    if buf:
        out.append(buf)
    return out


def _priv_target(tool, rest):
    """The uid `tool rest...` switches to, or None for root / undeterminable.

    None means "not a privilege DROP" and is the quiet case on purpose: a bare `sudo make install`
    or `su - root` stays root, and reporting it would be a false FAIL on a line that works.
    """
    toks = _sh_tokens(rest)
    if tool == "setpriv":
        m = re.search(r"--reuid[=\s]+(\S+)", rest)
        return m.group(1) if m else None
    if tool == "chroot":
        m = re.search(r"--userspec[=\s]+([^:\s]+)", rest)
        return m.group(1) if m else None
    if tool in ("sudo", "runuser"):
        for i, t in enumerate(toks):
            if t in ("-u", "--user") and i + 1 < len(toks):
                return toks[i + 1]
        if tool == "sudo":
            return None                       # no -u: sudo defaults to root, which is not a drop
    i = 0
    while i < len(toks):                      # first argument that is not an option or its value
        t = toks[i]
        if t in ("-c", "--command", "-s", "--shell", "-g", "--group", "--groups"):
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        return t
    return None


def _in_quotes(line, pos):
    """Is offset `pos` inside a quoted string on this physical line?

    This is the build-vs-verify discriminator. A `su` written as a quoted `printf` ARGUMENT is not
    executed by the RUN - it is text being written into a script that runs later, at verify time -
    while a `su` sitting in the command chain runs now. The two need different repairs, so telling
    them apart is not cosmetic.
    """
    q, esc = None, False
    for ch in line[:pos]:
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
    return q is not None


def _instruction_spans(txt):
    """[(start, end, joined)] - `_logical_lines` plus the END lineno.

    check_P needs both halves: the JOINED text to see whether the instruction redirects into a file,
    and the PHYSICAL line of each drop to report a site a reviewer can open. `_logical_lines` throws
    the second away - every drop in the target Dockerfile would report as one of two line numbers -
    and it is used by group E and by fix.py, so it is left alone rather than widened.
    """
    out, buf, start = [], [], None
    for i, raw in enumerate(txt.splitlines(), 1):
        line = raw.rstrip()
        if line.lstrip().startswith("#") and not buf:
            continue
        if start is None:
            start = i
        if line.endswith("\\"):
            buf.append(line[:-1])
            continue
        buf.append(line)
        joined = " ".join(x.strip() for x in buf).strip()
        if joined:
            out.append((start, i, joined))
        buf, start = [], None
    if buf:
        out.append((start or 1, len(txt.splitlines()), " ".join(x.strip() for x in buf).strip()))
    return out


_WRITES_FILE = re.compile(r">>?\s*(\S+)|tee\s+(?:-a\s+)?(\S+)")


def _written_script(joined, body=""):
    """The path this instruction writes, when what it writes looks like a shell script.

    The script test is what keeps this rule from repeating the mistake group E's heredoc filter
    exists to avoid. A `su` inside a PYTHON body is data and must not be reported; a `su` inside a
    body that carries a shebang, lands in a bin directory, or is `chmod +x`-ed is a command that
    will run at verify time.
    """
    # EVERY redirect is considered, not just the first. A generated script routinely contains
    # `>&2` and `2>/dev/null` in its own body, and those appear in the joined instruction BEFORE the
    # `> /usr/local/bin/...` that is the actual destination - so `search()` plus a reject on the
    # first hit returned None and classified every line of the script as a build-time command.
    dest = None
    for m in _WRITES_FILE.finditer(joined):
        cand = (m.group(1) or m.group(2) or "").strip("'\"")
        if not cand or cand.startswith("&") or cand.startswith("/dev/") or cand.isdigit():
            continue
        dest = cand
        break
    if not dest:
        return None
    blob = joined + "\n" + body
    if (re.search(r"#!\s*/\S*(?:sh|bash|ash|zsh)\b", blob)
            or re.match(rf"{_BIN_DIR}", dest)
            or re.search(rf"chmod\s+\S*x\S*\s+{re.escape(dest)}", joined)):
        return dest
    return None


def _privilege_sites(txt):
    """[dict] one per privilege drop in a Dockerfile, keyed to its PHYSICAL line.

        line     1-based physical lineno
        tool     su | sudo | gosu | runuser | setpriv | su-exec | chroot
        user     the uid being switched to (never root - those are not drops)
        phase    "build"   the RUN executes it, so `docker build` dies
                 "verify"  it is text being written into a script that runs at verify time
        dest     for phase=="verify", the script being written
        guarded  True when `/` is already made traversable BEFORE this drop, in the same layer (or
                 the same script) - i.e. the site is already repaired and is not a finding
        frag     the physical line, trimmed, for the evidence list
    """
    lines = txt.splitlines()
    docs = heredocs(txt)
    spans = _instruction_spans(txt)
    hd_of = {}
    for hd in docs:
        for n in range(hd["line"] + 1, (hd["end"] or len(lines) + 1)):
            hd_of[n] = hd
    in_span = {}
    for start, end, joined in spans:
        for n in range(start, end + 1):
            in_span[n] = joined

    out = []
    for n, raw in enumerate(lines, 1):
        if n not in in_span and n not in hd_of:
            continue                          # a comment or a blank line between instructions
        if raw.lstrip().startswith("#"):
            continue                          # a comment, including one inside a continuation
        for tool, rx in _PRIV_TOOLS:
            for m in rx.finditer(raw):
                user = _priv_target(tool, raw[m.end():])
                if not user or user.lstrip("#") in _ROOT_UIDS:
                    continue                  # stays root: not a privilege drop, not a finding
                quoted = _in_quotes(raw, m.end())
                hd = hd_of.get(n)
                if hd is not None:
                    dest = _written_script(hd["head"], "\n".join(hd["body"]))
                    if not dest:
                        continue              # a heredoc body that is not a script: data, not code
                    phase = "verify"
                    scope = hd["line"] + 1
                else:
                    joined = in_span.get(n, raw)
                    scope = next((st for st, en, _j in spans if st <= n <= en), n)
                    kw = re.match(r"(\w+)", joined)
                    kw = kw.group(1).upper() if kw else ""
                    if kw in ("CMD", "ENTRYPOINT"):
                        # Not a build-time command at all: it runs when the container starts, so it
                        # fails at verify time exactly like a generated starter script. Classifying
                        # it as `build` would send the reviewer to a RUN that does not exist and
                        # promise a same-layer chmod that cannot be written here.
                        phase, dest = "verify", f"the {kw}"
                    else:
                        dest = _written_script(joined)
                        phase = "verify" if (dest and _in_quotes(raw, m.end())) else "build"
                # IS `/` ALREADY MADE TRAVERSABLE BEFORE THIS DROP? Only the same layer counts for a
                # build site (`scope` is the enclosing instruction, never earlier), and only the
                # script's own text counts for a verify site (`scope` is the heredoc body or the
                # printf arg list). The quote-ness must MATCH the drop's own: a bare `chmod a+rx /`
                # sitting in the RUN that WRITES a script repairs the build layer, not the script
                # that runs later, so counting it would clear a finding the image still has.
                guarded = False
                for i in range(scope, n + 1):
                    seg = lines[i - 1][:m.start()] if i == n else lines[i - 1]
                    for cm in _CHMOD_ROOT.finditer(seg):
                        if _in_quotes(lines[i - 1], cm.start()) != quoted:
                            continue
                        if _grants_traverse(cm.group("mode")):
                            guarded = True
                            break
                    if guarded:
                        break
                # `col` is the offset of the TOOL NAME, which the fixer inserts in front of. Deriving
                # it as `m.end() - 2` worked only for `su`: on `gosu`/`runuser`/`setpriv` it landed
                # mid-token and the repair would have been spliced into the middle of the command.
                out.append({"line": n, "col": m.end() - len(tool), "tool": tool, "user": user,
                            "phase": phase, "guarded": guarded,
                            "dest": dest if phase == "verify" else None,
                            "frag": raw.strip().rstrip("\\").strip()})

    # THE JSON EXEC FORM, which the line scan above cannot see: in `RUN ["su", "pg", "-c", "initdb"]`
    # the tool name is followed by `"` rather than by whitespace, so the `(?=\s)` guard that keeps
    # `su` from matching `sudo` also skips this shape entirely. A silent miss is worse than a decline
    # - the fixer refuses the exec form anyway (no `&&` link can be prepended to it), so the point of
    # detecting it is to say so instead of reporting a clean bill of health.
    for st, en, joined in spans:
        m = re.match(r"(RUN|CMD|ENTRYPOINT)\s*(\[.*\])\s*$", joined, re.I | re.S)
        if not m:
            continue
        try:
            argv = json.loads(m.group(2))
        except Exception:
            continue
        if not argv or not isinstance(argv, list):
            continue
        tool = os.path.basename(str(argv[0]))
        if tool not in {t for t, _rx in _PRIV_TOOLS}:
            continue
        user = _priv_target(tool, " ".join(str(a) for a in argv[1:]))
        if not user or user.lstrip("#") in _ROOT_UIDS:
            continue
        kw = m.group(1).upper()
        out.append({"line": st, "col": 0, "tool": tool, "user": user,
                    "phase": "build" if kw == "RUN" else "verify", "guarded": False,
                    "dest": None if kw == "RUN" else f"the {kw}",
                    "frag": joined.strip()[:120]})
    return out


def _refuser(sites, txt):
    """(service, root_ok) for a service in these fragments that refuses to run as root."""
    blob = "\n".join(s["frag"] for s in sites) or txt
    for exe, (svc, root_ok) in _ROOT_REFUSERS.items():
        if re.search(rf"(?:^|[\s/;&|(`\"']){re.escape(exe)}(?![\w./-])", blob):
            return svc, root_ok
    return None, None


_ENV_FACT = ("The sandbox's docker daemon hands the build a rootfs whose ROOT DIRECTORY is 0750 "
             "(`drwxr-x---  /`), so NO non-root uid can traverse `/`: the dynamic loader cannot "
             "open libc and the process dies before main() with `error while loading shared "
             "libraries: libc.so.6: cannot open shared object file: Permission denied`, or `su: "
             "failed to execute /bin/bash: Permission denied`. The message names libc, and libc is "
             "fine - which is why this reads as a corrupt base image and costs hours. ")


def check_P(tasks, md=None):
    """v2 Hardening (BLOCKING) - can a non-root process execute in this image at all?"""
    if not tasks:
        return
    dpath = os.path.join(tasks, "environment", "Dockerfile")
    txt = read(dpath)
    if txt is None:
        return                                # missing Dockerfile is already group B's finding
    all_sites = _privilege_sites(txt)
    # A GUARDED SITE IS NOT A DEFECT. This check grades the ABSENCE OF THE REPAIR, not the presence
    # of a `su`: PostgreSQL cannot run as root, so the drops are permanent and correct, and a check
    # that FAILs them forever would make its own auto-fix unprovable.
    sites = [s for s in all_sites if not s["guarded"]]
    build = [s for s in sites if s["phase"] == "build"]
    verify = [s for s in sites if s["phase"] == "verify"]
    users = sorted({s["user"] for s in sites})

    def ev(rows):
        out = [f"Dockerfile:{s['line']}  {s['tool']} -> {s['user']}  {s['frag'][:96]}"
               for s in rows[:8]]
        if len(rows) > 8:
            out.append(f"... and {len(rows) - 8} more")
        return out

    if build:
        svc, root_ok = _refuser(build, txt)
        where = ", ".join("Dockerfile:%d" % s["line"] for s in build[:6])
        add("P", f"Dockerfile drops privileges at BUILD time on {len(build)} line(s) "
                 f"({where}{', ...' if len(build) > 6 else ''}), "
                 f"switching to `{'`, `'.join(users)}`. "
                 + _ENV_FACT
                 + "REPAIR: `chmod a+rx /` must run in the SAME `RUN` as the drop - a mode change "
                   "on `/` is not captured in a layer diff, so it reverts at the next instruction "
                   "and never ships in the image."
                 + (f" Dropping the `{build[0]['tool']}` instead is NOT available here: {svc} "
                    f"refuses to run as root (it aborts on `geteuid() == 0`, with no override), so "
                    f"the drop has to stay and the chmod is the only repair."
                    if svc and not root_ok else
                    f" Alternatively drop the privilege switch entirely: {svc} accepts "
                    f"`--user=root`." if svc else ""),
            fail=True, blocking=True, fid="env_nonroot_build", evidence=ev(build))

    if verify:
        dests = sorted({s["dest"] for s in verify if s["dest"]})
        add("P", f"Dockerfile writes a script that drops privileges at VERIFY time "
                 f"({', '.join(dests) or 'a generated script'}, {len(verify)} line(s)). These lines "
                 f"are quoted TEXT during the build, so they do not fail it - they fail when "
                 f"`test.sh` runs the script. " + _ENV_FACT
                 + "The shipped image still has `/` at 0750, so the generated script must itself "
                   "`chmod a+rx /` (as root) BEFORE its first privilege drop. Repairing only the "
                   "build-time sites moves the identical failure from `docker build` to the first "
                   "verify run, where it looks like a broken test rather than a broken image.",
            fail=True, blocking=True, fid="env_nonroot_verify", evidence=ev(verify))

    # `USER root` is not a finding AND must not suppress the OK line below: an image that says so
    # explicitly is provably safe here, and reporting nothing at all would read as "we did not look".
    user_dirs = []
    for start, _end, joined in _instruction_spans(txt):
        m = re.match(r"USER\s+(\S+)", joined, re.I)
        if m and m.group(1).strip("\"'").split(":")[0].lstrip("#") not in _ROOT_UIDS:
            user_dirs.append((start, m.group(1)))

    for start, uid in user_dirs:
        add("P", f"Dockerfile:{start} declares `USER {uid}`, and unlike a `su` fragment this "
                 f"CANNOT be repaired inside the image. " + _ENV_FACT
                 + "Whatever `chmod a+rx /` preceded the directive has already reverted (a mode "
                   "change on `/` does not survive into the next layer), and after the directive "
                   "there is no root process left to re-apply it - PID 1 is already non-root. The "
                   "repair is to drop the directive and run as root, which changes which uid the "
                   "tests execute as, so it is a task decision rather than a mechanical edit.",
            fail=True, blocking=True, fid="env_user_directive")

    if not sites and not user_dirs:
        if all_sites:
            nb = len([s for s in all_sites if s["phase"] == "build"])
            nv = len(all_sites) - nb
            add("P", f"Dockerfile drops privileges to "
                     f"`{'`, `'.join(sorted({s['user'] for s in all_sites}))}` on "
                     f"{len(all_sites)} line(s), and every one of them is already REPAIRED: `/` is "
                     f"made traversable in the same `RUN` for each of the {nb} build-time site(s), "
                     f"and inside the generated script itself for each of the {nv} verify-time "
                     f"one(s). That is the correct shape - the drop is required (PostgreSQL and "
                     f"friends refuse to run as root), so the chmod, not the drop, is what has to "
                     f"be there.", ok=True, fid="env_nonroot_guarded")
        else:
            add("P", "Dockerfile runs entirely as root: no `su`/`sudo`/`gosu`/`runuser`/`setpriv`/"
                     "`su-exec` privilege drop and no `USER` directive, so the 0750-rootfs failure "
                     "class cannot arise here.", ok=True, fid="env_nonroot_none")


def check_R(tasks, md, conf):
    """v3 - Rubrics: IF a rubrics.json ships, it parses and is well-formed (light structural check).

    The FULL audit (schema value, task-id consistency across the bundle, and the six
    'Rules for rubrics') lives in qc_rubrics.py; the SHAPE decision - whether this task should
    carry a rubric at all - lives in qc_rubric_format.py. Here we only confirm that a file which
    IS present parses and has a non-empty `criteria` list of {id, criterion}."""
    if not tasks:
        return
    rp = os.path.join(tasks, "tests/rubrics.json")
    if not os.path.exists(rp):
        # Absent is legal (Mode B: no rubric layer). Saying so out loud matters - this used to be
        # a hard FAIL, and silence would read as "we did not look".
        add("R", "no tests/rubrics.json - legal (Mode B, no rubric layer). Whether this task "
                 "SHOULD carry one is qc_rubric_format.py's call", ok=True)
        return
    if os.path.getsize(rp) == 0:
        add("R", "tests/rubrics.json is EMPTY", fail=True, fid="rubrics_missing")
        return
    data, err = load_json(rp)
    if err:
        add("R", f"tests/rubrics.json does not parse as JSON: {err}", fail=True,
            fid="rubrics_parse")
        return
    crit = data.get("criteria")
    if not isinstance(crit, list) or not crit:
        add("R", "rubrics.json `criteria` is missing or not a non-empty list", fail=True)
    else:
        for i, c in enumerate(crit):
            if not isinstance(c, dict) or not str(c.get("id", "")).strip() \
                    or not str(c.get("criterion", "")).strip():
                add("R", f"rubrics.json criteria[{i}] missing a non-empty id/criterion", fail=True)
    # task-id disagreement is a quick, high-value cross-check (full version in check_rubrics.py)
    rt, tt = data.get("task"), md.get("task_id")
    ct = (conf or {}).get("task_id")
    distinct = {x for x in (rt, tt, ct) if x}
    if len(distinct) > 1:
        add("R", f"task id disagrees: rubrics.json={rt!r} task.toml={tt!r} config.json={ct!r}",
            fail=True, fid="rubric_task_id")
    if not any(x for x in findings["R"] if x.startswith("[FAIL]")):
        add("R", "rubrics.json present, parses, criteria well-formed, task id consistent "
                 "(run check_rubrics.py for the full rule-by-rule audit + manual ACCURATE check)",
            ok=True)


# ------------------------------------------------- v2 #9  Tests - Implementation Overfit
# THE QUESTION: would a DIFFERENT but valid fix to what instruction.md asks for also pass these
# f2p tests? A green oracle plus a nop where every f2p fails only proves the tests DISCRIMINATE
# (they fail with no fix, pass
# with the golden one). A test can discriminate perfectly and still accept nothing but the golden
# implementation - that is exactly the overfit case, and no reward number can reveal it.
#
# This is decidable enough to be worth doing statically, at tier `bundle`, before any run:
# assertion FORM is visible in the test source. It is never a hard [FAIL], for one reason that
# matters - the checks cannot see the image. A term the test asserts on may be absent from
# instruction.md and still be perfectly fair because the before/after poster shows it. So a
# finding here either says "check the image" or gives a pinpointed structural reason.

# Standard vocabulary that carries no information about WHOSE implementation is being tested.
# Without this, a CSS-value fix (much of MM SWE) trips every heuristic: a fix whose whole diff is
# `content: '""'` would make the word `content` look implementation-specific, when any test of
# that bug must mention it.
_STD_VOCAB = {
    # CSS properties / values commonly touched by visual fixes
    "content", "color", "background", "background-color", "border", "border-bottom", "display",
    "position", "width", "height", "margin", "padding", "opacity", "visibility", "transform",
    "forced-color-adjust", "forced-colors", "active", "none", "block", "inline", "absolute",
    "relative", "before", "after", "hover", "focus", "disabled", "transition", "outline",
    "box-shadow", "font-size", "line-height", "text-decoration", "z-index", "overflow",
    # test / language vocabulary
    "expect", "assert", "describe", "const", "await", "async", "return", "function", "import",
    "from", "true", "false", "null", "undefined", "this", "style", "document", "window", "class",
    "value", "type", "name", "test", "props", "children", "default", "true", "string",
}
# LANGUAGE KEYWORDS ARE NOT SYMBOLS ANY FIX INTRODUCES. _STD_VOCAB above grew out of JS/CSS tasks
# and covers their vocabulary; a C/C++/Java/Go patch's keywords fell straight through it. On
# wxWidgets-25959 the golden fix adds a `for` loop, so `for` came out as a symbol the fix
# introduced and QC reported the test "asserts on ['for']" - the loop keyword read as the thing
# the test was pinned to. Every entry here is a reserved word in some language this corpus uses,
# so no fix can be the thing that introduced it. Kept separate from _STD_VOCAB so the two stay
# individually reviewable: that set is a judgement call about common vocabulary, this one is not.
_KEYWORDS = {
    # C / C++
    "alignas", "alignof", "and", "asm", "auto", "bool", "break", "case", "catch", "char",
    "constexpr", "const_cast", "continue", "decltype", "delete", "do", "double", "dynamic_cast",
    "else", "enum", "explicit", "export", "extern", "float", "for", "friend", "goto", "if",
    "inline", "int", "long", "mutable", "namespace", "new", "noexcept", "not", "nullptr",
    "operator", "or", "private", "protected", "public", "register", "reinterpret_cast",
    "short", "signed", "sizeof", "static", "static_assert", "static_cast", "struct", "switch",
    "template", "throw", "try", "typedef", "typeid", "typename", "union", "unsigned", "using",
    "virtual", "void", "volatile", "while", "xor", "size_t", "ssize_t", "uint", "std", "nan",
    # Java / C# / Go / Rust / Swift additions not already above
    "abstract", "boolean", "byte", "chan", "defer", "final", "finally", "func", "impl",
    "implements", "instanceof", "interface", "internal", "let", "match", "mod", "package",
    "print", "println", "pub", "range", "self", "super", "synchronized", "throws", "trait",
    "transient", "var", "where", "yield",
    # Python / JS keywords not already in _STD_VOCAB
    "def", "del", "elif", "except", "global", "lambda", "nonlocal", "pass", "raise", "with",
    "typeof", "extends", "debugger",
}
_SNAPSHOT = re.compile(r"toMatchSnapshot|toMatchInlineSnapshot|__snapshots__", re.I)
_COLOR_LIT = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\s*\(", re.I)
_NAMED_COLOR = {"red", "green", "blue", "black", "white", "yellow", "orange", "purple",
                "gray", "grey", "pink", "brown", "cyan", "magenta"}
# a strict-equality assertion against a string literal
_EQ_ASSERT = re.compile(r"(?:\.to\.equal|\.to\.eql|\.toBe|\.toEqual|===)\s*\(?\s*['\"]([^'\"]{1,40})['\"]")
# an exact class/id selector, with no substring or pattern matching
_EXACT_SEL = re.compile(r"""querySelector(?:All)?\(\s*['"][.#][A-Za-z][\w-]*['"]|\[class=['"]""")
# markers that the author deliberately allowed alternatives - these EARN the benefit of the doubt
_AGNOSTIC = re.compile(r"""\[class\*=|\[class\^=|getComputedStyle|\|\||\.test\(|\.match\(|"""
                       r"""new RegExp|/\^|candidates?|either|any of|does not assume|not hinge|"""
                       r"""or\s+`|satisfies it""", re.I)


def _introduced_symbols(patch, base_text=""):
    """Tokens the golden patch ADDS that the repository did not already have.

    THE SECOND ARGUMENT IS THE WHOLE POINT. This used to be `added - context`, where context meant
    the patch's OWN context lines - and a diff shows three lines of context, not a repository. A
    function the golden merely EDITS has its name on the added side and, if the declaration falls
    outside the visible hunk, nowhere in the context: it came out "introduced". On the reference
    task that mislabelled `computeCalibration` (declared at src/review/ops.ts:248 since long before
    this bug) and every rule gated on this set then reported the same false finding - four of them
    on one task, plus `map`, `let` and other passers-by.
    #
    Absent from the files I happened to look at is not absent from the repo. So the caller fetches
    the edited files AT BASE and passes them here, and anything declared there is subtracted. With
    no base text the old behaviour returns, which is why callers must say, in the finding, whether
    the claim was verified."""
    if not patch:
        return set()
    # STRIP THE PATCH'S OWN COMMENTS BEFORE TOKENISING. This used to read raw diff lines, so every
    # English word in a comment the golden fix added became a "symbol the golden introduces":
    # on the reference task that put July, Tuesday, Hovering, expensive, constructing and far into
    # the set. Most stay harmless because the test side is read through _code_only and prose does
    # not survive there too - but they are one coincidence away from a finding, and they make the
    # set impossible to read when debugging one.
    #
    # Joined and stripped as a BLOCK, not per line: a /* ... */ spanning five added lines is only
    # recognisable once the diff markers are off and the lines are back together.
    added_src, context_src = [], []
    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added_src.append(line[1:])
        elif line.startswith("-") or line.startswith(" "):
            context_src.append(line[1:])
    # The trailing `-` in the character class is for CSS, where `border-bottom` is one identifier.
    # In every brace language it is an operator, so `pressedButton->curState` tokenised to
    # `pressedButton-` and `a - b` could glue into `a-`: a symbol no grep in the repo can find, and
    # one that never matches a test body either, so it only ever inflated the count a finding
    # quotes. Trailing hyphens are stripped after the split - an interior one (a real CSS property)
    # still survives.
    tok = lambda text: {t.rstrip("-") for t in re.findall(r"[A-Za-z_][A-Za-z0-9_-]{2,}", text)}
    added = tok(_decomment("\n".join(added_src)))
    # Context is deliberately NOT stripped: anything it mentions is subtracted from `added`, so
    # reading it generously can only shrink the result, never invent an entry.
    context = tok("\n".join(context_src))
    out = {t for t in added - context
           if t.lower() not in _STD_VOCAB and t.lower() not in _KEYWORDS and t not in _PLATFORM}
    if base_text:
        out = {t for t in out
               if not re.search(r"\b%s\b" % re.escape(t), base_text)}
    return out


def _base_text_for_patch(tasks, md, patch):
    """The edited files as they stand at base_commit, concatenated. '' if they cannot be read.

    Same fetch the identifier check uses, so a task whose repo is unreachable degrades to the old
    unverified behaviour rather than failing.
    """
    repo = ((md or {}).get("repo_url") or "").strip()
    sha = ((md or {}).get("base_commit") or "").strip()
    if not repo or not sha or not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        return ""
    if os.environ.get("MM_QC_NO_NETWORK"):
        return ""
    import time
    deadline = time.monotonic() + 30
    out = []
    for f in re.findall(r"(?m)^diff --git a/\S+ b/(\S+)$", patch or ""):
        url = _raw_url(repo, sha, f)
        if not url:
            continue
        if url in _UPSTREAM_CACHE:
            body = _UPSTREAM_CACHE[url]
        else:
            body, definitive = _http_get(url, deadline, [], f)
            if definitive:
                _UPSTREAM_CACHE[url] = body
        if body:
            out.append(body)
    return "\n".join(out)


# ------------------------------------------------ agnostic.txt: the classification decision tree
# agnostic.txt sorts each test into AGNOSTIC / IMPLEMENTATION-SPECIFIC / INVALID through six
# questions. The nodes below implement the ones that are visible in test source. Every one of them
# is IDENTIFICATION ONLY: it names what the test pins and which other implementation that pin
# would reject. None proposes a repair, and none is a hard [FAIL] - the axis is heuristic, and a
# false blocker here stops a sound task, which costs more than a missed candidate.
#
# Two house rules bend the tree to this benchmark:
#
#   1. PROVENANCE, NOT PRIVACY. The tree treats any private or internal reference as
#      implementation-specific. That is wrong here, because an MM SWE task edits a PRE-EXISTING
#      repo: a test may legitimately touch a private that shipped with that repo long before this
#      bug, and routing through it is how the repo's own tests are written. What no other
#      implementation is obliged to reproduce is something THE GOLDEN PATCH INVENTED. So every
#      identifier node (Q2, Q4, Q6) is gated on `_introduced_symbols(fix.patch)` rather than on
#      the shape of the name.
#
#   2. CODE POSITION. A token inside a test NAME, a string literal or a comment is prose, not an
#      assertion about anyone's implementation. On the reference bundle, matching those produced
#      two of three candidates (`behind` inside an it() string, `border` inside a comment) against
#      one real assertion, so every identifier node reads `_code_only(body)`.

_STR_LIT = re.compile(r"'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`", re.S)
_BLOCK_COM = re.compile(r"/\*.*?\*/", re.S)
_LINE_COM = re.compile(r"//[^\n]*|^[ \t]*#[^\n]*", re.M)


def _decomment(text):
    """`text` with comments blanked, string literals LEFT ALONE. Same crudeness as _code_only.

    Split out because the patch scanner needs exactly this much and no more: a class name only
    ever written inside a string literal (`className="cal-grid"`) is still a symbol the golden
    introduced and a test asserting it is still pinned, so blanking strings there would cost a
    real finding.
    """
    t = _BLOCK_COM.sub(" ", text or "")
    return _LINE_COM.sub(" ", t)


def _code_only(text):
    """`text` with comments and string literals blanked. Deliberately crude - it only has to stop
    prose from being read as an assertion, and over-blanking costs a missed candidate, never a
    false one."""
    return _STR_LIT.sub(" ", _decomment(text))


# Names the PLATFORM supplies. A golden fix that starts calling `Intl.DateTimeFormat` puts that
# token on the added side of its own patch, and nothing in the base files has to mention it - so
# it came out "introduced by the golden", and a test using `new Intl.DateTimeFormat(...)` to BUILD
# ITS EXPECTED VALUE was read as pinning the golden's implementation. It pins nothing: every
# implementation has the same built-ins, and using one as an oracle is how a locale-correct
# expectation is written in the first place.
#
# Members are listed alongside globals because they reach the token scan the same way, via
# `Intl.DateTimeFormat`. The cost of a wrong entry is a missed finding on a golden fix that
# introduces a symbol of exactly that name, so keep this to real platform vocabulary.
_PLATFORM = {
    "Intl", "Math", "JSON", "Object", "Array", "Number", "String", "Boolean", "Date", "RegExp",
    "Map", "Set", "WeakMap", "WeakSet", "Promise", "Symbol", "Proxy", "Reflect", "BigInt",
    "Error", "TypeError", "RangeError", "ArrayBuffer", "console", "globalThis", "Infinity",
    "DateTimeFormat", "NumberFormat", "RelativeTimeFormat", "PluralRules", "Collator",
    "ListFormat", "Segmenter", "toLocaleString", "toLocaleDateString", "toLocaleTimeString",
}

# A name the TEST FILE declares for itself. `_introduced_members` already makes this argument for
# attributes ("same spelling, unrelated thing"); this is the same argument for bindings, and it is
# the one that stalled a well-built task. A test that writes its own
# `function formatFullDateTime(...)` helper - one that finds the real export by PROBING what the
# module returns, never naming it - was reported as pinning `formatFullDateTime`, when a fix
# calling its export something else passes that test untouched.
#
# Imports are deliberately NOT matched here. `import { foo }` IS a pin, it is the whole point of
# the Q2B/Q2C check above, and a name cannot be both imported and locally declared in one scope.
_LOCAL_BIND = re.compile(r"\bfunction\s+([A-Za-z_]\w*)"
                         r"|\b(?:const|let|var)\s+([A-Za-z_]\w*)\s*="
                         r"|\bclass\s+([A-Za-z_]\w*)"
                         r"|\bdef\s+([A-Za-z_]\w*)\s*\(")


def _test_local_bindings(src):
    """Names the test source declares itself: helpers, locals, classes. Read from code only, so a
    name that merely appears in a comment or a string does not count as a declaration."""
    out = set()
    for groups in _LOCAL_BIND.findall(_code_only(src or "")):
        out |= {g for g in groups if g}
    return out


# An assertion is not always an `expect(`. testing-library's getBy*/findBy* THROW on miss, and a
# bare `throw new Error(...)` inside a test is the assertion. Reading only the expect-family made
# QC report "shows no assertion in the source QC can read - a test that asserts nothing passes for
# any implementation including a broken one" about a test that fails loudly for a broken one: on
# the reference task, `plots the kept-rate curve...` asserts entirely through getByText and two
# explicit throws. Over-matching here is the safe direction - it can only make QC quieter about a
# test that really does assert nothing, never louder about one that does.
#
# C++ ASSERTS THROUGH MACROS THIS DID NOT KNOW. Catch2 - how every C++ task in this corpus writes
# assertions - spells them CHECK/REQUIRE (plus the _FALSE/_THROWS/_NOTHROW/_THAT family), and none
# of those contains an expect/assert/should token. On wxWidgets-25959 the f2p test carried eight
# Catch2 assertions and this regex matched zero of them, so QC reported "shows no assertion in the
# source QC can read" about a test that aborts the process on unfixed source. Adding more CHECK
# lines could not clear it, and the only escape was to write a redundant `assert()` or `throw`
# beside the real assertion purely to be seen - a workaround that shipped in that bundle. GTest
# was assumed covered here on the grounds that EXPECT_*/ASSERT_* match through the
# expect/assert tokens. They do not - this pattern is case-sensitive - so GTest is spelled out
# below alongside Catch2.
_ASSERT_TOK = re.compile(r"\b(?:expect|assert\w*|should\w*|verify|raise|throw)\b"
                         r"|\b(?:get|find|query)(?:All)?By[A-Z]\w*\s*\("
                         r"|\bt\.(?:Fatal|Error)\w*\s*\("
                         r"|\b(?:CHECK|REQUIRE)(?:_FALSE|_THROWS(?:_AS|_WITH)?|_NOTHROW|"
                         r"_THAT)?\s*\("
                         r"|\b(?:SUCCEED|FAIL|FAIL_CHECK|FAIL_IF|STATIC_REQUIRE)\s*\("
                         # GTest. The comment above claimed EXPECT_*/ASSERT_* "already
                         # matched through the expect/assert tokens" - they do not: this
                         # pattern is case-SENSITIVE, so every GTest assertion missed and
                         # C++ GTest tasks hit the same bogus "no assertion" as Catch2 did.
                         # Spelled out in caps rather than adding re.I, which would also
                         # match a local named `check` or a call to `require()`.
                         r"|\b(?:EXPECT|ASSERT)_\w+\s*\("
                         # C# (NUnit / MSTest / xUnit) spells it `Assert.AreEqual`,
                         # `Assert.That`, `Assert.Equal` - capital A, so `assert\w*` above
                         # misses every one of them for the same case-sensitivity reason
                         # GTest did. `\w*Assert` also picks up NUnit's StringAssert /
                         # CollectionAssert, which are the same idiom under another name.
                         r"|\b\w*Assert\s*\.\s*\w+"
                         # FluentAssertions / Shouldly, the third instance of the same
                         # case-sensitivity bug: `should\w*` above is lowercase, so
                         # `x.Should().Be(1)`, `x.ShouldBe(1)` and `Should.Throw<T>(...)`
                         # all missed. The trailing `[.(]` is what keeps this an assertion
                         # rather than a property read - `if (config.ShouldRetry)` and
                         # `bool ShouldRetry { get; set; }` do not match.
                         r"|\bShould\w*\s*[.(]")
# Q3B: mocking one of these is mocking a BOUNDARY, which the tree explicitly allows.
_BOUNDARY = re.compile(r"fetch|http|axios|request|xhr|socket|\bfs\b|readFile|writeFile|"
                       r"localStorage|sessionStorage|\bDate\b|clock|timer|setTimeout|random|"
                       r"process\.env|navigator|geolocation|database|\bdb\b|client|api\b|server",
                       re.I)
_MOCK_CALL = re.compile(r"\b(?:jest\.(?:mock|spyOn)|vi\.(?:mock|spyOn)|sinon\.(?:stub|spy|mock)|"
                        r"mock\.patch|patch\.object|patch|mockImplementation|spyOn)\s*\(\s*"
                        r"([^)\n]{0,80})")
_CALLED_WITH = re.compile(r"\.(?:toHaveBeenCalledWith|toHaveBeenCalledTimes|toBeCalledWith|"
                          r"calledWith|assert_called_once_with|assert_called_with)\b")
# Q5C: the shape of the result asserted instead of the result.
_KEY_ORDER = re.compile(r"Object\.keys\s*\([^)]*\)[^\n]{0,20}?"
                        r"\.(?:toEqual|toStrictEqual|to\.eql|to\.deep)")
_INSTANCE_OF = re.compile(r"\.(?:toBeInstanceOf|to\.be\.instanceOf|toBeA)\s*\(\s*([A-Za-z_]\w*)")
# Q6C: a write to a field before the action under test.
_FIELD_WRITE = re.compile(r"\.([A-Za-z_]\w*)\s*=(?!=)")
_IMPORT_LINE = re.compile(r"^[ \t]*(?:import\b[^\n]*|from\s+\S+\s+import[^\n]*|"
                          r"(?:const|let|var)\s*\{[^}]*\}\s*=\s*require[^\n]*)$", re.M)

# Beyond the tree: a MECHANISM the test names when the requirement is an outcome. An alignment
# bug has many correct answers - flexbox, grid, absolute positioning, plain margins - so a test
# that asserts the golden's choice of mechanism rejects every other one of them. Only values that
# name a layout STRATEGY belong here; outcome values (`center`, `space-between`) do not, because
# asserting those is asserting the requirement.
_MECHANISM = {
    "flex": "flexbox", "inline-flex": "flexbox", "grid": "CSS grid",
    "inline-grid": "CSS grid", "absolute": "absolute positioning",
    "fixed": "fixed positioning", "sticky": "sticky positioning",
    "table": "table layout", "table-cell": "table layout", "flow-root": "a block formatting root",
    "contents": "display:contents",
}
# Beyond the tree: an exact MAGNITUDE. If the golden widens something by 10px and the test asserts
# 10, a fix that reaches the same visual result with 11 fails a test it satisfies.
_NUM_EQ = re.compile(r"(?:\.to\.equal|\.to\.eql|\.toBe|\.toEqual|\.toBeCloseTo|===|==)\s*\(?\s*"
                     r"(-?\d+(?:\.\d+)?)")


def _introduced_numbers(patch):
    """Numeric literals the golden patch ADDS. 0/1 are excluded: they are framework defaults and
    counts far more often than they are magnitudes chosen by this fix."""
    if not patch:
        return set()
    added, ctx = set(), set()
    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        nums = set(re.findall(r"\d+(?:\.\d+)?", line))
        if line.startswith("+"):
            added |= nums
        elif line.startswith("-") or line.startswith(" "):
            ctx |= nums
    return {n for n in added - ctx if n not in ("0", "1", "0.0", "1.0")}


def _f2p_spans(src, f2p_ids):
    """[(start, end)] of each sliced f2p body as OFFSETS into `src`. Coverage has to be decided by
    position, not by text: `expect(material.borderOnForeground, false);` occurs 42 times in the
    reference bundle, so testing whether a line's *content* appears inside some block marks all 42
    as covered the moment any one of them is."""
    spans = []
    for ident in f2p_ids:
        start = _locate(src, ident)
        if start < 0:
            continue
        rest = src[start:]
        nxt = min([m.start() for m in _BLOCK_END.finditer(rest)] or [len(rest)])
        spans.append((start, start + nxt))
    return spans


def _orphan_added_lines(tasks, src, spans):
    """{file: [added lines]} for lines test.patch ADDS that fall inside no nameable f2p block.

    These are the check's blind spot, and on the reference bundle they were most of the evidence.
    A hunk that edits one assertion deep inside an existing test carries three lines of context,
    so git's section heading resolves to the enclosing `void main() {` / `describe(...)` and the
    test's own name is never in the patch at all. `_f2p_blocks` slices by finding the declared
    identifier in the source, so it cannot reach those tests - 12 of 14 declared f2p on the
    reference bundle, carrying 40 of the 42 added assertions on the symbol the golden introduced.

    Reporting them per FILE rather than per test is the honest resolution: the pin is visible,
    the name it belongs to genuinely is not in the bundle."""
    patch = read(os.path.join(tasks, "tests/test.patch")) or ""
    out, cur, pos = {}, None, 0
    for line in patch.splitlines():
        if line.startswith("+++"):
            cur = line[4:].strip()
            if cur.startswith("b/"):
                cur = cur[2:]
        elif line.startswith("+") and cur:
            body = line[1:]
            if not body.strip():
                continue
            # Added lines enter `src` in patch order, so a forward-only cursor gives each
            # occurrence its own offset and identical lines stop aliasing onto one another.
            idx = src.find(body, pos)
            if idx < 0:
                continue
            pos = idx + len(body)
            if not any(s <= idx < e for s, e in spans):
                out.setdefault(cur, []).append(body)
    return out


# Where one test body ends and the next begins. Sliced on the next declaration rather than by
# brace matching, which is unreliable on patch text.
#
# THIS MUST COVER EVERY LANGUAGE THE BENCHMARK SHIPS, not just JS. When the terminator is absent
# the slice runs to end-of-file, and a block that swallows the rest of the source is worse than no
# block at all: every later assertion is attributed to the first test, and any check that asks
# "what falls OUTSIDE a known test" sees nothing left. That is exactly what happened on the Dart
# reference bundle, where `it(`/`describe(` never appear - one block ran 2278 chars to EOF and
# covered the other declared test whole.
_BLOCK_END = re.compile(
    r"\b(?:it|xit|test|describe|context|suite|testWidgets|testWidgetsWithLeakTracking|group)\s*\(|"
    r"^[ \t]*(?:async\s+)?def\s+test\w*\s*\(|"
    r"^[ \t]*func\s+Test\w*\s*\(|"
    r"^[ \t]*(?:@Test\b|void\s+test\w*\s*\()|"
    # C++ declarations. Without these the first f2p block ran to EOF and swallowed every
    # later test - the exact failure this regex's own comment warns about. Harmless while
    # CHECK/REQUIRE were invisible; once they matched, a swallowed neighbour's assertions
    # got credited to an inert f2p and Q1D went SILENT on it.
    # SECTION/GIVEN/WHEN/THEN are deliberately ABSENT: they nest INSIDE a TEST_CASE, so
    # terminating there would cut the body off above its own assertions.
    r"^[ \t]*(?:TEST_CASE_METHOD|TEMPLATE_TEST_CASE|TEST_CASE|SCENARIO|"
    r"METHOD_AS_TEST_CASE|TYPED_TEST_P|TYPED_TEST|TEST_F|TEST_P|TEST)\s*\(|"
    # C# (NUnit / MSTest / xUnit). Same reasoning as the C++ line above, and it became
    # reachable for the same reason: once `Assert.` was recognised, an inert f2p that
    # swallowed the next method got credited with ITS assertions and Q1D went silent.
    # Anchored on the ATTRIBUTE rather than on `public void`, which would also terminate
    # on a local function declared inside the test body.
    r"^[ \t]*\[(?:Test|Fact|Theory|TestCase|TestMethod|DataTestMethod|InlineData)\b", re.M)


def _introduced_members(patch):
    """Introduced tokens the golden patch uses as a MEMBER (`.tok`), not as a bare word.

    Provenance alone over-fires. On the ClanGen bundle the golden changed `game.clan.name` to
    `game.clan.prefix`, so `prefix` is genuinely golden-introduced - but the test that mentions it
    uses it as a local loop variable (`for prefix in OTHER_PREFIXES`) and never touches
    `.prefix` at all. Same spelling, unrelated thing. When the golden introduced a name as an
    attribute, only an attribute access in the test is evidence of the same pin."""
    if not patch:
        return set()
    out = set()
    for line in patch.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            out |= set(re.findall(r"\.([A-Za-z_]\w{2,})", line))
    return out


def _f2p_blocks(src, f2p_ids):
    """{f2p id: the test body that declares it}."""
    out = {}
    for ident in f2p_ids:
        start = _locate(src, ident)
        if start < 0:
            continue
        rest = src[start:]
        nxt = min([m.start() for m in _BLOCK_END.finditer(rest)] or [len(rest)])
        out[ident] = rest[:nxt]
    return out


def check_O(tasks, conf, md):
    """v2 #9 - are the f2p tests agnostic, or do they only accept the golden solution?"""
    if not tasks:
        return
    f2p = list((conf or {}).get("f2p") or md.get("f2p") or [])
    src = collect_test_source(tasks, conf)
    if not f2p or not src.strip():
        add("O", "no f2p identifiers or no test source - cannot assess implementation overfit",
            pending=True, fid="tests_overfit_unknown")
        return
    instr = (read(os.path.join(tasks, "instruction.md")) or "").lower()
    patch = read(os.path.join(tasks, "solution/fix.patch"))
    base_text = _base_text_for_patch(tasks, md, patch)
    verified = bool(base_text)
    introduced = _introduced_symbols(patch, base_text)
    members = _introduced_members(patch)
    introduced_nums = _introduced_numbers(patch)

    def _pins(tok, text):
        """Does `text` reference `tok` the way the GOLDEN introduced it? A name the golden added
        as an attribute has to be read as an attribute here, or it is a different thing that
        happens to share a spelling."""
        pat = rf"\.{re.escape(tok)}\b" if tok in members else rf"\b{re.escape(tok)}\b"
        return re.search(pat, text) is not None
    blocks = _f2p_blocks(src, f2p)
    flagged = False
    # What the test declares for ITSELF is not evidence of a pin on the golden's symbol. Applied
    # AFTER the import scan below and never to it: an imported golden name is a real pin and must
    # keep firing Q2B/Q2C, and a name cannot be imported and locally declared in the same scope.
    local_bindings = _test_local_bindings(src)

    # Q2B/Q2C - does the test file import a golden-introduced entity directly? Imports sit at the
    # top of the file, not inside any one f2p block, so this is asked once over the whole source.
    imported = set()
    for line in _IMPORT_LINE.findall(_code_only(src)):
        imported |= {t for t in introduced if re.search(rf"\b{re.escape(t)}\b", line)}
    if imported:
        add("O", f"the test file imports {sorted(imported)[:4]}, which the golden fix INTRODUCES "
                 f"(agnostic.txt Q2). The tests can only resolve that import against this "
                 f"implementation - a fix that solves the same requirement without declaring "
                 f"those names fails at import time, before any assertion runs.",
            pending=True, fid="tests_overfit_private_import"); flagged = True

    # From here down, "introduced" means "introduced by the golden AND not something this test
    # file defines under the same spelling".
    introduced = introduced - local_bindings

    for ident, body in blocks.items():
        # Show the LEAF: `tests.mod.Class::test_x` truncated at 44 chars is all package path and
        # no test name, which is the one part the reader needs.
        disp = _ident_leaf(ident) or ident
        short = disp[:44] + ("…" if len(disp) > 44 else "")
        lenient = _AGNOSTIC.search(body) is not None
        code = _code_only(body)
        assert_lines = [l for l in code.splitlines() if _ASSERT_TOK.search(l)]

        # --- pinpointable: the assertion FORM rejects valid alternatives, image or no image ---
        if _SNAPSHOT.search(body):
            add("O", f"f2p `{short}` asserts against a SNAPSHOT. A snapshot encodes the golden "
                     f"output exactly, so any other correct fix fails it. This is not resolvable "
                     f"by the image - assert the behaviour instead.",
                pending=True, fid=_ident_fid("tests_overfit_snapshot", ident)); flagged = True

        for m in _EQ_ASSERT.finditer(body):
            lit = m.group(1).strip()
            is_color = bool(_COLOR_LIT.search(lit)) or lit.lower() in _NAMED_COLOR
            if is_color and not lenient:
                add("O", f"f2p `{short}` asserts strict equality on the colour literal {lit!r}. "
                         f"Hex, rgb() and named forms are equivalent, so a valid fix expressing "
                         f"the same colour differently FAILS. Normalise, or accept alternatives.",
                    pending=True, fid=_ident_fid("tests_overfit_exact_value", ident)); flagged = True
                break

        # --- image-resolvable: narrow, but the requirement may be shown in the poster ---
        # Read from `code`, not `body`: a golden-introduced word inside the it() name or a comment
        # is prose about the test, not an assertion about the implementation.
        all_hits = sorted({t for t in introduced
                           if _pins(t, code) and t.lower() not in instr})
        # Q1C/Q4B - a golden-introduced name that is also PRIVATE-shaped is the tree's strongest
        # implementation-specific signal, so it is reported as itself rather than folded in below.
        internal = [t for t in all_hits if t.startswith("_")]
        hits = [t for t in all_hits if not t.startswith("_")]
        if internal:
            add("O", f"f2p `{short}` reaches internal state named by the golden fix: {internal[:4]} "
                     f"(agnostic.txt Q1C/Q4B). These are not part of any public contract and no "
                     f"other implementation has to create them, so the test is pinned to this "
                     f"decomposition rather than to the behaviour the instruction asks for.",
                pending=True, fid=_ident_fid("tests_overfit_internal_state", ident)); flagged = True
        if hits:
            add("O", f"f2p `{short}` asserts on {hits[:4]}, which the golden fix "
                     f"{'INTRODUCES' if verified else 'appears to introduce (NOT verified against the base tree)'} and "
                     f"instruction.md never names. If the requirement is visible in "
                     f"environment/assets (before/after poster) the test may still be fair (#9 "
                     f"Pass) - CHECK THE IMAGE. If it is absent there too, the test only accepts "
                     f"the golden implementation.",
                pending=True, fid=_ident_fid("tests_overfit_fix_symbol", ident)); flagged = True

        if _EXACT_SEL.search(body) and not lenient:
            add("O", f"f2p `{short}` selects by one EXACT class/id and offers no fallback or "
                     f"substring match. A valid fix that restructures markup or renames the class "
                     f"would fail. CHECK THE IMAGE: if the instruction/poster pins that exact "
                     f"name it is fair; otherwise widen the selector.",
                pending=True, fid=_ident_fid("tests_overfit_exact_selector", ident)); flagged = True

        # --- Q3C/Q3D - is an INTERNAL collaborator mocked, or asserted to have been called? ---
        # Read the RAW body here, unlike every other node: a mock names its target as a string
        # literal (`jest.mock('../src/x')`, `patch('mod._helper')`), so blanking literals would
        # blank the only evidence this node has.
        for m in _MOCK_CALL.finditer(body):
            target = (m.group(1) or "").strip()
            if not target or _BOUNDARY.search(target):
                continue                          # Q3B: a boundary mock keeps the test agnostic
            if not any(re.search(rf"\b{re.escape(t)}\b", target) for t in introduced):
                continue                          # pre-existing collaborator: repo's own practice
            add("O", f"f2p `{short}` mocks `{target[:40]}`, an internal introduced by the golden "
                     f"fix (agnostic.txt Q3C). Mocking it presumes the solution is decomposed into "
                     f"that piece, so an implementation that produces the same result without that "
                     f"seam has nothing for the mock to attach to.",
                pending=True, fid=_ident_fid("tests_overfit_mock_internal", ident)); flagged = True
            break
        for l in assert_lines:
            if not _CALLED_WITH.search(l) or _BOUNDARY.search(l):
                continue
            add("O", f"f2p `{short}` asserts that a collaborator WAS CALLED, with given arguments "
                     f"(agnostic.txt Q3D). That is an assertion about how the work is carried out "
                     f"internally, not about what the code produces - a fix computing the same "
                     f"observable result through a different call sequence fails it.",
                pending=True, fid=_ident_fid("tests_overfit_call_assert", ident)); flagged = True
            break

        # --- Q5C - the SHAPE of the result asserted instead of the result ---
        if _KEY_ORDER.search(code):
            add("O", f"f2p `{short}` asserts an exact key set or key order (agnostic.txt Q5). If "
                     f"that shape is a documented public schema the test is fair (Q5B); if it is "
                     f"this implementation's own arrangement, a fix returning the same information "
                     f"with an extra key or a different order fails.",
                pending=True, fid=_ident_fid("tests_overfit_structure_pin", ident)); flagged = True
        for m in _INSTANCE_OF.finditer(code):
            cls = m.group(1)
            if cls in introduced:
                add("O", f"f2p `{short}` asserts the result is an instance of `{cls}`, a type the "
                         f"golden fix introduces (agnostic.txt Q5C). The intermediate type is an "
                         f"internal choice - another implementation satisfying the same behaviour "
                         f"with an existing type, or a plain value, fails on identity alone.",
                    pending=True, fid=_ident_fid("tests_overfit_instance_pin", ident)); flagged = True
                break

        # --- Q6C - does SETUP write state a normal caller cannot reach? ---
        setup = [l for l in code.splitlines() if not _ASSERT_TOK.search(l)]
        pre = sorted({m.group(1) for l in setup for m in _FIELD_WRITE.finditer(l)
                      if m.group(1) in introduced})
        if pre:
            add("O", f"f2p `{short}` writes {pre[:3]} directly during setup (agnostic.txt Q6C) - "
                     f"fields the golden fix introduces. The test arranges this implementation's "
                     f"internals before acting, so it can only run against an implementation that "
                     f"has them.",
                pending=True, fid=_ident_fid("tests_overfit_setup_internal", ident)); flagged = True

        # --- beyond the tree: the MECHANISM pinned, when the requirement is an outcome ---
        for m in _EQ_ASSERT.finditer(body):
            lit = m.group(1).strip().lower()
            mech = _MECHANISM.get(lit)
            if mech and lit not in instr and not lenient:
                add("O", f"f2p `{short}` asserts the literal {lit!r} - it pins the layout to "
                         f"{mech}, and instruction.md never asks for it. The stated requirement can "
                         f"be met by more than one mechanism, so every fix that reaches the same "
                         f"result another way is rejected for its choice rather than its result. "
                         f"CHECK THE IMAGE and the instruction: if {mech} is genuinely required, "
                         f"this is fair.",
                    pending=True, fid=_ident_fid("tests_overfit_mechanism", ident)); flagged = True
                break

        # --- beyond the tree: the exact MAGNITUDE the golden happened to choose ---
        pinned = sorted({m.group(1) for m in _NUM_EQ.finditer(code)
                         if m.group(1) in introduced_nums and m.group(1) not in instr},
                        key=lambda s: (len(s), s))
        if pinned and not lenient:
            add("O", f"f2p `{short}` asserts the exact value(s) {pinned[:3]}, which appear only on "
                     f"the ADDED side of the golden fix and nowhere in instruction.md. The "
                     f"instruction states an effect, not a number, so a fix that achieves the same "
                     f"effect with a neighbouring value fails an assertion it actually satisfies. "
                     f"CHECK THE IMAGE: if the value is legible there, or a tolerance is intended, "
                     f"this is fair.",
                pending=True, fid=_ident_fid("tests_overfit_magnitude", ident)); flagged = True

        # --- Q1D - no assertion visible at all ---
        if len(code.strip()) > 60 and not assert_lines:
            add("O", f"f2p `{short}` shows no assertion in the source QC can read (agnostic.txt "
                     f"Q1D - INVALID). A test that asserts nothing passes for any implementation "
                     f"including a broken one. QC slices test bodies textually, so confirm this is "
                     f"the whole test before treating it as real.",
                pending=True, fid=_ident_fid("tests_overfit_no_assertion", ident)); flagged = True

    # --- assertions the patch adds that belong to no test QC can name ---
    orphans = _orphan_added_lines(tasks, src, _f2p_spans(src, f2p))
    hit_files, hit_syms, n_lines = set(), set(), 0
    for path, lines in orphans.items():
        for l in lines:
            code = _code_only(l)
            if not _ASSERT_TOK.search(code):
                continue
            found = {t for t in introduced
                     if t.lower() not in instr and _pins(t, code)}
            if found:
                hit_files.add(path); hit_syms |= found; n_lines += 1
    if hit_syms:
        add("O", f"test.patch adds {n_lines} assertion(s) on {sorted(hit_syms)[:4]} - introduced by "
                 f"the golden fix, never named in instruction.md - across {len(hit_files)} file(s), "
                 f"in tests QC cannot name. Those hunks edit one line deep inside an existing test, "
                 f"so the diff's context resolves to the enclosing function and the test's own name "
                 f"is not in the bundle. The pin is the same one reported per-test above; this says "
                 f"how far it actually reaches.",
            evidence=sorted(hit_files)[:6], pending=True, fid="tests_overfit_unnamed_assertions"); flagged = True

    # Coverage is stated on EVERY run, not only the clean one. Reporting candidates while silently
    # inspecting a fraction of the declared f2p reads as "the rest were cleared".
    if len(blocks) < len(f2p):
        add("O", f"agnostic assessment inspected {len(blocks)} of {len(f2p)} declared f2p by name. "
                 f"The other {len(f2p) - len(blocks)} are pre-existing tests whose declarations are "
                 f"not in test.patch and whose file is not in the bundle, so nothing here is a "
                 f"statement about them either way.", ok=True, fid="tests_overfit_coverage")

    # OVERFIT IS NOT SETTLED BY THIS CHECK, and the report has to say so out loud. The rubric
    # defines it against the REPOSITORY ("a plausible implementation has any precedent in the
    # repo") and against the POSTERS, and this check can read neither: it sees the bundle's test
    # source and nothing else. Every candidate above is a pointer, not a verdict - and an empty
    # list is "no signal in the source", never "the tests are fair". Silence reading as a clean
    # bill is the failure this line exists to prevent.
    add("O", "THREE STEPS, IN THIS ORDER - REPORT, ASK TO INSPECT, THEN RULE. (1) REPORT every "
             "finding below to the CB in plain words: what the test pins, and which other "
             "correct implementation it would reject. Never paste an id as if it explained "
             "itself. (2) ASK THE CB WHETHER TO INSPECT, and WAIT for the answer. Do not "
             "investigate unasked and do not rule unasked - this check reads test source only, "
             "so every finding here is a QUESTION, and the CB decides whether it is worth your "
             "time to chase. Asking them to adjudicate it themselves is the other failure: they "
             "should be choosing whether you dig, not doing the digging. (3) IF THEY SAY YES, "
             "inspect with TEST_FITNESS.md - read the test BODY rather than the diff (the diff "
             "hides the helpers) to see whether a symbol is asserted BY NAME or discovered by "
             "behaviour; grep the BASE tree to check the \"the golden fix introduces this\" "
             "claim, the single most common false finding here; open the posters; and MEASURE "
             "where the read runs out. What the evidence then shows to be a FALSE POSITIVE you "
             "clear YOURSELF, with that evidence as the reason - it is recorded and replays on "
             "every later audit, so the gate stays green without anyone re-typing anything. What "
             "the evidence shows to be REAL you report as a defect to fix, not something to "
             "clear. Where it stays inconclusive, say so and go back to the CB. NEVER clear one "
             "you have not inspected: that turns a blocker into a formality and the CB never "
             "learns their tests were questioned. "
             "HOW THIS DIMENSION WORKS. Every overfit finding above BLOCKS - no QC pass is "
             "recorded, so oracle and nop stay grounded until each one is ruled on. But each is a "
             "heuristic read off test source, not a proven defect: this check cannot see the "
             "REPOSITORY, where the rubric's \"plausible implementation has precedent in the "
             "repo\" is decided, nor the POSTERS, where a literal that looks golden-only is often "
             "the spec. So each is a QUESTION, answered in either direction with a mandatory "
             "reason: `--adjudicated <id>=cleared:\"why\"` drops it to OK, `=confirmed:\"why\"` "
             "promotes it to a real defect to fix. DO NOT loosen an assertion merely because it is "
             "listed - on a well-built task most of these clear, and weakening a good test is the "
             "more expensive mistake. TEST_FITNESS.md is not reserved for a contested ruling - "
             "it is how you FORM one: the "
             "investigation: the digest, both posters, and a container where the alternative "
             "implementation can be RUN in about two seconds, which settles it as evidence instead "
             "of opinion. UNDERFIT - a plausible wrong fix that still scores - is not reachable "
             "here at all and needs that same procedure.",
        fid="overfit_not_settled_statically")
    if not flagged:
        lenient_n = sum(1 for b in blocks.values() if _AGNOSTIC.search(b))
        add("O", f"f2p tests show no overfit signal ({len(blocks)} inspected against the "
                 f"agnostic.txt tree Q1-Q6 plus mechanism and magnitude pinning; {lenient_n} carry "
                 f"explicit alternative-accepting markers - candidate selectors, computed-value "
                 f"reads, or regex). This is the absence of a detectable signal, not a proof: the "
                 f"decidable question is whether the tests reject a VALID implementation, and that "
                 f"is answered by naming one. Read instruction.md, describe a second implementation "
                 f"that satisfies it by other means, and walk it through each f2p assertion. If "
                 f"none of them rejects it, the tests are agnostic.", ok=True, fid="tests_agnostic")


# ------------------------------- v2 #3/#15  Instruction solvable WITHOUT the image?
# MM SWE is a MULTIMODAL benchmark: the poster is supposed to carry information the prose does
# not. So the question cuts both ways and neither end is good:
#   * instruction fully self-sufficient -> the image is decorative, the task never exercises
#     perception, and it is easier than its type claims;
#   * instruction too thin AND the image does not cover the gap -> unsolvable (#15).
# Both book against Hardening, which is why this lives there.
#
# THIS IS NOT STATICALLY DECIDABLE and is never a blocker. Whether prose alone is enough to
# locate and fix the defect is a reading judgement. So the check gathers the evidence, states a
# lean, and always asks for the read - severity CANDIDATE, which by construction cannot change
# the exit code (only FAIL does).

# Prose that hands the decisive detail to the picture. Their presence is EVIDENCE OF DEPENDENCE:
# the text is admitting it does not say the thing.
_DEFERS_TO_IMAGE = re.compile(
    r"shown in the (attached|screenshot|image|poster)|see the attached|as shown|"
    r"in the (attached |)(screenshot|image)s?\b|open them to determine|"
    r"attached screenshots? for|refer to the (image|screenshot)|"
    r"the (screenshot|image)s? (show|shows|illustrate)", re.I)
# Vague stand-ins for a detail the picture is expected to supply.
_VAGUE_CONFIG = re.compile(
    r"certain (display |rendering |)modes?|some (display |)configurations?|"
    r"a particular (mode|configuration|setting)|the (display |rendering )?"
    r"(mode|configuration) shown", re.I)


def check_M(tasks, md, conf):
    """Could the task be fixed from instruction.md alone, with the images set aside?"""
    if not tasks:
        return
    instr = read(os.path.join(tasks, "instruction.md")) or ""
    if not instr.strip():
        add("M", "instruction.md is empty or missing - nothing to assess", fid="instr_missing")
        return
    low = instr.lower()
    assets = []
    adir = os.path.join(tasks, "environment", "assets")
    if os.path.isdir(adir):
        assets = [f for f in sorted(os.listdir(adir)) if f != "ASSET_MANIFEST.json"]

    patch = read(os.path.join(tasks, "solution/fix.patch"))
    edited = sorted(md.get("files_edited") or list(diff_paths(patch)))
    def names_file(path):
        base = os.path.basename(path)
        stem = os.path.splitext(base)[0]
        return (base.lower() in low                       # "Input.js"
                or f"`{stem.lower()}`" in low             # `Input`
                or f"`{base.lower()}`" in low)
    named = [p for p in edited if names_file(p)]
    values = sorted(_introduced_symbols(patch))
    named_values = [v for v in values if v.lower() in low]
    defers = [m.group(0).strip() for m in _DEFERS_TO_IMAGE.finditer(instr)]
    vague = [m.group(0).strip() for m in _VAGUE_CONFIG.finditer(instr)]

    ev = [f"{len(instr.split())} words · {len(assets)} image asset(s) set aside: "
          f"{', '.join(assets) or 'none'}",
          f"names {len(named)}/{len(edited)} edited file(s) in prose"
          + (f": {[os.path.basename(p) for p in named]}" if named else ""),
          (f"names {len(named_values)}/{len(values)} value(s) the fix introduces"
           + (f": {named_values}" if named_values else ""))
          if values else "the fix introduces no distinctive values to name (e.g. a CSS-value "
                        "fix) - neutral, not a point against self-sufficiency",
          f"defers to the image {len(defers)} time(s)" + (f", e.g. {defers[0]!r}" if defers else ""),
          f"vague stand-in phrases: {len(vague)}" + (f", e.g. {vague[0]!r}" if vague else "")]

    if not assets:
        add("M", "no image assets, so nothing depends on them. Confirm instruction.md alone is "
                 "enough to locate AND fix the defect; if it is not, the task is unsolvable (#15).",
            fid="instr_no_assets", evidence=ev)
        return

    # A lean, not a verdict. Deference and vagueness say the prose is leaning on the picture;
    # naming the edited files and the fix's own values says it may not need to.
    leans_on_image = bool(defers or vague)
    # A fix that introduces no distinctive symbols (a CSS-value change, say) leaves nothing to
    # name, so requiring a named value would be unsatisfiable - a 0/0 denominator, the same trap
    # the always-pass rubric stub creates. Absent values are NEUTRAL here, not a strike.
    values_ok = (not values) or bool(named_values)
    self_sufficient = bool(named) and values_ok
    if self_sufficient and not leans_on_image:
        lean = ("LEAN: possibly SELF-SUFFICIENT - it names the edited file(s) and the value(s) the "
                "fix introduces, and never defers to the poster. If prose alone is enough, the "
                "image is decorative and the task does not exercise perception.")
    elif leans_on_image and not named:
        lean = ("LEAN: IMAGE-DEPENDENT - the prose defers the decisive detail to the poster and "
                "does not name the edited file(s)/values. That is the intended shape for a "
                "multimodal task; confirm the poster genuinely supplies what the prose withholds.")
    else:
        lean = ("LEAN: UNCLEAR - the signals point both ways. Read it and decide.")

    add("M", "READ instruction.md WITH THE IMAGES SET ASIDE and decide: could a competent engineer "
             "locate and fix this defect from the prose alone? Report the answer to the CB as a "
             "WARNING either way - this is never a blocker. " + lean,
        fid="instr_solvable_without_image", evidence=ev)


# ------------------------------------------------------------------ L: instruction wording lint
# THE LEAN INSTRUCTION PLAYBOOK (Official V25, instruction dims 3/4/5), AS A WORD SCAN.
#
# An LLM read of instruction.md against the images would judge these dims properly; it was costed
# and declined. This is the free part of that read: everything decidable from the TEXT alone. It
# cannot see the images, so it can never say whether the text is TRUE to them, whether a defect
# lives only in the pixels (pioneer's moon numbering - the Dim 4 = 3 case), or whether prose alone
# would be enough (that is group M's question). It is a lint, not a grader.
#
# ADVISORY BY CONSTRUCTION, NOT BY CONVENTION. Every finding is a CANDIDATE (never `fail=`, never
# `pending=`), and group L has NO entry in GROUP_DIM - the same arrangement as group T - so
# `dim in BLOCKING_DIMS` is False and `blocking` is never set. It cannot change the exit code,
# cannot withhold the QC pass, and cannot keep oracle/nop grounded. A PENDING here would be the
# opposite of advisory: it withholds the pass until someone rules, so it is deliberately not used.
#
# WHY PHRASES AND NOT WORDS. The playbook asks for a sentence saying the images are correct apart
# from the defect, and luanti says "Nothing that is already drawn correctly should change", so a
# bare "correct" word list would fire on the very sentences the scan asks for. What fails Dim 4 is a
# vague phrase STANDING ALONE ("Something does not render correctly in the frame centre"), so only
# the negated / generic forms are matched, and a vague phrase the same sentence goes on to explain
# (after `:` or a dash) is let through. The positive form is judged separately, by WHAT it calls
# correct: "<generic subject> is correct" ("what the screenshots show ... is correct") is flagged as
# instr_lint_vague_truth; a truth sentence that names what is correct is not.
#
# Calibrated on the playbook's two QC-PASS examples. luanti_org__luanti_12770_mm comes out clean.
# pioneerspacesim__pioneer_5999_mm comes out clean EXCEPT instr_lint_vague_truth, on purpose: its
# "what the screenshots show about this moon and its neighbours is correct" never says what is
# correct (CB ruling, 2026-11-05).

_MEDIA_EXT = r"(?:png|jpe?g|gif|webp|bmp|svg|mp4|webm|mov|mkv|avi|gifv)"
_CODE_EXT = (r"(?:c|cc|cpp|cxx|h|hh|hpp|hxx|py|pyi|js|mjs|cjs|jsx|ts|tsx|java|kt|kts|scala|go|rs|"
             r"rb|php|cs|swift|m|mm|lua|sh|bash|css|scss|sass|less|vue|svelte|sql|toml|ya?ml|ini|"
             r"cmake|gradle|xml|proto|glsl|hlsl|frag|vert|shader)")

# What the playbook's "cut from the text" list names, in the forms a static read can recognise.
_LINT_LEAKS = [
    # No closing bracket/quote and no trailing sentence punctuation: "(see https://x/1)." -> x/1
    ("URL", re.compile(r"\b(?:https?://|www\.)[^\s<>()\[\]\"'`]*[^\s<>()\[\]\"'`.,;:!?]", re.I)),
    ("code host", re.compile(r"\b(?:github|gitlab|bitbucket)(?:\.com)?\b", re.I)),
    ("issue / PR reference",
     re.compile(r"(?:\b(?:issue|pr|pull request|ticket|bug)\s*#?\d+\b|(?<![\w/])#\d{2,}\b"
                r"|\bpull request\b|\bupstream (?:fix|patch|commit|pr)\b)", re.I)),
    ("commit hash", re.compile(r"\bcommit\s+[0-9a-f]{7,40}\b", re.I)),
    ("source file", re.compile(r"(?<![\w/.-])[\w./-]*[\w-]\.%s\b" % _CODE_EXT)),
    ("function call", re.compile(r"\b[A-Za-z_][\w]*(?:(?:::|\.|->)[A-Za-z_]\w*)*\(\s*\)")),
    ("scoped name", re.compile(r"\b[A-Za-z_]\w*(?:::|->)[A-Za-z_]\w*")),
    ("code identifier", re.compile(r"\b(?:[a-z]+[A-Z][A-Za-z0-9]*|[A-Za-z][a-z0-9]*_[A-Za-z0-9_]+"
                                   r"|m_[A-Za-z]\w*|[A-Z]{2,}_[A-Z0-9_]+)\b")),
    ("measurement", re.compile(r"\b\d+(?:\.\d+)?\s?(?:px|pt|em|rem|ms|fps|hz|kb|mb|gb|km|mm|kg"
                               r"|°|deg)\b|\b\d+(?:\.\d+)?\s?%", re.I)),
    ("error text", re.compile(r"[\"'`][^\"'`\n]{0,80}\b(?:error|exception|traceback|segfault|"
                              r"assert(?:ion)?(?: failed)?|undefined|nullptr|null pointer|panic)"
                              r"\b[^\"'`\n]{0,80}[\"'`]", re.I)),
]

# Dim 4 = 2, "Unspecific Symptoms": a generic phrase where a plain defect word belongs. Only the
# NEGATED forms of correct/proper/right are vague - the positive forms are the playbook's own
# truth statements and are never matched.
_LINT_VAGUE = re.compile(
    r"\bsomething\b|\bsomehow\b|\bsome (?:issue|problem|bug|glitch)s?\b"
    r"|\b(?:an?|the) (?:issue|problem|bug|glitch)\b(?! (?:report|tracker|number|id)\b)"
    r"|\bglitch(?:es|y)?\b|\bbuggy\b|\bweird(?:ly)?\b|\bstrange(?:ly)?\b"
    r"|\b(?:looks?|seems?|appears?) (?:odd|off|funny|weird|strange)\b"
    r"|\bnot (?:quite )?right\b|\bisn't right\b"
    r"|\b(?:does not|doesn't|do not|don't|is not|isn't|are not|aren't) work(?:ing)?\b"
    r"|\bnot working\b|\bbroken\b|\bmisbehav\w*\b"
    r"|\bbehaves? (?:incorrectly|unexpectedly|strangely|oddly|badly|wrong(?:ly)?)\b"
    r"|\bunexpected(?:ly)?\b|\bincorrect(?:ly)?\b|\bimproper(?:ly)?\b"
    # "the wrong label" names what is wrong; "is drawn wrong" does not.
    r"|(?<!\bthe )(?<!\ba )\bwrong(?:ly)?\b"
    r"|\b(?:not|n't|never)\s+(?:\w+\s+){0,2}(?:correct(?:ly)?|proper(?:ly)?|as expected|"
    r"as intended|right)\b", re.I)

_LINT_TIMESTAMP = re.compile(r"\b\d{1,2}:\d{2}(?:\.\d+)?\b")
# A region of the frame given as the explanation, like a time window: "in the frame centre".
_LINT_REGION = re.compile(
    r"\b(?:in|at|near|around|towards?) the (?:frame|screen|image|window|view|picture)?\s*"
    r"(?:centre|center|middle|top|bottom|left|right|corner|edge)s?\b"
    r"|\b(?:top|bottom|upper|lower)[- ](?:left|right)(?: corner)?\b", re.I)

# Positive patterns the playbook asks for when images carry extra state. Absence is advisory.
_LINT_TRUTH = re.compile(
    r"\b(?:apart|aside) from the (?:defect|bug|problem|issue|fault)\b"
    r"|\b(?:other than|except(?: for)?) the (?:defect|bug|problem|issue|fault)\b"
    r"|\beverything else\b[^.]{0,80}\bcorrect\b"
    r"|\b(?:screenshots?|images?|pictures?|recording|video|frames?|take)\b[^.]{0,100}"
    r"\b(?:is|are) (?:otherwise |all |both )?(?:correct|accurate|as intended)\b"
    r"|\bnothing (?:else|that is already)[^.]{0,60}\b(?:should|must) change\b"
    r"|\bdrawn (?:normally|correctly)\b", re.I)
_LINT_REFERENCE = re.compile(
    r"\bshould (?:look|be drawn|appear|render|behave|read|show|be shown)\b[^.]{0,100}"
    r"\b(?:like|as|the way)\b"
    r"|\blike the\b[^.]{0,80}\b(?:screenshot|image|picture|frame|still|poster|recording)\b"
    r"|\bexpected[_ ](?:screenshot|image|result|look|state|output|rendering)\b"
    r"|\bthe way (?:it|they|this|these) (?:is|are|was|were|looks?|appears?)\b"
    r"|\b(?:before|until) (?:about )?\d{1,2}:\d{2}\b", re.I)

# A truth sentence is still vague when its "is correct" is about a GENERIC subject: "what the
# screenshots show ... is correct", "everything else is correct", "the screenshots are otherwise
# correct". It tells the agent to trust the images without saying WHAT to trust, so a label, a
# number or an injected second bug stays as ambiguous as with no sentence at all. Naming what is
# correct ("the moon names, their numbering and the orbit order ... are correct") clears it.
# Only "<subject> is/are correct" claims are judged; a change guard such as luanti's "Nothing that
# is already drawn correctly should change" makes no such claim and is left alone.
_LINT_TRUTH_CLAIM = re.compile(
    r"\b(?:is|are)\s+(?:(?:otherwise|all|both|also|entirely|fully)\s+)?"
    r"(?:correct|accurate|right|as intended)\b", re.I)
_LINT_TRUTH_ANCHOR = re.compile(
    r"^.*\b(?:(?:apart|aside) from|other than|except(?: for)?) the "
    r"(?:defect|bug|problem|issue|fault)s?\b\s*,?", re.I)
_LINT_GENERIC_SUBJECT = re.compile(
    r"\bwhat (?:the |this |these |each |both )?(?:screenshots?|images?|pictures?|recordings?|"
    r"videos?|frames?|posters?|stills?|take|clip)\s+(?:shows?|showed|depicts?|displays?|contains?)\b"
    r"|\b(?:everything|anything|all) else\b|\bthe rest\b"
    r"|\beverything (?:shown|visible|depicted|in (?:the|these|both))\b"
    r"|^(?:(?:the|these|both|all|its|their) )?(?:other )?(?:screenshots?|images?|pictures?|"
    r"recordings?|videos?|frames?|posters?|stills?)(?: themselves)?$"
    r"|^(?:it|they|this|that|these|those|everything|all)$", re.I)

# Words the golden fix's own code and comments use that carry no cause: language keywords, plumbing
# and common English. A coincidence with these says nothing about the instruction.
_LINT_CODE_STOP = set("""
abstract assert async await auto bool boolean break byte case catch char class const constexpr
continue default define delete double elif else endif enum explicit export extern false final
finally float func function goto ifdef ifndef import include inline instanceof int interface
lambda let long mutable namespace native new nil none noexcept null nullptr operator override
package private protected public register return self short signed sizeof static struct super
switch template this throw throws true try typedef typeid typename union unsigned using var
virtual void volatile while yield std vector string size_t uint int32 int64 uint32 uint64 fixed
fixedf printf snprintf sprintf fprintf buf buffer len length tmp temp idx index args argv argc
param params value values result results data info item items list array map set get put add
init update create make build load save read write open close start stop begin end next prev
count total first last left right upper lower bound bounds min max sum avg diff ptr ref obj
num number numbers flag flags type types name names key keys val node nodes func callback
handler helper util utils test tests mock assert expect should
""".split())
_LINT_EN_STOP = set("""
about above after again against also always another anything around because been before being
below between both cannot could does doing done down during each either else enough even ever
every from further have having here into itself just keep kept known later least less like made
many maybe might more most much must need needs never once only other otherwise over same
since some still such than that their them then there these they thing things this those though
through thus under until upon very want well were what when where whether which while whom whose
will with within without would your yours case cases point note fine work works working change
changes changed instead already actually rather really simply still using used uses
""".split())

_ASSET_LINK = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def _lint_prose(instr, assets, keep_headings=False, keep_evidence=False):
    """instruction.md as prose: no image embeds, no asset paths, no evidence-list section.
    Returns (prose_text, headings). `keep_headings` leaves them in the text, in place: the model
    read needs the title, which is often where the element is named. `keep_evidence` keeps the
    evidence section too: the agent reads its captions, and a caption can vouch for a defect."""
    text = _ASSET_LINK.sub(" ", instr)
    out, headings, skipping = [], [], False
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("#"):
            # The packaged "Attached visual evidence" section is a file list the packager adds.
            skipping = (bool(re.match(r"#+\s*attached (?:visual )?evidence\b", s, re.I))
                        and not keep_evidence)
            headings.append(s.lstrip("#").strip())
            if keep_headings and not skipping:
                out.append(ln)
            continue
        if skipping:
            continue
        out.append(ln)
    prose = "\n".join(out)
    # Asset names and any path ending in a media extension are the evidence, not a leak.
    for a in sorted(assets, key=len, reverse=True):
        prose = re.sub(r"[\w./-]*" + re.escape(a), " <asset> ", prose)
    prose = re.sub(r"[\w./-]+\.%s\b" % _MEDIA_EXT, " <asset> ", prose, flags=re.I)
    return prose, headings


def _lint_sentences(prose):
    flat = re.sub(r"\s+", " ", prose).strip()
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`\"(<])", flat) if s.strip()]


def _lint_cap(items, n=6):
    """The renderer prints at most 6 evidence lines (qc_common: `f.evidence[:6]`), so a 7th
    "... and N more" line would be silently dropped. Keep the count inside the 6."""
    return items if len(items) <= n else items[:n - 1] + [f"... and {len(items) - n + 1} more"]


def _lint_clip(s, n=150):
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _lint_cause_words(patch):
    """Words the golden fix's CHANGED lines use - identifiers split into parts, plus comment
    prose - minus keywords, plumbing and common English. Maps word -> one source token."""
    words = {}
    for ln in (patch or "").splitlines():
        if not ln or ln[0] not in "+-" or ln.startswith(("+++", "---")):
            continue
        for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", ln[1:]):
            parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tok.replace("_", " ")).split()
            for p in parts:
                w = p.lower()
                if (len(w) >= 5 and w.isalpha() and w not in _LINT_CODE_STOP
                        and w not in _LINT_EN_STOP):
                    words.setdefault(w, tok)
    return words


# THE INSTRUCTION READ. ONE text-only model call (qc_llm, Sonnet 5 by default) judges the three
# instruction requirements together:
#   instruction check      - the element is named by type, without hinting at the fix; the defect
#                            and expected result may be in the text or in a comparison image the
#                            text points to; which instance may stay in the image.
#   symptom specificity    - a general phrase passes when the same or next sentence gives context
#                            (what is affected, what kind of problem, which image is correct); it
#                            fails standing alone, or when a time window or region is all there is.
#   image dependency       - the text says what kind of problem it is or points to the correct
#                            result; the clue to the cause (instance, trigger, size, timing, error
#                            text) stays in the image; the problem is not misdescribed.
# It is given instruction.md (title, headings and the evidence captions included), the f2p test
# names, and, when task.toml has one, the author's difficulty_explanation. The tests and the
# explanation are ground truth for what the task grades: every graded behaviour must be stated in
# the text or shown in an image the text points to for it (pioneer_5999's injected moon numbering
# was neither), and no truth sentence or caption may vouch for something a graded defect changes.
# No images, no fix, no test bodies.
#
# When the model is not reachable, or MM_QC_LLM=0, the phrase scans for vague stand-ins and bare
# time windows/regions run instead; the rest has no scan and is reported as not checked (group S's
# test-name overlap still asks the coverage question). The vague "... is correct" truth sentence
# is always the static scan: it is a CB ruling, not part of these requirements. Leaks and cause
# words stay static too, because a word list is exact there. Every finding says which read produced
# it, and the group stays advisory: the model's verdict is a CANDIDATE like the scan's.
#
# A finding is kept only if its quote is in the prose the model was given, and an undescribed test
# only if its name is in the f2p list. That is what stops an invented finding from reaching the
# CB, and it costs no second call.
_SYMPTOM_PROMPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts",
                               "instruction_read.txt")
_SYMPTOM_REASON_FID = {
    "unnamed_element": "instr_lint_vague",
    "generic_stand_in": "instr_lint_vague",
    "no_problem_kind": "instr_lint_vague",
    "bare_window_or_region": "instr_lint_time_window",
    "hints_at_fix": "instr_lint_hints_fix",
    "clue_leak": "instr_lint_clue_leak",
    "misdescribed": "instr_lint_misdescribed",
    "vouches_for_defect": "instr_lint_vouches_defect",
}
_UNDESCRIBED_FID = "instr_lint_undescribed_defect"
_EXPLAIN_BUDGET = 12_000                 # ~5k tokens; a longer difficulty explanation is cut
_QUOTE_FOLD = str.maketrans({"\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
                             "\u201c": '"', "\u201d": '"', "*": None, "`": None})


def _fold_quote(s):
    return re.sub(r"\s+", " ", (s or "").translate(_QUOTE_FOLD)).strip().lower()


def _difficulty_explanation(tasks, md):
    text = md.get("difficulty_explanation")
    if not isinstance(text, str):
        # parse_toml's regex fallback (Python < 3.11) does not read triple-quoted strings
        m = re.search(r'^[ \t]*difficulty_explanation[ \t]*=[ \t]*"""(.*?)"""',
                      read(os.path.join(tasks, "task.toml")) or "", re.M | re.S)
        text = m.group(1) if m else ""
    text = text.strip()
    return text[:_EXPLAIN_BUDGET] + ("\n[... cut for length ...]" if len(text) > _EXPLAIN_BUDGET
                                     else "")


def _llm_symptom_read(prose, assets, explain="", f2p=()):
    """({fid: [evidence line, ...]}, source) when the model read happened, else (None, reason)."""
    try:
        import qc_llm
        with open(_SYMPTOM_PROMPT, encoding="utf-8") as f:
            system = f.read()
    except (ImportError, OSError) as exc:
        return None, f"model read unavailable ({exc})"
    user = (("The task ships these image files, which you cannot see: " + ", ".join(assets) + "."
             if assets else "The task ships no image files.")
            + "\n\n<instruction>\n" + prose.strip() + "\n</instruction>"
            + ("\n\n<graded_tests>\n" + "\n".join(f2p) + "\n</graded_tests>"
               if f2p else "\n\nNo graded test names were given.")
            + ("\n\n<difficulty_explanation>\n" + explain + "\n</difficulty_explanation>"
               if explain else "\n\nNo difficulty explanation was given."))
    reply, meta = qc_llm.ask_json(system, user)
    if reply is None:
        return None, f"model read unavailable: {meta}"
    items = reply.get("findings")
    if not isinstance(items, list):
        return None, "model read unavailable: the reply had no findings list"
    hay = _fold_quote(prose)
    by_fid, dropped = {}, 0
    for it in items:
        if not isinstance(it, dict):
            continue
        quote = str(it.get("quote") or "").strip()
        if not quote or _fold_quote(quote) not in hay:
            dropped += 1
            continue
        reason = str(it.get("reason") or "").strip()
        clue = str(it.get("clue") or "").strip() if reason == "clue_leak" else ""
        line = f"{clue or reason or 'unspecific'}: {_lint_clip(quote)!r}"
        why, fix = str(it.get("why") or "").strip(), str(it.get("suggest") or "").strip()
        if why:
            line += f" - {_lint_clip(why, 200)}"
        if fix:
            line += f" Suggest: {_lint_clip(fix, 200)}"
        by_fid.setdefault(_SYMPTOM_REASON_FID.get(reason, "instr_lint_vague"), []).append(line)
    known = {_fold_quote(t): t for t in f2p}
    bad_tests = 0
    for it in reply.get("undescribed_tests") or []:
        if not isinstance(it, dict):
            continue
        test = known.get(_fold_quote(str(it.get("test") or "")))
        if not test:
            bad_tests += 1
            continue
        line = f"test {_lint_clip(test, 120)!r}"
        why, fix = str(it.get("why") or "").strip(), str(it.get("suggest") or "").strip()
        if why:
            line += f" - {_lint_clip(why, 200)}"
        if fix:
            line += f" Suggest: {_lint_clip(fix, 200)}"
        by_fid.setdefault(_UNDESCRIBED_FID, []).append(line)
    source = (f"read by {meta['model']}" + (" (cached)" if meta.get("cached") else "")
              + ("" if f2p else "; no f2p test names, so coverage was judged from the "
                                "explanation alone")
              + ("" if explain else "; no difficulty_explanation"))
    if dropped:
        source += f"; {dropped} finding(s) dropped, their quote is not in instruction.md"
    if bad_tests:
        source += f"; {bad_tests} test finding(s) dropped, the name is not an f2p test"
    return by_fid, source


def check_L(tasks, md, conf=None):
    """Lean Instruction Playbook word scan (ADVISORY, never a blocker). See the block above."""
    if not tasks:
        return
    instr = read(os.path.join(tasks, "instruction.md")) or ""
    if not instr.strip():
        return                                   # group M already reports the empty file
    adir = os.path.join(tasks, "environment", "assets")
    assets = ([f for f in sorted(os.listdir(adir)) if f != "ASSET_MANIFEST.json"]
              if os.path.isdir(adir) else [])
    prose, headings = _lint_prose(instr, assets)
    sentences = _lint_sentences(prose)
    hits = 0

    # Headings are scanned for leaks and cause words (a repo name in the title leaks just the same)
    # but not for vague phrases: a title is a label, and the playbook grades the prose under it.
    scan = "\n".join(headings) + "\n" + prose

    # 1. Leaks: what the playbook says to cut. The repo's own name is task-specific.
    leaks, spans = [], []
    def _leak(label, m):
        tok = m.group(0).strip()
        if "<asset>" in tok or any(a <= m.start() and m.end() <= b for a, b in spans):
            return                               # the evidence itself, or inside an earlier hit
        spans.append((m.start(), m.end()))
        leaks.append(f"{label}: {tok!r}")
    for label, rx in _LINT_LEAKS:
        for m in rx.finditer(scan):
            _leak(label, m)
    repo = str(md.get("repository_name") or "")
    for part in sorted({p for p in re.split(r"[/_.-]", repo) if len(p) >= 4}):
        for m in re.finditer(r"\b%s\b" % re.escape(part), scan, re.I):
            _leak(f"repository name (from {repo!r})", m)
    leaks = list(dict.fromkeys(leaks))
    if leaks:
        hits += 1
        add("L", f"instruction.md names {len(leaks)} thing(s) the Lean Instruction Playbook says "
                 "to cut from the text (repo, URLs, issue/PR links, files, functions, code names, "
                 "sizes, error text). Each one points the agent at the cause instead of leaving it "
                 "to the images. Remove it, or keep it only if it is an honest environment fact. "
                 "ADVISORY - never a blocker.",
            fid="instr_lint_leak", evidence=_lint_cap(leaks))

    # 2. Cause words: vocabulary from the golden fix's changed lines that the prose repeats.
    cause = _lint_cause_words(read(os.path.join(tasks, "solution/fix.patch")))
    low = scan.lower()
    named = []
    for w, src in sorted(cause.items()):
        if re.search(r"\b%ss?\b" % re.escape(w), low):
            named.append(f"{w!r} (the golden fix uses `{src}`)")
    if named:
        hits += 1
        add("L", f"instruction.md uses {len(named)} word(s) that also appear in the golden fix's "
                 "changed lines. The playbook cuts \"words that point at the cause\" (\"its radius is "
                 "wrong\"). If a word names the ELEMENT (the thing that looks wrong), keep it - the "
                 "playbook wants the element named. If it names the CAUSE or mechanism, cut it. "
                 "ADVISORY - never a blocker.",
            fid="instr_lint_cause_word", evidence=_lint_cap(named))

    # 3-4. The instruction read: the model when one is reachable, else the vague and window scans.
    f2p = [str(t) for t in ((conf or {}).get("f2p") or md.get("f2p") or [])]
    by_fid, symptom_source = _llm_symptom_read(
        _lint_prose(instr, assets, keep_headings=True, keep_evidence=True)[0], assets,
        _difficulty_explanation(tasks, md), f2p)
    if by_fid is not None:
        reader = symptom_source.split(";")[0].replace("read by ", "").replace(" (cached)", "")
        vague = by_fid.get("instr_lint_vague", [])
        bare_windows = by_fid.get("instr_lint_time_window", [])
    else:
        reader = f"static phrase scan; {symptom_source}"
        symptom_source = (f"static phrase scan; {symptom_source}; undescribed graded defects, "
                          "sentences vouching for a defect, hints at the fix, clue leaks and "
                          "misdescription need the model and were not checked")
        by_fid, vague, bare_windows = {}, [], []
        # 3. Vague stand-ins: a generic phrase where one plain defect word belongs (Dim 4 = 2).
        for s in sentences:
            for m in _LINT_VAGUE.finditer(s):
                rest = s[m.end():]
                if re.match(r"\s*(?::|—|–| - )\s*\S", rest):
                    continue                     # explained in the same sentence
                vague.append(f"{m.group(0)!r} in: {_lint_clip(s)}")
                break
        # 4. A time window or region as the whole explanation (fine next to an element and a defect).
        for s in sentences:
            if not (_LINT_TIMESTAMP.search(s) or _LINT_REGION.search(s)):
                continue
            rest = re.findall(r"[A-Za-z]+", _LINT_REGION.sub(" ", _LINT_TIMESTAMP.sub(" ", s)))
            if _LINT_VAGUE.search(s) or len(rest) < 6:
                bare_windows.append(_lint_clip(s))
    src = [f"instruction read: {symptom_source}"]

    # 4b. A truth sentence that says "correct" about a generic subject, without naming what. Always
    # the static scan: see the INSTRUCTION READ block.
    vague_truth = []
    for s in sentences:
        for m in _LINT_TRUTH_CLAIM.finditer(s):
            subj = _LINT_TRUTH_ANCHOR.sub("", s[:m.start()]).strip(" ,;:\"'`()")
            if subj and _LINT_GENERIC_SUBJECT.search(subj):
                vague_truth.append(f"{m.group(0)!r} about {subj!r} in: {_lint_clip(s)}")
                break
    hints = by_fid.get("instr_lint_hints_fix", [])
    clues = by_fid.get("instr_lint_clue_leak", [])
    wrong = by_fid.get("instr_lint_misdescribed", [])
    untold = by_fid.get(_UNDESCRIBED_FID, [])
    vouch = by_fid.get("instr_lint_vouches_defect", [])

    if untold:
        hits += 1
        add("L", f"{len(untold)} graded behaviour(s) are neither stated in instruction.md nor shown "
                 "in an image the text points to for them, so the agent cannot know they are part "
                 "of the task and will read the mismatch as intended. Name each affected element "
                 "and the kind of problem, or point to an image that shows it; which instance, "
                 "and why, can stay in the image. ADVISORY - never a blocker.",
            fid=_UNDESCRIBED_FID, evidence=src + _lint_cap(untold, 5))

    if vouch:
        hits += 1
        add("L", f"instruction.md has {len(vouch)} sentence(s) or caption(s) that vouch for "
                 "something a graded defect changes (\"what the screenshots show ... is correct\" "
                 "when the names in them are the defect). The agent is told to trust exactly what "
                 "it should fix. Narrow the sentence to what really is correct, and state the "
                 "defect. ADVISORY - never a blocker.",
            fid="instr_lint_vouches_defect", evidence=src + _lint_cap(vouch, 5))

    if vague:
        hits += 1
        add("L", f"instruction.md has {len(vague)} sentence(s) where the symptom is unspecific: a "
                 "general phrase stands alone, the affected element is never named by type, or "
                 "the text never says what kind of problem it is nor points to where the correct "
                 "result can be seen. The playbook's Dim 4 Fail (\"Unspecific Symptoms\") is e.g. "
                 "\"Something does not render correctly\" with nothing after it. Name the element "
                 "by type, and either give one plain word for the defect (\"empty\", \"spiky\", "
                 "\"missing\") or point to the image that shows the correct result, without naming "
                 "the cause. ADVISORY - never a blocker.",
            fid="instr_lint_vague", evidence=src + _lint_cap(vague, 5))

    if bare_windows:
        hits += 1
        add("L", f"instruction.md gives a time window or region in {len(bare_windows)} sentence(s) "
                 "as the only explanation, with no element and kind of problem beside it. The "
                 "playbook allows a time window only next to both (as luanti does); it fails Dim 4 "
                 "when the window is the whole explanation. ADVISORY - never a blocker.",
            fid="instr_lint_time_window", evidence=src + _lint_cap(bare_windows, 5))

    if hints:
        hits += 1
        add("L", f"instruction.md describes the cause, the mechanism or the fix in {len(hints)} "
                 "sentence(s). The instruction names the element and the kind of problem; why it "
                 "happens is for the agent to find. ADVISORY - never a blocker.",
            fid="instr_lint_hints_fix", evidence=src + _lint_cap(hints, 5))

    if clues:
        hits += 1
        add("L", f"instruction.md gives away {len(clues)} clue(s) the image is meant to keep: which "
                 "instance, what triggers it, how big it is, when it happens, the error text, or an "
                 "expected result precise enough to point at the cause. Keep the element and the "
                 "kind of problem in the text, leave the clue to the image, and point to a "
                 "reference image (\"should look like reference.png\") when stating the expected "
                 "result would give it away. ADVISORY - never a blocker.",
            fid="instr_lint_clue_leak", evidence=src + _lint_cap(clues, 5))

    if wrong:
        hits += 1
        add("L", f"instruction.md describes the problem as the wrong kind in {len(wrong)} "
                 "sentence(s) (e.g. a console crash called a problem in a rendered image), so the "
                 "agent would look in the wrong place. ADVISORY - never a blocker.",
            fid="instr_lint_misdescribed", evidence=src + _lint_cap(wrong, 5))

    if vague_truth:
        hits += 1
        add("L", f"instruction.md has {len(vague_truth)} sentence(s) that say the images are "
                 "\"correct\" without saying WHAT is correct (\"what the screenshots show ... is "
                 "correct\", \"everything else is correct\"). That is an unspecific symptom in "
                 "reverse: the agent is told to trust the images but not which parts, so a label, a "
                 "number or a second defect stays ambiguous. Name what the agent can trust, e.g. "
                 "\"Apart from the defect, the moon names, their numbering and the orbit order in "
                 "the screenshots are correct\". ADVISORY - never a blocker.",
            fid="instr_lint_vague_truth", evidence=_lint_cap(vague_truth))
    if not (vague or bare_windows or hints or clues or wrong or untold or vouch):
        add("L", f"instruction read ({reader}): clean", ok=True, fid="instr_lint_symptom_clean",
            evidence=src)

    # 5. The sentences the playbook asks for when images ship. Absence is a question, not a defect.
    if assets:
        body = " ".join(sentences)
        if not _LINT_TRUTH.search(body):
            hits += 1
            add("L", "instruction.md never says the images are correct apart from the defect "
                     "(e.g. \"Apart from the defect, the moon names, their numbering and the orbit "
                     "order in the screenshots are correct\" - name WHAT is correct; or luanti's "
                     "\"Nothing that is already drawn correctly should change\"). Without "
                     "it, anything else the images show - labels, numbering, an injected second "
                     "bug - carries no signal, and agents read a mismatch as intended behaviour. "
                     "Add one if the images carry state the text does not describe. ADVISORY - "
                     "never a blocker.",
                fid="instr_lint_no_image_truth",
                evidence=[f"{len(assets)} image asset(s): {', '.join(assets)}"])
        if not _LINT_REFERENCE.search(body):
            hits += 1
            add("L", "instruction.md does not point to a reference for the expected result - an "
                     "expected image (\"It should look like the minor body in the last "
                     "screenshot\") or the good part of the same take (\"drawn the way they are "
                     "before 0:08\"). The playbook keeps that pointer in the text so the agent "
                     "knows what correct looks like. ADVISORY - never a blocker.",
                fid="instr_lint_no_reference",
                evidence=[f"{len(assets)} image asset(s): {', '.join(assets)}"])

    if not hits:
        add("L", "instruction wording: no leaks, cause words, vague stand-ins or bare time windows; "
                 "truth and reference sentences present", ok=True, fid="instr_lint_clean",
            evidence=src)


def check_S(tasks, md, conf):
    """v2 #15 (ADVISORY) - can the solver PERCEIVE every behaviour they must satisfy?

    REBASED ON THE f2p TESTS, not on solution/fix.patch. The golden patch's file list is one
    author's implementation choice: a different valid fix might consolidate the same behaviours
    into a shared parent, or spread them wider. Deriving "how many subjects does this task have"
    from it measures the golden solution rather than the task, and can mislead either way.

    The f2p tests are the measurement. Whatever a solver writes, those are what must pass - so
    the number of distinct behaviours they cover IS the task's scope, and each one has to be
    perceivable from instruction.md or the posters. A behaviour visible in neither is an
    unsolvable-by-perception cut (#15 Fail).

    Subjects come from what DIFFERS between the f2p ids rather than from splitting on a
    separator, which produced truncated sentences on ids written as prose.

    NOT the same question as #9. This asks whether the solver can tell WHAT to fix; #9 (group O)
    asks whether the tests would accept a different valid fix. Both matter, independently.
    IMAGE-BLIND, so never a hard [FAIL] - it only says where to look.
    """
    if not tasks:
        return
    instr = (read(os.path.join(tasks, "instruction.md")) or "").lower()
    f2p = list((conf or {}).get("f2p") or md.get("f2p") or [])

    # Generic words carry no subject identity, so they must not satisfy the anchor test. Without
    # this, an f2p test about Tooltips "anchored" on the word `correct` because the instruction
    # happened to say "produces the correct rendering" - a false pass on the one question that
    # matters.
    _FILLER = {"correct", "correctly", "render", "renders", "rendered", "rendering", "should",
               "must", "still", "keeps", "keep", "work", "works", "valid", "proper", "properly",
               "expected", "behavior", "behaviour", "fix", "fixed", "test", "tests", "mode",
               "modes", "with", "without", "the", "and", "not", "any", "all", "when", "then",
               "value", "values", "shown", "appears", "look", "looks", "same", "other", "first"}

    def toks(s):
        return {t for t in re.split(r"[^A-Za-z0-9]+", s) if len(t) > 2}

    def substantive(ts):
        return {t for t in ts if t.lower() not in _FILLER}

    if len(f2p) > 1:
        sets = [toks(f) for f in f2p]
        shared = set.intersection(*sets) if sets else set()
        distinct = [s - shared for s in sets]
        # behaviours that are genuinely distinguished from one another
        groups = [(f2p[i], d) for i, d in enumerate(distinct) if d]
        if groups:
            add("S", f"the {len(f2p)} f2p tests cover {len(groups)} distinguishable behaviour(s). "
                     f"A solver must satisfy ALL of them, however they choose to implement it, so "
                     f"each must be perceivable from instruction.md or the posters.")
            for fid, d in groups:
                anchored = sorted(w for w in substantive(d) if w.lower() in instr)
                short = fid[:52] + ("…" if len(fid) > 52 else "")
                if anchored:
                    add("S", f"  `{short}` - distinguished by {sorted(d)[:4]}; "
                             f"anchored in instruction.md via {anchored[:3]}")
                else:
                    add("S", f"  `{short}` - distinguished by {sorted(d)[:4]}, NONE of which appear "
                             f"in instruction.md. CHECK THE POSTERS show this behaviour; if they do "
                             f"not, it is unsolvable by perception -> #15 Fail")
    elif len(f2p) == 1:
        add("S", "a single f2p test, so there is one behaviour to perceive. Confirm "
                 "instruction.md or the posters make it identifiable.", ok=True)

    # SECONDARY, and deliberately weak: the golden patch's file spread is an implementation
    # detail, so it is reported as context only - never as the basis for the #15 judgement above.
    fe = md.get("files_edited") or list(diff_paths(read(os.path.join(tasks, "solution/fix.patch"))))
    stems = sorted({os.path.splitext(os.path.basename(p))[0] for p in fe})
    if len(stems) > 1:
        add("S", f"context only: the GOLDEN fix happens to touch {len(stems)} file(s) {stems}. That "
                 f"is one author's structuring, not the task's scope - a different valid fix could "
                 f"consolidate or spread it. Judge scope from the f2p tests above.")
    if not findings["S"]:
        add("S", "no f2p ids to analyse - cannot assess perceivable scope", ok=True)
    add("S", "NB: whether the tests would ACCEPT a different valid fix is a separate question - "
             "see group O (v2 #9 Implementation Overfit).", ok=True)


# ------------------------------------------------------------------- main
GROUP_TITLES = {
    "A": "v2 #2  Structure - Deliverables & Packaging",
    "B": "v2 #1  Structure - Task Bundle Files (+ #4 poster decode)",
    "D": "v2 #8  Golden Fix - Source-Only Scope",
    "E": "v2     Hardening - can the HARNESS run in this image? (BLOCKING; Dockerfile vs harbor)",
    "F": "v2 #10 Tests - f2p/p2p Identifier Validity",
    "H": "v2 #5  Metadata - task_type Accuracy (value)",
    "I": "v2 #6  Evidence - Chain Consistency",
    "K": "v2 #1  Structure - task.toml identity ([task] name, [metadata] task_id/title/repository_name)",
    "M": "v2 #3/#15 Instruction - solvable WITHOUT the image? (ADVISORY, never a blocker)",
    "L": "V25 #3/#4 Instruction - Lean Instruction Playbook word scan (ADVISORY, never a blocker)",
    "N": "v2     Hardening - is the AGENT phase sealed? ([agent] network_mode)",
    "O": "v2 #9  Tests - Implementation Overfit (agnostic vs golden-specific)",
    "P": "v2     Hardening - can a NON-ROOT process run in this image? (BLOCKING; `/` is 0750)",
    "R": "v3     Rubrics - rubrics.json present & parses (full audit: check_rubrics.py)",
    "S": "v2 #15 Hardening - Real & Feasible (ADVISORY: is every f2p behaviour perceivable?)",
    "T": "mm     Tooling - submission capture wired in tests/test.sh (ADVISORY, never a blocker)",
}


def export_findings(path):
    """Translate this script's native `records` into the shared Finding model.

    Severity mapping preserves the existing contract exactly: a `[FAIL]` line is a hard FAIL, a
    line the script itself words as a v2 #6 "Non-Fail" is NON-FAIL, and everything else is a
    CANDIDATE - which is what the module docstring has always said ("every finding is a CANDIDATE
    unless marked [FAIL]"). Only the grouping, the tier, and PENDING are new.
    """
    from qc_common import Finding, FAIL, NON_FAIL, PENDING, CANDIDATE, OK, dump_findings
    out = []
    for r in records:
        if r["ok"]:
            sev = OK
        elif r["fail"]:
            sev = FAIL
        elif r.get("pending"):
            sev = PENDING
        elif "Non-Fail" in r["msg"]:
            sev = NON_FAIL
        else:
            sev = CANDIDATE
        dim = GROUP_DIM.get(r["group"])
        out.append(Finding(r["id"], r["msg"], sev, category=r["category"],
                           rubric_dim=dim, tier=r["tier"], source=["qc_structure"],
                           evidence=r.get("evidence"), blocking=r.get("blocking")))
    dump_findings(out, path)
    return len(out)


# The dimension each group books against - previously only in GROUP_TITLES prose.
GROUP_DIM = {
    "A": "Fail - Deliverable Packaging", "B": "Fail - Broken Structure",
    "D": "Fail - Dirty Fix Scope", "E": "Fail - Unreal or Infeasible",
    "F": "Fail - Bad Test IDs",
    "H": "Fail - Wrong task_type", "I": "Fail - Evidence Mismatch",
    "K": "Fail - Broken Structure",
    "M": "Fail - Unreal or Infeasible",
    "N": "Fail - Unreal or Infeasible",
    "O": "Fail - Implementation Overfit",
    "P": "Fail - Unreal or Infeasible",
    "R": "Fail - Rubric Quality", "S": "Fail - Unreal or Infeasible",
}


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
    root = argv[0]
    deliv, tasks = find_tasks_root(root)
    md = (parse_toml(os.path.join(tasks, "task.toml")) or {}).get("metadata", {}) if tasks else {}
    conf, _ = load_json(os.path.join(tasks, "tests/config.json")) if tasks else (None, None)

    check_A(deliv)
    check_B(tasks)
    check_D(tasks, md)
    check_E(tasks, md)
    check_F(tasks, conf, md)
    check_H(md)
    check_I(tasks)
    check_K(tasks)
    check_O(tasks, conf, md)
    check_M(tasks, md, conf)
    check_L(tasks, md, conf)
    check_N(tasks)
    check_P(tasks, md)
    check_R(tasks, md, conf)
    check_S(tasks, md, conf)
    check_T(tasks)

    print(f"\nVarmint Sheriffs static pre-checks (v3.1) - {os.path.abspath(root)}")
    print(f"Tasks/ = {tasks or 'NOT FOUND'}\n")
    total_fail = 0
    for g in GROUPS:
        print(f"-- {g}  {GROUP_TITLES[g]}")
        for line in findings[g] or ["(no output)"]:
            print(f"     {line}")
        total_fail += fails[g]
        print()
    print(f"SUMMARY: {total_fail} hard [FAIL] finding(s). Confirm every candidate by hand; run "
          f"check_rubrics.py (Step 0.55) for the full rubric audit and check_judge.py (Step 7.6) "
          f"for the judge mechanics; the gate (#16), tests (#9/#11/#12/#13), instruction (#3), "
          f"image (#4) and hardening (#14/#15) dims still need Steps 0.6-0.7 and a manual read.")
    if emit:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        n = export_findings(emit)
        print(f"  wrote {n} finding(s) -> {emit}")


if __name__ == "__main__":
    main()
    # MM_SWE_QC: propagate hard failures to the orchestrator.
    sys.exit(1 if sum(fails.values()) else 0)
