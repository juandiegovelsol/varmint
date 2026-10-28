#!/usr/bin/env python3
"""
verifier.py — Parse the JUnit XML produced by scrollbar-corner-test.js and write the
reward to /logs/verifier/reward.txt.

Reward policy (single behavioral verdict):
  1.0 — every f2p test passes AND every p2p test passes.
  0.5 — f2p passes but a p2p regressed (fix works but introduces a regression),
         OR a strict subset of f2p passes (partial credit for partial fix).
  0.0 — no f2p passes, or the suite failed to produce a report.

Harbor reads /logs/verifier/reward.txt.  This script MUST write that file.
Printing a JSON blob alone is not sufficient — the EXIT trap in test.sh writes 0
only if the file is absent, so a crash here still results in 0.

NOTE: This verifier NEVER inspects the candidate's source code.  It reads only the
test-execution report produced by the JS test script, which itself only observes
rendered pixel output from a real headless browser.
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

CONF   = json.load(open('/tests/config.json'))
F2P    = CONF['f2p']
P2P    = CONF['p2p']
REPORT = '/logs/verifier/report.xml'   # must match test.sh
REWARD = '/logs/verifier/reward.txt'

def load_results():
    """Return {test_identifier: 'pass'|'fail'|'skip'} from the JUnit XML."""
    results = {}
    if not os.path.exists(REPORT):
        print(f"[verifier] WARNING: report not found at {REPORT}", file=sys.stderr)
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError as exc:
        print(f"[verifier] ERROR: malformed XML — {exc}", file=sys.stderr)
        return results
    for tc in tree.iter('testcase'):
        classname = tc.get('classname', '')
        name      = tc.get('name', '')
        ident     = f"{classname}::{name}".strip('::')
        children  = list(tc)
        if any(c.tag == 'skipped' for c in children):
            results[ident] = 'skip'
        elif any(c.tag in ('failure', 'error') for c in children):
            results[ident] = 'fail'
        else:
            results[ident] = 'pass'
    return results

def match(idents, results):
    """
    Match each configured identifier against reported test names.
    Uses substring + regex-escape fallback for tolerance against
    framework-dependent classname variations.
    """
    out = {}
    for ident in idents:
        hit_key = next(
            (k for k in results if ident in k or re.search(re.escape(ident), k)),
            None
        )
        out[ident] = results[hit_key] if hit_key else 'missing'
    return out

def main():
    r    = load_results()
    f2p  = match(F2P, r)
    p2p  = match(P2P, r)

    f2p_passing = [k for k, v in f2p.items() if v == 'pass']
    p2p_passing = [k for k, v in p2p.items() if v == 'pass']

    all_f2p = (len(F2P) > 0) and (len(f2p_passing) == len(F2P))
    all_p2p = (len(p2p_passing) == len(P2P))   # vacuously true if P2P is empty

    if all_f2p and all_p2p:
        reward = 1.0
    elif f2p_passing:
        # Some f2p passed (partial f2p) OR all f2p passed but a p2p regressed → 0.5
        reward = 0.5
    else:
        # No f2p passed (fix absent or suite crashed)
        reward = 0.0

    os.makedirs(os.path.dirname(REWARD), exist_ok=True)
    with open(REWARD, 'w') as fh:
        fh.write(str(reward))

    summary = {
        'reward':      reward,
        'f2p_results': f2p,
        'p2p_results': p2p,
        'all_f2p':     all_f2p,
        'all_p2p':     all_p2p,
    }
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
