#!/usr/bin/env python3
"""MM SWE QC FIX (SANDBOX) - check, plan, apply, verify. For CBs working in the sandbox.

NO API KEY IS NEEDED ANYWHERE IN THIS FLOW. The rubric judge is a sub-agent that makes no model
call, so oracle and nop run keyless; the four checks are stdlib-only with no network; and
--emit-graders writes prompts for YOUR OWN agent to grade rather than calling an API. This skill
never runs the trial, which is the only step that would need credentials.

Harbor is never invoked directly: every run goes through the MM SWE runner
(`mm_run.sh`, the same commands you already use for oracle/nop/trial), resolved in this order:
    $MM_RUNNER  ->  ~/.claude/skills/mmswe-runner/mm_run.sh  (required for --run)
The bundled copy also has `rescore`, which this skill no longer drives - see
report_rubric_grading() for why the rubric half is settled by grading, not by folding.

SELF-CONTAINED: the QC checks ship inside this skill (checks/), so it works on its own with
nothing else installed. If MM_SWE_QC happens to be installed it is ignored - the bundled copy
always wins, so a fix is never planned against a different version of the checks than the one
that reported the finding.

NOTHING IS CHANGED OR RUN WITHOUT EXPLICIT AUTHORIZATION.

Two actions have a real cost, so each is authorized separately and neither happens by default:

    --apply     authorize writes to Tasks/   (create / delete / rewrite inside the bundle)
    --run       authorize the oracle+nop docker runs   ($MM_RUN_TIMEOUT, default 5400s)

Naming a fix is itself the approval - `apply --approve judge_drift` identifies exactly what will
change, so it needs nothing more. A BLANKET selection identifies nothing, so `--approve-all-auto`
(and `auto`, which uses it) additionally needs `--apply`.

`auto` used to apply every AUTO fix unprompted and then start docker. The snapshot and the
rollback made that recoverable, but recovery is not consent: by the time they help, the files
have already changed. So `auto` is now a DRY RUN that reports what it would do.

ONE AUDIT, NOT TWO. `qc` and a bare `auto` print the SAME complete report: the four checks'
findings AND the live repair plan, joined on finding id. They used to be separate commands, so
neither was complete on its own - `qc` never mentioned five of the fixes (debris, empty_noncanon,
stray_files, unused_assets, asset_not_in_instruction are detected only by detect()), and its `action:` column came from a
static hint table rather than a fix proven to apply. Both are read-only, so the split bought
nothing. Whichever you type, you cannot get a partial picture.

SIX COMMANDS

    fix.py qc     <root> [--phase P] [--verbose] [--no-report]
                                                THE COMPLETE AUDIT. Findings + repair plan.
                                                Read-only.
    fix.py auto   <root> [--apply] [--run]      the same audit, plus how to authorize. With
                                                --apply it fixes; with --run it reproduces the
                                                gate. THE NORMAL ENTRY POINT.
    fix.py plan   <root> [--out plan.json]      classify every fixable finding (machine-readable)
    fix.py apply  <root> [--approve ID,ID | --approve-all-auto --apply] [--verify]
    fix.py verify <root> --run                  reproduce the gate only (oracle + nop)
    fix.py rollback <root> --snapshot DIR

EXIT CODES
    0  everything asked for succeeded          4  the gate broke after fixing
    2  no task.toml found                      5  applied but NOT VERIFIED (gate unproven)
    3  canonical-layout violation, rolled back 6  DRY RUN - nothing was changed or run

FOUR FIX KINDS - who writes the bytes, NOT how important the fix is
    auto   mechanical, no judgment. Applied when approved (or with --approve-all-auto).
    agent  ONE known-correct repair that a SCRIPT must not perform. fix.py detects it, names the
           exact sites, and stops; the agent makes the edit following the RUBRIC_MODES.md section
           named in .playbook, then proves it with .verify. This is INSIDE the CB's single
           approval - it is not a second question. It is not `auto` because verifier.py carries
           task-specific scoring and judge.py the grading contract: a regex that floors a reward,
           or a blind block-merge, can silently change what the task grades, and a wrong "fix"
           there is worse than the defect because the number still looks like a score.
    ask    a human must decide FIRST. Never applied without an explicit --approve of its id.
           Assets live here on purpose: an image may be the visual source the task depends on,
           so "unused" is never a safe inference.
    never  reported only. Changing it is authoring, not fixing.

`agent` replaced the dead end. These three defects (the 0.5 reward ladder, a judge with no API
backend, the verifier reward block) used to be kind=never, so the skill reported them and STOPPED -
and `apply --approve` refused them. In practice that meant nobody fixed them, or a CB who is not a
harbor expert fixed them wrong. They always had exactly one correct repair, already written down in
RUBRIC_MODES.md; what was missing was permission for the agent to perform it and an obligation to
prove it.

TRIAL CLASSES - whether the existing Trials/ run survives the fix
    A  verifier-side cosmetic. The agent never saw it, scoring unchanged  -> keep the trial
    B  rubric/judge only. Trajectory still valid, but whether the golden fix still
       satisfies the rubric is open again          -> keep + re-check vs the golden fix
    C  agent-visible or measurement change                                -> trial invalid, re-run
The plan reports the worst class present. Only A/B leave the trial salvageable, and even then
the human decides - the skill never silently keeps or discards a run.

SAFETY
    * CONSENT FIRST: no write and no docker run without --apply / --run (see above). The
      guarantees below are the net under that, not a substitute for it.
    * snapshot of Tasks/ taken before any edit, OUTSIDE the bundle; restored on regression
    * canonical-layout whitelist: a fix may add a path the layout ALLOWS (judge_missing adds
      tests/judge.py); anything outside the layout aborts and rolls back
    * oracle (1.0) + nop (every f2p fails, every p2p passes) re-verified after applying
      WHEN --run was given; the trial is
      NEVER run. Unverified - whether because --run was withheld or the runner is absent - exits
      5 (NOT VERIFIED) rather than claiming success. "Not checked" never reads as "passed".
    * qc_report.json / FIX_REPORT.md / plan.json are derived output written outside Tasks/, so
      they are not gated. `qc --no-report` opts out for a strictly read-only run.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, hashlib, glob, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "checks"))
from qc_layout import (find_task_dir, deliverables_root, find_trial_dirs, trial_dir as _newest_trial,
                       job_dir, AmbiguousLayout)

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template")
TEMPLATE_JUDGE = os.path.join(TEMPLATE, "tests", "judge.py")
# What judge_missing INSTALLS, which is not the same file as the drift baseline.
#
# template/tests/judge.py is the sub-agent-only stub. Installing it now manufactures a blocking
# defect: qc_rubric_format requires an API backend (`call_eval_api`), and the stub has none -- so
# the auto-fix would repair "no judge" into "a judge that cannot grade in-band", which is the
# same class of bug that once had judge_missing creating half-wired Mode B tasks.
#
# reference/judge.py is byte-identical in BOTH reference tasks (one TypeScript, one JavaScript --
# same sha256), so it is task-agnostic, and it was verified grading in-band in a live oracle run
# and degrading correctly to the sub-agent request when its endpoint was killed.
REFERENCE_JUDGE = os.path.join(HERE, "reference", "judge.py")
INSTALL_JUDGE = REFERENCE_JUDGE if os.path.isfile(REFERENCE_JUDGE) else TEMPLATE_JUDGE
TEMPLATE_TESTSH = os.path.join(TEMPLATE, "tests", "test_sh_judge_block.sh")
TEMPLATE_SUBCAP = os.path.join(TEMPLATE, "tests", "submission_capture_block.sh")
TEMPLATE_VERIFIER = os.path.join(TEMPLATE, "tests", "verifier_reward_block.py")
TEMPLATE_CONFIG = os.path.join(TEMPLATE, "tests", "config_required_keys.json")
# qc_judge.py compares judge.py against the template; point it at our bundled copy so the
# byte-identity check works with nothing else installed.
# qc_judge's own drift check reads this. Point it at the REFERENCE for the same reason
# judge_drift uses it: against the stub, every correct task drifts, so the signal was noise.
os.environ.setdefault("MM_RUBRIC_TEMPLATE", INSTALL_JUDGE)

# Path SET allowed inside Tasks/. Contents may vary; membership may not.
# README.md is allowed, not required: harbor treats it as a task file in its own right (it is one of
# the three root files compute_content_hash covers - see qc_digest.HARBOR_ROOT_FILES), so a task
# that ships one is not carrying a stray, and offering to delete it would move the bundle digest.
CANON_EXACT = {"evidence_bundle.json", "instruction.md", "task.toml", "README.md",
               "environment/Dockerfile",
               "tests/config.json", "tests/judge.py", "tests/rubrics.json",
               "tests/test.patch", "tests/test.sh", "tests/verifier.py"}
# `environment/bugs/*` is layout, not litter. The defect patches are staged there and applied
# by environment/Dockerfile at build time, so they are load-bearing for the image the agent
# works in - and because the build context IS environment/, that is the only place a COPY can
# reach them from. Leaving them off this list reported every task that stages its defects this
# way as two stray files, and the offered action was to DELETE them.
CANON_GLOB = ["environment/assets/*", "environment/bugs/*", "solution/*"]
JUNK = re.compile(r"(^|/)(__pycache__(/|$)|__MACOSX(/|$)|\.DS_Store$|node_modules(/|$))|\.pyc$")


# --------------------------------------------------------------------------- model
class Fix:
    def __init__(self, fid, title, kind, trial_class, evidence, why, action=None,
                 playbook=None, verify=None):
        self.id, self.title, self.kind = fid, title, kind
        self.trial_class, self.evidence, self.why = trial_class, evidence, why
        self.action = action                       # callable(tasks) -> str
        # kind="agent" only. `playbook` names the section of RUBRIC_MODES.md that already documents
        # the repair -- a POINTER, never a restatement, so the instructions cannot drift from the
        # doc that owns them. `verify` is the command whose output must flip to [OK ] before the
        # agent may report the blocker cleared.
        self.playbook, self.verify = playbook, verify

    def as_dict(self):
        d = {"id": self.id, "title": self.title, "kind": self.kind,
             "trial_class": self.trial_class, "evidence": self.evidence, "why": self.why}
        if self.playbook:
            d["playbook"] = self.playbook
        if self.verify:
            d["verify"] = self.verify
        return d


def _one_arg_line(line):
    """Is this physical line exactly ONE quoted argument (plus indent and an optional `\\`)?

    Decides whether a new `printf` argument can be added as its own LINE or has to be spliced into
    an existing one. See the call site: getting it wrong strands the new argument between a
    continuation and the `&&` that followed it, and the Dockerfile stops parsing.
    """
    core = line.strip()
    if core.endswith("\\"):
        core = core[:-1].strip()
    return bool(re.fullmatch(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'", core))


def _arg_start(line, col):
    """The offset of the opening quote of the argument containing `col`, else `col` itself."""
    q = None
    start = col
    i = 0
    while i < col:
        ch = line[i]
        if ch == "\\":
            i += 2
            continue
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q, start = ch, i
        i += 1
    return start if q else col


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def locate(root):
    """The task dir: flat <root>/Tasks/task.toml or nested <root>/Tasks/<any-name>/task.toml, or
    the task dir itself. Several tasks under one Tasks/ is an error naming them, never a guess."""
    try:
        return find_task_dir(root)
    except AmbiguousLayout as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


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
    if r in CANON_EXACT or r in {"environment", "tests", "solution", "environment/assets",
                                 "environment/bugs"}:
        return True
    return any(glob.fnmatch.fnmatch(r, g) for g in CANON_GLOB)


def reward_domain_sites(tasks):
    """[(lineno, key, value)] for reward keys bound outside their closed set - the 0.5 ladder.

    IMPORTS THE CHECK'S OWN WALK rather than re-deriving it. Two reasons the duplicate would be
    worse than the coupling: the agent is told to edit exactly the lines listed here, so a second
    implementation that drifted would send it to the wrong place; and the AST walk is the whole
    point of the check (`reward = 0.5` is a defect, a docstring describing a legacy 0.5 rung and
    `round(x, 2)` are not - a regex cannot tell them apart).

    Returns [] on any import/parse failure: the check still reports the finding, and a fix that
    cannot name its sites should offer nothing rather than guess.
    """
    import ast
    vp = os.path.join(tasks, "tests", "verifier.py")
    if not os.path.isfile(vp):
        return []
    try:
        if CHECKS not in sys.path:
            sys.path.insert(0, CHECKS)
        from qc_rubric_format import (REWARD_DOMAIN, REWARD_WRITERS, assigned_name,
                                      result_constants)
        tree = ast.parse(open(vp, errors="replace").read())
    except Exception:
        return []

    bad = []

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
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in REWARD_WRITERS:
                if node.args:
                    audit("reward", node.args[0])
                for kw in node.keywords:
                    if kw.arg in REWARD_DOMAIN:
                        audit(kw.arg, kw.value)
        if isinstance(node, ast.Dict):
            for k, val in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value in REWARD_DOMAIN:
                    audit(k.value, val)
    return sorted(set(bad))


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

    # --- an f2p/p2p identifier that carries no test's full name ---------------------- A / auto
    #
    # WHY THIS IS MECHANICAL. The correct string is not a judgment call: the identifier resolves to
    # exactly ONE real test, and that test's name is the replacement. Nothing about the task's
    # meaning changes - the verifier already scored that same testcase through its containment
    # match, which is precisely why the truncation was invisible. What changes is that the
    # declaration now says so.
    #
    # AMBIGUOUS ONES ARE NOT REPAIRED HERE. When the identifier sits inside two or more test names
    # there is no derivable answer, only a choice, so check_F reports those as PENDING and this
    # offers nothing. Same rule for a name carrying a quote or a backslash: re-quoting it correctly
    # into both TOML and JSON is not worth guessing at, and getting it wrong corrupts two files
    # that must stay byte-identical in their f2p/p2p lists.
    #
    # TRIAL CLASS A, deliberately. The corrected identifier matches the same single testcase the
    # truncated one already matched, so no recorded reward moves. The bundle digest does move,
    # which sends oracle+nop through gate_needs_rerun() below - keyless, and the controls have to
    # agree with the bundle anyway.
    try:
        if CHECKS not in sys.path:
            sys.path.insert(0, CHECKS)
        from qc_structure import truncated_identifiers, parse_toml, load_json
        _conf, _ = load_json(os.path.join(tasks, "tests/config.json"))
        _md = (parse_toml(os.path.join(tasks, "task.toml")) or {}).get("metadata") or {}
        _trunc, _complete = truncated_identifiers(tasks, _conf, _md)
    except Exception:
        _trunc, _complete = [], False
    _rewrites, _unsafe = [], []
    for _ident, _leaf, _longer in _trunc:
        if len(_longer) != 1 or not _ident.endswith(_leaf):
            _unsafe.append(_ident); continue
        _real = _longer[0]
        if any(c in _real for c in '"\\'):
            _unsafe.append(_ident); continue
        _new = _ident[:len(_ident) - len(_leaf)] + _real
        # THE REWRITE MUST NOT DUPLICATE WHAT THE PREFIX ALREADY SAYS. `_leaf` is the tail this
        # splices `_real` over, but `_real` can itself carry a dotted owner the retained prefix
        # ALSO ends with - and then the splice says it twice. That produced
        # `...::TableCellNode.TableCellNode.constructor`, written into task.toml and
        # tests/config.json, on ids that were correct to begin with; re-running added another
        # copy each time, because nothing downstream re-reads the result. Anything that does not
        # come out carrying `_real` exactly once is not a repair anyone derived - hand it to the
        # CB instead of writing it.
        if _real in _ident or _new.count(_real) != 1:
            _unsafe.append(_ident); continue
        _rewrites.append((_ident, _new))
    if _rewrites:
        def fix_idents(t, _r=_rewrites):
            n = 0
            for rel in ("task.toml", "tests/config.json"):
                p = os.path.join(t, rel)
                txt = open(p, encoding="utf-8").read()
                before = txt
                for old, new in _r:
                    # The QUOTED literal, so a replacement can never land inside a longer
                    # identifier that merely contains this one. Both files quote with `"`.
                    txt = txt.replace('"%s"' % old, '"%s"' % new)
                if txt != before:
                    open(p, "w", encoding="utf-8").write(txt)
                    n += 1
            return "corrected %d identifier(s) in %d file(s)" % (len(_r), n)
        fixes.append(Fix("tests_ident_truncated", "f2p/p2p identifier(s) carry no test's full name",
                         "auto", "A",
                         ["%s\n      -> %s" % (o, n) for o, n in _rewrites],
                         "Each one names no test. It resolves only because tests/verifier.py "
                         "matches by containment, against a test whose name it carries in part - "
                         "so the reward reads as a pass while the declaration is wrong. Rewritten "
                         "in task.toml AND tests/config.json together, which the two must be.",
                         fix_idents))

    # --- BuildKit-only heredoc -> a portable RUN that writes the same file ------------- A / auto
    #
    # THE BODY IS ALREADY IN THE DOCKERFILE, which is what makes this a mechanical fix rather than an
    # authoring job: the fixer reads it at apply time and re-emits it, so it never needs to know what
    # the script contains, and no sidecar file is created. That last part is not a detail - the
    # canonical layout allows only `environment/Dockerfile` and `environment/assets/*`, so writing
    # `environment/obfuscate_harbor.py` would trip fix.py's own whitelist guard ("the fixer added
    # non-canonical path(s) ...; rolling back", exit 3) and, if it somehow survived, would surface for
    # the NEXT reviewer as a `stray_files` candidate whose offered action is to delete it - breaking
    # the build again, with a genuinely missing COPY source this time. Rewriting in place is legal
    # everywhere and needs no policy change.
    #
    #   COPY <<'PYEOF' /tmp/obfuscate_harbor.py     ->    RUN mkdir -p /tmp \
    #   import re, pathlib                                 && printf '%s\n' \
    #   ...                                                  'import re, pathlib' \
    #   PYEOF                                                ... \
    #                                                        > /tmp/obfuscate_harbor.py
    #
    # `printf '%s\n'` is exact for a QUOTED tag: %s applies no escape processing, so backslashes and
    # `%` in the body survive, and single-quoted arguments suppress every shell expansion - which is
    # what <<'TAG' means. It is also a shell builtin, so unlike `base64 -d` it needs nothing
    # installed, and unlike a base64 blob the script stays READABLE in the Dockerfile, which matters
    # when the thing being written is anti-cheat a reviewer has to audit.
    #
    # WHAT IT REFUSES TO TOUCH, and why each refusal is the honest answer rather than a gap:
    #   * an UNQUOTED tag (<<TAG) - the frontend expands ARG/ENV inside the body. Single-quoted
    #     printf args would not, so the rewrite would silently change behaviour.
    #   * a RUN heredoc - that is a script fed to the shell, not a file. Any faithful conversion has
    #     to decide about shebangs and `set -e` semantics, which is a judgement, not a transcription.
    #   * more than one heredoc on one instruction, an unterminated one, or a dest ending in `/`.
    if os.path.isfile(dfp := os.path.join(tasks, "environment", "Dockerfile")):
        try:
            if CHECKS not in sys.path:
                sys.path.insert(0, CHECKS)
            from qc_structure import heredocs, _BUILDKIT_ONLY, _SYNTAX_DIRECTIVE
            dtxt = open(dfp, errors="replace").read()
            docs = heredocs(dtxt)
        except Exception:
            docs = []

        def _dest_of(head):
            toks = re.sub(r"--[\w-]+(?:=\S+)?\s*", "", re.sub(r"^\s*\w+\s*", "", head)).split()
            return toks[-1] if toks else None

        doable, manual = [], []
        for hd in docs:
            dest = _dest_of(hd["head"])
            if (hd["instr"] in ("COPY", "ADD") and hd["quoted"] and hd["n_docs"] == 1
                    and hd["end"] and dest and not dest.endswith("/")):
                doable.append((hd, dest))
            else:
                why = ("a RUN heredoc is a script, not a file - converting it means deciding about "
                       "shebang and `set -e` semantics" if hd["instr"] == "RUN" else
                       "an unquoted tag expands ARG/ENV inside the body, which single-quoted printf "
                       "would not" if not hd["quoted"] else
                       "unterminated heredoc" if not hd["end"] else
                       "more than one heredoc on one instruction" if hd["n_docs"] > 1 else
                       f"destination {dest!r} is a directory, so the written filename is implicit")
                manual.append((hd, why))

        if doable:
            def dehere(t, _d=doable):
                p = os.path.join(t, "environment", "Dockerfile")
                lines = open(p, errors="replace").read().splitlines()
                out, skip = [], {}
                for hd, dest in _d:
                    skip[hd["line"]] = (hd, dest)
                i, done = 0, 0
                while i < len(lines):
                    n = i + 1
                    if n not in skip:
                        out.append(lines[i]); i += 1; continue
                    hd, dest = skip[n]
                    body = [b.lstrip("\t") if hd["dash"] else b for b in hd["body"]]
                    q = lambda s: "'" + s.replace("'", "'\\''") + "'"   # noqa: E731
                    d = os.path.dirname(dest)
                    lead = f"RUN mkdir -p {d} \\\n && printf '%s\\n' \\\n" if d not in ("", "/", ".") \
                        else "RUN printf '%s\\n' \\\n"
                    block = lead + "".join(f"      {q(b)} \\\n" for b in body) + f"      > {dest}"
                    out.append(f"# was a BuildKit-only heredoc; rewritten to build on any builder")
                    out.extend(block.splitlines())
                    i = hd["end"]                      # skip body + terminator
                    done += 1
                text = "\n".join(out) + "\n"
                # The `# syntax=` directive exists to enable exactly this syntax. Drop it only when
                # nothing left in the file needs a modern frontend - otherwise removing it would
                # trade a portability defect for a parse error.
                # PER LINE, not over the whole file: every `_BUILDKIT_ONLY` pattern is anchored with
                # `^` and compiled WITHOUT re.M (check_E applies them to one instruction at a time),
                # so `rx.search(whole_text)` only ever matches at byte 0 and silently reported "no
                # BuildKit features left" for a file whose second RUN still used `--mount`. That
                # dropped the directive it was supposed to keep.
                # Any heredoc still present is one this fix declined to touch (unquoted tag, RUN
                # heredoc), and those genuinely need the frontend - so the directive stays.
                still = sorted({f for rx, f, _ in _BUILDKIT_ONLY
                                for line in text.splitlines() if rx.search(line)}) \
                    + (["heredoc"] if heredocs(text) else [])
                dropped = 0
                if not still:
                    keep = [l for l in text.splitlines() if not _SYNTAX_DIRECTIVE.match(l)]
                    dropped = len(text.splitlines()) - len(keep)
                    text = "\n".join(keep) + "\n"
                open(p, "w").write(text)
                # Report what was DONE, not what the branch was for. Saying "removed the `# syntax=`
                # directive" on a Dockerfile that never had one is a false claim in the audit trail,
                # and the report is the only record of what a --apply run touched.
                return (f"rewrote {done} heredoc(s) as portable `RUN printf`"
                        + (f"; removed the `# syntax=` directive" if dropped else
                           f"; KEPT `# syntax=` ({', '.join(still)} still needs it)" if still else
                           "; no `# syntax=` directive was present"))

            fixes.append(Fix(
                "heredoc_to_run",
                f"Dockerfile uses BuildKit-only heredoc(s) ({len(doable)} rewritable)",
                "auto", "A",
                [f"Dockerfile:{hd['line']}  {hd['instr']} <<{hd['tag']} -> {dest} "
                 f"({len(hd['body'])} body line(s))" for hd, dest in doable]
                + [f"Dockerfile:{hd['line']}  NOT auto-fixable: {why}" for hd, why in manual],
                "A heredoc COPY creates a file from an inline body - a frontend feature, not core "
                "docker. On the classic builder the `<<TAG` token is read as a source path, nothing "
                "matches it, and the build dies with `COPY failed: no source files were specified` "
                "before any layer exists (measured, docker 29.6). The rewrite emits the same bytes "
                "with `printf '%s\\n'`, which is a shell builtin and needs no frontend feature, no "
                "registry round-trip for a parser, and no new file in the bundle - so it builds "
                "identically on every builder and needs no canonical-layout change.",
                dehere))
        elif manual:
            fixes.append(Fix(
                "heredoc_manual", "BuildKit-only heredoc(s) needing a hand rewrite", "never", "A",
                [f"Dockerfile:{hd['line']}  {hd['instr']} <<{hd['tag']}: {why}"
                 for hd, why in manual],
                "The build fails outright on a builder without heredoc support, but a faithful "
                "conversion needs a judgement the fixer will not make on your behalf - see the "
                "reason on each line."))

    # --- Dockerfile strips a binary the harness needs ---------------------- A / auto | ask
    #
    # Repairs the "exit 127: curl: command not found" class: an anti-cheat RUN that deletes
    # curl/wget/git/bash from the image, which is also how harbor installs the agent CLI, diffs the
    # candidate, and spawns every phase. See qc_structure.check_E for why nothing else catches it.
    #
    # THE REPAIR IS SUBTRACTION, AND ONLY LEGAL WHEN THE AGENT PHASE IS SEALED. With
    # `[agent] network_mode = "no-network"` the deletion protects nothing that harbor's own seal
    # does not already cover more completely (the seal also stops urllib, node fetch and
    # git-over-ssh), so dropping the fragment loses no hardening. WITHOUT the seal that fragment is
    # the only egress control there is, and removing it would silently open the trial - so the fix
    # downgrades itself to `ask` and says to seal the agent phase first. An auto-fix that unseals a
    # task while claiming to repair it is worse than no fix.
    if os.path.isfile(dfp):
        try:
            if CHECKS not in sys.path:
                sys.path.insert(0, CHECKS)
            from qc_structure import _logical_lines, _removed_bins
            dtxt = open(dfp, errors="replace").read()
            stripped = [(ln, b, frag) for ln, text in _logical_lines(dtxt)
                        for b, _how, frag in _removed_bins(text)]
        except Exception:
            stripped = []
        if stripped:
            ttxt = open(os.path.join(tasks, "task.toml"), errors="replace").read() \
                if os.path.isfile(os.path.join(tasks, "task.toml")) else ""
            am = re.search(r"^\[agent\]\s*$(.*?)(?=^\[|\Z)", ttxt, re.M | re.S)
            anm = re.search(r"^\s*network_mode\s*=\s*[\"']([^\"']*)[\"']",
                            am.group(1) if am else "", re.M)
            sealed = (anm.group(1) if anm else None) in ("no-network", "no_network", "none")

            def unstrip(t):
                """Drop the offending fragment, preserving the shell chain around it.

                Physical-line deletion is what breaks here: the fragment is one `&&` link inside a
                multi-line RUN, so removing its line leaves the previous line ending in a dangling
                `\\` and the Dockerfile no longer parses. So each PHYSICAL line is rewritten in
                place, its trailing `\\` and leading `&&` restored to whatever the chain still
                needs, and a line that becomes empty is dropped only when it is not the last link.
                """
                p = os.path.join(t, "environment", "Dockerfile")
                src = open(p, errors="replace").read()
                out, removed = [], 0
                for raw in src.splitlines():
                    body = raw.rstrip()
                    cont = body.endswith("\\")
                    if cont:
                        body = body[:-1].rstrip()
                    lead = re.match(r"^(\s*)", body).group(1)
                    core = body[len(lead):]
                    had_and = core.startswith("&&")
                    core_n = core[2:].strip() if had_and else core
                    # `|| true` belongs to the chain, not to the fragment - keep it.
                    tail = ""
                    m = re.search(r"(\|\|\s*true\s*)$", core_n)
                    if m:
                        tail = m.group(1).strip()
                        core_n = core_n[:m.start()].strip()
                    if core_n and not re.match(r"^(?:RUN|ENV|FROM|COPY|WORKDIR|CMD|ENTRYPOINT|"
                                               r"ARG|LABEL|USER|EXPOSE|VOLUME|SHELL|ADD|"
                                               r"HEALTHCHECK|ONBUILD|STOPSIGNAL)\b", core_n, re.I) \
                            and _removed_bins(core_n):
                        removed += 1
                        if not tail:
                            continue                      # nothing left on this line at all
                        # The chain's `|| true` is not part of the fragment - dropping it would
                        # change the RUN's exit status. Fold it onto the previous link instead of
                        # leaving it stranded on a line of its own, so the diff reads as one
                        # fragment deleted rather than as a reflowed block.
                        if out and out[-1].rstrip().endswith("\\"):
                            prev = out[-1].rstrip()[:-1].rstrip()
                            out[-1] = f"{prev} {tail}" + (" \\" if cont else "")
                        else:
                            out.append(f"{lead}{tail}" + (" \\" if cont else ""))
                        continue
                    out.append(raw)
                text = "\n".join(out)
                # A RUN may now end on a dangling continuation, or start with `&&`; repair both.
                text = re.sub(r"\\\s*\n(\s*)(?=(?:RUN|FROM|COPY|ENV|WORKDIR|CMD|ARG|LABEL|USER|"
                              r"EXPOSE|VOLUME|SHELL|ADD|HEALTHCHECK|ONBUILD|STOPSIGNAL)\b|$)",
                              "\n\\1", text, flags=re.I)
                text = re.sub(r"\\\s*\Z", "", text)
                text = re.sub(r"^(\s*RUN\s+)&&\s*", r"\1", text, flags=re.M | re.I)
                if not text.endswith("\n"):
                    text += "\n"
                open(p, "w").write(text)
                return (f"removed {removed} fragment(s) that stripped "
                        + ", ".join(sorted({b for _, b, _ in stripped}))
                        + " from the image")

            bins = sorted({b for _, b, _ in stripped})
            fixes.append(Fix(
                "agent_runtime_blocked",
                "Dockerfile strips binaries the harness needs (" + ", ".join(bins) + ")",
                "auto" if sealed else "ask", "A",
                [f"Dockerfile:{ln}  {b}  <- {frag}" for ln, b, frag in stripped[:6]],
                ("harbor installs the agent CLI into this image over curl (glibc bases) or "
                 "`npm install -g` (apk bases), diffs the candidate with git, and spawns every "
                 "phase under bash. Removing any of them makes the trial die at startup with a "
                 "127, and oracle/nop cannot see it because they install no agent. "
                 + ("`[agent] network_mode` is already sealed, so this fragment protects nothing "
                    "the harness seal does not cover more completely - it is pure subtraction."
                    if sealed else
                    "WARNING: `[agent] network_mode` is NOT sealed, so this fragment is currently "
                    "the only egress control. Set it to \"no-network\" FIRST (see the "
                    "agent_unsealed finding), then apply this - otherwise the repair unseals the "
                    "trial.")),
                unstrip))

    # --- Dockerfile drops privileges on a 0750 rootfs ---------------------- A / auto | never
    #
    # Repairs the "libc.so.6: cannot open shared object file: Permission denied" class. The sandbox
    # daemon's rootfs has `/` at 0750, so no non-root uid can traverse it and every `su`/`gosu`/
    # `setpriv` dies before main(). See qc_structure.check_P for the measurement and for why the
    # symptom points at the wrong culprit.
    #
    # THE REPAIR IS ADDITIVE AND A NO-OP OFF THIS DAEMON, which is what makes it `auto` where the
    # binary-strip repair next door has to ask. It removes no hardening, changes no uid, and runs the
    # same command as before - on a normal daemon `chmod a+rx /` finds `/` already 0755 and does
    # nothing. So there is no state in which applying it is worse than not applying it.
    #
    # BOTH HALVES OR NEITHER. Fixing only the build-time sites moves the identical failure from
    # `docker build` to the first `test.sh`, where it reads as a broken test rather than a broken
    # image - so the same fix also injects the chmod into the starter script the Dockerfile WRITES.
    if os.path.isfile(dfp):
        try:
            if CHECKS not in sys.path:
                sys.path.insert(0, CHECKS)
            from qc_structure import _privilege_sites, _instruction_spans, heredocs
            ptxt = open(dfp, errors="replace").read()
            psites = _privilege_sites(ptxt)
        except Exception:
            ptxt, psites = "", []
        if psites:
            # WHAT THIS FIXER WILL AND WILL NOT TOUCH. A shell-form RUN can take one more `&&` link;
            # the exec form `RUN ["x"]` cannot, a CMD/ENTRYPOINT drop has no build layer to repair,
            # and a script assembled by anything other than a quoted `printf` arg list or a heredoc
            # is not a shape a regex should be editing. Those are reported as `nonroot_manual`,
            # exactly as heredoc_manual reports the heredocs the rewriter declines.
            #
            # CLASSIFICATION IS RECOMPUTED AT APPLY TIME, NOT REUSED FROM DETECT TIME. Another fix in
            # the same `--apply` can rewrite this very file first - `unstrip` DELETES lines and
            # `heredoc_to_run` re-emits whole instructions - so every line number recorded during
            # detect may have moved by the time the edit runs. Injecting at a stale line number is
            # how a repair corrupts a Dockerfile, so detect and apply call one shared function and
            # apply calls it on the bytes it just read.
            def classify(txt):
                # `guarded` sites are already repaired, so they are neither offered nor edited. This
                # is what makes the fix idempotent at the OFFER level too: after one apply the fix
                # stops appearing in PROPOSED FIXES instead of promising a no-op edit forever.
                sites = [s for s in _privilege_sites(txt) if not s["guarded"]]
                spans = _instruction_spans(txt)
                docs = heredocs(txt)
                lines = txt.splitlines()

                def span_of(n):
                    for st, en, joined in spans:
                        if st <= n <= en:
                            return st, en, joined
                    for hd in docs:                   # a heredoc BODY line belongs to its opener
                        if hd["line"] <= n <= (hd["end"] or n):
                            return hd["line"], hd["end"] or n, hd["head"]
                    return None

                build, script, decl = set(), {}, []
                for s in sites:
                    sp = span_of(s["line"])
                    if sp is None:
                        decl.append((s, "could not locate the enclosing instruction"))
                        continue
                    st, en, joined = sp
                    if s["phase"] == "build":
                        if re.match(r"^\s*RUN\s+(?:--\S+\s+)*(?!\[)\S", lines[st - 1], re.I):
                            build.add(st)
                        else:
                            decl.append((s, "not a shell-form `RUN` - a `chmod` link cannot be "
                                            "prepended to the exec form"))
                        continue
                    hd = next((h for h in docs
                               if h["line"] < s["line"] <= (h["end"] or s["line"])), None)
                    if hd is not None:
                        script.setdefault(("heredoc", hd["line"], en), []).append(s)
                    elif re.search(r"printf\s+[\"']%s\\n[\"']", joined):
                        script.setdefault(("printf", st, en), []).append(s)
                    else:
                        decl.append((s, f"{s['dest'] or 'this site'} is not written as a quoted "
                                        f"`printf` arg list or a heredoc"))
                return sites, docs, span_of, build, script, decl

            _s, _d, _so, fixable_build, fixable_script, declined = classify(ptxt)

            def chmod_rootfs(t):
                """Inject `chmod a+rx /` at every site that drops privileges, in both phases."""
                p = os.path.join(t, "environment", "Dockerfile")
                src = open(p, errors="replace").read()
                lines = src.splitlines()
                _si, docs, span_of, f_build, f_script, _dc = classify(src)
                n_build, n_script = 0, 0
                ins = []
                # 1. BUILD: one more link IMMEDIATELY BEFORE the first drop in each RUN - the same
                #    layer, because a mode change on `/` is not captured in a layer diff and a
                #    separate `RUN chmod a+rx /` reverts before the next instruction even starts.
                #
                #    WHY BEFORE THE DROP RATHER THAN AT THE HEAD OF THE RUN, which read more tidily:
                #    the head is not always upstream of everything that matters. On
                #    `RUN chmod 750 / && su pg -c x` a prepended chmod is REVOKED by the RUN's own
                #    later chmod, and the repair silently produced a Dockerfile that still failed to
                #    build while reporting success. Measured - it was caught by building the fixture,
                #    not by reading it. Inserting at the drop is the only position nothing later in
                #    the chain can undo, and it is equally correct in every other shape: at the head
                #    of the RUN it degrades to exactly the old output, inside a `for … do` block it
                #    lands in the block, and inside a `sh -c "…"` it lands inside the quotes where it
                #    is still what runs first.
                #
                #    IDEMPOTENCY COMES FROM `guarded`, NOT FROM A SUBSTRING TEST. An earlier version
                #    skipped any RUN whose text already contained `chmod a+rx /`, which got
                #    `RUN su pg -c x && chmod a+rx /` exactly wrong: the chmod is there but it runs
                #    AFTER the drop, so the site is still broken and the fixer declared it repaired.
                #    classify() already filters to sites the check considers unguarded - i.e. with no
                #    traversal repair BEFORE them - so reaching here is itself the proof that work is
                #    needed, and a second test can only disagree with the check.
                for st in sorted(f_build):
                    rows = sorted((s for s in _si if s["phase"] == "build"
                                   and span_of(s["line"]) and span_of(s["line"])[0] == st),
                                  key=lambda s: (s["line"], s["col"]))
                    if not rows:
                        continue
                    ins.append((rows[0]["line"], rows[0]["col"], "chmod a+rx / && "))
                    n_build += 1
                # 2. VERIFY: the shipped image still has `/` at 0750, so the generated script has to
                #    repeat the chmod as root before its own first drop.
                #
                #    THE INDEX IS THE DELICATE PART. `lines` is 0-based and the site line numbers are
                #    1-based, so the insert index that lands a new line immediately AFTER physical
                #    line L is exactly L. Getting that wrong is not cosmetic: `+1` too far in the
                #    no-shebang branch puts the chmod AFTER the first `su`, which is the one place it
                #    cannot help. Insertions are applied bottom-up so each recorded index stays valid.
                for (shape, anchor, end), rows in f_script.items():
                    first = min(r["line"] for r in rows)
                    if shape == "heredoc":
                        hd = next((h for h in docs if h["line"] == anchor), None)
                        if hd is None:
                            continue
                        shebang = next((hd["line"] + 1 + i for i, b in enumerate(hd["body"])
                                        if b.lstrip().startswith("#!")), None)
                        at = shebang if shebang is not None else first - 1
                        ref = lines[min(at, len(lines) - 1)]
                        pad = re.match(r"^(\s*)", ref).group(1)
                        ins.append((at, None, f"{pad}chmod a+rx /"))
                    else:
                        shebang = next((n for n in range(anchor, end + 1)
                                        if "#!" in lines[n - 1]), None)
                        at = shebang if shebang is not None else first - 1
                        ref = lines[min(at, len(lines) - 1)]
                        # ONE ARGUMENT PER LINE OR SEVERAL? A printf arg list is a single logical
                        # line, so a whole-line insert is only safe where the anchor line holds
                        # exactly one argument. Where the args share a physical line, inserting a
                        # line breaks the chain: the new line lands between a `\` and the `&&` that
                        # followed it, and the Dockerfile stops parsing (measured - it produced
                        # `"chmod a+rx /"` stranded on its own line above an orphaned `&& chmod +x`).
                        # There the argument is spliced INTO the line instead, before the drop's own
                        # quoted argument, which leaves every continuation exactly as it was.
                        if _one_arg_line(ref):
                            pad = re.match(r"^(\s*)", ref).group(1)
                            qm = re.search(r"[\"']", ref)
                            q = qm.group(0) if qm else '"'
                            cont = " \\" if ref.rstrip().endswith("\\") else ""
                            ins.append((at, None, f"{pad}{q}chmod a+rx /{q}{cont}"))
                        else:
                            row = next(r for r in rows if r["line"] == first)
                            col = _arg_start(lines[first - 1], row["col"])
                            q = lines[first - 1][col] if lines[first - 1][col] in "\"'" else '"'
                            ins.append((first, col, f"{q}chmod a+rx /{q} "))
                # Bottom-up, and column-descending within a line, so every recorded position is
                # still valid when its own edit runs.
                for at, col, text in sorted(ins, key=lambda x: (x[0], x[1] if x[1] is not None else -1),
                                            reverse=True):
                    if col is None:
                        lines.insert(at, text)
                    else:
                        lines[at - 1] = lines[at - 1][:col] + text + lines[at - 1][col:]
                    n_script += 1
                out = "\n".join(lines)
                if not out.endswith("\n"):
                    out += "\n"
                open(p, "w").write(out)
                return (f"injected `chmod a+rx /` into {n_build} privilege-dropping RUN(s) and "
                        f"{n_script} generated script(s)")

            if fixable_build or fixable_script:
                nb, nv = (len([s for s in psites if s["phase"] == "build"]),
                          len([s for s in psites if s["phase"] == "verify"]))
                users = sorted({s["user"] for s in psites})
                fixes.append(Fix(
                    "nonroot_privilege_drop",
                    f"Dockerfile drops privileges (to {', '.join(users)}) on a rootfs whose `/` "
                    f"is 0750",
                    "auto", "A",
                    [f"Dockerfile:{s['line']}  {s['phase']:<6} {s['tool']} -> {s['user']}  "
                     f"{s['frag'][:72]}" for s in psites[:6]]
                    + [f"... and {len(psites) - 6} more" for _ in [1] if len(psites) > 6],
                    f"The sandbox daemon's rootfs has `/` at 0750, so no non-root uid can traverse "
                    f"it: every drop dies before main() with `libc.so.6: cannot open shared object "
                    f"file: Permission denied`, which reads as a corrupt base image. "
                    f"{nb} build-time site(s) get `chmod a+rx /` as the first link of their own RUN "
                    f"(a mode change on `/` is not captured in a layer diff, so it MUST be the same "
                    f"layer), and {nv} verify-time site(s) get it injected into the generated "
                    f"script, which the shipped image still needs because `/` is unchanged there. "
                    f"The chmod is additive and a no-op on a normal daemon - it removes no "
                    f"hardening and changes no uid, which is why it applies without a question.",
                    chmod_rootfs))
            if declined:
                fixes.append(Fix(
                    "nonroot_manual", "privilege drop(s) needing a hand repair", "never", "A",
                    [f"Dockerfile:{s['line']}  {s['tool']} -> {s['user']}: {why}"
                     for s, why in declined[:6]],
                    "These sites fail the same way on a 0750 rootfs, but repairing them needs a "
                    "judgement the fixer will not make on your behalf - see the reason on each "
                    "line. A `USER <non-root>` directive is the extreme case: after it there is no "
                    "root process left to fix `/` with, so no in-image repair exists at all."))

    # --- task.toml [verifier.env] --------------------------------------------- REMOVED
    # This used to be an `auto` fix that STRIPPED [verifier.env] / ANTHROPIC_* / JUDGE_MODEL from
    # task.toml, on the theory that the judge is always a keyless sub-agent and the credentials are
    # retired leftovers. Both halves of that were wrong:
    #   * harbor expands [verifier.env]'s "${VAR:-}" entries from its OWN environment, which is
    #     where the runner exports the judge credentials. A task declaring no [verifier.env] block
    #     never receives them, so stripping the block is what breaks in-container grading.
    #   * the block is now REQUIRED in Mode A, not merely harmless. Stripping it manufactures
    #     rubfmt_verifier_env on every task it touches -- the fix would have created the blocking
    #     defect that verifier_env (below) exists to repair.
    # The second bullet used to read "task.toml's verifier config is out of scope for rubric QC
    # anyway: it varies legitimately across tasks, and BOTH judge backends are valid." That is the
    # pre-in-band-grading position and it is no longer true; see qc_rubric_format's
    # check_verifier_env. Credentials still never live in a bundle, because [verifier.env] holds
    # ${VAR} REFERENCES that harbor expands at run time.
    # An auto-fix that rewrites task.toml on a false premise is worse than no fix, so this is
    # deleted rather than downgraded. A LITERAL secret in a bundle (not a ${VAR} reference) is a
    # security escalation, not a mechanical repair.
    tp = os.path.join(tasks, "task.toml")

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

    # --- task.toml verifier phase ------------------------------------- B / auto (+ C, below)
    # Both have exactly one correct value, so there is no judgement to escalate. They edit
    # task.toml -- a task file, not a wiring artifact -- so like every other fix they are gated
    # behind --apply, and the snapshot/rollback applies.
    #
    # THE TWO ARE GATED DIFFERENTLY, which is the point:
    #   verifier_network_mode  EVERY TASK. A sealed verifier cannot install what the tests need
    #                          (npm/pip install, or npx resolving a runner from the registry), so
    #                          the f2p test fails and a correct submission records 0.0. That
    #                          mis-scores rubric-less tasks exactly as readily as rubric ones.
    #   verifier_env           MODE A ONLY. Nothing reads EVAL_* without a judge, and the block's
    #                          bare "${VAR}" entries are REQUIRED host vars to harbor (cli/jobs.py
    #                          exits 1 before any container if unset) -- so writing it into a
    #                          rubric-less task breaks its keyless oracle/nop for nothing.
    tt = os.path.join(tasks, "task.toml")
    ttxt = open(tt, errors="replace").read() if os.path.isfile(tt) else ""

    def _section(txt, name):
        m = re.search(r"^\[" + re.escape(name) + r"\]\s*$(.*?)(?=^\[|\Z)", txt, re.M | re.S)
        return m.group(1) if m else None

    # --- [verifier] network_mode -------------------------------------- EVERY TASK / auto
    # Class C, not B: this changes what the VERIFIER CAN DO, so a trial whose tests failed for
    # want of a registry was measuring the seal rather than the submission. Its reward does not
    # survive the fix. (verifier_env is Class B -- it only ever affected the rubric verdict.)
    vbody = _section(ttxt, "verifier")
    vmode = re.search(r"^\s*network_mode\s*=\s*[\"']([^\"']*)[\"']", vbody or "", re.M)
    if os.path.isfile(tt) and (not vmode or vmode.group(1) != "public"):
        def set_netmode(t):
            p = os.path.join(t, "task.toml"); s = open(p).read()
            body = _section(s, "verifier")
            if body is not None and re.search(r"^\s*network_mode\s*=", body, re.M):
                new = re.sub(r"^(\s*network_mode\s*=\s*)[\"'][^\"']*[\"']",
                             r'\1"public"', body, count=1, flags=re.M)
                s = s.replace(body, new, 1)
            elif body is not None:
                s = s.replace("[verifier]\n", '[verifier]\nnetwork_mode = "public"\n', 1)
            else:
                s = s.rstrip("\n") + '\n\n[verifier]\nnetwork_mode = "public"\n'
            open(p, "w").write(s)
            return 'set [verifier] network_mode = "public"'
        fixes.append(Fix(
            "verifier_network_mode", '[verifier] network_mode is not "public"', "auto", "C",
            [f"network_mode={vmode.group(1)!r}" if vmode else "network_mode absent"],
            "A sealed verifier cannot install what the tests need, so the f2p test fails and a "
            "CORRECT submission records 0.0. On a rubric task it also leaves the judge unable to "
            "reach its endpoint. An allowlist cannot name a run-time-injected host (harbor "
            "validates allowed_hosts as literal hostnames; there is no --allow-verifier-host). "
            "The verifier runs after the agent phase and test.sh restores the tests from "
            "harbor_base, so this cannot help a submission cheat; [agent] stays sealed.",
            set_netmode))

    # --- [verifier.env] EVAL_* ------------------------------------------- MODE A / auto
    # Gated on a rubric that PARSES AND HAS A REAL CRITERION, matching qc_rubric_format's Mode A
    # exactly. It used to gate on rubrics.json merely EXISTING, which is a wider net than the
    # check's: a stub-only or unparseable rubric drew a proposed fix here while the check (which
    # routes those to Mode B) raised no matching finding, so `PROPOSED FIXES` listed a repair for
    # a defect the report never named. Those tasks are told to strip the layer, not to wire it.
    if _rubric_is_real(tasks):
        ebody = _section(ttxt, "verifier.env")
        need = {"EVAL_API_KEY": "${OPENAI_API_KEY}",
                "EVAL_BASE_URL": "${OPENAI_API_BASE}",
                "EVAL_MODEL": "${EVAL_MODEL:-anthropic/claude-opus-4-5-20251101}"}
        absent = [k for k in need
                  if ebody is None or not re.search(r"^\s*" + k + r"\s*=", ebody, re.M)]
        if absent:
            def set_env(t, _absent=tuple(absent)):
                p = os.path.join(t, "task.toml"); s = open(p).read()
                lines = "".join(f'{k} = "{need[k]}"\n' for k in _absent)
                if _section(s, "verifier.env") is None:
                    s = s.rstrip("\n") + "\n\n[verifier.env]\n" + lines
                else:
                    s = s.replace("[verifier.env]\n", "[verifier.env]\n" + lines, 1)
                open(p, "w").write(s)
                return f"mapped {list(_absent)} in [verifier.env]"
            fixes.append(Fix(
                "verifier_env", f"[verifier.env] does not map {absent}", "auto", "B",
                [f"missing: {absent}"],
                "judge.py's API backend reads these three and skips grading entirely if any is "
                "empty. They are ${VAR} REFERENCES expanded by harbor at run time, so no "
                "credential is written into the bundle.", set_env))

    # --- legacy reward key rename ---------------------------------------------- B / ask
    # `rubric_pass` is the pre-rename spelling of `rubric_passed`. Everything that reads the
    # reward wants the canonical name -- the platform schema, the runner's report(), the
    # skill's own template -- so a task writing the old one records a rubric verdict nothing
    # downstream can see. Measured symptom: an oracle run that DID grade the rubric in-band
    # reported "no rubric verdict from the verifier", because report() refuses the legacy key.
    #
    # AUTO. This was ask-only on the theory that a reviewer wants to SEE a corpus-wide defect
    # rather than have it quietly repaired -- but the report shows it either way, so holding it
    # back never bought visibility. What it cost was a round trip per task, on a defect with one
    # correct answer and no grading consequence: the same value, under the name every consumer
    # reads. The rename is idempotent (`\b` before `ed` never matches, so a re-run cannot produce
    # `rubric_passeded`) and it is guarded below.
    #
    # It also declines to offer itself unless a rename is the WHOLE fix: if other canonical keys
    # are absent too, the verifier needs the reward block merged by hand and a rename would just
    # mask how much is missing.
    vp_r = os.path.join(tasks, "tests", "verifier.py")
    vsrc = open(vp_r, errors="replace").read() if os.path.isfile(vp_r) else ""
    if re.search(r"\brubric_pass\b", vsrc):
        others = [k for k in ("reward", "tests_passed", "f2p_passed", "f2p_total",
                              "p2p_passed", "p2p_total") if f'"{k}"' not in vsrc]
        if others:
            fixes.append(Fix(
                "rubric_key_rename", "legacy `rubric_pass`, and other canonical keys missing too",
                "never", "B", [f"also absent: {others}"],
                "A rename alone would not make reward.json canonical, and would hide how much "
                "is missing. Merge template/tests/verifier_reward_block.py by hand instead."))
        else:
            n_hits = len(re.findall(r"\brubric_pass\b", vsrc))

            def rename_key(t, _n=n_hits):
                p = os.path.join(t, "tests", "verifier.py")
                s = open(p, errors="replace").read()
                # \b before `ed` never matches, so this is idempotent and can never produce
                # `rubric_passeded` on a re-run or a partially-migrated file.
                open(p, "w").write(re.sub(r"\brubric_pass\b", "rubric_passed", s))
                return f"renamed rubric_pass -> rubric_passed in tests/verifier.py ({_n} site(s))"
            fixes.append(Fix(
                "rubric_key_rename", "tests/verifier.py writes the legacy key `rubric_pass`",
                "auto", "B", [f"{n_hits} occurrence(s) in tests/verifier.py",
                              "every other canonical key is already present"],
                "Records the same value under the name every consumer reads - the platform "
                "schema, the runner's report(), this skill's own template. Grading is unchanged; "
                "only the key. Measured symptom: an oracle run that DID grade the rubric in-band "
                "reported 'no rubric verdict from the verifier', because report() refuses the "
                "legacy key.", rename_key))

    # --- judge.py -------------------------------------------------------------- B / ask
    # BOTH of these used to be `auto`, and both were wrong under the two-shape rubric policy:
    #   * judge_missing installed a judge into a task that has NO rubrics.json - Mode B, where
    #     judge.py is correctly absent. It manufactured the very half-wired state
    #     qc_rubric_format reports as a blocking defect.
    #   * judge_drift OVERWROTE judge.py with the bundled template whenever the bytes differed.
    #     There are two valid backends (keyless sub-agent, API-capable) and the template is only
    #     one of them, so on a task using the other backend this silently replaced a working
    #     judge with a different one - measured: the template matches NEITHER reference task.
    # judge_missing now only fires when a rubric actually ships, and drift is a question, not a
    # repair.
    jp = os.path.join(tasks, "tests", "judge.py")
    has_rubric = os.path.isfile(os.path.join(tasks, "tests", "rubrics.json"))
    if os.path.isfile(INSTALL_JUDGE) and has_rubric:
        if not os.path.isfile(jp):
            fixes.append(Fix("judge_missing", "tests/judge.py missing but a rubric ships",
                             "auto", "B", ["tests/judge.py"],
                             "A rubric that ships with no judge is never graded. Installs the "
                             "API-backend reference judge, so the result also satisfies "
                             "rubfmt_judge_backend rather than trading one blocker for another.",
                             lambda t: (shutil.copy(INSTALL_JUDGE,
                                        os.path.join(t, "tests", "judge.py")),
                                        f"installed judge.py from "
                                        f"{os.path.basename(os.path.dirname(INSTALL_JUDGE))}/")[1]))
        else:
            jsrc = open(jp, errors="replace").read()
            stub = os.path.isfile(TEMPLATE_JUDGE) and sha(jp) == sha(TEMPLATE_JUDGE)
            if "call_eval_api" not in jsrc:
                # BLOCKING, and it has exactly one correct repair: copy reference/judge.py whole.
                # A sub-agent-only judge cannot grade during the run -- it writes a request, prints
                # nothing, and every run records rubric_passed = -1 until someone reads PROMPT.md,
                # writes verdict.json and reruns rescore. That step is routinely skipped, so the
                # rubric is decorative in exactly the way an all-pass stub is.
                #
                # SHA-CONDITIONAL, and the sha is what decides -- not the shape of the repair.
                #
                # The repair is `cp reference/judge.py tests/judge.py`: a whole-file copy of a
                # task-agnostic file (byte-identical in both reference tasks), with nothing to
                # merge and no logic to read. judge_missing performs that EXACT copy as kind=auto
                # when judge.py is absent, so making it kind=agent whenever the file merely EXISTS
                # graded the wrong thing -- the only real difference is whether a copy destroys
                # someone's work, and the sha answers that outright:
                #
                #   sha == the sub-agent stub  -> provably untouched boilerplate, nothing to lose
                #   sha != the stub            -> someone customised it; read the diff first
                #
                # This is NOT the reasoning that keeps verifier_reward_domain out of `auto`. There
                # the values sit inside task-specific branches (`reward = tests_passed * 0.5`
                # floors to `* 0.0`, i.e. every run scores zero), so no hash can make the rewrite
                # safe. Here the file is opaque boilerplate and the hash settles it completely.
                ev = [f"tests/judge.py defines no call_eval_api ({len(jsrc.splitlines())} lines)"]
                # verifier.py reading a rubric.json nobody writes is the SAME defect from the other
                # end: reference/judge.py writes it, so one copy closes both. Reported here rather
                # than as its own fix so nobody makes two edits for one repair.
                closes_rubric_json = "/logs/verifier/rubric.json" in vsrc
                if closes_rubric_json:
                    ev.append("also closes judge.rubric_json: verifier.py reads "
                              "/logs/verifier/rubric.json, which the reference judge writes")
                if stub:
                    ev.append(f"byte-identical to the sub-agent stub "
                              f"(sha {sha(jp)[:12]}) - provably nothing task-specific to lose")
                    fixes.append(Fix(
                        "judge_backend", "tests/judge.py cannot grade in-band (no API backend)",
                        "auto", "B", ev,
                        "A rubric that only grades on a manual follow-up never grades at all. This "
                        "judge is the untouched boilerplate stub, so installing the API-backend "
                        "reference judge over it can destroy nothing - the same copy judge_missing "
                        "already makes when judge.py is absent.",
                        lambda t: (shutil.copy(INSTALL_JUDGE,
                                   os.path.join(t, "tests", "judge.py")),
                                   "installed the API-backend judge from reference/ "
                                   "(replaced the sub-agent stub)")[1]))
                else:
                    ev.append(f"NOT the known stub (sha {sha(jp)[:12]}) - it was adapted, so a "
                              f"blind copy could destroy the adaptation")
                    fixes.append(Fix(
                        "judge_backend", "tests/judge.py cannot grade in-band (no API backend)",
                        "agent", "B", ev,
                        "A rubric that only grades on a manual follow-up never grades at all. This "
                        "judge is NOT the stock stub, so read the diff first: if the local changes "
                        "are worth keeping, merge template/tests/judge_api_block.py instead of "
                        "copying the reference over them.",
                        playbook="RUBRIC_MODES.md §2b (and §2c for the contract)",
                        verify="python3 checks/qc_rubric_format.py <Tasks> "
                               "| grep -E 'judge\\.(backend|rubric_json)'"))
            elif sha(jp) != sha(INSTALL_JUDGE):
                # Narrowed to judges that ALREADY have the API backend. Previously this also fired
                # on every stub, so one defect produced two findings with different advice -- a
                # blocking "no backend" and an ask "it differs, have a look". With the backend
                # present, a hash mismatch is genuinely a judgement: the task adapted a working
                # judge, and overwriting would replace it.
                #
                # Baseline is the REFERENCE, not the stub. Against the stub this fired on every
                # correct task -- the note used to concede "the template matches NEITHER reference
                # task", a drift check that can never be satisfied.
                fixes.append(Fix("judge_drift", "tests/judge.py differs from the reference judge",
                                 "ask", "B", [f"sha {sha(jp)[:12]} != {sha(INSTALL_JUDGE)[:12]}",
                                              "it DOES define call_eval_api, so it can grade "
                                              "in-band - this is not a blocker"],
                                 "Still ASK, not auto: a task may have adapted the judge "
                                 "deliberately, and overwriting would replace a working one. Check "
                                 "the contract first - prints pass/fail or nothing, writes "
                                 "summary.json, always exits 0.",
                                 lambda t: (shutil.copy(INSTALL_JUDGE,
                                            os.path.join(t, "tests", "judge.py")),
                                            "restored judge.py from reference/")[1]))

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
    # The three corpora are read SEPARATELY, not concatenated. Pooling them was a false negative:
    # an asset named in ASSET_MANIFEST.json but nowhere in instruction.md counted as "referenced"
    # and no finding was raised at all - by this check or by the runner's integrity gate, whose
    # instruction.md test only reached posters already documented in both files. The two states are
    # different defects with different repairs, so they are now two findings.
    adir = os.path.join(tasks, "environment", "assets")
    if os.path.isdir(adir):
        def _read(*parts):
            p = os.path.join(tasks, *parts)
            return open(p, errors="replace").read() if os.path.isfile(p) else ""

        instr = _read("instruction.md")
        docs = _read("evidence_bundle.json") + _read("environment", "assets", "ASSET_MANIFEST.json")
        posters = [f for f in sorted(os.listdir(adir)) if f != "ASSET_MANIFEST.json"]
        unused = [f for f in posters if f not in instr and f not in docs]
        # Documented, so not "unused" - but the task statement never sends the agent to it.
        undocumented_in_instr = [f for f in posters if f not in instr and f in docs]
        if undocumented_in_instr:
            fixes.append(Fix(
                "asset_not_in_instruction",
                "Asset(s) documented but not referenced in instruction.md", "never", "C",
                undocumented_in_instr,
                "The evidence documents cite these, so they are not dead - but instruction.md "
                "never tells the agent to look at them, and COPY assets/ ships them regardless. "
                "Either the instruction is missing the reference it needs, or the poster does not "
                "belong in the bundle; if it is an 'after' render, it is the answer. Both repairs "
                "are authoring - one writes task prose, the other decides what evidence the task "
                "is - so this is reported, never applied. Warning, not a blocker: the reference "
                "may be implicit in prose this grep cannot see."))
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

    # --- test.sh submission capture ------------------------------------------ T / auto
    # PAIRED WITH qc_structure's check_T, which reports the same condition as an ADVISORY. This
    # is mechanical because there is no judgment in it: the block is fixed text, the insertion
    # point is determined (`cd /app`, above the restore loop), and getting it wrong is detectable
    # -- a capture below test.patch records the task's own tests instead of the agent's work.
    #
    # OFFERED ONLY WHEN THE HOST SCRIPT CAN SUPPORT IT. The block writes through $STDOUT_LOG and
    # $STDERR_LOG and anchors on `cd /app`; a test.sh shaped differently gets no mechanical fix,
    # because a blind splice into an unfamiliar script is how a working verifier gets broken.
    ts_cap = os.path.join(tasks, "tests", "test.sh")
    if os.path.isfile(ts_cap) and os.path.isfile(TEMPLATE_SUBCAP):
        cap_body = open(ts_cap, errors="replace").read()
        cap_anchor = re.search(r"^cd /app\b[^\n]*$", cap_body, re.M)
        wired = "/logs/verifier/submission.patch" in cap_body
        supported = bool(cap_anchor) and "STDOUT_LOG" in cap_body and "STDERR_LOG" in cap_body
        if not wired and supported:
            def wire_capture(t):
                p2 = os.path.join(t, "tests", "test.sh")
                b = open(p2, errors="replace").read()
                m = re.search(r"^cd /app\b[^\n]*$", b, re.M)
                if not m:
                    return "no `cd /app` anchor in tests/test.sh - nothing written"
                blk = open(TEMPLATE_SUBCAP).read()
                # Strip the template's own provenance header: it explains the file to a reader of
                # the SKILL, and repeating it inside every task's test.sh is noise.
                blk = re.sub(r"\A(?:#[^\n]*\n|\n)+?(?=# Capture the agent's submission)", "", blk)
                b = b[:m.end()] + "\n\n" + blk.strip("\n") + "\n" + b[m.end():]
                open(p2, "w").write(b)
                return "wired the submission capture block into tests/test.sh after `cd /app`"
            fixes.append(Fix(
                "submission_capture", "tests/test.sh does not save the agent's submission",
                "auto", "A", ["tests/test.sh"],
                "Without it a recorded trial cannot be re-scored against edited tests: the "
                "container is gone and the agent's file state with it, so the only way to a "
                "current trial number is another paid agent run. The block costs nothing and "
                "writes /logs/verifier/submission.patch, which harbor already exports.",
                wire_capture))

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
        # --- the 0.5 ladder ------------------------------------------------- B / agent
        # Split out of verifier_rubric, which used to carry it as a substring gap ("mentions 0.5")
        # inside a kind=never block. That reported ONE defect TWICE with contradictory advice: a
        # targeted finding the agent could act on, and a "never auto-patched, merge the whole block
        # by hand" line that won the summary. It also matched text, so a docstring documenting a
        # legacy 0.5 rung counted as a verifier that emits one.
        sites = reward_domain_sites(tasks)
        if sites:
            fixes.append(Fix(
                "verifier_reward_domain", "tests/verifier.py can emit a reward outside {0, 1}",
                "agent", "B",
                [f"line {ln}: {k} = {v!r}" for ln, k, v in sites[:6]]
                + ["these are ASSIGNMENT sites from the AST - a 0.5 in a docstring or a "
                   "round(x, 2) is deliberately not listed"],
                "Reward is binary: a partial fix is a fail. Floor to 0.0 - never round to nearest, "
                "never cap at 0.5 - and reword any docstring still documenting the old ladder, "
                "which the AST-only check cannot see.",
                playbook="RUBRIC_MODES.md §2 (and §2c for the contract)",
                verify="python3 checks/qc_rubric_format.py <Tasks> | grep reward_domain"))

        gaps = []
        if "--rubric" not in vb:
            gaps.append("does not parse --rubric")
        if "reward.json" not in vb:
            gaps.append("does not write reward.json (no per-test counts)")
        # The canonical reward.json is exactly seven flat numeric keys; a missing one is not
        # cosmetic, since downstream analysis reads them across the whole corpus.
        _missing = [k for k in ("reward", "tests_passed", "f2p_passed", "f2p_total",
                                "p2p_passed", "p2p_total", "rubric_passed")
                    if f'"{k}"' not in vb and f"'{k}'" not in vb]
        # Defer to rubric_key_rename when the ONLY gap is the legacy spelling. Both used to fire:
        # the targeted rename you can actually approve, and this kind=never block-merge telling
        # you it is "never auto-patched" - contradictory advice for one defect, and the more
        # discouraging half won the summary line.
        if _missing == ["rubric_passed"] and re.search(r"\brubric_pass\b", vb):
            _missing = []
        if "reward.json" in vb and _missing:
            gaps.append(f"reward.json is missing canonical key(s) {_missing}")
        if gaps:
            fixes.append(Fix(
                # Was kind=never, which made it a dead end: the report said "merge it by hand" and
                # nobody did. kind=agent keeps fix.py's hands off verifier.py -- action stays None,
                # nothing is written by the script -- while making the repair someone's job.
                "verifier_rubric", "tests/verifier.py rubric gate incomplete", "agent", "B", gaps,
                "verifier.py carries TASK-SPECIFIC scoring logic, so no script patches it: a blind "
                "insert could silently change what the task grades. Merge the canonical block from "
                f"{os.path.relpath(TEMPLATE_VERIFIER, HERE)} by hand, keeping the task's own "
                "per-test pass/fail logic - you are replacing how the outcome is SCORED, not how "
                "it is measured.",
                playbook="RUBRIC_MODES.md §2 (and §2c for the contract)",
                verify="python3 checks/qc_rubric_format.py <Tasks> "
                       "| grep -E 'verifier\\.(gate|reward_json)'"))

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
                        # A blank we do not invent content for. This used to write the sentence
                        # "No rubric needed — fully covered by behavioral tests." whenever the file
                        # held only an always-pass stub, which MANUFACTURED the exact artefact
                        # qc_rubric_format now reports as a blocking defect: a rubric that declares
                        # itself unnecessary instead of being stripped. Never re-add that.
                        d["description"] = ""
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
# A whole harbor run: image build + tests. Generous, but bounded - an unbounded run leaves a CB
# staring at nothing with no way to tell "slow" from "hung".
RUN_TIMEOUT = int(os.environ.get("MM_RUN_TIMEOUT", "5400"))


def resolve_runner():
    """$MM_RUNNER -> the installed mmswe-runner. Returns None if neither is present.

    No capability probing. The only modes this skill drives are oracle and nop, which every runner
    in circulation implements. An earlier version preferred a `rescore`-capable runner; the rubric
    half is now settled by GRADING the oracle's judge request instead of folding a verdict into a
    reward, so that machinery was deleted rather than carried.

    There used to be a third candidate, a copy of the runner bundled under this skill's `runner/`,
    so a standalone install could still reproduce the gate. It was removed: a duplicate of a
    1500-line script is a maintenance liability, and it proved the point by drifting 626 lines
    behind the real one -- missing every judge fix -- while the docs still recommended it. The
    caller already handles None by reporting the gate as NOT verified (exit 2), so losing the
    fallback costs a clear message, never a false pass.
    """
    for cand in (os.environ.get("MM_RUNNER"),
                 os.path.expanduser("~/.claude/skills/mmswe-runner/mm_run.sh")):
        if cand and os.path.isfile(cand):
            return cand
    return None


STUB_IDS = {"always_pass", "always-pass", "alwayspass"}


def rubric_is_stub(tasks):
    """(nothing_to_grade, why). True when no criterion could ever fail, so no verdict is worth
    establishing - but the TWO ways that happens are not equally acceptable:

      * no tests/rubrics.json at all  -> Mode B, a legal shape. Genuinely nothing to grade.
      * an always-pass stub           -> NOT legal. A BLOCKING defect (qc_rubric_format), because
                                        the stub reports rubric_passed=1 as though a real rubric had
                                        been satisfied. Strip the layer instead of stubbing it.

    Both short-circuit the golden-fix re-check, so one return value still serves; the `why` string
    is what distinguishes them for the caller's message.
    """
    rp = os.path.join(tasks, "tests", "rubrics.json")
    if not os.path.isfile(rp):
        return True, "no tests/rubrics.json - no rubric layer at all (Mode B, legal)"
    try:
        doc = json.load(open(rp))
    except Exception as exc:
        return False, f"rubrics.json does not parse ({exc}) - treat as real until fixed"
    crit = [c for c in (doc.get("criteria") or []) if isinstance(c, dict)]
    real = [c for c in crit
            if str(c.get("id", "")).strip().lower() not in STUB_IDS
            and not re.search(r"written in english|no rubric needed",
                              str(c.get("criterion", "")), re.I)]
    if not real:
        return True, (f"always-pass stub only ({len(crit)} criterion) - NOT a legal shape; "
                      f"qc_rubric_format reports this as a BLOCKING defect")
    return False, f"{len(real)} contributor-written criterion(s) to grade"


def _rubric_is_real(tasks):
    """Is this task in qc_rubric_format's MODE A? Ships a rubrics.json that PARSES and holds at
    least one non-stub criterion.

    NOT rubric_is_stub()'s inverse, and the difference is deliberate. That helper answers "is
    there a verdict worth establishing", and for an UNPARSEABLE rubrics.json it answers "treat as
    real until fixed" -- the right conservative call when the question is whether to re-check the
    golden fix. Here the question is whether to WIRE the judge's credentials, and
    qc_rubric_format sends an unparseable rubric down its BROKEN branch, which never reaches
    check_verifier_env. Wiring a task the report is telling its author to fix or strip would put a
    repair in `PROPOSED FIXES` with no finding to join it to.

    This is the ONE place the two vocabularies have to agree on the Mode A boundary, so it mirrors
    the check's predicate directly rather than approximating it.
    """
    rp = os.path.join(tasks, "tests", "rubrics.json")
    if not os.path.isfile(rp):
        return False
    try:
        doc = json.load(open(rp))
    except Exception:
        return False                     # BROKEN branch in the check, not Mode A
    crit = [c for c in (doc.get("criteria") or []) if isinstance(c, dict)]
    return any(str(c.get("id", "")).strip().lower() not in STUB_IDS
               and not re.search(r"written in english|no rubric needed",
                                 str(c.get("criterion", "")), re.I)
               for c in crit)


def read_reward(run_dir):
    """Authoritative: the reward file harbor wrote, not a line scraped from stdout."""
    import glob
    # The newest trial first, so an older timestamped job kept beside it cannot answer.
    newest = _newest_trial(run_dir)
    first = [os.path.join(newest, "verifier", "reward.txt")] if newest else []
    for pat in (None, "**/verifier/reward.txt", "**/reward.txt"):
        cands = [c for c in first if os.path.isfile(c)] if pat is None else \
            sorted(glob.glob(os.path.join(run_dir, pat), recursive=True))
        for f in cands:
            try:
                return open(f).read().strip(), f
            except Exception:
                pass
    return None, None


def read_counts(run_dir):
    """(f2p_passed, f2p_total, p2p_passed, p2p_total) from a run's reward.json, or None.

    THE NOP GATE TURNS ON THESE, NOT ON THE REWARD. `reward` is 0.0 whenever ANY f2p test fails,
    so a nop scoring 0 is equally consistent with "every f2p failed" and with "one passed on an
    empty submission" - and that one is an INERT test, which cannot detect the bug, so the task
    grades nothing real. Same rule as mm_run.sh's control_counts() and qc_gate's nop_gate(); the
    three must agree or a bundle passes one gate and is refused by another.
    """
    import glob
    newest = _newest_trial(run_dir)
    first = [os.path.join(newest, "verifier", "reward.json")] if newest else []
    for f in [c for c in first if os.path.isfile(c)] + \
            sorted(glob.glob(os.path.join(run_dir, "**", "reward.json"), recursive=True)):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        r = d.get("rewards") or (d.get("verifier_result") or {}).get("rewards") or d
        if not isinstance(r, dict):
            continue
        out = []
        for k in ("f2p_passed", "f2p_total", "p2p_passed", "p2p_total"):
            v = r.get(k)
            # bool is an int subclass; `f2p_passed: false` must not read as a healthy 0.
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                out = None
                break
            out.append(int(v))
        if out:
            return tuple(out)
    return None


def nop_counts_verdict(counts):
    """(ok, description) for nop's counts. None means they were not recorded at all."""
    if counts is None:
        return False, ("reward.json carries no f2p/p2p counts - re-run nop "
                       "(QC reports this as verifier.reward_json.keys)")
    fp, ft, pp, pt = counts
    if ft <= 0:
        return False, f"f2p_total={ft} - no f2p test ran, so nothing was measured"
    if fp:
        return False, (f"{fp} of {ft} f2p test(s) PASS on an empty submission - they cannot "
                       f"detect the bug")
    if pp != pt:
        return False, f"{pt - pp} of {pt} p2p test(s) FAIL on nop - they are really f2p"
    return True, f"0 of {ft} f2p pass, {pp} of {pt} p2p pass"


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


def _resolve_qc_marker():
    """Where this audit records its pass. $MM_QC_MARKER wins (mm_run.sh exports it so the two
    cannot disagree); otherwise qc_digest picks the first directory that can hold a record.

    The fallback is the point: a clean audit that cannot record its pass leaves the CB with
    oracle and nop blocked behind a gate that has no bypass flag, over a directory problem that
    is not theirs to fix. See qc_digest.record_path.
    """
    explicit = os.environ.get("MM_QC_MARKER")
    if explicit:
        return explicit
    try:
        if CHECKS not in sys.path:
            sys.path.insert(0, CHECKS)
        sys.path.insert(0, HERE)
        import qc_digest
        return qc_digest.record_path("check")
    except Exception:
        return "/tmp/qc_check.md"


QC_MARKER = _resolve_qc_marker()


def _adjudication_ledger():
    """Where rulings are recorded. $MM_QC_ADJUDICATIONS wins, exactly as $MM_QC_MARKER does for the
    pass record, so the fix.py mm_run.sh spawns resolves the identical path its gate resolved."""
    explicit = os.environ.get("MM_QC_ADJUDICATIONS")
    if explicit:
        return explicit
    try:
        return _qc_digest().record_path("adjudications")
    except Exception:
        return None


def _qc_digest():
    if CHECKS not in sys.path:
        sys.path.insert(0, CHECKS)
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import qc_digest
    return qc_digest


def _load_recorded_rulings(tasks):
    """({fid: (verdict, reason)}, [notes]) from the ledger. Never raises into an audit.

    INTERNAL, like both records: the notes describe the STATE of the rulings and never name the
    file, for the same reason _record_detail does not - a reader who learns the path can hand-write
    one, and a hand-written ruling is indistinguishable from a ruled one.
    """
    try:
        from qc_common import CLEARED, CONFIRMED
        path = _adjudication_ledger()
        if not path:
            return {}, []
        return _qc_digest().load_rulings(tasks, path, valid_verdicts={CLEARED, CONFIRMED})
    except Exception:
        # An unreadable ledger costs a re-typed flag. An audit that dies over one costs a run.
        return {}, []


def _save_recorded_rulings(tasks, rulings):
    """Record freshly-made rulings so the next audit - including mm_run.sh's gate - replays them."""
    if not rulings:
        return None
    try:
        path = _adjudication_ledger()
        if not path:
            return None
        return _qc_digest().save_rulings(tasks, rulings, path)
    except Exception:
        return None


def update_qc_marker(tasks, findings, phase):
    """Write the QC marker when the bundle has no blocking defects; REMOVE it when it does.

    NOT CB-FACING. The marker is an INTERNAL artifact, and nothing in this function may disclose
    it -- not the path, not whether it was written, removed, or failed to write. Every print here
    is scoped to what the CB needs to act on: the blocking finding ids. That is why the blocker
    branch no longer says "QC PASS NOT RECORDED" and the clean branch prints nothing at all.
    Diagnostics for a failed write go to stderr only under $MM_QC_MARKER_DEBUG, so the team can
    still tell a broken marker from an absent one without putting it in the CB's output.

    This is a disclosure boundary, not a security one: the file is in /tmp and readable, and this
    module says plainly what it does. What changed is that the tooling no longer announces it.

    The marker gates NOTHING. mm_run.sh's qc_gate() decides from this script's EXIT CODE, and no
    code in either skill tests for the file's presence -- so suppressing the messaging costs the CB
    no actionable feedback. Do not make anything depend on the file without revisiting that.

    An audit trail a human can check afterwards: does this task still have blockers? Written by
    fix.py rather than by mm_run.sh's check gate for one reason -- the marker has to be earnable
    by FIXING the task, and the way you fix a task is this skill, which never runs harbor. If the
    check gate owned the file, a CB who repaired their bundle would have to spend a credentialed
    `check` run just to record that the repair worked.

    So every audit updates it, from whichever entry point ran: `fix.py qc`, `auto`, or mm_run.sh's
    gate calling `qc --gate-tier bundle`. Two properties follow, and both matter:

      * REMOVING on blockers is half the contract. A marker that were only ever written could
        survive the defect it vouches for -- fix a task, break it again, and the stale file still
        says clean. Every path either writes the current verdict or deletes the old one.
      * Overriding the check gate needs no special case. Reaching mm_run.sh's "[y/N] spend a run
        anyway?" prompt means this function JUST removed the marker, so proceeding records
        nothing. The gate having RUN and the gate having PASSED stay distinguishable.

    BUNDLE-TIER FAILs only, deliberately -- the same set `--gate-tier bundle` blocks on. A stale
    Oracle is a real finding and is still shown, but it describes a RUN, not the bundle, and
    re-running it is not "fixing the task". Keying off the exit code instead would make the marker
    mean different things depending on which flags the caller passed.
    """
    try:
        sys.path.insert(0, CHECKS)
        from qc_common import TIER_ORDER, FAIL, PENDING, TIER_BUNDLE
        limit = TIER_ORDER.index(TIER_BUNDLE)
        blocking = sorted({f.id for f in findings
                           if f.severity == FAIL and TIER_ORDER.index(f.tier) <= limit})
        # PENDING withholds the marker without being a blocker. THIS IS THE HALF THAT KEEPS THE
        # THREE-STATE MODEL HONEST. check_F no longer decides a collision itself - it proposes and
        # an agent rules via --adjudicated. If an unadjudicated proposal simply waited quietly, a
        # headless audit (mm_run.sh's gate, cron, CI) would have nobody to rule on it and would
        # write a marker saying the bundle is clean, on a task whose identifiers may genuinely
        # collide. A false positive costs a CB an argument; that would ship a broken task. So
        # "nobody looked yet" must not be able to earn the marker.
        pending = sorted({f.id for f in findings
                          if f.severity == PENDING and TIER_ORDER.index(f.tier) <= limit})
    except Exception:
        return None                        # cannot judge -> touch nothing, claim nothing

    if pending and not blocking:
        try:
            os.remove(QC_MARKER)
        except OSError:
            pass
        # "no QC pass was recorded", not "no marker was written": this line is CB-facing, and the
        # file vocabulary is what leads a reader to ask for the path and then create one by hand.
        # TWO FAMILIES, TWO DIFFERENT NEXT ACTIONS, and conflating them is how a blocker became a
        # formality. A collision finding IS decided by a code read, so the agent rules and moves
        # on. An overfit finding is not: it needs the posters, the repository and knowledge of
        # what the task is for, so it goes to the CB and the agent WAITS. Printing one blanket
        # "re-run with --adjudicated cleared" taught the agent to clear both on sight.
        overfit = [p for p in pending if p.startswith("tests_overfit_")]
        other = [p for p in pending if p not in overfit]
        print(f"\n  {len(pending)} finding(s) awaiting adjudication, so no QC pass was recorded: "
              f"{', '.join(pending[:4])}{' …' if len(pending) > 4 else ''}")
        print("  These are NOT failures and do not affect the exit code.")
        # A PARTIAL RULING IS THE EASIEST FAILURE TO MISREAD. "ADJUDICATED THIS RUN: 1 cleared"
        # prints further up and reads like success; this line then names the survivors, and when
        # one collision has raised two near-identically-named findings the survivor looks like the
        # id just cleared. Reported as "adjudication does not write the marker" - it does, once
        # NOTHING is left pending. Said here, next to the count, because the two halves being
        # printed by different code paths is what let them be read as unrelated.
        ruled_now = [f for f in findings if getattr(f, "adjudication", None)]
        if ruled_now:
            print(f"\n  NOTE: you ruled on {len(ruled_now)} finding(s) this run, and those ARE "
                  f"settled - but the\n  {len(pending)} above are not, and the QC pass needs ALL "
                  f"of them. Check whether a survivor is\n  the SAME collision reported from "
                  f"another angle (its evidence says so): those are separate\n  ids and each "
                  f"needs its own ruling.")
        if overfit:
            print(f"\n  {len(overfit)} of them are OVERFIT findings — THE CB DECIDES WHETHER "
                  f"YOU DIG:\n    " + "\n    ".join(overfit[:6])
                  + ("\n    …" if len(overfit) > 6 else ""))
            # THREE STEPS, AND THE ORDER IS THE WHOLE POINT. This message has been wrong in
            # three different ways, each fixing the last and introducing its own:
            #   "report and STOP"            -> the CB is handed a finding and no question, and
            #                                   left to work out that a CLI flag is involved.
            #   "ask if it is deliberate"    -> the CB is handed the ANALYSIS, which is what they
            #                                   have an agent for.
            #   "investigate, then confirm"  -> the agent digs unasked, and a dig here can mean
            #                                   building a container; that is the CB's call.
            # The checkpoint belongs BEFORE the dig (the CB authorises it) and the verdict belongs
            # AFTER it, with the agent, because by then it is evidence and not opinion. Do not
            # collapse these back into one step in either direction.
            print("  STEP 1 - REPORT. Tell the CB, in plain words, what each test pins and which "
                  "other\n  correct implementation it would reject. Never paste an id as if it "
                  "explained itself.")
            print("\n  STEP 2 - ASK WHETHER TO INSPECT, AND WAIT. Do not investigate unasked and "
                  "do not rule\n  unasked. This check reads test source only, so each finding is "
                  "a QUESTION; the CB\n  decides whether chasing it is worth the time. Do not ask "
                  "them to adjudicate it - that\n  is the analysis they have you for.")
            print("\n  STEP 3 - IF THEY SAY YES, INSPECT (TEST_FITNESS.md):")
            print("    - read the test BODY, not the diff (the diff hides the helpers): is the "
                  "symbol\n      imported and asserted BY NAME, or discovered by behaviour?")
            print("    - verify the \"the golden fix INTRODUCES this\" claim by grepping the BASE "
                  "tree.\n      Getting that backwards is the single most common false finding.")
            print("    - read instruction.md AND the posters: is the requirement anchored there?")
            print("    - where the read is not conclusive, MEASURE - build the alternative "
                  "implementation\n      and run the test (~2s each). That is the only step that "
                  "proves anything.")
            print("\n  What the evidence shows to be a FALSE POSITIVE, clear it yourself with "
                  "that evidence\n  as the reason - it is recorded and replayed on every later "
                  "audit, so the gate stays\n  green and nobody re-types anything. What it shows "
                  "to be REAL is a defect to FIX, not\n  to clear. Inconclusive: say so and go "
                  "back to the CB.")
            print("\n  NEVER clear one you have not inspected, and THE CB NEVER TYPES A FLAG.")
        if other:
            print(f"\n  {len(other)} are matcher/collision finding(s) — those ARE yours to rule "
                  f"on. Read the cited\n  line in tests/verifier.py, then re-run with "
                  f"`--adjudicated <id>=confirmed:\"why\"`\n  or `=cleared:\"why\"`.")
        # Says the ruling STICKS, without saying where. The old text implied the opposite by
        # omission, and an agent who believes a ruling evaporates re-types it on every audit - or
        # worse, concludes adjudication is broken and reaches for --no-qc.
        print("\n  A ruling only has to be made once: it is remembered and re-applied on later "
              "audits,\n  and it lapses on its own if tests/ or solution/ changes, since it was a "
              "judgment about\n  that code. Nothing to clean up either way.")
        return False

    if blocking:
        try:
            os.remove(QC_MARKER)
        except OSError:
            pass
        # The count and the ids, which is the whole of what the CB acts on. No mention of what was
        # or was not recorded, and nothing said about the previous marker being removed.
        print(f"\n  {len(blocking)} blocking defect(s) must be fixed first: "
              f"{', '.join(blocking[:4])}{' …' if len(blocking) > 4 else ''}")
        return False

    body = [
        "# QC check passed", "",
        f"- task_dir: `{tasks}`",
        f"- checked_at: {datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"- phase audited: {phase}",
        f"- audit: `{os.path.relpath(__file__, os.path.dirname(HERE))} qc`", "",
        "The QC audit found **no bundle-level blocking defects**, so this task is clear to spend",
        "a `harbor check` run on.", "",
        "This file is rewritten by every audit and deleted the moment one finds a blocker, so it",
        "always describes the latest state. It is never written by overriding the check gate —",
        "answering `y` to \"spend a check run anyway?\" or passing `--no-qc` leaves no marker.", "",
        "## What this does NOT assert", "",
        "- that the oracle/nop gate was reproduced (`mm_run.sh <task> oracle|nop`)",
        "- that the trial was run, or that the task is hard enough",
        "- that findings ABOVE bundle tier were clean — a stale Oracle is shown, not blocking",
        "- that a human reviewed the candidates and advisories", "",
    ]

    # Content digest of the bundle this verdict describes. Without it the marker asserts a
    # pass against a task PATH and a timestamp, neither of which survives an edit — the files
    # can change completely and the marker goes on vouching for them. mm_run.sh compares this
    # before oracle/nop. Best-effort: a marker with no digest is the pre-existing behaviour and
    # the comparison treats it as "nothing recorded", so a failure here degrades rather than
    # costing anyone their audit.
    try:
        import qc_digest
        body.append(qc_digest.marker_section(tasks))
    except Exception as exc:
        if os.environ.get("MM_QC_MARKER_DEBUG"):
            print(f"\n  could not compute bundle digest: {exc}", file=sys.stderr)
    try:
        with open(QC_MARKER, "w") as fh:
            fh.write("\n".join(body))
    except OSError as exc:
        # Silent to the CB. Opt in with MM_QC_MARKER_DEBUG=1 to tell a broken write from a bundle
        # that simply had blockers -- otherwise a permissions problem in /tmp is indistinguishable
        # from a failed audit to whoever reads the markers later.
        if os.environ.get("MM_QC_MARKER_DEBUG"):
            print(f"\n  could not write {QC_MARKER}: {exc}", file=sys.stderr)
        return None
    # Deliberately silent. A clean audit already prints its verdict; announcing the marker here is
    # what disclosed it.
    return True


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


def audit(a, footer=False):
    """ONE complete read-only audit: the four checks AND the live repair plan, joined.

    These used to be two commands - `qc` for the diagnosis and `auto` for the repair plan - which
    meant neither was complete on its own. `qc` never mentioned five of the fixes (debris,
    empty_noncanon, stray_files, unused_assets, asset_not_in_instruction are detected only here),
    and its `action:` column
    came from a static hint table rather than a fix that provably applies. Both are read-only, so
    there was never a safety reason to split them.

    Direction of dependency matters: fix.py drives checks/, never the reverse, so the checks stay
    standalone. qc_all.py runs --quiet and hands back structured findings; the join and the
    rendering happen here.
    """
    tasks = locate(a.root)
    if not tasks:
        print("error: no task.toml found", file=sys.stderr); return 2, None
    p = os.path.join(CHECKS, "qc_all.py")
    if not os.path.isfile(p):
        print(f"error: bundled checks missing at {CHECKS}", file=sys.stderr); return 2, None
    sys.path.insert(0, CHECKS)
    from qc_common import (Finding, render, verdict, detect_phase, join_fixes,
                           apply_phase, dedup, suppress_stale,
                           parse_adjudications, apply_adjudications, CLEARED)

    try:
        flag_verdicts = parse_adjudications(getattr(a, "adjudicated", None))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2, None

    # A RULING HAS TO SURVIVE THE NEXT AUDIT. mm_run.sh's qc_gate() re-invokes this command with a
    # fixed argument list, so before the ledger existed an agent could rule, earn the QC pass, and
    # have the very next `/run-check` recompute the finding as PENDING and delete the pass again -
    # a task with a correctly cleared finding could never get through the gate. Recorded rulings
    # are replayed here so the gate sees what the agent decided.
    #
    # FLAGS WIN over the record: re-ruling on the command line is how a verdict gets corrected, and
    # a stored `cleared` that could not be overridden by a fresh `confirmed` would be a trap.
    replayed, ledger_notes = _load_recorded_rulings(tasks)
    verdicts = dict(replayed)
    verdicts.update(flag_verdicts)
    for note in ledger_notes:
        # Never silent: an ignored or expired ledger looks exactly like one that was never written.
        print(f"\n  {note}")

    deliv = deliverables_root(tasks)
    tmp = tempfile.mkdtemp(prefix="qc_join_")
    try:
        rpath = os.path.join(tmp, "r.json")
        args = [sys.executable, p, a.root, "--quiet", "--json", rpath]
        if getattr(a, "emit_graders", None):
            args += ["--emit-graders", a.emit_graders]
        if getattr(a, "phase", None) and a.phase != "auto":
            args += ["--phase", a.phase]
        rc = subprocess.run(args, capture_output=True, text=True)
        if not os.path.isfile(rpath):
            print(rc.stdout + rc.stderr, file=sys.stderr)
            print("error: the checks produced no findings file", file=sys.stderr)
            return 2, None
        # --json writes the full report OBJECT, not the bare array that load_findings() reads;
        # using load_findings here silently swallowed every finding and left only the fixes.
        doc = json.load(open(rpath))
        findings = [Finding.from_dict(d) for d in doc.get("findings") or []]
        phase = doc.get("phase") or detect_phase(deliv)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    fixes = {f.id: f for f in detect(tasks, a.root)}
    findings, _matched = join_fixes(findings, fixes)
    findings = apply_phase(dedup(findings), phase)
    findings, _stale = suppress_stale(findings)
    # AFTER dedup, so a verdict names the id the report actually printed, and after apply_phase so
    # adjudicating something not decidable at this phase cannot resurrect it.
    findings, unused = apply_adjudications(findings, verdicts)
    for fid in unused:
        # Loud, not silent: an agent that adjudicated a stale or mistyped id must not walk away
        # believing it cleared something.
        print(f"\n  warning: --adjudicated `{fid}` matched no PENDING finding "
              f"(already resolved, or the id is wrong)", file=sys.stderr)
    # A RULING MUST LEAVE A VISIBLE TRACE. `cleared` drops the finding to OK, and OK findings are
    # collapsed in the rendered report - so a clearing was recoverable only by opening
    # qc_report.json. That is the same shape as every other defect this skill has chased: a
    # decision nobody can see. run-check.md already requires the agent to report which findings it
    # cleared and on what evidence; this makes forgetting harder than remembering.
    ruled = [f for f in findings if getattr(f, "adjudication", None)]
    # Only what was ruled on the command line AND matched a live PENDING finding is recorded.
    # `unused` ids already warn above; persisting one would make a typo permanent, and persisting a
    # replayed ruling would keep rewriting a record that already holds it.
    _save_recorded_rulings(tasks, {f.id: f.adjudication for f in ruled if f.id in flag_verdicts})
    if ruled:
        n_c = sum(1 for f in ruled if f.adjudication[0] == CLEARED)
        print(f"\n  ADJUDICATED THIS RUN: {n_c} cleared, {len(ruled) - n_c} confirmed. "
              f"Report these to the CB with their reasons -\n  a clean verdict that does not "
              f"mention them is misleading.")
        for f in ruled:
            verdict_, reason = f.adjudication
            # THE ORIGIN IS PART OF THE REPORT. A replayed `cleared` on an overfit finding is a
            # decision the CB made earlier, and one nobody re-states is one nobody can catch if it
            # was wrong - which is the single way persistence could hide an unmade ruling.
            origin = "ruled now" if f.id in flag_verdicts else "replayed from an earlier ruling"
            print(f"    [{verdict_.upper():9}] {f.id}  ({origin})\n                  {reason}")
    report, code = render(findings, phase, tasks, deliv=deliv,
                          verbose=getattr(a, "verbose", False), proposals=fixes)
    gate_tier = getattr(a, "gate_tier", None)
    if gate_tier:
        # Render everything at the detected phase (so nothing is hidden), but count only FAILs at
        # or below `gate_tier` toward the exit code. `harbor check` grades the TASK, so a stale
        # Oracle must be SHOWN and must not cost the run.
        from qc_common import TIER_ORDER, FAIL
        limit = TIER_ORDER.index(gate_tier)
        blocking = [f for f in findings
                    if f.severity == FAIL and TIER_ORDER.index(f.tier) <= limit]
        code = 1 if blocking else 0
        others = [f for f in findings
                  if f.severity == FAIL and TIER_ORDER.index(f.tier) > limit]
        print(f"\n  GATE SCOPE: blocking on {gate_tier}-tier FAILs only "
              f"({len(blocking)} blocking, {len(others)} shown-but-not-blocking).")
        if others:
            print("    not blocking: " + ", ".join(sorted({f.id for f in others})))
    print(report)
    repairs = render_agent_repairs(fixes)
    if repairs:
        print("\n" + repairs)
    # NOT gated by --no-report. That flag opts out of qc_report.json, which is a derived artifact;
    # the marker is the audit trail itself, and mm_run.sh's check gate passes --no-report on every
    # call -- so honouring it here would mean the one path that most needs a marker never got one.
    marker = update_qc_marker(tasks, findings, phase)

    # EXIT CODE 3 -- "no blockers, but nothing may vouch for this bundle yet."
    #
    # THE THREE-STATE MODEL HAS TO REACH THE CALLER. update_qc_marker withholds the marker on an
    # unadjudicated PENDING, but PENDING is deliberately not EXIT_WORTHY, so this function used to
    # hand back 0 -- and mm_run.sh's qc_gate, which reads nothing but the exit code, printed
    # "QC clean" and spent a credentialed check run on a task that had just been recorded as NOT
    # clean. Worse, the run left no marker, so check_digest() then grounded oracle/nop with
    # "no QC audit is on record -- run /run-check first", which produced the same clean verdict and
    # the same missing marker. A livelock with no exit.
    #
    # Derived from update_qc_marker's OWN return value rather than by re-deriving the PENDING set
    # here. Two functions computing "is this clean?" from the same findings is exactly how the two
    # halves drifted apart in the first place; keying off the marker decision makes the exit code
    # and the marker unable to disagree by construction.
    #
    # `is False` is load-bearing. False means "judged, and deliberately withheld". The `code == 0`
    # guard keeps FAILs at 1: when blockers withhold the marker the caller already has the stronger
    # signal.
    if code == 0 and marker is False:
        code = 3

    # EXIT CODE 4 -- "no verdict was recorded, and not on purpose."
    #
    # None is the THIRD return, and it re-opened the very livelock 3 was added to close. It means
    # either the judging block raised (a malformed tier, a failed qc_common import) or the marker
    # write raised (read-only /tmp, no space, a marker file owned by another user in a shared
    # sandbox, $MM_QC_MARKER pointing somewhere unwritable). Both leave no marker, and both used to
    # return 0 -- so the gate said "QC clean", spent the run, and check_digest then refused
    # oracle/nop with "no QC audit is on record", forever. Identical symptom to the PENDING bug,
    # different door.
    #
    # 4 IS NOT A FAILURE AND THE GATE DOES NOT STOP ON IT. Nothing here says the task is bad: at
    # code 0 no decidable finding was a FAIL, so the check run is still worth spending. What is
    # false is the word "clean", which claims a pass was recorded when none was. The gate warns and
    # proceeds -- the same stance the runner already takes for "QC skill not found" and for the two
    # check_digest exceptions, where the CHECK is unavailable rather than the bundle being bad.
    #
    # Deliberately silent HERE. update_qc_marker's contract is that the marker is internal and this
    # module never discloses its path; mm_run.sh owns the CB-facing message and already names
    # $QC_MARKER in check_digest's output, so the actionable half is said there, once.
    if code == 0 and marker is None:
        code = 4
    report_gate_decision(tasks, None)
    if footer:
        _authorize_footer(a, fixes)
    if not getattr(a, "no_report", False):
        out = os.path.join(deliv, "qc_report.json")
        v, _ = verdict(findings, phase)
        try:
            with open(out, "w") as fh:
                json.dump({"phase": phase, "tasks_dir": tasks, "verdict": v, "exit_code": code,
                           "proposed_fixes": [f.as_dict() for f in fixes.values()],
                           # Broken out so the agent can drive its own worklist without parsing
                           # the rendered report.
                           "agent_repairs": [f.as_dict() for f in fixes.values()
                                             if f.kind == "agent"],
                           "findings": [f.as_dict() for f in findings]}, fh, indent=2)
            print(f"\n  wrote {out}")
        except Exception as exc:
            print(f"\n  could not write {out}: {exc}", file=sys.stderr)
    return code, fixes


def render_agent_repairs(fixes, width=78):
    """The work the AGENT does after --apply: one known-correct repair each, no second approval.

    Deliberately a POINTER, not a playbook. Every one of these repairs is already written down in
    RUBRIC_MODES.md, and a second copy here would drift from it -- the same reason this skill
    deleted its bundled copy of the runner. What is printed is the part the doc cannot know: which
    sites in THIS bundle, and the command that proves the repair landed.
    """
    ag = sorted((f for f in fixes.values() if f.kind == "agent"), key=lambda f: f.id)
    if not ag:
        return ""
    out = [f"AGENT REPAIRS — {len(ag)} blocker(s) the agent fixes itself, inside the same approval",
           "  Not a second question for the CB. Each has ONE correct repair, documented where the",
           "  .playbook points. Make the edit, then run .verify and show the [OK ] — an unproven",
           "  repair is reported as unproven, never as done."]
    for f in ag:
        out.append(f"\n  [agent] [{f.trial_class}] {f.id}: {f.title}")
        for e in list(f.evidence or [])[:6]:
            out.append(f"            → {e}")
        if f.playbook:
            out.append(f"            read:   {f.playbook}")
        if f.verify:
            out.append(f"            prove:  {f.verify}")
    return "\n".join(out)


def _authorize_footer(a, fixes):
    auto = [f for f in fixes.values() if f.kind == "auto"]
    agent = [f for f in fixes.values() if f.kind == "agent"]
    print("\n  NOTHING WAS CHANGED. To authorize:")
    if auto:
        print(f"    fix.py auto \"{a.root}\" --apply          apply the {len(auto)} mechanical fix(es)")
    print(f"    fix.py auto \"{a.root}\" --run            reproduce the gate (oracle + nop)")
    if auto:
        print(f"    fix.py auto \"{a.root}\" --apply --run    both")
    if agent:
        print(f"\n  The same --apply approval also covers the {len(agent)} AGENT REPAIRS above — "
              f"the agent\n  makes those edits itself and proves them. Do not ask the CB again "
              f"for each one.")
    for f in fixes.values():
        if f.kind == "ask":
            print(f"    fix.py apply \"{a.root}\" --approve {f.id}   (needs your decision first)")


def cmd_qc(a):
    """The complete read-only audit: findings AND the repair plan that would fix them."""
    return audit(a)[0]


def cmd_plan(a):
    tasks = locate(a.root)
    if not tasks:
        print("error: no task.toml found", file=sys.stderr); return 2
    fixes = detect(tasks, a.root)
    VERDICT = {"A": "keep the existing trial as-is",
               "B": "keep the trajectory; re-check the rubric against the golden fix",
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
        tag = {"auto": "AUTO ", "agent": "AGENT", "ask": "ASK  ", "never": "NEVER"}.get(f.kind,
                                                                                        f.kind)
        print(f"  [{tag}] [{f.trial_class}] {f.id}: {f.title}")
        for e in f.evidence[:6]:
            print(f"            - {e}")
        print(f"            why: {f.why}")
        if f.playbook:
            print(f"            read: {f.playbook}")
    print(f"\n  TRIAL - depends on what you approve:")
    print(f"    approve AUTO only          -> class {auto_worst}: {VERDICT[auto_worst]}")
    if any(f.kind == "ask" for f in fixes):
        w = max(auto_worst, ask_worst)
        print(f"    + any ASK item             -> class {w}: {VERDICT[w]}")
    print("\n  AUTO  = mechanical, safe to apply once approved")
    print("  AGENT = one correct repair, but a script must not write it. The AGENT makes the edit "
          "and proves it,")
    print("          inside the same approval as AUTO - it is not a second question for the CB")
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
        for chunk in a.approve:
            approved |= {x.strip() for x in chunk.split(",") if x.strip()}
    if a.approve_all_auto:
        approved |= {i for i, f in fixes.items() if f.kind == "auto"}
    todo = [f for i, f in fixes.items() if i in approved and f.action]
    refused = [i for i in approved if i in fixes and fixes[i].kind == "never"]
    if refused:
        print(f"  refusing {refused}: kind=never, fixing it is authoring", file=sys.stderr)
        todo = [f for f in todo if f.id not in refused]
    # kind=agent is refused too -- fix.py must never write verifier.py or judge.py -- but it is NOT
    # a dead end, so the message routes rather than just declining. Naming one of these is the
    # agent asking the wrong tool: the repair is its own job, and it is already authorized.
    for i in sorted(approved):
        if i in fixes and fixes[i].kind == "agent":
            f = fixes[i]
            print(f"  refusing {i}: kind=agent — no script writes this file. YOU make the edit "
                  f"({f.playbook or 'see RUBRIC_MODES.md §2c'}), then prove it:\n"
                  f"      {f.verify or 'python3 checks/qc_rubric_format.py <Tasks>'}",
                  file=sys.stderr)
    if not todo:
        print("  nothing approved to apply."); return 0

    # CONSENT MODEL. Naming a fix (`--approve judge_drift`) IS the approval - the id identifies
    # exactly what will change, so nothing more is needed. A BLANKET selection
    # (`--approve-all-auto`, which is what `auto` uses) does not identify anything, so it needs a
    # separate `--apply` on the command line before a single byte is written.
    if a.approve_all_auto and not getattr(a, "apply", False):
        print(f"\n  DRY RUN - nothing was written. {len(todo)} fix(es) would be applied:")
        for f in todo:
            print(f"    [{f.trial_class}] {f.id}: {f.title}")
            for e in f.evidence[:4]:
                print(f"            - {e}")
        print(f"\n  authorize with:  fix.py apply \"{a.root}\" --approve-all-auto --apply")
        print(f"  or name them:    fix.py apply \"{a.root}\" --approve "
              f"{','.join(f.id for f in todo)}")
        return 6

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
    changed_desc = f"{len(applied)} fix(es) applied: " + ", ".join(f.id for f, _ in applied)
    qc_after = qc_state(a.root)
    regressed = print_qc_delta(qc_before, qc_after)
    report = write_report(a.root, tasks, applied, worst, snap, qc_before, qc_after)
    print(f"  report -> {report}")
    report_gate_decision(tasks, changed_desc if applied else None)
    report_rubric_grading(tasks, [f.id for f, _ in applied])

    # Re-detect rather than reusing the pre-apply set: an auto fix can settle an agent repair's
    # precondition (installing judge.py, or mapping the EVAL_* block), and telling the agent to fix
    # something that is already fixed is how a worklist stops being trusted.
    repairs = render_agent_repairs({f.id: f for f in detect(tasks, a.root)})
    if repairs:
        print("\n" + repairs)
        print("\n  These are NOT applied and NOT a second question — they are covered by the "
              "approval\n  you already have. Make the edits, prove each one, then re-run "
              f"`fix.py qc \"{a.root}\"`.")

    if a.verify:
        # `--verify` is an explicit request for the run, so it authorizes it - same logic as a
        # named --approve authorizing its own fix.
        rc = verify(tasks, a.root, authorized=True)
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


def gate_needs_rerun(tasks, changed):
    """(needs_rerun, reason) - is an oracle+nop run actually warranted right now?

    A docker run costs real time, so it should not be asked for reflexively. It IS warranted when
    the bundle changed, because the previous rewards describe a bundle that no longer exists.

    But "we changed nothing" is not on its own evidence that the gate holds - it is only evidence
    that nothing got WORSE. Two cases need a run even with no edit:
      * the gate was never reproduced at all (the pre-trial default - no Oracle/ or Nop/ yet);
      * the last run predates the current bundle, so its reward describes older files.
    Otherwise there is genuinely nothing to learn from running it again, and we say so.
    """
    root = deliverables_root(tasks)
    if changed:
        return True, "the bundle was modified, so the previous rewards describe files that no " \
                     "longer exist"

    # Any trial dir, whatever its name (a nested task's are `<task-name>__*`, not `Tasks__*`).
    missing = [n for n in ("Oracle", "Nop")
               if not any(os.path.isfile(os.path.join(t, "verifier", "reward.txt"))
                          for t in find_trial_dirs(os.path.join(root, n)))]
    if missing:
        return True, (f"the gate has never been reproduced ({', '.join(missing)} absent), so it is "
                      f"unproven - not passing")

    newest = 0
    for dp, _dn, fn in os.walk(tasks):
        for f in fn:
            try:
                newest = max(newest, os.path.getmtime(os.path.join(dp, f)))
            except OSError:
                pass
    for n in ("Oracle", "Nop"):
        cfg = os.path.join(job_dir(os.path.join(root, n)), "config.json")
        if os.path.isfile(cfg) and newest > os.path.getmtime(cfg) + 120:
            return True, (f"the last {n} run predates the current bundle, so its reward describes "
                          f"older files")
    return False, "nothing was modified and the existing oracle/nop runs still match this bundle"


def report_gate_decision(tasks, changed):
    """State plainly what changed and whether a re-run is warranted. The caller (a human, or an
    agent talking to one) should not have to infer either from prose."""
    print(f"\n  MODIFIED: {'yes — ' + changed if changed else 'nothing'}")
    need, why = gate_needs_rerun(tasks, changed)
    print(f"  GATE: {'MUST be re-reproduced' if need else 'no re-run needed'} — {why}")
    return need


def verify(tasks, root, modes=("oracle", "nop"), authorized=False):
    """0 = verified, 1 = regressed, 2 = COULD NOT verify (never silently 'ok').

    Runs through the MM SWE runner, exactly the commands a CB uses by hand. The TRIAL is never
    run here: it is the only step needing credentials, and re-running it is a human decision
    because it costs a real model call.

    CONSENT: a docker run is a real action - it builds the environment image and can occupy up to
    $MM_RUN_TIMEOUT (default 5400s). It therefore never starts unless it was explicitly asked for
    (`--run`, or `apply --verify`). Unauthorized, this prints the exact commands and returns 2,
    which is NOT VERIFIED - never a pass. "We did not run the gate" must not be able to read as
    "the gate holds".
    """
    if not authorized:
        print("  the gate was NOT reproduced - a docker run needs explicit authorization.")
        for mode in modes:
            print(f"    would run: bash <runner> {tasks} {mode}   "
                  f"(expect {'1.0' if mode == 'oracle' else 'every f2p to FAIL, every p2p to PASS'})")
        print("  authorize with --run (bounded by $MM_RUN_TIMEOUT, default 5400s).")
        return 2
    runner = resolve_runner()
    if not runner:
        print("  WARNING: no MM SWE runner found - oracle/nop were NOT verified.\n"
              "           Install the mmswe-runner skill, set $MM_RUNNER, or re-run without\n"
              "           --verify to accept that nothing was checked.", file=sys.stderr)
        return 2
    print(f"  runner: {runner}")
    expect = {"oracle": "1.0", "nop": "all f2p fail, all p2p pass"}
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
        run_dir = os.path.join(deliverables_root(tasks), mode.capitalize())
        got, src = read_reward(run_dir)
        if got is None:                       # fall back to the log line
            m = re.search(r"reward(?:\.txt)?\s*=?\s*([0-9.]+)", out)
            got, src = (m.group(1) if m else None), "stdout"
        if got is None:
            print(f"  COULD NOT VERIFY: {mode} produced no reward. Last output:\n"
                  + "\n".join("    " + l for l in out.strip().splitlines()[-8:]), file=sys.stderr)
            return 2
        print(f"    {mode} reward = {got}   (from {src})")
        if mode == "nop":
            # Nop is judged on the counts; the reward above is printed for the record only.
            ok, why = nop_counts_verdict(read_counts(run_dir))
            print(f"    nop counts: {why}")
            if not ok:
                print(f"  REGRESSED: nop - {why}", file=sys.stderr)
                return 1
        elif got != want:
            print(f"  REGRESSED: {mode} is {got}, expected {want}", file=sys.stderr)
            return 1
    return 0


# Fixes that change the rubric/judge half of the score. After these, whether the rubric is still
# satisfied by the golden fix is an open question again.
# `legacy_creds` is deliberately NOT here: stripping [verifier.env] removes credentials the
# sub-agent judge never needed, so it cannot change a verdict.
RUBRIC_SIDE = {"judge_missing", "judge_drift", "rubric_task_id", "test_sh_judge",
               "rubrics_shape", "rubric_file", "rubric_quality"}


def find_judge_request(root, runs=("Oracle",)):
    """(run_dir, request_dir) for the first judge request found.

    ORACLE by default, and that is the whole point: the oracle run applies solution/fix.patch, so
    its candidate diff IS the golden fix. A rubric that the golden fix fails would fail every
    correct submission. Nop is useless here (empty submission -> empty diff -> nothing to grade).
    """
    for r in runs:
        for prompt in sorted(glob.glob(os.path.join(root, r, "**", "PROMPT.md"), recursive=True)):
            return os.path.join(root, r), os.path.dirname(prompt)
    return None, None


def report_rubric_grading(tasks, applied_ids):
    """After the gate, say whether the rubric still needs checking against the golden fix.

    WHY THERE IS NO `rescore` STEP. Re-running oracle regenerates the judge REQUEST but cannot
    answer it: judge.py finds no verdict, takes phase 1, prints nothing, and the verifier scores on
    tests alone - so the reward comes back 1.0 whether or not the rubric is satisfiable. Folding a
    verdict back into reward.txt/reward.json only re-proves the 1.0 -> 0.5 arithmetic, and
    qc_judge already checks that statically by reading verifier.py.

    What nothing else can decide is whether the golden fix actually satisfies each criterion. One it
    fails would fail every correct submission - a Major "Incorrect Criterion" - and that is one of
    the six semantic issues the static checks can only report as OPEN. Grading the request against
    the oracle's own diff settles it, keylessly, before any trial.

    So this locates the request and stops. Grading is the agent's job; nothing is written.
    """
    touched = sorted(set(applied_ids) & RUBRIC_SIDE)
    if not touched:
        return
    stub, why = rubric_is_stub(tasks)
    print(f"\n  RUBRIC SIDE CHANGED: {', '.join(touched)}")
    if stub:
        print(f"  nothing to re-check — {why}.")
        if "always-pass stub" in why:
            print("  A stub cannot fail, so there is no verdict to establish — but that is the")
            print("  defect, not a pass. STRIP the rubric layer: delete tests/rubrics.json and")
            print("  tests/judge.py and drop \"rubric_file\" from tests/config.json, leaving the")
            print("  --rubric gate in verifier.py and the guarded judge block in test.sh.")
        return
    root = deliverables_root(tasks)
    run_dir, reqdir = find_judge_request(root)
    print(f"  the rubric needs checking against the golden fix — {why}.")
    if not reqdir:
        print("  no judge request yet. Reproduce the gate (--run): the keyless ORACLE run applies")
        print("  solution/fix.patch, so the request it writes is exactly what the rubric must be")
        print("  true of.")
        return
    print(f"  judge request: {reqdir}")
    print("    criteria_payload.json · source.txt (the golden diff) · changed_files.txt · PROMPT.md")
    print("  GRADE IT and report each criterion pass/fail. Any criterion the GOLDEN fix fails would")
    print("  fail every correct submission — report that as a Major 'Incorrect Criterion'.")
    print("  No model call by this skill; the judge is a sub-agent. Nothing needs to be written.")


def write_report(root, tasks, applied, worst, snap, qc_before=None, qc_after=None):
    p = os.path.join(deliverables_root(tasks), "FIX_REPORT.md")
    verdict = {"A": "**Keep the existing trial.** Nothing the agent saw or that scoring depends "
                    "on changed.",
               "B": "**Keep the trajectory, but the rubric half of the score is stale.** Re-grade "
                    "the oracle's judge request against the golden fix. No "
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
                 "- behavioural: the oracle's judge request appears, and the GOLDEN fix "
                 "satisfies every criterion\n")
    return p


def cmd_auto(a):
    """Report what WOULD be fixed and run. Writes nothing and runs nothing without authorization.

    THIS IS A DRY RUN BY DEFAULT. It used to apply every AUTO fix unprompted - deleting files and
    rewriting task.toml, config.json, rubrics.json, test.sh and judge.py - and then start docker.
    The snapshot and the rollback made that recoverable, but recovery is not consent: by the time
    they help, the change has already happened. Two separate authorizations now exist, because
    they are two different costs:

        --apply    authorize writes to Tasks/
        --run      authorize the oracle+nop docker runs ($MM_RUN_TIMEOUT, default 5400s)

    Verification stays unconditional WHEN AUTHORIZED - including when nothing was fixed, since a
    task that needed no repair can still have a broken gate. Without --run the gate is simply
    reported as unproven (exit 5), never as holding.
    """
    tasks = locate(a.root)
    if not tasks:
        print("error: no task.toml found", file=sys.stderr); return 2
    fixes = detect(tasks, a.root)
    auto = [f for f in fixes if f.kind == "auto"]
    ask = [f for f in fixes if f.kind == "ask"]
    never = [f for f in fixes if f.kind == "never"]
    do_apply = getattr(a, "apply", False)
    do_run = getattr(a, "run", False) and not getattr(a, "no_verify", False)

    rc = 0
    if not do_apply and not do_run:
        # Bare `auto` prints the SAME complete audit as `qc`, plus the authorize footer. Two entry
        # points, one output - so whichever a CB types, they cannot end up with a partial picture.
        code, _ = audit(a, footer=True)
        return 6 if (auto or ask) else code
    if not auto:
        print(f"\nMM SWE QC FIX - nothing to fix automatically in {tasks}")
        report_gate_decision(tasks, None)
    elif not do_apply:
        print(f"\nMM SWE QC FIX - {len(auto)} fix(es) NOT applied (--run given without --apply).")
        for f in auto:
            print(f"    [auto] [{f.trial_class}] {f.id}: {f.title}")
        print("\n  MODIFIED: nothing")
        rc = 6
    else:
        # apply WITHOUT verifying here; we verify once below so a no-op run is covered too
        a.approve, a.approve_all_auto, a.plan = None, True, None
        want_verify, a.verify = do_run, False
        rc = cmd_apply(a)
        a.verify = want_verify
        if rc != 0:
            return rc

    if getattr(a, "no_verify", False):
        print("\n  --no-verify: oracle/nop were NOT run. The gate is unproven.")
        if rc == 0:
            rc = 5
    else:
        print("\n  the gate (oracle + nop; the trial is never run):")
        vrc = verify(tasks, a.root, authorized=do_run)
        if vrc == 1:
            print("\n  GATE BROKEN - see above. The task is NOT ready.", file=sys.stderr)
            rc = 4
        elif vrc == 2:
            # In a dry run the block above already said the gate was not reproduced and why;
            # repeating it on stderr just interleaves ahead of the report.
            if rc != 6:
                print("\n  NOT VERIFIED - the gate was not reproduced.", file=sys.stderr)
                rc = 5
        else:
            print("  gate holds: oracle 1.0 / nop all-f2p-fail, all-p2p-pass")
            # Ordering matters: the keyless oracle/nop run is what WRITES the judge request, so
            # the grading step can only be pointed at after the gate has been reproduced.
            if do_apply:
                report_rubric_grading(tasks, [f.id for f in auto])

    if rc == 6:
        print(f"\n  NOTHING WAS CHANGED. To authorize:")
        if auto and not do_apply:
            print(f"    fix.py auto \"{a.root}\" --apply          apply the {len(auto)} fix(es)")
        if not do_run:
            print(f"    fix.py auto \"{a.root}\" --run            reproduce the gate")
        if auto and not do_apply and not do_run:
            print(f"    fix.py auto \"{a.root}\" --apply --run    both")

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
    """Reproduce the gate on its own - no fixing. Oracle and nop only, never the trial.

    Needs --run: this command's whole job is to start docker, so it is exactly the action that
    must not happen because someone typed a command to "have a look".
    """
    tasks = locate(a.root)
    if not tasks:
        print("error: no task.toml found", file=sys.stderr); return 2
    authorized = getattr(a, "run", False)
    rc = verify(tasks, a.root, authorized=authorized)
    if not authorized:
        print("\n  DRY RUN: nothing was run. Authorize with "
              f"`fix.py verify \"{a.root}\" --run`.")
        return 6
    print({0: "\n  VERIFIED: oracle 1.0 / nop all-f2p-fail, all-p2p-pass",
           1: "\n  FAILED: the gate does not hold",
           2: "\n  NOT VERIFIED: nothing was run"}[rc])
    return rc


# ------------------------------------------------------------------ test-fitness runs
# WHY THESE ARE RUNNERS AND NOT CHECKS. Overfit and underfit are opposite ends of one axis, and a
# static scan reaches only the extremes: an assertion pinning a literal only the golden produces,
# and a test asserting nothing that could tell a right fix from a wrong one. The MIDDLE - a
# plausible, wrong, non-trivial fix that scores 1.0 - is not decidable by reading. It is decidable
# by RUNNING one, which is all these two commands do.
#
# What they deliberately do NOT do is author the patch or judge it. `variant` scoring < 1.0 means
# EITHER the test is overfit OR the variant is wrong, and nothing here can tell those apart - so it
# reports both readings and names the failing tests, never a verdict. The correctness judgment
# belongs to the agent driving TEST_FITNESS.md.
#
# THE ROUTE IS NOT OBVIOUS AND WAS ARRIVED AT BY EXPERIMENT. Swapping solution/fix.patch changes
# the bundle, so `mm_run.sh <copy> oracle` is REFUSED outright ("no QC audit is on record for this
# task", exit 2) - the controls gate has no bypass flag. The run therefore needs its own QC pass,
# minted for the swapped bundle. And it must be minted somewhere ELSE: the marker is a single file
# holding one task's digest, the work copy shares the real task's task_id, so writing the default
# path would clobber the real task's record and ground its oracle. $MM_QC_MARKER pointed at a
# throwaway inside the work dir keeps the two apart - verified: the real marker is never created.
_FITNESS = {
    # kind:      (expected reward, what the expectation means)
    "probe":   (0.0, "a deliberately WRONG fix must be rejected by the suite"),
    "variant": (1.0, "a correct fix written differently must still pass"),
}


def _read_reward(out_dir):
    """(reward, {test-key: 1.0/0.0}) from the run's reward.json, or (None, {})."""
    for cand in sorted(glob.glob(os.path.join(out_dir, "**", "reward.json"), recursive=True)):
        try:
            d = json.load(open(cand))
        except Exception:
            continue
        if isinstance(d, dict) and d.get("reward") is not None:
            per = {k: v for k, v in d.items() if k.startswith(("f2p::", "p2p::"))}
            return float(d["reward"]), per
    return None, {}


def cmd_fitness(a, kind):
    expected, meaning = _FITNESS[kind]
    tasks = locate(a.root)
    if not tasks:
        print("error: no task.toml found", file=sys.stderr); return 2
    if not os.path.isfile(a.patch):
        print(f"error: no such patch: {a.patch}", file=sys.stderr); return 2
    label = a.label or os.path.splitext(os.path.basename(a.patch))[0]
    runner = resolve_runner()

    print(f"\n  {kind.upper()}  {label}")
    print(f"    patch     {a.patch}")
    print(f"    expects   reward = {expected}  ({meaning})")
    if not getattr(a, "run", False):
        print(f"\n  DRY RUN: nothing was run. This starts docker, so authorize it explicitly:\n"
              f"    fix.py {kind} \"{a.root}\" --patch \"{a.patch}\" --run")
        return 6
    if not runner:
        print("\n  NOT RUN: no MM SWE runner found (set $MM_RUNNER or install mmswe-runner).",
              file=sys.stderr)
        return 2

    work = tempfile.mkdtemp(prefix=f"qcfit_{kind}_")
    copy = os.path.join(work, "Tasks")
    shutil.copytree(tasks, copy)
    shutil.copyfile(a.patch, os.path.join(copy, "solution", "fix.patch"))
    # `files_edited` DESCRIBES THE PATCH, so on the work copy it has to describe the swapped one.
    # A probe or variant touches a different file set almost by definition - the shallow-fix probe
    # is literally "the golden minus one file" - and leaving the original list makes the audit
    # report a real task-coherence defect (`d_fix_patch_paths_*`, QC #8: patch paths set-equal to
    # files_edited) about a scratch copy nobody is submitting. That blocks the mint, which blocks
    # the oracle, and every fitness run would die before measuring anything. Rewriting the list
    # here keeps the check meaningful for the REAL task and truthful about the copy.
    _pt = open(a.patch, encoding="utf-8", errors="replace").read()
    _paths = sorted({p.strip() for p in
                     re.findall(r"(?m)^diff --git a/\S+ b/(\S+)$", _pt) if p.strip()})
    _toml = os.path.join(copy, "task.toml")
    _txt = open(_toml, encoding="utf-8", errors="replace").read()
    _new = "files_edited = [\n" + ",\n".join('  "%s"' % p for p in _paths) + "\n]"
    _txt2 = re.sub(r"(?m)^files_edited\s*=\s*\[.*?\n\]", _new, _txt, count=1, flags=re.S)
    if _txt2 != _txt:
        open(_toml, "w", encoding="utf-8").write(_txt2)
        print(f"    files_edited rewritten on the work copy to the patch's {len(_paths)} path(s)")
    env = dict(os.environ)
    # Isolated records: nothing this run writes may touch the real task's QC pass.
    env["MM_QC_MARKER"] = os.path.join(work, "qc_check.md")
    env["MM_QC_TRIAL_MARKER"] = os.path.join(work, "qc_trial.md")

    # The swapped bundle needs its OWN audit pass before the controls gate will let the oracle run.
    # Free, no docker. A blocker here is reported as such rather than surfacing later as an
    # unexplained refusal from the runner.
    qc = subprocess.run([sys.executable, os.path.abspath(__file__), "qc", copy,
                         "--gate-tier", "bundle", "--no-report"],
                        capture_output=True, text=True, env=env)
    if not os.path.exists(env["MM_QC_MARKER"]):
        print(f"\n  NOT RUN: the audit found blocking defects in the swapped bundle, so no QC pass "
              f"was recorded and the controls gate will refuse the oracle.\n"
              f"  This is about the PATCH, not the task: fix the patch, or audit the task first.\n"
              f"  work copy: {copy}", file=sys.stderr)
        for line in (qc.stdout or "").splitlines():
            if "blocking defect" in line:
                print("   " + line.strip(), file=sys.stderr)
        return 2

    out = os.path.join(work, "out")
    r = subprocess.run(["bash", runner, copy, "oracle", "--root", out],
                       capture_output=True, text=True, env=env,
                       timeout=int(os.environ.get("MM_RUN_TIMEOUT", "5400")))
    reward, per = _read_reward(out)
    if reward is None:
        print(f"\n  NOT MEASURED: the run produced no reward.json - an infra failure, never a "
              f"verdict in either direction.\n  logs: {out}", file=sys.stderr)
        print((r.stdout or "")[-1200:], file=sys.stderr)
        return 2

    failed = sorted(k for k, v in per.items() if not v)
    passed_f2p = sorted(k for k, v in per.items() if v and k.startswith("f2p::"))
    print(f"\n    reward    {reward}   (expected {expected})")
    print(f"    work copy {copy}\n    run       {out}")

    if reward == expected:
        if kind == "probe":
            print("\n  PASS - the suite REJECTS this hack. It says nothing about hacks you did "
                  "not write: record what was probed, not that the tests are tight.")
        else:
            print("\n  PASS - the tests are agnostic FOR THIS VARIANT. Other implementations are "
                  "unexamined.")
        return 0

    if kind == "probe":
        print("\n  FAIL - TESTS TOO FORGIVING. A fix that does not implement the required "
              "behaviour scored 1.0, so the suite cannot tell it from a real one and a trial can "
              "hack its way to a pass.")
        print(f"    f2p that PASSED on the hack ({len(passed_f2p)}):")
        for k in passed_f2p[:8]:
            print(f"      {k[5:]}")
        print("    Tighten those, then re-run the gate AND any variants - tightening must not tip "
              "into overfit.")
        return 1

    print("\n  UNRESOLVED - this variant did not pass, and that has TWO readings this tool cannot "
          "tell apart:")
    print("      the variant is WRONG          -> fix the variant; it indicts nothing")
    print("      the variant is CORRECT        -> the assertion below pins the golden: OVERFIT")
    print(f"    failing tests ({len(failed)}):")
    for k in failed[:8]:
        print(f"      {k}")
    print("    Decide with the correctness critic in TEST_FITNESS.md BEFORE touching any test.")
    return 1


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
    pv = sub.add_parser("verify");   pv.add_argument("root")
    pv.add_argument("--run", action="store_true",
                    help="authorize the oracle/nop docker runs (without it, a dry run)")
    pa = sub.add_parser("auto");     pa.add_argument("root")
    # Both authorizations are opt-IN. `auto` used to apply and run unprompted; the snapshot made
    # that recoverable but not consented to.
    pa.add_argument("--apply", action="store_true",
                    help="authorize writes to Tasks/ (without it, a dry run)")
    pa.add_argument("--run", action="store_true",
                    help="authorize the oracle/nop docker runs (without it, the gate is unproven)")
    pa.add_argument("--no-verify", action="store_true",
                    help="never run the gate, even with --run; accept an unproven gate")
    pa.add_argument("--phase", default="auto",
                    choices=["auto", "bundle", "gate", "post-trial", "submission"])
    pa.add_argument("--verbose", action="store_true")
    pa.add_argument("--no-report", action="store_true")
    pa.add_argument("--emit-graders", default=None)
    p0 = sub.add_parser("qc");       p0.add_argument("root"); p0.add_argument("--emit-graders")
    p0.add_argument("--no-report", action="store_true",
                    help="do not write qc_report.json beside Tasks/")
    # forwarded to qc_all.py - previously unreachable through fix.py, so the documented entry
    # point could not do something the engine already supported
    p0.add_argument("--phase", default="auto",
                    choices=["auto", "bundle", "gate", "post-trial", "submission"])
    p0.add_argument("--verbose", action="store_true", help="expand clean categories")
    p0.add_argument("--gate-tier", choices=["bundle", "gate", "trial", "submission"],
                    help="show everything, but exit non-zero only for FAILs at or below this "
                         "tier (used by mm_run.sh's check pre-flight)")
    # append, for the same reason --approve is: silently keeping only the last of several verdicts
    # would let an agent believe it had adjudicated three findings and have recorded one.
    p0.add_argument("--adjudicated", action="append", metavar="ID=cleared|confirmed:\"why\"",
                    help="record a verdict on a PENDING finding, e.g. "
                         "--adjudicated tests_ident_collision_x_ab12cd=cleared:\"verifier.py:115 "
                         "matches with endswith; the pair is prefix-related so the keys differ\". "
                         "`confirmed` promotes it to a blocking FAIL; `cleared` records the reason "
                         "and drops it. A reason is required either way. The ruling is RECORDED "
                         "and replayed by later audits - including the one mm_run.sh's gate runs, "
                         "which forwards this flag - so you type it once; it expires by itself if "
                         "tests/ or solution/ changes, and re-passing the flag overrides it.")
    p1 = sub.add_parser("plan");     p1.add_argument("root"); p1.add_argument("--out")
    p2 = sub.add_parser("apply");    p2.add_argument("root"); p2.add_argument("--plan")
    # Naming a fix IS the approval; a blanket --approve-all-auto additionally needs --apply.
    # append, not store: `--approve a --approve b` used to keep only `b` and silently drop `a`.
    # For the flag that IS the consent, dropping one is a CB believing they approved two fixes
    # and getting one. Comma-separated values keep working.
    p2.add_argument("--approve", action="append")
    p2.add_argument("--approve-all-auto", action="store_true")
    p2.add_argument("--apply", action="store_true",
                    help="required with --approve-all-auto; not needed when naming ids")
    p2.add_argument("--verify", action="store_true",
                    help="also reproduce the gate (this authorizes the docker run)")
    p3 = sub.add_parser("rollback"); p3.add_argument("root"); p3.add_argument("--snapshot", required=True)
    for _k in ("probe", "variant"):
        _p = sub.add_parser(_k); _p.add_argument("root")
        _p.add_argument("--patch", required=True)
        _p.add_argument("--label")
        _p.add_argument("--run", action="store_true",
                        help="authorize the docker oracle run on the work copy")
    a = ap.parse_args()
    return {"verify": cmd_verify, "auto": cmd_auto, "qc": cmd_qc, "plan": cmd_plan,
            "apply": cmd_apply, "rollback": cmd_rollback,
            "probe": lambda x: cmd_fitness(x, "probe"),
            "variant": lambda x: cmd_fitness(x, "variant")}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
