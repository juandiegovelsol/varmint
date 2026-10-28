#!/usr/bin/env python3
"""Reward policy (all flutter multimodal tasks):
  1.0  — every f2p passes AND every p2p passes
  0.5  — some f2p pass but not all, OR any p2p regressed
  0.0  — no f2p passes or report absent / suite failed to compile

Behavioral only: reads `flutter test --reporter json` output; NEVER inspects source.
"""
import json
import os
import re

CONF   = json.load(open('/tests/config.json'))
F2P    = CONF['f2p']
P2P    = CONF['p2p']
REPORT = '/logs/verifier/report.json'
REWARD = '/logs/verifier/reward.txt'


def load_results():
    """Parse `flutter test --reporter json` events → {test_name: 'pass'|'fail'|'skip'}."""
    if not os.path.exists(REPORT):
        return {}
    results = {}
    id_to_name = {}
    for raw in open(REPORT, errors='replace'):
        raw = raw.strip()
        if not raw:
            continue
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            continue
        etype = ev.get('type', '')
        if etype == 'testStart':
            t = ev.get('test', {})
            id_to_name[t.get('id')] = t.get('name', '')
        elif etype == 'testDone':
            tid  = ev.get('testID')
            name = id_to_name.get(tid, str(tid))
            res  = ev.get('result', 'error')   # 'success' | 'failure' | 'error'
            skip = ev.get('skipped', False)
            if skip:
                results[name] = 'skip'
            elif res == 'success':
                results[name] = 'pass'
            else:
                results[name] = 'fail'
    return results


def match_ident(ident, results):
    """Substring-tolerant match: first hit wins."""
    for name, val in results.items():
        if ident == name or ident in name or re.search(re.escape(ident), name):
            return val
    return 'missing'


def main():
    r    = load_results()
    f2p  = {k: match_ident(k, r) for k in F2P}
    p2p  = {k: match_ident(k, r) for k in P2P}

    f2p_pass = [k for k, v in f2p.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p.items() if v == 'pass']

    all_f2p  = len(f2p_pass) == len(F2P) and len(F2P) > 0
    all_p2p  = len(p2p_pass) == len(P2P)

    if all_f2p and all_p2p:
        reward = 1.0
    elif f2p_pass:          # partial f2p pass, or p2p regression
        reward = 0.5
    else:
        reward = 0.0        # no f2p passed (includes compile error / empty report)

    os.makedirs(os.path.dirname(REWARD), exist_ok=True)
    with open(REWARD, 'w') as fh:
        fh.write(str(reward))
    print(json.dumps({'reward': reward, 'f2p': f2p, 'p2p': p2p}))


if __name__ == '__main__':
    main()
