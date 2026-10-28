#!/usr/bin/env python3
"""
Verifier for OpenCTI-Platform__opencti-16540-mm.

Same shape and report format as the shipped OpenCTI donor
(OpenCTI-Platform__opencti-16116-mm): parses the vitest JUnit XML written by test.sh and
computes the reward.

The policy is BINARY - there is no partial credit:

  1.0 - every f2p passes AND every p2p still passes
  0.0 - anything else: a strict subset of f2p passing, a p2p regression, or no
        report at all. A half-fix is unsolved, and the f2p_passed / p2p_passed
        counts in reward.json already carry how close it got.

A failed rubric verdict (--rubric fail) zeroes the reward; "pass" and "not graded"
never lower it. This task ships no rubric, so rubric_passed is always -1.

vitest JUnit format (classname = test file path relative to vitest root,
name = "<describe> > <test name>"):

  <testcase classname="harbor_tests/draftValidationWorkLabel.test.jsx"
            name="Draft validation work status &gt; names the validation work state after the validation it reports on" .../>

Matching strategy: for each configured identifier we check whether it appears as a
substring of the compound key "<classname> :: <name>"; failing that, whether every
non-trivial token of the identifier appears in that key. This survives minor separator
differences (' > ' vs ' :: ') across vitest versions.

Paths default to the in-container locations; the HARBOR_* env vars exist only so the
verifier can be exercised outside the container during authoring.
"""
import atexit
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

TESTS_DIR = os.environ.get('HARBOR_TESTS_DIR', '/tests')
LOGS_DIR = os.environ.get('HARBOR_LOGS_DIR', '/logs/verifier')

CONF = json.load(open(os.path.join(TESTS_DIR, 'config.json')))
F2P = CONF['f2p']
P2P = CONF['p2p']
REPORT = os.path.join(LOGS_DIR, 'report.xml')
REWARD = os.path.join(LOGS_DIR, 'reward.txt')
REWARD_JSON = os.path.join(LOGS_DIR, 'reward.json')

# ── Canonical reward writer + --rubric gate ───────────────────────────────────────
# Merged from the corpus template (verifier_reward_block.py). Logic is the template's;
# the paths honour HARBOR_LOGS_DIR so the verifier can still be exercised outside the
# container during authoring, and in-container both resolve to /logs/verifier.
#
# CRITICAL - reward.json MUST be a FLAT map of numbers, and exactly these seven keys:
#     {reward, tests_passed, f2p_passed, f2p_total, p2p_passed, p2p_total, rubric_passed}
# harbor parses it as VerifierResult.rewards: dict[str, float | int] and takes it in
# PREFERENCE to reward.txt. A nested dict, list, string or None raises a pydantic
# ValidationError that aborts the trial BEFORE any reward is recorded - while reward.txt
# still gets written inside the container, so the run looks scored when harbor in fact
# stored nothing. Per-test detail goes to stdout only, never into this dict.
#   rubric_passed: 1 pass / 0 fail / -1 not graded (no rubric shipped, or judge unavailable).
#
# Registered with atexit so it writes LAST, which is what makes this a safe merge onto a
# task's own scoring rather than a rewrite of it.
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric,
                 f2p_detail=None, p2p_detail=None):
    """THE reward policy for the whole corpus. BINARY -- there is no partial credit.

    tests_passed is 1.0 only when every f2p test passes AND every p2p test still passes. A
    strict subset of f2p passing is not partial progress worth scoring: the task is unsolved,
    so it is 0.0.

    reward is the same value, zeroed when the rubric judge failed a criterion. A "pass" or a
    "not graded" verdict never lowers the score -- the judge must never be able to penalise a
    run it could not grade.
    """
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
    # Per-test outcomes as FLAT scalar `f2p::<name>` / `p2p::<name>` = 1.0/0.0 keys -- never a
    # nested map, which harbor would reject. These are what let the QC gate detect an INERT f2p
    # test: one that passes on an empty submission, and therefore cannot detect the bug.
    for prefix, detail in (('f2p::', f2p_detail), ('p2p::', p2p_detail)):
        for ident, status in (detail or {}).items():
            _canon[prefix + ident] = 1.0 if status == 'pass' else 0.0
    return _canon['reward']


@atexit.register
def _canon_capture():
    """Write reward.json and reward.txt from ONE dict, so they cannot disagree."""
    if not _canon:
        return
    try:
        os.makedirs(os.path.dirname(REWARD_JSON), exist_ok=True)
        with open(REWARD_JSON, 'w') as h:
            json.dump(_canon, h, indent=2)
        # reward.txt too: harbor prefers reward.json, but the sandbox teardown script and
        # the lighthouse UI read reward.txt.
        with open(REWARD, 'w') as h:
            h.write(str(_canon['reward']))
    except Exception as exc:
        print('WARNING: could not write %s: %s' % (REWARD_JSON, exc), file=sys.stderr)


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`.

    Anything that is not an explicit pass/fail -- including the empty string test.sh passes
    when no rubric ships -- means "not graded", which must never penalise the run.
    """
    if '--rubric' not in argv:
        return None
    i = argv.index('--rubric')
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ''
    return value if value in ('pass', 'fail') else None


def load_results():
    """Return {"<classname> :: <name>": 'pass'|'fail'|'skip'} from the vitest JUnit XML."""
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
        compound = f"{classname} :: {name}"
        failed = any(c.tag in ('failure', 'error') for c in tc)
        skipped = any(c.tag == 'skipped' for c in tc)
        results[compound] = 'skip' if skipped else ('fail' if failed else 'pass')
    return results


def _tokens(s):
    return re.split(r'[\s:>|/\\-]+', s.lower())


def match_one(ident, results):
    for key, val in results.items():
        if ident in key:
            return val
    toks = [t for t in _tokens(ident) if len(t) > 3]
    if not toks:
        return 'missing'
    for key, val in results.items():
        key_lower = key.lower()
        if all(t in key_lower for t in toks):
            return val
    return 'missing'


def matched(idents, results):
    return {ident: match_one(ident, results) for ident in idents}


def main():
    r = load_results()
    f2p = matched(F2P, r)
    p2p = matched(P2P, r)
    f2p_pass = [k for k, v in f2p.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p.items() if v == 'pass']

    # Binary policy, single decision point. _canon_capture() writes reward.json and
    # reward.txt at exit.
    reward = canon_reward(len(f2p_pass), len(F2P),
                          len(p2p_pass), len(P2P),
                          rubric_verdict(sys.argv[1:]),
                          f2p_detail=f2p, p2p_detail=p2p)

    # The human-readable report. These NESTED maps are stdout-only; reward.json carries the
    # same detail as flat `f2p::<name>` scalars, because harbor rejects a nested value there.
    print(json.dumps({
        'reward': reward,
        'f2p': f2p,
        'p2p': p2p,
        'f2p_pass_count': len(f2p_pass),
        'f2p_total': len(F2P),
        'p2p_pass_count': len(p2p_pass),
        'p2p_total': len(P2P),
    }))


if __name__ == '__main__':
    main()
