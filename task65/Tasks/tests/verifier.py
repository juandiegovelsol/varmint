#!/usr/bin/env python3
"""
Verifier for carbon-design-system__carbon-22307-mm.

Reads the JUnit XML report produced by test.sh (jest-junit) and computes the
reward. NEVER inspects candidate source - reward derives solely from the test
report.

Reward domain is pass/fail only:
  1.0 - every f2p passes AND every p2p passes AND the rubric did not fail.
  0.0 - anything else. How close a partial fix got is carried by the counts.
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

CONF = json.load(open('/tests/config.json'))
F2P = CONF['f2p']
P2P = CONF['p2p']
REPORT = '/logs/verifier/report.xml'   # keep in sync with test.sh
REWARD_TXT = '/logs/verifier/reward.txt'
REWARD_JSON = '/logs/verifier/reward.json'

RUBRIC_NOT_GRADED = -1


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--rubric',
        default=None,
        help='Optional path to a rubric verdict file. Absent => rubric_passed = -1.',
    )
    args, _unknown = parser.parse_known_args()
    return args


def load_results():
    """Return {classname::name: 'pass'|'fail'|'skip'} from JUnit XML."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError as e:
        print(f'[verifier] XML parse error: {e}', file=sys.stderr)
        return results
    for tc in tree.iter('testcase'):
        name = f"{tc.get('classname', '')}::{tc.get('name', '')}".strip(':')
        failed = any(c.tag in ('failure', 'error') for c in tc)
        skipped = any(c.tag == 'skipped' for c in tc)
        results[name] = 'skip' if skipped else ('fail' if failed else 'pass')
    return results


def matched(idents, results):
    """Match each configured identifier against reported test names (substring)."""
    out = {}
    for ident in idents:
        hit = next(
            (v for k, v in results.items()
             if ident in k or re.search(re.escape(ident), k)),
            None,
        )
        out[ident] = hit or 'missing'
    return out


def load_rubric(path):
    """Return 1 (passed), 0 (failed) or -1 (not graded)."""
    if not path or not os.path.exists(path):
        return RUBRIC_NOT_GRADED
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return RUBRIC_NOT_GRADED
    if isinstance(data, bool):
        return int(data)
    if isinstance(data, dict):
        for key in ('rubric_passed', 'rubric_pass', 'passed', 'pass'):
            if key in data and isinstance(data[key], (bool, int, float)):
                return int(data[key])
    return RUBRIC_NOT_GRADED


def main():
    args = parse_args()
    r = load_results()
    f2p = matched(F2P, r)
    p2p = matched(P2P, r)

    f2p_passed = sum(1 for v in f2p.values() if v == 'pass')
    p2p_passed = sum(1 for v in p2p.values() if v == 'pass')

    all_f2p = len(F2P) > 0 and f2p_passed == len(F2P)
    all_p2p = p2p_passed == len(P2P)

    rubric_passed = load_rubric(args.rubric)
    # "Not graded" (-1) must never withhold a reward; only an explicit 0 does.
    rubric_ok = rubric_passed != 0

    tests_ok = all_f2p and all_p2p
    reward = 1.0 if (tests_ok and rubric_ok) else 0.0

    # reward.json stays flat and numeric. `tests_passed` is a binary 0/1 flag,
    # not a count -- the counts live in the f2p_*/p2p_* fields.
    payload = {
        'reward': reward,
        'tests_passed': 1 if tests_ok else 0,
        'f2p_passed': f2p_passed,
        'f2p_total': len(F2P),
        'p2p_passed': p2p_passed,
        'p2p_total': len(P2P),
        'rubric_passed': rubric_passed,
    }
    # Per-test scalars let a nop run prove no f2p is inert (passes with no fix).
    for ident, v in f2p.items():
        payload[f'f2p::{ident}'] = 1.0 if v == 'pass' else 0.0
    for ident, v in p2p.items():
        payload[f'p2p::{ident}'] = 1.0 if v == 'pass' else 0.0

    os.makedirs(os.path.dirname(REWARD_TXT), exist_ok=True)
    with open(REWARD_TXT, 'w') as fh:
        fh.write(str(reward))
    with open(REWARD_JSON, 'w') as fh:
        json.dump(payload, fh)

    print(json.dumps({**payload, 'f2p': f2p, 'p2p': p2p,
                      'testcases_in_report': len(r)}))


if __name__ == '__main__':
    main()
