#!/usr/bin/env python3
"""MM SWE QC FIX (SANDBOX) - check, plan, apply, verify. For CBs working in the sandbox.

NO API KEY IS NEEDED ANYWHERE IN THIS FLOW. The rubric judge is a sub-agent that makes no model
call, so oracle and nop run keyless; the four checks are stdlib-only with no network; and
--emit-graders writes prompts for YOUR OWN agent to grade rather than calling an API. This skill
never runs the trial, which is the only step that would need credentials.

Harbor is never invoked directly: every run goes through the MM SWE runner
(`mm_run.sh`, the same commands you already use for oracle/nop/trial), resolved in this order:
    $MM_RUNNER  ->  ~/.claude/skills/mmswe-runner/mm_run.sh  ->  the copy bundled in runner/
The bundled copy is the one WITH `rescore`, so the rubric verdict can actually be folded in.

SELF-CONTAINED: the QC checks ship inside this skill (checks/), so it works on its own with
nothing else installed. If MM_SWE_QC happens to be installed it is ignored - the bundled copy
always wins, so a fix is never planned against a different version of the checks than the one
that reported the finding.

FIVE COMMANDS

    fix.py auto   <root> [--no-verify]          apply every AUTO fix, ALWAYS reproduce the gate
                                                (oracle+nop), escalate only what needs a human.
                                                THE NORMAL ENTRY POINT.
    fix.py qc     <root>                        the full QC report, no edits
    fix.py plan   <root> [--out plan.json]      classify every fixable finding
    fix.py apply  <root> --plan plan.json [--approve ID,ID|--approve-all-auto] [--verify]
    fix.py verify <root>                        reproduce the gate only (oracle + nop)
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

LAYOUT
    <root> may be the deliverables root, Tasks/, or the bundle itself. The bundle - the folder
    holding task.toml - is Tasks/<task_id>/ in V2 (TASK101+) and Tasks/ in V1. Every fix and the
    whitelist act on the bundle; FIX_REPORT.md and the Oracle/Nop runs live in the root, beside
    Tasks/, never inside it.

SAFETY
    * snapshot of the bundle taken before any edit, OUTSIDE it; restored on regression
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
TEMPLATE_VERIFIER_V2 = os.path.join(TEMPLATE, "tests", "verifier_rubric_gate_v2.py")
TEMPLATE_CONFIG = os.path.join(TEMPLATE, "tests", "config_required_keys.json")
# qc_judge.py compares judge.py against the template; point it at our bundled copy so the
# byte-identity check works with nothing else installed.
os.environ.setdefault("MM_RUBRIC_TEMPLATE", TEMPLATE_JUDGE)

# Path SET allowed inside the bundle (Tasks/<task_id>/ in V2). Contents may vary; membership may not.
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
    """The bundle for the deliverables root, Tasks/, or the bundle itself: Tasks/<task_id>/ in
    V2 (TASK101+), Tasks/ in V1. None when there is none, or more than one (ambiguous)."""
    root = os.path.abspath(root)
    tasks = root if os.path.basename(root) == "Tasks" else os.path.join(root, "Tasks")
    for c in (tasks, root):
        if os.path.isfile(os.path.join(c, "task.toml")):
            return c
    if os.path.isdir(tasks):
        found = [os.path.join(tasks, d) for d in sorted(os.listdir(tasks))
                 if os.path.isfile(os.path.join(tasks, d, "task.toml"))]
        if len(found) == 1:
            return found[0]
        if found:
            print(f"error: {len(found)} task bundles under {tasks} - pass the one to fix: "
                  f"{[os.path.basename(f) for f in found]}", file=sys.stderr)
    return None


def deliv_root(tasks):
    """The folder holding Tasks/ (and Oracle/ Nop/ Trials/) for a bundle of either layout."""
    tasks = os.path.abspath(tasks)
    up = os.path.dirname(tasks)
    if os.path.basename(tasks) != "Tasks" and os.path.basename(up) == "Tasks":
        return os.path.dirname(up)                    # V2: <root>/Tasks/<task_id>
    return up                                         # V1: <root>/Tasks


def rel_paths(tasks):
    # always "/"-separated: the whitelist and JUNK patterns are, and Windows relpath is not
    out = set()
    for dp, dn, fn in os.walk(tasks):
        for f in fn:
            out.add(os.path.relpath(os.path.join(dp, f), tasks).replace(os.sep, "/"))
        for d in dn:
            out.add(os.path.relpath(os.path.join(dp, d), tasks).replace(os.sep, "/") + "/")
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
                open(p, "w", newline="\n").write(re.sub(r"\n{3,}", "\n\n", s))
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
                json.dump(d, open(p, "w", newline="\n"), indent=2); open(p, "a", newline="\n").write("\n")
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
                json.dump(d, open(p, "w", newline="\n"), indent=2); open(p, "a", newline="\n").write("\n")
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
        # files only: assets/bugs/ holds the injected-bug patches the Dockerfile applies and
        # then deletes from the image (hardening.md) - build input, not agent-visible evidence
        unused = [f for f in sorted(os.listdir(adir))
                  if f != "ASSET_MANIFEST.json" and os.path.isfile(os.path.join(adir, f))
                  and f not in refs]
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
                m = re.search(r"^python3 /tests/verifier\.py[^\n]*$", b, re.M)
                if m and "REPORTS" not in b:
                    # V2 harness (TASK101+): there is no REPORTS array, and the call carries
                    # its own logging (`2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"`). The
                    # template's call line would drop both, so keep the task's own call, hand
                    # it --rubric, and insert only the judge half of the block above it.
                    call, done = m.group(0), []
                    judge = ""
                    if "judge.py" not in b:
                        judge = blk[:blk.rindex("python3 /tests/verifier.py")].rstrip() + "\n\n"
                        done.append("inserted the template judge block")
                    if "--rubric" not in call:
                        call = call.replace("/tests/verifier.py",
                                            '/tests/verifier.py --rubric "${RUBRIC:-}"', 1)
                        done.append("passed --rubric to the task's own verifier call")
                    if not done:
                        return "left test.sh unchanged - custom judge wiring, fix it by hand"
                    # newline="\n": text mode on Windows writes CRLF, and a CRLF test.sh
                    # breaks bash in the container (`set: pipefail\r: invalid option`)
                    open(p2, "w", newline="\n").write(b[:m.start()] + judge + call + b[m.end():])
                    return "; ".join(done)
                # replace the plain verifier invocation with block + rubric-aware invocation
                if m:
                    tail = b[m.end():].lstrip("\n")
                    b = b[:m.start()] + blk.rstrip() + "\n" + (("\n" + tail) if tail else "")
                else:
                    b = b.rstrip() + "\n\n" + blk
                open(p2, "w", newline="\n").write(b)
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
            # The V2 harness verifier (TASK101+) already writes a flat reward.json plus
            # reward_detail.json; its gate is a three-edit proposal, not the V1 reward writer.
            v2 = "reward_detail.json" in vb and os.path.isfile(TEMPLATE_VERIFIER_V2)
            tpl = TEMPLATE_VERIFIER_V2 if v2 else TEMPLATE_VERIFIER
            fixes.append(Fix(
                # kind=never: approving it only PRINTED the block, so asking bought nothing but
                # a prompt. Report it and move on; merging is a human edit either way.
                "verifier_rubric", "tests/verifier.py rubric gate incomplete", "never", "B", gaps,
                "verifier.py carries TASK-SPECIFIC scoring logic, so it is never auto-patched: a "
                "blind insert could silently change what the task grades. The canonical block is "
                f"in {os.path.relpath(tpl, HERE)} - merge it by hand, then re-run.",
                lambda t, _tpl=tpl: (print(open(_tpl).read()),
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
                    json.dump(ordered, open(p2, "w", newline="\n"), indent=2); open(p2, "a", newline="\n").write("\n")
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
BUNDLED_RUNNER = os.path.join(HERE, "runner", "mm_run.sh")
# A whole harbor run: image build + tests. Generous, but bounded - an unbounded run leaves a CB
# staring at nothing with no way to tell "slow" from "hung".
RUN_TIMEOUT = int(os.environ.get("MM_RUN_TIMEOUT", "5400"))


def resolve_runner():
    """$MM_RUNNER -> the installed mmswe-runner -> the copy bundled with this skill."""
    for cand in (os.environ.get("MM_RUNNER"),
                 os.path.expanduser("~/.claude/skills/mmswe-runner/mm_run.sh"),
                 BUNDLED_RUNNER):
        if cand and os.path.isfile(cand):
            return cand
    return None


def read_reward(run_dir):
    """Authoritative: the reward file harbor wrote, not a line scraped from stdout."""
    import glob
    for pat in ("**/verifier/reward.txt", "**/reward.txt"):
        for f in sorted(glob.glob(os.path.join(run_dir, pat), recursive=True)):
            try:
                return open(f).read().strip(), f
            except Exception:
                pass
    return None, None


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
QC_COMPONENTS = [("structure", "qc_structure.py"), ("rubrics", "qc_rubrics.py"),
                 ("judge", "qc_judge.py"), ("gate", "qc_gate.py")]


def qc_state(root):
    """{component: exit_code} for the four static checks. Used to prove a fix actually landed."""
    out = {}
    for name, script in QC_COMPONENTS:
        sp = os.path.join(CHECKS, script)
        if not os.path.isfile(sp):
            out[name] = None; continue
        try:
            r = subprocess.run([sys.executable, sp, root], capture_output=True, text=True,
                               timeout=300)
            out[name] = r.returncode
        except Exception:
            out[name] = None
    return out


def print_qc_delta(before, after):
    """Report before -> after per component. A fix is not assumed to have worked."""
    if all(v is None for v in after.values()):
        print(f"\n  QC re-check UNAVAILABLE - no bundled checks found at {CHECKS}. The fixes were "
              f"applied but nothing confirmed they landed; re-run `fix.py qc <root>` from a "
              f"complete install before trusting them.")
        return 0
    print("\n  QC re-check (static components, before -> after):")
    verdict = lambda v: "?" if v is None else ("PASS" if v == 0 else "findings")
    improved = regressed = 0
    for name, _ in QC_COMPONENTS:
        b, a2 = before.get(name), after.get(name)
        mark = ""
        if b != a2:
            if b not in (0, None) and a2 == 0:
                mark = "  <-- FIXED"; improved += 1
            elif b == 0 and a2 not in (0, None):
                mark = "  <-- REGRESSED"; regressed += 1
            else:
                mark = "  <-- changed"
        print(f"    {name:10} {verdict(b):9} -> {verdict(a2):9}{mark}")
    if regressed:
        print("    WARNING: a component that passed before now has findings - inspect before "
              "trusting this fix.")
    elif improved:
        print(f"    {improved} component(s) now clean.")
    else:
        print("    no component changed state - the fixes were cosmetic, or the remaining "
              "findings are ones the fixer cannot repair (kind=never / ASK).")
    return regressed


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
    qc_before = qc_state(a.root)
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
    qc_after = qc_state(a.root)
    regressed = print_qc_delta(qc_before, qc_after)
    report = write_report(a.root, tasks, applied, worst, snap, qc_before, qc_after)
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


def verify(tasks, root, modes=("oracle", "nop")):
    """0 = verified, 1 = regressed, 2 = COULD NOT verify (never silently 'ok').

    Runs through the MM SWE runner, exactly the commands a CB uses by hand. The TRIAL is never
    run here: it is the only step needing credentials, and re-running it is a human decision
    because it costs a real model call.
    """
    runner = resolve_runner()
    if not runner:
        print("  WARNING: no MM SWE runner found - oracle/nop were NOT verified.\n"
              "           Install the mmswe-runner skill, set $MM_RUNNER, or re-run without\n"
              "           --verify to accept that nothing was checked.", file=sys.stderr)
        return 2
    print(f"  runner: {runner}")
    expect = {"oracle": "1.0", "nop": "0.0"}
    for mode in modes:
        want = expect[mode]
        print(f"  {mode}: expecting {want} (the trial is never run by this skill)")
        try:
            r = subprocess.run(["bash", runner, tasks, mode],
                               capture_output=True, text=True, timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            print(f"  COULD NOT VERIFY: {mode} exceeded {RUN_TIMEOUT}s. Raise $MM_RUN_TIMEOUT, "
                  f"or run `bash {os.path.basename(runner)} <task> {mode}` yourself.",
                  file=sys.stderr)
            return 2
        out = r.stdout + r.stderr
        # the runner writes <root>/Oracle|Nop, beside Tasks/ - in V2 that is two levels up
        run_dir = os.path.join(deliv_root(tasks), mode.capitalize())
        got, src = read_reward(run_dir)
        if got is None:                       # fall back to the log line
            m = re.search(r"reward(?:\.txt)?\s*=?\s*([0-9.]+)", out)
            got, src = (m.group(1) if m else None), "stdout"
        if got is None:
            print(f"  COULD NOT VERIFY: {mode} produced no reward. Last output:\n"
                  + "\n".join("    " + l for l in out.strip().splitlines()[-8:]), file=sys.stderr)
            return 2
        print(f"    {mode} reward = {got}   (from {src})")
        if got != want:
            print(f"  REGRESSED: {mode} is {got}, expected {want}", file=sys.stderr)
            return 1
    return 0


def write_report(root, tasks, applied, worst, snap, qc_before=None, qc_after=None):
    # beside Tasks/, never inside it - in V2 dirname(bundle) IS Tasks/, which ships
    p = os.path.join(deliv_root(tasks), "FIX_REPORT.md")
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
        if qc_before and qc_after:
            fh.write("\n## QC re-check\n\n| component | before | after |\n|---|---|---|\n")
            v = lambda x: "?" if x is None else ("PASS" if x == 0 else "findings")
            for name, _ in QC_COMPONENTS:
                fh.write(f"| {name} | {v(qc_before.get(name))} | {v(qc_after.get(name))} |\n")
            fh.write("\nThe checks were re-run after fixing; this is measured, not assumed.\n")
        fh.write(f"\n## Trial\n\nWorst class applied: **{worst}**\n\n{verdict}\n\n"
                 "Classes: **A** verifier-side cosmetic · **B** rubric/judge only · "
                 "**C** agent-visible or measurement change.\n\n"
                 "## Still outstanding\n\n"
                 "- rubric criterion rewrites (kind=never) — authoring, do by hand\n"
                 "- ACCURATE: each criterion must be factually true of `solution/fix.patch`\n"
                 "- behavioural: a judge request appears, then `rescore` yields `rubric: \"pass\"`\n")
    return p


def cmd_auto(a):
    """Apply every AUTO fix without asking, ALWAYS verify oracle+nop, then report escalations.

    Verification is unconditional - including when nothing was fixed. A task that needed no
    repair can still have a broken gate, and "we changed nothing" is not evidence the gate
    holds. Pass --no-verify only when you knowingly accept an unverified result.
    """
    tasks = locate(a.root)
    if not tasks:
        print("error: no task.toml found", file=sys.stderr); return 2
    fixes = detect(tasks, a.root)
    auto = [f for f in fixes if f.kind == "auto"]
    ask = [f for f in fixes if f.kind == "ask"]
    never = [f for f in fixes if f.kind == "never"]

    rc = 0
    if not auto:
        print(f"\nMM SWE QC FIX - nothing to fix automatically in {tasks}")
    else:
        # apply WITHOUT verifying here; we verify once below so a no-op run is covered too
        a.approve, a.approve_all_auto, a.plan = None, True, None
        want_verify, a.verify = not getattr(a, "no_verify", False), False
        rc = cmd_apply(a)
        a.verify = want_verify
        if rc != 0:
            return rc

    if getattr(a, "no_verify", False):
        print("\n  --no-verify: oracle/nop were NOT run. The gate is unproven.")
    else:
        print("\n  verifying the gate (oracle + nop; the trial is never run) ...")
        vrc = verify(tasks, a.root)
        if vrc == 1:
            print("\n  GATE BROKEN after fixing - see above. The task is NOT ready.",
                  file=sys.stderr)
            rc = 4
        elif vrc == 2:
            print("\n  NOT VERIFIED - the gate could not be reproduced.", file=sys.stderr)
            rc = 5
        else:
            print("  gate holds: oracle 1.0 / nop 0.0")

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
    elif rc == 0:
        print("\n  Nothing needs a human.")
    return rc


def cmd_verify(a):
    """Reproduce the gate on its own - no fixing. Oracle and nop only, never the trial."""
    tasks = locate(a.root)
    if not tasks:
        print("error: no task.toml found", file=sys.stderr); return 2
    rc = verify(tasks, a.root)
    print({0: "\n  VERIFIED: oracle 1.0 / nop 0.0",
           1: "\n  FAILED: the gate does not hold",
           2: "\n  NOT VERIFIED: nothing was run"}[rc])
    return rc


def cmd_rollback(a):
    tasks = locate(a.root)
    if not tasks:
        print("error: no task.toml found", file=sys.stderr); return 2
    src = os.path.join(a.snapshot, "Tasks")
    if not os.path.isdir(src):
        print(f"error: no Tasks/ in {a.snapshot}", file=sys.stderr); return 2
    shutil.rmtree(tasks); shutil.copytree(src, tasks)
    print(f"  restored {tasks} from {a.snapshot}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pv = sub.add_parser("verify");   pv.add_argument("root")
    pa = sub.add_parser("auto");     pa.add_argument("root")
    # verification is ON by default; this is the deliberate opt-OUT
    pa.add_argument("--no-verify", action="store_true",
                    help="skip the oracle/nop run and accept an unproven gate")
    p0 = sub.add_parser("qc");       p0.add_argument("root"); p0.add_argument("--emit-graders")
    p1 = sub.add_parser("plan");     p1.add_argument("root"); p1.add_argument("--out")
    p2 = sub.add_parser("apply");    p2.add_argument("root"); p2.add_argument("--plan")
    p2.add_argument("--approve"); p2.add_argument("--approve-all-auto", action="store_true")
    p2.add_argument("--verify", action="store_true")
    p3 = sub.add_parser("rollback"); p3.add_argument("root"); p3.add_argument("--snapshot", required=True)
    a = ap.parse_args()
    return {"verify": cmd_verify, "auto": cmd_auto, "qc": cmd_qc, "plan": cmd_plan,
            "apply": cmd_apply, "rollback": cmd_rollback}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
