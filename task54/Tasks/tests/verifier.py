#!/usr/bin/env python3
"""Reward computation for trezor__trezor-suite-30020-mm.

Parses the JUnit XML report test.sh writes (jest + jest-junit) and computes the reward from
config.json's grounded f2p/p2p identifiers. NEVER inspects the candidate's source -- only the
test report.

Identifier format is "<classname> > <name>", where test.sh's JEST_JUNIT_* templates set
classname = the test file path as jest reports it (workspace-relative) and
name = the full ` > `-joined describe/it chain (confirmed empirically against this repo's own
report.xml).

Reward policy -- BINARY, no partial credit:
  1.0 -- every f2p test passes AND every p2p test still passes.
  0.0 -- anything else: a strict subset of f2p passing, a p2p regression, or a report that
         produced no results at all.
A half-finished fix is unsolved, so it scores 0.0 rather than a middle rung: partial credit would
let it read as "solved" to pass@k. Nothing is lost by collapsing the middle, because the four
count keys in reward.json (f2p_passed / f2p_total / p2p_passed / p2p_total) carry exactly how
close the candidate got.

Writes BOTH /logs/verifier/reward.json (harbor's preferred source -- a flat map of numbers under
the canonical seven keys) and /logs/verifier/reward.txt (bare float), from one dict, so the two
can never disagree.
"""
import atexit
import json
import os
import sys
import xml.etree.ElementTree as ET

CONF = json.load(open('/tests/config.json'))
F2P = CONF['f2p']
P2P = CONF['p2p']
REPORT = '/logs/verifier/report.xml'

# --- canonical reward writer + --rubric gate ----------------------------------------------------
# reward.json MUST be a FLAT map of numbers under exactly these seven keys:
#     {reward, tests_passed, f2p_passed, f2p_total, p2p_passed, p2p_total, rubric_passed}
# harbor parses it as VerifierResult.rewards: dict[str, float | int] and takes it in PREFERENCE to
# reward.txt. A nested dict, list, string or None raises a pydantic ValidationError that aborts the
# trial BEFORE any reward is recorded -- while reward.txt still gets written inside the container,
# so the run would look scored when harbor in fact stored nothing.
#   rubric_passed: 1 pass / 0 fail / -1 not graded.
# This task ships NO rubric layer (its behavioral tests fully cover the fix), so the gate below is
# present but never fires and rubric_passed records -1 on every run. It is kept so one verifier
# contract serves both shapes.
_CANON_JSON = '/logs/verifier/reward.json'
_CANON_TXT = '/logs/verifier/reward.txt'
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric):
    """THE reward policy. Binary: solved means every f2p passes AND every p2p still passes."""
    f, t = int(f2p_passed), int(f2p_total)
    p, q = int(p2p_passed), int(p2p_total)
    solved = bool(t) and f == t and p == q
    tests_passed = 1.0 if solved else 0.0
    _canon.clear()
    _canon.update({
        'reward': 0.0 if rubric == 'fail' else tests_passed,
        'tests_passed': tests_passed,
        'f2p_passed': f, 'f2p_total': t,
        'p2p_passed': p, 'p2p_total': q,
        'rubric_passed': {'pass': 1, 'fail': 0}.get(rubric, -1),
    })
    return _canon['reward']


@atexit.register
def _canon_flush():
    if not _canon:
        return
    try:
        os.makedirs(os.path.dirname(_CANON_JSON), exist_ok=True)
        with open(_CANON_JSON, 'w') as fh:
            json.dump(_canon, fh, indent=2)
        with open(_CANON_TXT, 'w') as fh:
            fh.write(str(_canon['reward']))
    except Exception as exc:
        print('WARNING: could not write %s: %s' % (_CANON_JSON, exc), file=sys.stderr)


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`.

    Anything that is not an explicit pass/fail -- including the empty string test.sh passes when
    no rubric ships -- means "not graded", which must never penalise the run.
    """
    if '--rubric' not in argv:
        return None
    i = argv.index('--rubric')
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ''
    return value if value in ('pass', 'fail') else None


# --- task-specific report parsing ---------------------------------------------------------------


def load_results():
    """Return {"<classname> > <name>": "pass"|"fail"|"skip"} parsed from the jest JUnit report."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError:
        return results
    for tc in tree.iter('testcase'):
        classname = tc.get('classname', '')
        name = tc.get('name', '')
        key = f"{classname} > {name}" if classname else name
        failed = any(c.tag in ('failure', 'error') for c in tc)
        skipped = any(c.tag == 'skipped' for c in tc)
        results[key] = 'skip' if skipped else ('fail' if failed else 'pass')
    return results


def match(idents, results):
    """Match each configured identifier to a reported test's status. Exact match first (our
    identifiers are literally `${classname} > ${name}` from the same report format), falling
    back to substring tolerance in case of minor formatting drift."""
    out = {}
    for ident in idents:
        if ident in results:
            out[ident] = results[ident]
            continue
        hit = next((v for k, v in results.items() if ident in k or k in ident), None)
        out[ident] = hit or 'missing'
    return out


def main():
    results = load_results()
    f2p = match(F2P, results)
    p2p = match(P2P, results)

    f2p_pass = [k for k, v in f2p.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p.items() if v == 'pass']

    reward = canon_reward(len(f2p_pass), len(F2P),
                         len(p2p_pass), len(P2P),
                         rubric_verdict(sys.argv[1:]))
    summary = dict(_canon)

    # Per-test detail rides along as extra SCALAR keys (1.0/0.0) on the same FLAT dict -- never a
    # nested map, which harbor would reject. Without these, reward.json cannot answer "did this
    # f2p pass on the nop control?", so an INERT f2p test -- one that is green even with no fix
    # applied, and therefore grades nothing -- is undetectable from the run record alone.
    for ident, status in f2p.items():
        _canon[f'f2p::{ident}'] = 1.0 if status == 'pass' else 0.0
    for ident, status in p2p.items():
        _canon[f'p2p::{ident}'] = 1.0 if status == 'pass' else 0.0

    print(json.dumps({'reward': reward, 'counts': summary,
                      'f2p': f2p, 'p2p': p2p}, indent=2))


if __name__ == '__main__':
    main()
