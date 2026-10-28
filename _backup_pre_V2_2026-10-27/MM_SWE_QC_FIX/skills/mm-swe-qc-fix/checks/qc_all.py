#!/usr/bin/env python3
"""MM SWE QC - run every static check and print one verdict.

Order matches how the defects actually surface:
  1. structure   qc_structure.py  bundle shape, files, patch scope, identifiers, evidence chain
  2. rubrics     qc_rubrics.py    the 11 appendix issues + 5/15/25 FAIL thresholds
  3. judge       qc_judge.py      judge wiring, keyless, hygiene, test.sh syntax, judge identity
  4. gate        qc_gate.py       submitted rewards, checksums, and PER-TEST f2p-on-nop

Usage:
    qc_all.py <deliverables root | Tasks dir> [--emit-graders DIR] [--json OUT]

Exit 0 = everything static passed. Non-zero = at least one component failed; the semantic
rubric issues are never auto-passed - they are listed as pending until a grader runs.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
COMPONENTS = [("structure", "qc_structure.py"), ("rubrics", "qc_rubrics.py"),
              ("judge", "qc_judge.py"), ("gate", "qc_gate.py")]


def run(script, args):
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, script)] + args,
                           capture_output=True, text=True, timeout=300)
        return r.returncode, r.stdout + r.stderr
    except Exception as exc:
        return 2, f"could not run {script}: {exc}\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--emit-graders", metavar="DIR")
    ap.add_argument("--json", metavar="OUT")
    a = ap.parse_args()

    results, transcript = {}, []
    for name, script in COMPONENTS:
        args = [a.path]
        if name == "rubrics" and a.emit_graders:
            args += ["--emit-graders", a.emit_graders]
        rc, out = run(script, args)
        results[name] = rc
        transcript.append(f"\n{'='*78}\n== {name.upper()}  ({script})\n{'='*78}\n{out}")

    print("".join(transcript))
    print("=" * 78)
    print("== MM SWE QC SUMMARY")
    print("=" * 78)
    for name, _ in COMPONENTS:
        rc = results[name]
        print(f"  {name:10} {'PASS' if rc == 0 else 'FAIL / findings'}   (exit {rc})")
    failed = [n for n, _ in COMPONENTS if results[n] != 0]
    print()
    # The rubric dimension is the UNION of content and wiring. qc_rubrics cannot see the judge
    # wiring and qc_judge cannot see criterion quality, so either one passing in isolation must
    # not be read as a pass for the dimension as a whole.
    if results.get("rubrics") == 0 and results.get("judge") != 0:
        print("  UNION NOTE: the rubric CONTENT is clean but the judge WIRING is not. The rubric")
        print("              dimension is the union of the two - qc_rubrics cannot see the wiring,")
        print("              so its isolated PASS is not a pass for the dimension. Book the")
        print("              failure against the rubric dimension, not structure.")
    if results.get("judge") == 0 and results.get("rubrics") != 0:
        print("  UNION NOTE: the judge wiring is clean but the rubric CONTENT is not - same")
        print("              dimension, so it still fails as a whole.")
    if failed:
        print(f"  VERDICT: FAIL - see {', '.join(failed)} above.")
    else:
        print("  VERDICT: static checks PASS.")
    print("  NOT covered by any static check - these can still fail the task:")
    print("    * the six semantic rubric issues (Incorrect, Contradiction, Overfitting,")
    print("      Underfitting, Missing, Overlapping) - run with --emit-graders and grade them")
    print("    * ACCURATE: each criterion must be factually true of solution/fix.patch")
    print("    * the behavioural half: reproduce oracle/nop, confirm a judge request appeared,")
    print("      then rescore and confirm the oracle shows rubric: \"pass\"")
    if a.json:
        json.dump({"components": results, "failed": failed,
                   "verdict": "FAIL" if failed else "PASS"}, open(a.json, "w"), indent=2)
        print(f"\n  wrote {a.json}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
