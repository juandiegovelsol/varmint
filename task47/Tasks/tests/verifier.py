#!/usr/bin/env python3
"""Reward computation for fossasia__eventyay-4158-mm.

Parses the JUnit XML report emitted by test.sh and computes the reward from
config.json's f2p/p2p lists. NEVER inspects candidate source — only the test report.

Reward policy is BINARY (Mode B -- no rubric shipped, per RUBRIC_MODES.md):
  1.0  -- every f2p test passes AND every p2p test still passes.
  0.0  -- otherwise (a strict subset of f2p passing is NOT partial credit --
          the task is unsolved).

reward.json's rubric_passed is always -1 ("not graded"): this task ships no
rubric/judge, so --rubric is parsed only for contract uniformity and is never
meaningfully "pass"/"fail".
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

CONF = json.load(open('/tests/config.json'))
F2P, P2P = CONF['f2p'], CONF['p2p']
REPORT = '/logs/verifier/report.xml'
REWARD = '/logs/verifier/reward.txt'
REWARD_JSON = '/logs/verifier/reward.json'


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`.

    This task ships no rubric (Mode B), so RUBRIC is always empty and this
    always resolves to None ("not graded") -- the flag is parsed only to keep
    the same call contract as Mode A tasks.
    """
    if '--rubric' not in argv:
        return None
    i = argv.index('--rubric')
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ''
    return value if value in ('pass', 'fail') else None


def load_results():
    """Return {test_identifier: 'pass'|'fail'|'skip'} parsed from the JUnit report."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    tree = ET.parse(REPORT)
    for tc in tree.iter('testcase'):
        classname = tc.get('classname', '')
        name = tc.get('name', '')
        # pytest junitxml classname is dotted module path; identifiers in config.json are
        # "path/to/file.py::test_name" -- match tolerantly against both forms below.
        full = f"{classname}::{name}".strip(':')
        failed = any(c.tag in ('failure', 'error') for c in tc)
        skipped = any(c.tag == 'skipped' for c in tc)
        results[full] = 'skip' if skipped else ('fail' if failed else 'pass')
    return results


def matched(idents, results):
    """Match each configured identifier against reported test names (substring tolerant,
    since junitxml classnames use dotted module paths, e.g. tests.snapshot_tests.test_snapshots)."""
    out = {}
    for ident in idents:
        test_name = ident.split('::')[-1]
        hit = None
        for k, v in results.items():
            if ident in k or k.endswith(f"::{test_name}") or re.search(re.escape(test_name), k):
                hit = v
                break
        out[ident] = hit or 'missing'
    return out


def main():
    results = load_results()
    f2p = matched(F2P, results)
    p2p = matched(P2P, results)
    f2p_pass = [k for k, v in f2p.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p.items() if v == 'pass']

    f2p_passed, f2p_total = len(f2p_pass), len(F2P)
    p2p_passed, p2p_total = len(p2p_pass), len(P2P)
    solved = bool(f2p_total) and f2p_passed == f2p_total and p2p_passed == p2p_total
    tests_passed = 1.0 if solved else 0.0

    rubric = rubric_verdict(sys.argv[1:])
    rubric_passed = {'pass': 1, 'fail': 0}.get(rubric, -1)
    # A "not graded" or "pass" verdict never lowers the score -- the judge must never be
    # able to penalise a run it could not grade. Moot here: this task ships no rubric, so
    # rubric is always None and rubric_passed is always -1.
    reward = 0.0 if rubric == 'fail' else tests_passed

    payload = {
        'reward': reward,
        'tests_passed': tests_passed,
        'f2p_passed': f2p_passed, 'f2p_total': f2p_total,
        'p2p_passed': p2p_passed, 'p2p_total': p2p_total,
        'rubric_passed': rubric_passed,
    }
    # Per-test detail rides along as extra flat scalar keys (never a nested map -- harbor
    # parses reward.json as dict[str, float] and a nested value aborts the trial).
    per_test = {f'f2p::{k}': (1.0 if v == 'pass' else 0.0) for k, v in f2p.items()}
    per_test.update({f'p2p::{k}': (1.0 if v == 'pass' else 0.0) for k, v in p2p.items()})

    payload.update(per_test)

    os.makedirs(os.path.dirname(REWARD), exist_ok=True)
    with open(REWARD, 'w') as fh:
        fh.write(str(reward))
    with open(REWARD_JSON, 'w') as fh:
        json.dump(payload, fh, indent=2)
    print(json.dumps({**payload, 'f2p': f2p, 'p2p': p2p}))


if __name__ == '__main__':
    main()
