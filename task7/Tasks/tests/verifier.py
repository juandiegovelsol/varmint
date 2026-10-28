#!/usr/bin/env python3
"""
Verifier for radix-ui-primitives-2611-mm (ContextMenu re-anchor).

Reward policy:
  1.0 — every f2p passes AND every p2p passes.
  0.5 — every f2p passes but ≥1 p2p regressed; or strict subset of f2p passes.
  0.0 — no f2p passes, or the suite failed to run.
"""
import json, os, re, sys, xml.etree.ElementTree as ET

CONF = json.load(open('/tests/config.json'))
F2P, P2P = CONF['f2p'], CONF['p2p']
REPORT = '/logs/verifier/report.xml'
REWARD = '/logs/verifier/reward.txt'


def load_results():
    """Return {test_identifier: 'pass'|'fail'|'skip'} parsed from JUnit XML."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError as e:
        print(f"XML parse error: {e}", file=sys.stderr)
        return results
    for tc in tree.iter('testcase'):
        classname = tc.get('classname', '')
        name = tc.get('name', '')
        # Build two keys: full qualified and name-only for flexible matching
        full_key = f"{classname}::{name}".strip('::')
        failed = any(c.tag in ('failure', 'error') for c in tc)
        skipped = any(c.tag == 'skipped' for c in tc)
        status = 'skip' if skipped else ('fail' if failed else 'pass')
        results[full_key] = status
        # Also store by name alone for substring matching
        if name and name not in results:
            results[name] = status
    return results


def matched(idents, results):
    """Match each identifier against reported test names (substring/regex tolerant)."""
    out = {}
    for ident in idents:
        hit = next(
            (v for k, v in results.items()
             if ident in k or re.search(re.escape(ident), k)),
            None
        )
        out[ident] = hit or 'missing'
    return out


def main():
    r = load_results()
    f2p_matched = matched(F2P, r)
    p2p_matched = matched(P2P, r)

    f2p_pass = [k for k, v in f2p_matched.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p_matched.items() if v == 'pass']

    all_f2p = len(f2p_pass) == len(F2P) and len(F2P) > 0
    all_p2p = len(p2p_pass) == len(P2P)

    if all_f2p and all_p2p:
        reward = 1.0
    elif f2p_pass and (not all_p2p or not all_f2p):
        reward = 0.5
    else:
        reward = 0.0

    os.makedirs(os.path.dirname(REWARD), exist_ok=True)
    open(REWARD, 'w').write(str(reward))
    print(json.dumps({'reward': reward, 'f2p': f2p_matched, 'p2p': p2p_matched}))


if __name__ == '__main__':
    main()
