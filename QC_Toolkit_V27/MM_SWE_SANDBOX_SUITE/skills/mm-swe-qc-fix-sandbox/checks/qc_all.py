#!/usr/bin/env python3
"""MM SWE QC - run every static check, route the findings by category, print one verdict.

WHAT CHANGED AND WHY. This used to concatenate the four checks' stdout and print a four-line
component tally. That grouped findings by the TOOL that found them rather than by the defect
class, in four incompatible severity vocabularies, and - because two checks treated a run
directory that did not exist yet as a hard failure - it reported FAIL on a sound bundle whenever
QC ran before the trial. On a real task that was 11 [FAIL] findings of which 9 were artifacts.

Now: each check emits structured findings (`--emit-findings`), this script routes them into the
six QC-rubric-v2 dimensions, merges findings that are the same defect seen twice, demotes anything
whose tier is not available at the current phase to OPEN, and renders one report.

    qc_all.py <root | Tasks dir> [--phase auto|bundle|gate|post-trial|submission]
                                [--verbose] [--next-steps] [--text]
                                [--emit-graders DIR] [--json OUT]

PHASE. `auto` (the default) infers it from what is on disk. The point of the phase is that QC has
to be useful BEFORE the trial is spent, so:

    bundle      Tasks/ only                    free                <- default
    gate        + Oracle/ + Nop/               keyless, docker only
    post-trial  + Trials/                      a real model call
    submission  + the four .tar.gz             packaging time

Exit 0 = nothing decidable failed. Non-zero = at least one hard FAIL. An OPEN finding NEVER
affects the exit code - but the verdict line always names what was not checked, so "the gate has
not been reproduced" can never be misread as "the gate holds".
"""
import argparse, json, os, shutil, subprocess, sys, tempfile


class _SkipReport(Exception):
    """--no-report: the report write is skipped, not failed."""

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from qc_layout import resolve_layout, AmbiguousLayout
from qc_common import (Finding, load_findings, apply_phase, dedup, render, verdict,
                       detect_phase, suppress_stale, PHASES, CATEGORY_ORDER, CATEGORY_TITLE,
                       DECIDABLE, FAIL, OPEN, NA)

# `rubric_format` runs FIRST of the rubric trio on purpose: it decides which of the two legal
# shapes the rubric layer is in (Mode A rubric / Mode B none), and its findings are BLOCKING.
# qc_rubrics grades rubric CONTENT and qc_judge the judge WIRING; neither is meaningful until the
# shape is right, so the shape verdict should be the first thing a CB reads.
COMPONENTS = [("structure", "qc_structure.py"), ("rubric_format", "qc_rubric_format.py"),
              ("rubrics", "qc_rubrics.py"), ("judge", "qc_judge.py"), ("gate", "qc_gate.py")]

# qc_judge compares judge.py against the rubric template. Standalone it would report the identity
# check as unchecked; the bundled template is the right default so the report is complete either
# way (fix.py sets the same variable).
os.environ.setdefault("MM_RUBRIC_TEMPLATE",
                      os.path.join(os.path.dirname(HERE), "template", "tests", "judge.py"))


def resolve_roots(path):
    """(deliverables_root, tasks_dir).

    Both are resolved once here and every check is handed the root, because the checks disagree
    about what they want: qc_gate reads <root>/Oracle, while the SKILL.md examples and every CB
    point at <root>/Tasks. Guessing wrong is what produced `Oracle/ folder missing` on a task
    whose Oracle/ was sitting one level up.
    """
    # Flat (Tasks/task.toml) and nested (Tasks/<any-name>/task.toml) both resolve; see qc_layout.
    try:
        deliv, tasks = resolve_layout(path)
    except AmbiguousLayout as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    return deliv, tasks or os.path.join(deliv, "Tasks")


def run(script, args):
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, script)] + args,
                           capture_output=True, text=True, timeout=300)
        return r.returncode, r.stdout + r.stderr
    except Exception as exc:
        return 2, f"could not run {script}: {exc}\n"


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("path")
    ap.add_argument("--phase", default="auto",
                    choices=["auto"] + PHASES,
                    help="artifact tier to judge against; `auto` detects it from disk")
    ap.add_argument("--verbose", action="store_true", help="expand clean categories")
    ap.add_argument("--next-steps", action="store_true",
                    help="also print the harbor reproduce-the-gate command block")
    ap.add_argument("--text", action="store_true",
                    help="also print each check's own raw output")
    ap.add_argument("--emit-graders", metavar="DIR")
    ap.add_argument("--quiet", action="store_true",
                    help="write the JSON and print nothing — for fix.py, which joins these "
                         "findings against its live fixes and renders the merged report itself")
    ap.add_argument("--no-report", action="store_true",
                    help="do not write qc_report.json (the report is derived output, not a "
                         "change to the bundle, so it is written by default)")
    ap.add_argument("--json", metavar="OUT",
                    help="where to write qc_report.json (default: beside Tasks/)")
    a = ap.parse_args()

    deliv, tasks = resolve_roots(a.path)
    detected = detect_phase(deliv)
    phase = detected if a.phase == "auto" else a.phase

    findings, transcript, rcs = [], [], {}
    tmp = tempfile.mkdtemp(prefix="qc_findings_")
    try:
        _collect(findings, transcript, rcs, tmp, deliv, a, tasks)
    finally:
        # ours, and nothing outside this process reads it - so it is cleaned up rather than
        # leaving one findings dir per invocation behind in /tmp
        shutil.rmtree(tmp, ignore_errors=True)

    if a.text and not a.quiet:
        print("".join(transcript))

    findings = apply_phase(dedup(findings), phase)
    findings, _stale = suppress_stale(findings)
    report, code = render(findings, phase, tasks, deliv=deliv, verbose=a.verbose,
                          detected=detected)
    if not a.quiet:
        print(report)
    _write_report(a, deliv, tasks, detected, phase, findings, rcs, code)

    # The rubric dimension is the UNION of content (qc_rubrics) and wiring (qc_judge): neither can
    # see the other half, so an isolated PASS is not a pass for the dimension. Both now land in
    # the same category, which is what the note used to have to say in prose.
    if rcs.get("rubrics") == 0 and rcs.get("judge") != 0 and not a.quiet:
        print("  note: rubric CONTENT is clean but judge WIRING is not - both book against "
              "RUBRIC & JUDGE.")
    return code


def _collect(findings, transcript, rcs, tmp, deliv, a, tasks):
    for name, script in COMPONENTS:
        out_json = os.path.join(tmp, f"{name}.json")
        # Every other check takes the ROOT and re-locates Tasks/ itself, which silently audits
        # <root>/Tasks even when the caller pointed at a task dir NOT named Tasks - so a bundle in
        # e.g. /work/MyTask would be judged against a sibling /work/Tasks. resolve_roots() has
        # already worked out the real task dir, so hand it over directly rather than making the
        # check guess a second time.
        # ...so hand the resolved task dir to every check that audits the BUNDLE. Only `gate`
        # keeps the deliverables root, because it reads the sibling run folders (Oracle/, Nop/,
        # Trials/) rather than the bundle. Previously only `rubric_format` got `tasks`, so a
        # bundle in e.g. /work/MyTask had its structure, rubrics and judge judged against
        # /work/Tasks - a different task entirely, reported under this task's name.
        args = [deliv if name == "gate" else tasks, "--emit-findings", out_json]
        if name == "rubrics" and a.emit_graders:
            args += ["--emit-graders", a.emit_graders]
        if name == "gate" and a.next_steps:
            args += ["--next-steps"]
        rc, out = run(script, args)
        rcs[name] = rc
        transcript.append(f"\n{'=' * 78}\n== {name.upper()}  ({script})\n{'=' * 78}\n{out}")
        got = load_findings(out_json)
        if not got and rc == 2:
            # A check that could not run at all must not look like a check that found nothing.
            findings.append(Finding(f"{name}_check_failed",
                                    f"the {name} check did not run to completion - its dimension "
                                    f"is UNVERIFIED, not clean",
                                    OPEN, category="structure", needs="a working check",
                                    evidence=[l for l in out.strip().splitlines()[-3:]],
                                    source=[f"qc_{name}"]))
        findings += got


def _write_report(a, deliv, tasks, detected, phase, findings, rcs, code):
    """qc_report.json is DERIVED OUTPUT, not a change to the bundle - it never touches Tasks/ - so
    it is written by default. `--no-report` opts out for a strictly read-only run."""
    out_path = None if a.no_report else (a.json or os.path.join(deliv, "qc_report.json"))
    v, _ = verdict(findings, phase)
    cats = {}
    for key in CATEGORY_ORDER:
        fs = [f for f in findings if f.category == key]
        n_fail = sum(1 for f in fs if f.severity == FAIL)
        cats[key] = {"title": CATEGORY_TITLE[key],
                     "verdict": "FAIL" if n_fail else ("OK" if fs else "n/a"),
                     "n_fail": n_fail,
                     "n_open": sum(1 for f in fs if f.severity in (OPEN, NA)),
                     "n_findings": len(fs)}
    try:
        if out_path is None:
            raise _SkipReport
        with open(out_path, "w") as fh:
            json.dump({"phase": phase, "detected_phase": detected, "tasks_dir": tasks, "deliverables_root": deliv,
                       "verdict": v, "exit_code": code,
                       "component_exit_codes": rcs,
                       "categories": cats,
                       "findings": [f.as_dict() for f in findings]}, fh, indent=2)
        if not a.quiet:
            print(f"\n  wrote {out_path}")
    except _SkipReport:
        pass
    except Exception as exc:
        print(f"\n  could not write {out_path}: {exc}", file=sys.stderr)

    # The rubric dimension is the UNION of content (qc_rubrics) and wiring (qc_judge): neither can
    # see the other half, so an isolated PASS is not a pass for the dimension. Both now land in
    # the same category, which is what the note used to have to say in prose.
    if rcs.get("rubrics") == 0 and rcs.get("judge") != 0:
        print("  note: rubric CONTENT is clean but judge WIRING is not - both book against "
              "RUBRIC & JUDGE.")
    return code


if __name__ == "__main__":
    sys.exit(main())
