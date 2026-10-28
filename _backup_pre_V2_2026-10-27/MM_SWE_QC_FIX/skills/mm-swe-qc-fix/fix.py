#!/usr/bin/env python3
"""MM SWE QC FIX - check, plan, approve, apply.

SELF-CONTAINED: the QC checks ship inside this skill (checks/), so it works on its own with
nothing else installed. If MM_SWE_QC happens to be installed it is ignored - the bundled copy
always wins, so a fix is never planned against a different version of the checks than the one
that reported the finding.

FIVE COMMANDS

    fix.py auto   <root> [--verify]             apply every AUTO fix, escalate only what needs
                                                a human. THE NORMAL ENTRY POINT.
    fix.py qc     <root>                        the full QC report, no edits
    fix.py plan   <root> [--out plan.json]      classify every fixable finding
    fix.py apply  <root> --plan plan.json [--approve ID,ID|--approve-all-auto] [--verify]
    fix.py rollback <root> --snapshot DIR

THREE FIX KINDS
    auto   mechanical, no judgment. Applied when approved (or with --approve-all-auto).
    ask    a human must decide FIRST. Never applied without an explicit --approve of its id.
           Assets live here on purpose: an image may be the visual source the task depends on,
           so "unused" is never a safe inference.
    never  reported only. Changing it is authoring, not fixing.

TRIAL CLASSES - whether the existing Trials/ run survives the fix
    A  verifier-side cosmetic. The agent never saw it, scoring unchanged  -> keep the trial
    B  rubric/judge only. Trajectory still valid, only the rubric half is stale
                                                                          -> keep + `rescore`
    C  agent-visible or measurement change                                -> trial invalid, re-run
The plan reports the worst class present. Only A/B leave the trial salvageable, and even then
the human decides - the skill never silently keeps or discards a run.

SAFETY
    * snapshot of Tasks/ taken before any edit, OUTSIDE the bundle; restored on regression
    * canonical-layout whitelist: a fix may add a path the layout ALLOWS (judge_missing adds
      tests/judge.py); anything outside the layout aborts and rolls back
    * oracle (1.0) + nop (0.0) re-verified after applying; the trial is NEVER run. If the
      runner is absent the run exits 5 (NOT VERIFIED) rather than claiming success
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, hashlib, glob, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template")
TEMPLATE_JUDGE = os.path.join(TEMPLATE, "tests", "judge.py")
TEMPLATE_TESTSH = os.path.join(TEMPLATE, "tests", "test_sh_judge_block.sh")
TEMPLATE_VERIFIER = os.path.join(TEMPLATE, "tests", "verifier_reward_block.py")
TEMPLATE_CONFIG = os.path.join(TEMPLATE, "tests", "config_required_keys.json")
# qc_judge.py compares judge.py against the template; point it at our bundled copy so the
# byte-identity check works with nothing else installed.
os.environ.setdefault("MM_RUBRIC_TEMPLATE", TEMPLATE_JUDGE)

# Path SET allowed inside Tasks/. Contents may vary; membership may not.
CANON_EXACT = {"evidence_bundle.json", "instruction.md", "task.toml",
               "environment/Dockerfile",
               "tests/config.json", "tests/judge.py", "tests/rubrics.json",
               "tests/test.patch", "tests/test.sh", "tests/verifier.py"}
CANON_GLOB = ["environment/assets/*", "solution/*"]
JUNK = re.compile(r"(^|/)(__pycache__(/|$)|\.DS_Store$|node_modules(/|$))|\.pyc$")


# --------------------------------------------------------------------------- model
class Fix:
    def __init__(self, fid, title, kind, trial_class, evidence, why, action=None):
        self.id, self.title, self.kind = fid, title, kind
        self.trial_class, self.evidence, self.why = trial_class, evidence, why
        self.action = action                       # callable(tasks) -> str

    def as_dict(self):
        return {"id": self.id, "title": self.title, "kind": self.kind,
                "trial_class": self.trial_class, "evidence": self.evidence, "why": self.why}


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def locate(root):
    root = os.path.abspath(root)
    for c in (os.path.join(root, "Tasks"), root):
        if os.path.isfile(os.path.join(c, "task.toml")):
            return c
    return None


def rel_paths(tasks):
    out = set()
    for dp, dn, fn in os.walk(tasks):
        for f in fn:
            out.add(os.path.relpath(os.path.join(dp, f), tasks))
        for d in dn:
            out.add(os.path.relpath(os.path.join(dp, d), tasks) + "/")
    return out


def is_canonical(rel):
    r = rel.rstrip("/")
    if r in CANON_EXACT or r in {"environment", "tests", "solution", "environment/assets"}:
        return True
    return any(glob.fnmatch.fnmatch(r, g) for g in CANON_GLOB)


# ---------------------------------------------------------------------- detectors
def detect(tasks, root):
    fixes = []

    # --- junk -------------------------------------------------------------- A / auto
    junk = sorted(p for p in rel_paths(tasks) if JUNK.search(p))
    if junk:
        def rm_junk(t, _j=junk):
            removed = []
            for r in _j:
                p = os.path.join(t, r.rstrip("/"))
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True); removed.append(r)
                elif os.path.isfile(p):
                    os.remove(p); removed.append(r)
            return f"removed {len(removed)} junk path(s)"
        fixes.append(Fix("junk", "Build junk committed in the bundle", "auto", "A",
                         junk[:8], "A stale .pyc can shadow a deleted .py, and a deliverable "
                                   "should contain only authored files.", rm_junk))

    # --- empty non-canonical files ----------------------------------------- A / auto
    empties = sorted(p for p in rel_paths(tasks)
                     if not p.endswith("/") and not JUNK.search(p)
                     and not is_canonical(p) and os.path.getsize(os.path.join(tasks, p)) == 0)
    if empties:
        def rm_empty(t, _e=empties):
            for r in _e:
                os.remove(os.path.join(t, r))
            return f"removed {len(_e)} empty non-canonical file(s)"
        fixes.append(Fix("empty_noncanon", "Empty file(s) outside the canonical layout",
                         "auto", "A", empties,
                         "Not part of the bundle layout and carry no content.", rm_empty))

    # --- non-canonical, non-empty --------------------------- auto if clearly junk, else ask
    strays = sorted(p for p in rel_paths(tasks)
                    if not JUNK.search(p) and not is_canonical(p)
                    and p not in empties and not p.endswith("/"))
    # Files whose extension makes them unambiguously build/editor debris. Deleting these needs
    # no judgment, so gating them behind a question was friction without safety.
    KNOWN_DEBRIS = re.compile(r"\.(log|bak|orig|rej|tmp|swp|swo|pyc|zip|tar\.gz|tgz)$|~$", re.I)
    debris = [p for p in strays if KNOWN_DEBRIS.search(p)]
    strays = [p for p in strays if p not in debris]
    if debris:
        def rm_debris(t, _d=debris):
            for r in _d:
                os.remove(os.path.join(t, r))
            return f"removed {len(_d)} build/editor debris file(s)"
        fixes.append(Fix("debris", "Build/editor debris in the bundle", "auto", "A", debris,
                         "Unambiguous debris by extension (.log/.bak/.orig/.zip/...); not part "
                         "of the layout and never load-bearing.", rm_debris))
    if strays:
        fixes.append(Fix("stray_files", "File(s) outside the canonical layout", "ask", "C",
                         strays, "Not in the canonical bundle layout. They may still be load-"
                                 "bearing, so a human decides before anything is removed.",
                         lambda t, _s=strays: "removed " + ", ".join(
                             [_ for _ in _s if not os.remove(os.path.join(t, _))] or _s)))

    # --- task.toml legacy credentials -------------------------------------- A / auto
    tp = os.path.join(tasks, "task.toml")
    if os.path.isfile(tp):
        txt = open(tp, errors="replace").read()
        if "[verifier.env]" in txt or re.search(r"ANTHROPIC_|JUDGE_MODEL", txt):
            def strip_creds(t):
                p = os.path.join(t, "task.toml")
                s = open(p, errors="replace").read()
                s = re.sub(r"\n?#[^\n]*\n(?=\[verifier\.env\])", "\n", s)
                s = re.sub(r"\[verifier\.env\][^\[]*", "", s)
                s = re.sub(r"^\s*(ANTHROPIC_[A-Z_]+|JUDGE_MODEL)\s*=.*$\n?", "", s, flags=re.M)
                open(p, "w").write(re.sub(r"\n{3,}", "\n\n", s))
                return "stripped [verifier.env] / ANTHROPIC_* / JUDGE_MODEL"
            fixes.append(Fix("legacy_creds", "task.toml carries legacy judge credentials",
                             "auto", "A", ["[verifier.env] or ANTHROPIC_*/JUDGE_MODEL"],
                             "The judge is a sub-agent and calls no model; these are leftovers "
                             "from the retired api backend and mislead reviewers.", strip_creds))

    # --- config.json rubric_file ------------------------------------------- A / auto
    cp = os.path.join(tasks, "tests", "config.json")
    if os.path.isfile(cp) and os.path.isfile(os.path.join(tasks, "tests", "rubrics.json")):
        try:
            cfg = json.load(open(cp))
        except Exception:
            cfg = None
        if isinstance(cfg, dict) and cfg.get("rubric_file") != "rubrics.json":
            def set_rf(t):
                p = os.path.join(t, "tests", "config.json")
                d = json.load(open(p)); d["rubric_file"] = "rubrics.json"
                json.dump(d, open(p, "w"), indent=2); open(p, "a").write("\n")
                return 'set "rubric_file": "rubrics.json"'
            fixes.append(Fix("rubric_file", 'tests/config.json missing "rubric_file"',
                             "auto", "A", [f'rubric_file={cfg.get("rubric_file")!r}'],
                             "Without it the rubric is never picked up.", set_rf))

    # --- judge.py drift ----------------------------------------------------- B / auto
    jp = os.path.join(tasks, "tests", "judge.py")
    if os.path.isfile(TEMPLATE_JUDGE):
        if not os.path.isfile(jp):
            fixes.append(Fix("judge_missing", "tests/judge.py missing", "auto", "B",
                             ["tests/judge.py"], "The rubric cannot be graded without it.",
                             lambda t: (shutil.copy(TEMPLATE_JUDGE,
                                        os.path.join(t, "tests", "judge.py")),
                                        "installed judge.py from template")[1]))
        elif sha(jp) != sha(TEMPLATE_JUDGE):
            fixes.append(Fix("judge_drift", "tests/judge.py differs from the template",
                             "auto", "B", [f"sha {sha(jp)[:12]} != {sha(TEMPLATE_JUDGE)[:12]}"],
                             "An edited judge changes grading semantics invisibly.",
                             lambda t: (shutil.copy(TEMPLATE_JUDGE,
                                        os.path.join(t, "tests", "judge.py")),
                                        "restored judge.py from template")[1]))

    # --- rubrics task id ----------------------------------------------------- B / auto
    rp = os.path.join(tasks, "tests", "rubrics.json")
    if os.path.isfile(rp) and os.path.isfile(tp):
        try:
            rub = json.load(open(rp))
        except Exception:
            rub = None
        m = re.search(r'^\s*task_id\s*=\s*"([^"]+)"', open(tp, errors="replace").read(), re.M)
        if rub is not None and m and rub.get("task") != m.group(1):
            def fix_task(t, _want=m.group(1)):
                p = os.path.join(t, "tests", "rubrics.json")
                d = json.load(open(p)); d["task"] = _want
                json.dump(d, open(p, "w"), indent=2); open(p, "a").write("\n")
                return f'set rubrics.json task = "{_want}"'
            fixes.append(Fix("rubric_task_id", "rubrics.json task id disagrees with task.toml",
                             "auto", "B", [f'{rub.get("task")!r} != {m.group(1)!r}'],
                             "A mismatched id breaks the bundle cross-check.", fix_task))

    # --- unused assets --------------------------------------------- ask (never auto)
    adir = os.path.join(tasks, "environment", "assets")
    if os.path.isdir(adir):
        refs = ""
        for f in ("instruction.md", "evidence_bundle.json",
                  os.path.join("environment", "assets", "ASSET_MANIFEST.json")):
            p = os.path.join(tasks, f)
            if os.path.isfile(p):
                refs += open(p, errors="replace").read()
        unused = [f for f in sorted(os.listdir(adir))
                  if f != "ASSET_MANIFEST.json" and f not in refs]
        if unused:
            fixes.append(Fix(
                "unused_assets", "Asset(s) not referenced anywhere", "ask", "C", unused,
                "An unreferenced image may STILL be the visual source the task depends on - the "
                "model can be expected to read it, and the reference may be implicit. 'Unused' is "
                "not a safe inference, so this is never removed automatically. A human must "
                "confirm each file is genuinely dead before it goes. Removing one makes the "
                "existing trial invalid (class C).",
                lambda t, _u=unused: (
                    [os.remove(os.path.join(t, "environment", "assets", f)) for f in _u],
                    f"removed {len(_u)} unused asset(s)")[1]))

    # --- test.sh judge block ------------------------------------------------ B / auto
    ts = os.path.join(tasks, "tests", "test.sh")
    if os.path.isfile(ts) and os.path.isfile(TEMPLATE_TESTSH):
        body = open(ts, errors="replace").read()
        missing = []
        if "judge.py" not in body:
            missing.append("does not invoke judge.py")
        if "--rubric" not in body:
            missing.append("does not pass --rubric to the verifier")
        if "judge.py" in body and '|| echo ""' not in body:
            missing.append('missing the load-bearing `|| echo ""`')
        if missing:
            def patch_testsh(t):
                p2 = os.path.join(t, "tests", "test.sh")
                b = open(p2, errors="replace").read()
                blk = open(TEMPLATE_TESTSH).read()
                # replace the plain verifier invocation with block + rubric-aware invocation
                m = re.search(r"^python3 /tests/verifier\.py[^\n]*$", b, re.M)
                if m:
                    tail = b[m.end():].lstrip("\n")
                    b = b[:m.start()] + blk.rstrip() + "\n" + (("\n" + tail) if tail else "")
                else:
                    b = b.rstrip() + "\n\n" + blk
                open(p2, "w").write(b)
                return "inserted the canonical judge block from the template"
            fixes.append(Fix("test_sh_judge", "tests/test.sh judge wiring incomplete",
                             "auto", "B", missing,
                             "Without it the rubric is never run, or its verdict never reaches "
                             "the verifier. Restored from the template so every task wires it "
                             "the same way.", patch_testsh))

    # --- verifier.py rubric gate ---------------------------------- ask (propose only)
    vp = os.path.join(tasks, "tests", "verifier.py")
    if os.path.isfile(vp):
        vb = open(vp, errors="replace").read()
        gaps = []
        if "--rubric" not in vb:
            gaps.append("does not parse --rubric")
        if "reward.json" not in vb:
            gaps.append("does not write reward.json (no per-test f2p map)")
        if "--rubric" in vb and "0.5" not in vb:
            gaps.append("parses --rubric but no 0.5 gate value is visible")
        if gaps:
            fixes.append(Fix(
                # kind=never: approving it only PRINTED the block, so asking bought nothing but
                # a prompt. Report it and move on; merging is a human edit either way.
                "verifier_rubric", "tests/verifier.py rubric gate incomplete", "never", "B", gaps,
                "verifier.py carries TASK-SPECIFIC scoring logic, so it is never auto-patched: a "
                "blind insert could silently change what the task grades. The canonical block is "
                f"in {os.path.relpath(TEMPLATE_VERIFIER, HERE)} - merge it by hand, then re-run.",
                lambda t: (print(open(TEMPLATE_VERIFIER).read()),
                           "printed the canonical block for manual merge")[1]))

    # --- rubrics.json shape --------------------------------------------------- B / auto
    if os.path.isfile(rp):
        try:
            rub2 = json.load(open(rp))
        except Exception:
            rub2 = None
        if isinstance(rub2, dict):
            # BOTH schema ids are in live use across good tasks (3x rubrics.schema/v1,
            # 2x projectbench.rubrics/v1), and the review side validates against a SET of
            # known values. Rewriting a recognised id would edit a valid file, so only a
            # missing or unrecognised schema is a finding.
            KNOWN_SCHEMAS = {"rubrics.schema/v1", "projectbench.rubrics/v1"}
            shape = []
            if not rub2.get("schema"):
                shape.append("no `schema` key")
            elif rub2.get("schema") not in KNOWN_SCHEMAS:
                shape.append(f'schema={rub2.get("schema")!r} is not one of {sorted(KNOWN_SCHEMAS)}')
            if "description" not in rub2:
                shape.append("no `description` key")
            if shape:
                def fix_shape(t):
                    p2 = os.path.join(t, "tests", "rubrics.json")
                    d = json.load(open(p2))
                    if "description" not in d:
                        # a stub gets the sanctioned sentence; a real rubric gets a blank we do
                        # not invent content for
                        crit = d.get("criteria") or []
                        stub = len(crit) == 1 and str(crit[0].get("id", "")).lower() in (
                            "always_pass", "always-pass", "alwayspass")
                        d["description"] = ("No rubric needed — fully covered by behavioral tests."
                                            if stub else "")
                    d["schema"] = "rubrics.schema/v1"
                    ordered = {k: d[k] for k in ("schema", "task", "description", "criteria")
                               if k in d}
                    ordered.update({k: v for k, v in d.items() if k not in ordered})
                    json.dump(ordered, open(p2, "w"), indent=2); open(p2, "a").write("\n")
                    return "normalised rubrics.json to rubrics.schema/v1"
                fixes.append(Fix("rubrics_shape", "rubrics.json does not match the schema shape",
                                 "auto", "B", shape,
                                 "The bundle contract is {schema, task, description, criteria}; "
                                 "a missing schema key breaks downstream validation.", fix_shape))

    # --- rubric content: propose, never apply --------------------------------- never
    if os.path.isfile(rp):
        rq = run_qc("qc_rubrics.py", tasks)
        bad = [l.strip() for l in rq.splitlines() if re.match(r"\s*\[(Major|Moderate|Minor)", l)]
        if bad:
            fixes.append(Fix("rubric_quality", "Rubric criteria carry quality issues",
                             "never", "B", bad[:10],
                             "Rewording a criterion is authoring: a wrong 'fix' silently changes "
                             "what the task grades. Rewrite by hand, then re-run QC.", None))
    return fixes


CHECKS = os.path.join(HERE, "checks")          # bundled; this skill never reaches outside itself


def run_qc(script, tasks, extra=None):
    """Run one bundled check. Bundled-only on purpose: planning a fix against a different
    version of the checks than the one that produced the finding is how tools drift apart."""
    p = os.path.join(CHECKS, script)
    if not os.path.isfile(p):
        return f"[qc-fix] bundled check missing: {p}\n"
    r = subprocess.run([sys.executable, p, tasks] + (extra or []),
                       capture_output=True, text=True)
    return r.stdout + r.stderr


# ------------------------------------------------------------------------ commands
def cmd_qc(a):
    """The full QC report, exactly as MM_SWE_QC would produce it. Read-only."""
    tasks = locate(a.root)
    if not tasks:
        print("error: no task.toml found", file=sys.stderr); return 2
    p = os.path.join(CHECKS, "qc_all.py")
    if not os.path.isfile(p):
        print(f"error: bundled checks missing at {CHECKS}", file=sys.stderr); return 2
    args = [sys.executable, p, a.root]
    if a.emit_graders:
        args += ["--emit-graders", a.emit_graders]
    return subprocess.run(args).returncode


def cmd_plan(a):
    tasks = locate(a.root)
    if not tasks:
        print("error: no task.toml found", file=sys.stderr); return 2
    fixes = detect(tasks, a.root)
    VERDICT = {"A": "keep the existing trial as-is",
               "B": "keep the trajectory; re-grade the rubric and `rescore` (no container run)",
               "C": "the trial is INVALID and must be re-run"}
    # The trial verdict depends on WHAT YOU APPROVE, so report both paths rather than the
    # pessimistic union - otherwise an ASK item you decline still reads as "must re-run".
    auto_worst = max([f.trial_class for f in fixes if f.kind == "auto"] or ["A"])
    ask_worst = max([f.trial_class for f in fixes if f.kind == "ask"] or ["A"])
    plan = {"tasks_dir": tasks, "generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "fixes": [f.as_dict() for f in fixes],
            "auto_only_trial_class": auto_worst, "auto_only_verdict": VERDICT[auto_worst],
            "if_all_ask_approved_class": max(auto_worst, ask_worst),
            "if_all_ask_approved_verdict": VERDICT[max(auto_worst, ask_worst)]}
    print(f"\nMM SWE QC FIX - plan for {tasks}\n")
    if not fixes:
        print("  nothing to fix.")
    for f in fixes:
        tag = {"auto": "AUTO ", "ask": "ASK  ", "never": "NEVER"}[f.kind]
        print(f"  [{tag}] [{f.trial_class}] {f.id}: {f.title}")
        for e in f.evidence[:6]:
            print(f"            - {e}")
        print(f"            why: {f.why}")
    print(f"\n  TRIAL - depends on what you approve:")
    print(f"    approve AUTO only          -> class {auto_worst}: {VERDICT[auto_worst]}")
    if any(f.kind == "ask" for f in fixes):
        w = max(auto_worst, ask_worst)
        print(f"    + any ASK item             -> class {w}: {VERDICT[w]}")
    print("\n  AUTO  = mechanical, safe to apply once approved")
    print("  ASK   = a human must decide BEFORE it is applied (assets always land here)")
    print("  NEVER = reported only; fixing it is authoring")
    if a.out:
        json.dump(plan, open(a.out, "w"), indent=2); print(f"\n  wrote {a.out}")
    return 0


def cmd_apply(a):
    tasks = locate(a.root)
    if not tasks:
        print("error: no task.toml found", file=sys.stderr); return 2
    fixes = {f.id: f for f in detect(tasks, a.root)}
    approved = set()
    if a.approve:
        approved |= {x.strip() for x in a.approve.split(",") if x.strip()}
    if a.approve_all_auto:
        approved |= {i for i, f in fixes.items() if f.kind == "auto"}
    todo = [f for i, f in fixes.items() if i in approved and f.action]
    refused = [i for i in approved if i in fixes and fixes[i].kind == "never"]
    if refused:
        print(f"  refusing {refused}: kind=never, fixing it is authoring", file=sys.stderr)
        todo = [f for f in todo if f.id not in refused]
    if not todo:
        print("  nothing approved to apply."); return 0

    before = rel_paths(tasks)
    snap = tempfile.mkdtemp(prefix="qcfix_snapshot_")
    shutil.copytree(tasks, os.path.join(snap, "Tasks"))
    print(f"  snapshot -> {snap}")

    applied = []
    for f in todo:
        try:
            applied.append((f, f.action(tasks)))
            print(f"  applied {f.id}: {applied[-1][1]}")
        except Exception as exc:
            print(f"  ERROR applying {f.id}: {exc}", file=sys.stderr)

    # The guard is a CANONICAL-LAYOUT whitelist, not a no-new-files rule. Comparing only
    # against the pre-fix path set made every addition a violation -- including
    # tests/judge.py, which the layout explicitly allows and which the judge_missing fix
    # exists solely to add. That made judge_missing impossible to apply and, because the
    # rollback is wholesale, also reverted innocent fixes approved in the same run.
    added = {p for p in rel_paths(tasks) - before
             if not p.endswith("/") and not is_canonical(p)}
    if added:
        print(f"  WHITELIST VIOLATION - the fixer added non-canonical path(s) "
              f"{sorted(added)}; rolling back", file=sys.stderr)
        shutil.rmtree(tasks); shutil.copytree(os.path.join(snap, "Tasks"), tasks)
        return 3

    worst = max([f.trial_class for f, _ in applied] or ["A"])
    report = write_report(a.root, tasks, applied, worst, snap)
    print(f"  report -> {report}")

    if a.verify:
        rc = verify(tasks, a.root)
        if rc == 1:
            print("  oracle/nop REGRESSED - rolling back", file=sys.stderr)
            shutil.rmtree(tasks); shutil.copytree(os.path.join(snap, "Tasks"), tasks)
            return 4
        if rc == 2:
            # Could not verify. The fixes are sound as far as we know, so they stay applied,
            # but the run must not report success -- otherwise "verified" means nothing.
            print(f"\n  worst applied trial class: {worst}")
            print("  NOT VERIFIED - fixes applied but oracle/nop were never run.",
                  file=sys.stderr)
            return 5
    print(f"\n  worst applied trial class: {worst}")
    return 0


def verify(tasks, root):
    """0 = verified, 1 = regressed, 2 = COULD NOT verify (never silently 'ok')."""
    runner = os.path.expanduser("~/.claude/skills/mmswe-runner/mm_run.sh")
    if not os.path.isfile(runner):
        # Returning 0 here made `apply --verify` print a clean exit having verified nothing,
        # so a fix looked oracle/nop-checked when no container had ever run.
        print("  WARNING: mm_run.sh not installed - oracle/nop were NOT verified. "
              "Install the mmswe-runner skill, or re-run without --verify to accept that.",
              file=sys.stderr)
        return 2
    for mode, want in (("oracle", "1.0"), ("nop", "0.0")):
        print(f"  verifying {mode} (expect {want}) - the trial is never run")
        r = subprocess.run(["bash", runner, tasks, mode], capture_output=True, text=True)
        out = r.stdout + r.stderr
        m = re.search(r"reward(?:\.txt)?\s*=?\s*([0-9.]+)", out)
        got = m.group(1) if m else "?"
        print(f"    {mode} reward = {got}")
        if got != want:
            return 1
    return 0


def write_report(root, tasks, applied, worst, snap):
    p = os.path.join(os.path.dirname(os.path.abspath(tasks)), "FIX_REPORT.md")
    verdict = {"A": "**Keep the existing trial.** Nothing the agent saw or that scoring depends "
                    "on changed.",
               "B": "**Keep the trajectory, but the rubric half of the score is stale.** Re-grade "
                    "the judge request and run `mm_run.sh <task> rescore --run <dir>`. No "
                    "container re-run needed.",
               "C": "**The trial is invalid and must be re-run.** Something agent-visible or "
                    "measurement-affecting changed."}[worst]
    with open(p, "w") as fh:
        fh.write(f"# QC FIX report\n\nTask: `{tasks}`  \n"
                 f"Generated: {datetime.datetime.now().isoformat(timespec='seconds')}  \n"
                 f"Snapshot (rollback point): `{snap}`\n\n## Applied\n\n")
        for f, res in applied:
            fh.write(f"- **{f.id}** [{f.trial_class}] {f.title} — {res}\n")
        fh.write(f"\n## Trial\n\nWorst class applied: **{worst}**\n\n{verdict}\n\n"
                 "Classes: **A** verifier-side cosmetic · **B** rubric/judge only · "
                 "**C** agent-visible or measurement change.\n\n"
                 "## Still outstanding\n\n"
                 "- rubric criterion rewrites (kind=never) — authoring, do by hand\n"
                 "- ACCURATE: each criterion must be factually true of `solution/fix.patch`\n"
                 "- behavioural: a judge request appears, then `rescore` yields `rubric: \"pass\"`\n")
    return p


def cmd_auto(a):
    """Apply every AUTO fix without asking, then report what (if anything) needs a human.

    The point of AUTO is that it needs no judgment - so asking about it was friction, not
    safety. This is the normal entry point; `plan`/`apply` remain for the cases where a
    human wants to see the plan first or approve an ASK item.
    """
    tasks = locate(a.root)
    if not tasks:
        print("error: no task.toml found", file=sys.stderr); return 2
    fixes = detect(tasks, a.root)
    auto = [f for f in fixes if f.kind == "auto"]
    ask = [f for f in fixes if f.kind == "ask"]
    never = [f for f in fixes if f.kind == "never"]

    if not auto:
        print(f"\nMM SWE QC FIX - nothing to fix automatically in {tasks}")
    else:
        a.approve, a.approve_all_auto, a.plan = None, True, None
        rc = cmd_apply(a)
        if rc != 0:
            return rc

    if ask or never:
        print("\n  ESCALATED - needs a human:")
        for f in ask:
            print(f"    [DECIDE] [{f.trial_class}] {f.id}: {f.title}")
            for e in f.evidence[:6]:
                print(f"               - {e}")
            print(f"               {f.why}")
            print(f"               apply with: fix.py apply \"{a.root}\" --approve {f.id}")
        for f in never:
            print(f"    [REPORT] [{f.trial_class}] {f.id}: {f.title} (authoring, not a fix)")
            for e in f.evidence[:4]:
                print(f"               - {e}")
    else:
        print("\n  Nothing needs a human.")
    return 0


def cmd_rollback(a):
    tasks = locate(a.root)
    src = os.path.join(a.snapshot, "Tasks")
    if not os.path.isdir(src):
        print(f"error: no Tasks/ in {a.snapshot}", file=sys.stderr); return 2
    shutil.rmtree(tasks); shutil.copytree(src, tasks)
    print(f"  restored {tasks} from {a.snapshot}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("auto");     pa.add_argument("root")
    pa.add_argument("--verify", action="store_true")
    p0 = sub.add_parser("qc");       p0.add_argument("root"); p0.add_argument("--emit-graders")
    p1 = sub.add_parser("plan");     p1.add_argument("root"); p1.add_argument("--out")
    p2 = sub.add_parser("apply");    p2.add_argument("root"); p2.add_argument("--plan")
    p2.add_argument("--approve"); p2.add_argument("--approve-all-auto", action="store_true")
    p2.add_argument("--verify", action="store_true")
    p3 = sub.add_parser("rollback"); p3.add_argument("root"); p3.add_argument("--snapshot", required=True)
    a = ap.parse_args()
    return {"auto": cmd_auto, "qc": cmd_qc, "plan": cmd_plan,
            "apply": cmd_apply, "rollback": cmd_rollback}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
