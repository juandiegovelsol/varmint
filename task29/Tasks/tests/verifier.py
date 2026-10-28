#!/usr/bin/env python3
"""Report -> reward for textualize__textual-5826-mm.

Parses the JUnit XML report produced by test.sh (pytest --junitxml) and computes the reward
from config.json's f2p/p2p identifiers. It NEVER inspects candidate source for the behavioural
half of the score: it only reads the test report.

Reward policy (tests, BINARY, no partial credit):
  1.0 -- every f2p test passes AND every p2p test passes
  0.0 -- anything else (a strict subset of f2p, a p2p regression, a suite that failed to run,
         a skipped test, or an identifier that matched no test)

Rubric gate: test.sh forwards the judge verdict via `--rubric pass|fail`. A "fail" verdict forces
the reward to 0.0 even when every test passes. A "pass" or unavailable verdict (judge not graded
yet, or an empty value) never lowers the score, so oracle and nop runs are unaffected by a judge
that did not run.

Identifier matching: pytest appends a "-content<N>" counter to the ids of the parametrized
`test_to_content` cases, because several parameter sets stringify to the same id fragment. The
counter is an artefact of the parameter list's ORDER, so it is stripped before matching -- a
candidate that leaves the test file alone (the only supported case; test.sh restores it anyway)
still matches, and the configured identifiers stay readable.

IMPORTANT: this script WRITES /logs/verifier/reward.txt (bare float) and /logs/verifier/reward.json.
reward.json MUST stay a FLAT map of numbers: harbor validates it as dict[str, float | int] and
prefers it over reward.txt; a nested dict/list/string/None raises a validation error that aborts
the trial before any reward is recorded.
"""
import argparse
import atexit
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

CONF = json.load(open('/tests/config.json'))
F2P, P2P = CONF['f2p'], CONF['p2p']

REPORT = '/logs/verifier/report.xml'
_CANON_TXT = '/logs/verifier/reward.txt'
_CANON_JSON = '/logs/verifier/reward.json'
RUBRIC_SUMMARY = '/logs/verifier/judge/summary.json'

# "test_to_content[[bold red]Hello[/] World-content6]" -> "test_to_content[[bold red]Hello[/] World]"
PARAM_COUNTER_RE = re.compile(r'-content\d+\]$')

# Worst outcome wins when one identifier resolves to several reported results.
_RANK = {'pass': 0, 'skip': 1, 'fail': 2}

# --- canonical reward writer -------------------------------------------------
# The seven mandatory keys, plus one flat scalar per test (f2p::<name> / p2p::<name>).
# The per-test keys surface in harbor's result.json metrics, which is what lets the gate audit
# confirm that every f2p individually fails on the untouched base.
_canon = {}


def canon_reward(f2p_statuses, p2p_statuses, rubric):
    f = sum(1 for v in f2p_statuses.values() if v == 'pass')
    p = sum(1 for v in p2p_statuses.values() if v == 'pass')
    t, q = len(f2p_statuses), len(p2p_statuses)
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
    for name, status in f2p_statuses.items():
        _canon['f2p::%s' % name] = 1.0 if status == 'pass' else 0.0
    for name, status in p2p_statuses.items():
        _canon['p2p::%s' % name] = 1.0 if status == 'pass' else 0.0
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


def load_results():
    """Return {test_name: 'pass'|'fail'|'skip'} parsed from the JUnit XML report.

    Both the raw pytest id and the id with the parametrize counter stripped are recorded, so a
    configured identifier matches either form. A name reported more than once keeps its worst
    outcome, so neither a duplicate nor a collision after stripping can mask a failure.
    """
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError as exc:
        print('WARNING: could not parse %s: %s' % (REPORT, exc), file=sys.stderr)
        return results

    def record(name, status):
        previous = results.get(name)
        if previous is None or _RANK[status] > _RANK[previous]:
            results[name] = status

    for testcase in tree.iter('testcase'):
        name = testcase.get('name', '')
        if not name:
            continue
        failed = any(child.tag in ('failure', 'error') for child in testcase)
        skipped = any(child.tag == 'skipped' for child in testcase)
        status = 'skip' if skipped else ('fail' if failed else 'pass')
        record(name, status)
        record(PARAM_COUNTER_RE.sub(']', name), status)
    return results


def match_ident(ident, results):
    """Resolve one configured identifier to 'pass' | 'fail' | 'skip' | 'missing' | 'ambiguous'.

    Exact name first. Only if there is no exact name does this fall back to substring matching,
    and that fallback demands a UNIQUE hit: the suite contains test names that are strict
    prefixes of other test names (`test_to_content` is a prefix of `test_to_content_variables`),
    so a permissive substring match could silently score the wrong test. A non-unique hit is
    reported as 'ambiguous' and never counts as a pass, making the misconfiguration loud.
    """
    if ident in results:
        return results[ident]
    hits = {name: status for name, status in results.items() if ident in name}
    if len(hits) == 1:
        return next(iter(hits.values()))
    if len(hits) > 1:
        return 'ambiguous'
    return 'missing'


def rubric_failed_ids():
    """Failed criterion ids from the judge summary, when one exists."""
    if os.path.isfile(RUBRIC_SUMMARY):
        try:
            return json.load(open(RUBRIC_SUMMARY)).get('failed', [])
        except Exception:
            return []
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rubric', default='', help='"pass" | "fail" | "" (no verdict yet)')
    args = ap.parse_args()
    rubric = (args.rubric or '').strip().lower()
    rubric = rubric if rubric in ('pass', 'fail') else None

    results = load_results()
    f2p_statuses = {ident: match_ident(ident, results) for ident in F2P}
    p2p_statuses = {ident: match_ident(ident, results) for ident in P2P}

    reward = canon_reward(f2p_statuses, p2p_statuses, rubric)

    print(json.dumps({
        'reward': reward,
        'tests_passed': _canon['tests_passed'],
        'rubric': rubric,
        'rubric_failed': rubric_failed_ids(),
        'f2p': f2p_statuses,
        'p2p': p2p_statuses,
        'f2p_passed': _canon['f2p_passed'], 'f2p_total': _canon['f2p_total'],
        'p2p_passed': _canon['p2p_passed'], 'p2p_total': _canon['p2p_total'],
        'parsed_tests': len(results),
    }, indent=2))
    print('\nREWARD: %s' % reward)


if __name__ == '__main__':
    main()
