#!/usr/bin/env python3
"""Behavioral verifier for fabricjs__fabric.js-10640-mm.
Parses JUnit XML from vitest and computes reward from f2p/p2p.
NEVER greps source for the fix — scores from test results only.
Reward policy:
  1.0 — every f2p PASS AND every p2p PASS
  0.5 — some f2p pass but not all, OR any p2p regressed
  0.0 — no f2p passes or suite failed to run
"""
import json, os, re, sys
try:
    import xml.etree.ElementTree as ET
except ImportError:
    pass

CONF = json.load(open('/tests/config.json'))
F2P, P2P = CONF['f2p'], CONF['p2p']
REPORT = '/logs/verifier/report.xml'
REWARD = '/logs/verifier/reward.txt'


def load_results():
    """Return {test_key: 'pass'|'fail'|'skip'} from JUnit XML."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except Exception as e:
        print(f"Warning: could not parse report: {e}", file=sys.stderr)
        return results
    for tc in tree.iter('testcase'):
        classname = tc.get('classname', '')
        name = tc.get('name', '')
        key = f"{classname} > {name}" if classname else name
        failed = any(c.tag in ('failure', 'error') for c in tc)
        skipped = any(c.tag == 'skipped' for c in tc)
        results[key] = 'skip' if skipped else ('fail' if failed else 'pass')
    return results


def matched(idents, results):
    """Resolve each identifier to exactly one test result.

    Exact match on the leaf test name (or the full key) wins, so an identifier
    that is a prefix of a longer test name cannot silently score the wrong
    test. Substring matching is only the fallback.
    """
    out = {}
    for ident in idents:
        hit = next(
            (v for k, v in results.items()
             if k == ident or k.split(' > ')[-1] == ident),
            None
        )
        if hit is None:
            hit = next((v for k, v in results.items() if ident in k), None)
        out[ident] = hit or 'missing'
    return out


def main():
    r = load_results()
    f2p = matched(F2P, r)
    p2p = matched(P2P, r)

    f2p_pass = [k for k, v in f2p.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p.items() if v == 'pass']

    all_f2p = len(f2p_pass) == len(F2P) and len(F2P) > 0
    all_p2p = len(p2p_pass) == len(P2P)

    if all_f2p and all_p2p:
        reward = 1.0
    elif f2p_pass and (not all_p2p or not all_f2p):
        reward = 0.5
    else:
        reward = 0.0

    os.makedirs(os.path.dirname(REWARD), exist_ok=True)
    with open(REWARD, 'w') as fh:
        fh.write(str(reward))
    print(json.dumps({
        'reward': reward,
        'f2p': f2p,
        'p2p': p2p,
        'f2p_pass': f2p_pass,
        'p2p_pass': p2p_pass,
    }))


if __name__ == '__main__':
    main()
