#!/usr/bin/env python3
"""Step 0.5 - static mechanical pre-checks for a Varmint Sheriffs deliverable bundle (v3).

Usage:
    python3 review_checks.py "task_<taskId>/deliverables"     # the four-folder root
    python3 review_checks.py "path/to/Tasks"                  # a bare Tasks/ (partial checks)
    python3 review_checks.py "path/to/Tasks/<task_id>"        # the bundle itself (V2)

Layouts: V2 (TASK101+) nests the bundle one level down, at Tasks/<task_id>/task.toml; V1 kept
task.toml directly in Tasks/. Both are detected, and every bundle check runs on the folder that
holds task.toml.

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
  F  ->  v2 #10 Tests - f2p/p2p Identifier Validity       [Fail - Bad Test IDs]
  H  ->  v2 #5  Metadata - task_type Accuracy (value)     [Fail - Wrong task_type]
  I  ->  v2 #6  Evidence - Chain Consistency              [Fail - Evidence Mismatch]
  R  ->  v3     Rubrics - rubrics.json present & parses    [Fail - Missing/Broken Rubrics]
              (structure only; run check_rubrics.py for the full rule-by-rule audit)
  S  ->  v2 #15 Hardening - Real & Feasible (ADVISORY)    [Fail - Unreal or Infeasible]
              (multi-subject fix/f2p aid; never a hard [FAIL] - needs the image, Step 8)
"""
import json, sys, os, re, py_compile, tempfile

SEVEN_TYPES = {
    "visual_bug_fix", "visual_regression", "design_reference", "build_render_repair",
    "temporal_interaction", "accessibility_visual", "data_viz_correctness",
}
REQUIRED_TASK_FILES = [
    "task.toml", "instruction.md", "evidence_bundle.json",
    "environment/Dockerfile", "environment/assets/ASSET_MANIFEST.json",
    "solution/fix.patch", "solution/solve.sh",
    "tests/config.json", "tests/test.patch", "tests/test.sh", "tests/verifier.py",
    "tests/rubrics.json",   # v3: rubric layer (always present - real rubric or always-pass stub)
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
    for k, v in re.findall(r'^\s*([a-z_]+)\s*=\s*"([^"]*)"', txt, re.M):
        md[k] = v
    for k, v in re.findall(r'^\s*([a-z_]+)\s*=\s*(\d+)\s*$', txt, re.M):
        md.setdefault(k, int(v))
    for k, v in re.findall(r'^\s*([a-z_]+)\s*=\s*(true|false)\s*$', txt, re.M):
        md.setdefault(k, v == "true")
    for k, body in re.findall(r'^\s*([a-z_]+)\s*=\s*\[(.*?)\]', txt, re.M | re.S):
        items = re.findall(r'"([^"]*)"', body)
        md.setdefault(k, items)
    return {"metadata": md}


def diff_paths(patch_text):
    """Return the set of file paths from `diff --git a/... b/...` headers."""
    if not patch_text:
        return set()
    a = re.findall(r"^diff --git a/(.*?) b/", patch_text, re.M)
    b = re.findall(r"^diff --git a/.*? b/(.*)$", patch_text, re.M)
    return {p.strip() for p in (a + b) if p.strip()}


BUNDLE_MARKERS = ("task.toml", "instruction.md", "tests", "solution", "environment")


def looks_like_bundle(d):
    """A task bundle, recognised by its harness files - so one missing task.toml is still found
    and the file checks can name what is missing instead of reporting no bundle at all."""
    return any(os.path.exists(os.path.join(d, m)) for m in BUNDLE_MARKERS)


def task_dirs(tasks):
    """Every bundle in a Tasks/ folder: Tasks/ itself (V1) or each Tasks/<task_id>/ (V2)."""
    if looks_like_bundle(tasks):
        return [tasks]
    return sorted(os.path.join(tasks, d) for d in os.listdir(tasks)
                  if os.path.isdir(os.path.join(tasks, d)) and looks_like_bundle(os.path.join(tasks, d)))


def find_tasks_root(root):
    """Return (deliverables_root, bundle_dir); `root` may be the deliverables root, Tasks/, or
    the bundle itself. The bundle is Tasks/<task_id>/ in V2 (TASK101+) and Tasks/ in V1.
    bundle_dir is None when there is no bundle - or more than one, which is ambiguous."""
    root = os.path.normpath(root)
    tasks = root if os.path.basename(root) == "Tasks" else os.path.join(root, "Tasks")
    if os.path.isfile(os.path.join(root, "task.toml")) or (
            not os.path.isdir(tasks) and looks_like_bundle(root)):
        up = os.path.dirname(root)
        if os.path.basename(root) != "Tasks" and os.path.basename(up) == "Tasks":
            return os.path.dirname(up), root              # V2: <deliv>/Tasks/<task_id>
        return up, root                                   # V1 Tasks/, or a bare bundle
    if not os.path.isdir(tasks):
        return root, None
    found = task_dirs(tasks)
    if len(found) > 1:
        print(f"warning: {len(found)} task bundles under {tasks} - pass the one to check: "
              f"{[os.path.basename(f) for f in found]}", file=sys.stderr)
    return os.path.dirname(tasks), (found[0] if len(found) == 1 else None)


def layout_note(bundle):
    """Which layout the bundle was found in, for the report header."""
    if not bundle:
        return ""
    if os.path.basename(os.path.normpath(bundle)) == "Tasks":
        return "  (V1 layout: task.toml directly in Tasks/)"
    if os.path.basename(os.path.dirname(os.path.normpath(bundle))) == "Tasks":
        return "  (V2 layout: Tasks/<task_id>/)"
    return ""


GROUPS = "ABDFHIRS"
findings = {g: [] for g in GROUPS}
fails = {g: 0 for g in GROUPS}


def add(g, msg, fail=False):
    findings[g].append(("[FAIL] " if fail else "") + msg)
    if fail:
        fails[g] += 1


# ------------------------------------------------------------------ checks
def check_A(deliv, tasks=None, md=None):
    """v2 #2 - Structure: Deliverables & Packaging."""
    for req in ("Tasks", "Trials", "Oracle", "Nop"):
        d = os.path.join(deliv, req)
        if not os.path.isdir(d):
            add("A", f"deliverable folder `{req}/` missing at root", fail=True)
        tgz = os.path.join(deliv, req + ".tar.gz")
        if not os.path.exists(tgz):
            add("A", f"archive `{req}.tar.gz` missing at root")
    tdir = os.path.join(deliv, "Tasks")
    if os.path.isdir(tdir):
        # run folders are root siblings: never inside Tasks/, nor inside a V2 Tasks/<task_id>/
        for where in [tdir] + ([tasks] if tasks and os.path.normpath(tasks) != tdir else []):
            rel = os.path.relpath(where, deliv).replace(os.sep, "/")
            for nested in ("Trials", "Oracle", "Nop"):
                if os.path.isdir(os.path.join(where, nested)):
                    add("A", f"`{nested}/` is nested inside `{rel}/` (must be a root sibling)",
                        fail=True)
        bundles = task_dirs(tdir)
        if len(bundles) > 1:
            add("A", f"`Tasks/` holds {len(bundles)} task bundles "
                     f"{[os.path.basename(b) for b in bundles]} - deliver exactly one", fail=True)
        elif bundles and bundles[0] != tdir:              # V2: Tasks/<task_id>/
            name = os.path.basename(bundles[0])
            extra = sorted(set(os.listdir(tdir)) - {name})
            if extra:
                add("A", f"`Tasks/` holds {extra} beside the task folder `{name}/` - V2 ships "
                         f"only `Tasks/<task_id>/`")
            tid = (md or {}).get("task_id")
            if tid and name != tid:
                add("A", f"task folder `Tasks/{name}/` is not named after task_id `{tid}` "
                         f"(V2 uses `Tasks/<task_id>/`) - confirm")
    for name in os.listdir(deliv) if os.path.isdir(deliv) else []:
        if name.lower() == "tasks" and name != "Tasks":
            add("A", f"folder `{name}` is mis-cased (must be capital-T `Tasks`)", fail=True)
    if not any(findings["A"]):
        add("A", "four deliverables present, sibling, correctly named")


def check_B(tasks):
    """v2 #1 - Structure: Task Bundle Files (+ poster decode feeds v2 #4)."""
    if not tasks:
        add("B", "no task bundle found (Tasks/<task_id>/ in V2, Tasks/ in V1) - cannot check "
                 "bundle files", fail=True)
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
                    add("B", f"poster `{f}` does not decode (bad signature) [feeds v2 #4]", fail=True)
    if not any(x for x in findings["B"] if x.startswith("[FAIL]")):
        add("B", "all required bundle files present, non-empty, valid; posters decode")


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
        add("D", f"fix.patch touches source-only paths, equal to files_edited ({sorted(paths)})")


def collect_test_source(tasks, conf):
    """Test source text = existing test files + added lines of test.patch."""
    text = ""
    for tf in (conf or {}).get("test_files") or []:
        t = read(os.path.join(tasks, tf))
        if t:
            text += "\n" + t
    patch = read(os.path.join(tasks, "tests/test.patch")) or ""
    text += "\n" + "\n".join(l[1:] for l in patch.splitlines() if l.startswith("+"))
    return text


def check_F(tasks, conf, md):
    """v2 #10 - Tests: f2p/p2p Identifier Validity."""
    if not tasks:
        return
    src = collect_test_source(tasks, conf)
    ids = list((conf or {}).get("f2p") or []) + list((conf or {}).get("p2p") or [])
    for ident in ids:
        n = src.count(ident)
        if n == 0:
            toks = [t for t in re.split(r"[-_]", ident) if len(t) > 1]
            present = [t for t in toks if t in src]
            if len(present) >= max(2, len(toks) - 2):
                add("F", f"identifier `{ident}` not found verbatim but its tokens {present} appear "
                         f"- likely a DYNAMIC test name; confirm it resolves to exactly one test")
            else:
                add("F", f"identifier `{ident}` not found in test source (tokens present: "
                         f"{present}) - confirm it resolves to exactly one test")
        elif n > 1:
            add("F", f"identifier `{ident}` appears {n}x in test source (may be ambiguous)")
        for other in ids:
            if other != ident and ident in other:
                add("F", f"identifier `{ident}` is a SUBSTRING of `{other}` - a substring "
                         f"matcher will collide (known real bug)", fail=True)
    # config.json f2p/p2p must equal task.toml f2p/p2p (part of the v2 #10 Fail condition)
    for key in ("f2p", "p2p"):
        c = set((conf or {}).get(key) or [])
        t = set(md.get(key) or [])
        if t and c != t:
            add("F", f"{key}: config.json {sorted(c)} != task.toml {sorted(t)}", fail=True)
    if not any(x for x in findings["F"] if x.startswith("[FAIL]")):
        add("F", "all f2p/p2p identifiers resolve and match between config.json and task.toml")


def check_H(md):
    """v2 #5 - Metadata: task_type Accuracy (value only; poster match is manual)."""
    tt = md.get("task_type")
    if not tt:
        add("H", "task_type missing from task.toml", fail=True)
    elif tt not in SEVEN_TYPES:
        add("H", f"task_type `{tt}` not one of the seven allowed values", fail=True)
    else:
        add("H", f"task_type `{tt}` is a valid value (confirm it MATCHES the image in Step 5)")


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
                 "(confirm evidence_bundle too - a lone mismatch there is a v2 #6 Non-Fail)")


def check_R(tasks, md, conf):
    """v3 - Rubrics: rubrics.json present, parses, well-formed (light structural check).

    The FULL audit (schema value, task-id consistency across the bundle, and the six
    'Rules for rubrics') lives in the dedicated v3 component check_rubrics.py. Here we only
    confirm the file exists, parses, and has a non-empty `criteria` list of {id, criterion}."""
    if not tasks:
        return
    rp = os.path.join(tasks, "tests/rubrics.json")
    if not os.path.exists(rp):
        add("R", "tests/rubrics.json MISSING (v3 requires it - a real rubric or the always-pass "
                 "stub)", fail=True)
        return
    if os.path.getsize(rp) == 0:
        add("R", "tests/rubrics.json is EMPTY", fail=True)
        return
    data, err = load_json(rp)
    if err:
        add("R", f"tests/rubrics.json does not parse as JSON: {err}", fail=True)
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
            fail=True)
    if not any(x for x in findings["R"] if x.startswith("[FAIL]")):
        add("R", "rubrics.json present, parses, criteria well-formed, task id consistent "
                 "(run check_rubrics.py for the full rule-by-rule audit + manual ACCURATE check)")


def check_S(tasks, md, conf):
    """v2 #15 (ADVISORY) - multi-subject scope aid for Step 8.

    Flags when the golden fix / f2p span more than one distinct source *subject* (module stem),
    so the reviewer builds the Step 8 scope-coverage table and confirms EACH subject is anchored
    in instruction.md or the image. A subject the instruction never names is an
    unsolvable-by-perception cut -> #15 Fail. This is IMAGE-BLIND, so it never emits [FAIL];
    it only tells you where to look."""
    if not tasks:
        return
    instr = (read(os.path.join(tasks, "instruction.md")) or "").lower()
    # distinct fix subjects = stem of each edited source file (e.g. eternity-points, infinity-points)
    fe = md.get("files_edited") or list(diff_paths(read(os.path.join(tasks, "solution/fix.patch"))))
    stems = sorted({os.path.splitext(os.path.basename(p))[0] for p in fe})
    if len(stems) > 1:
        add("S", f"fix.patch spans {len(stems)} distinct subjects {stems} - build the Step 8 "
                 f"scope-coverage table and confirm EACH is referenced by instruction.md or the "
                 f"image (an unreferenced subject = unsolvable-by-perception cut -> #15 Fail)")
        for st in stems:
            # crude anchor heuristic: is any word of the stem present in the instruction text?
            words = [w for w in re.split(r"[-_]", st) if len(w) > 2]
            anchored = [w for w in words if w in instr]
            if not anchored:
                add("S", f"  subject `{st}` has NO word anchored in instruction.md "
                         f"(check the image; if absent there too -> #15 Fail)")
    # distinct f2p subject prefixes (e.g. ip-*, ep-*) vs instruction mentions
    f2p = (conf or {}).get("f2p") or md.get("f2p") or []
    prefixes = sorted({fid.split("-", 1)[0] for fid in f2p if "-" in fid})
    if len(prefixes) > 1:
        add("S", f"f2p ids span {len(prefixes)} subject prefixes {prefixes} - confirm each maps to "
                 f"a symptom shown in instruction.md or the image (Step 8 / #15)")
    if not findings["S"]:
        add("S", "fix + f2p appear single-subject (still confirm the Step 8 anchor by hand)")


# ------------------------------------------------------------------- main
GROUP_TITLES = {
    "A": "v2 #2  Structure - Deliverables & Packaging",
    "B": "v2 #1  Structure - Task Bundle Files (+ #4 poster decode)",
    "D": "v2 #8  Golden Fix - Source-Only Scope",
    "F": "v2 #10 Tests - f2p/p2p Identifier Validity",
    "H": "v2 #5  Metadata - task_type Accuracy (value)",
    "I": "v2 #6  Evidence - Chain Consistency",
    "R": "v3     Rubrics - rubrics.json present & parses (full audit: check_rubrics.py)",
    "S": "v2 #15 Hardening - Real & Feasible (ADVISORY: multi-subject scope aid)",
}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    root = sys.argv[1]
    deliv, tasks = find_tasks_root(root)
    md = (parse_toml(os.path.join(tasks, "task.toml")) or {}).get("metadata", {}) if tasks else {}
    conf, _ = load_json(os.path.join(tasks, "tests/config.json")) if tasks else (None, None)

    check_A(deliv, tasks, md)
    check_B(tasks)
    check_D(tasks, md)
    check_F(tasks, conf, md)
    check_H(md)
    check_I(tasks)
    check_R(tasks, md, conf)
    check_S(tasks, md, conf)

    print(f"\nVarmint Sheriffs static pre-checks (v3.1) - {os.path.abspath(root)}")
    print(f"task bundle = {tasks or 'NOT FOUND'}{layout_note(tasks)}\n")
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


if __name__ == "__main__":
    main()
    # MM_SWE_QC: propagate hard failures to the orchestrator.
    sys.exit(1 if sum(fails.values()) else 0)
