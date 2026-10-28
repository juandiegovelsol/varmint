#!/usr/bin/env python3
"""Reward computation for fossasia__eventyay-4771-mm.

Parses the JUnit XML report emitted by test.sh and computes the reward from
config.json's f2p/p2p lists. NEVER inspects candidate source — only the test report.

Reward policy:
  1.0 -- every f2p test passes AND every p2p test passes.
  0.0 -- otherwise.
"""
import json
import os
import re
import xml.etree.ElementTree as ET

CONF = json.load(open('/tests/config.json'))
F2P, P2P = CONF['f2p'], CONF['p2p']
REPORT = '/logs/verifier/report.xml'
REWARD = '/logs/verifier/reward.txt'


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

    all_f2p = len(F2P) > 0 and len(f2p_pass) == len(F2P)
    all_p2p = len(p2p_pass) == len(P2P)

    if all_f2p and all_p2p:
        reward = 1.0
    else:
        reward = 0.0

    os.makedirs(os.path.dirname(REWARD), exist_ok=True)
    with open(REWARD, 'w') as fh:
        fh.write(str(reward))
    reward_json = {
        'reward': reward,
        'tests_passed': reward,
        'f2p_passed': len(f2p_pass),
        'f2p_total': len(F2P),
        'p2p_passed': len(p2p_pass),
        'p2p_total': len(P2P),
        'rubric_passed': -1,
    }
    with open('/logs/verifier/reward.json', 'w') as fh:
        json.dump(reward_json, fh)

    print(json.dumps({'reward': reward, 'f2p': f2p, 'p2p': p2p}))
if __name__ == '__main__':
    main()
