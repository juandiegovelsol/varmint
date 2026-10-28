#!/usr/bin/env python3
"""Behavioral verifier for fabricjs__fabric.js-10683-mm.
Parses JUnit XML from vitest and computes reward from f2p/p2p.
NEVER greps source for the fix — scores from test results only.
Reward policy is binary: 1.0 only if every f2p test passes AND every p2p test
still passes, else 0.0. See canon_reward() below.
"""
import atexit, json, os, re, sys
try:
    import xml.etree.ElementTree as ET
except ImportError:
    pass

CONF = json.load(open('/tests/config.json'))
F2P, P2P = CONF['f2p'], CONF['p2p']
REPORT = '/logs/verifier/report.xml'
_CANON_JSON = '/logs/verifier/reward.json'
_CANON_TXT = '/logs/verifier/reward.txt'
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total):
    f, t = int(f2p_passed), int(f2p_total)
    p, q = int(p2p_passed), int(p2p_total)
    solved = bool(t) and f == t and p == q
    tests_passed = 1.0 if solved else 0.0
    _canon.clear()
    _canon.update({
        'reward': tests_passed,
        'tests_passed': tests_passed,
        'f2p_passed': f, 'f2p_total': t,
        'p2p_passed': p, 'p2p_total': q,
        'rubric_passed': -1,  # no rubric judge in this task
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
    """Substring-match each identifier against test keys."""
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
    f2p = matched(F2P, r)
    p2p = matched(P2P, r)

    f2p_pass = [k for k, v in f2p.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p.items() if v == 'pass']

    reward = canon_reward(len(f2p_pass), len(F2P), len(p2p_pass), len(P2P))

    print(json.dumps({
        'reward': reward,
        'f2p': f2p,
        'p2p': p2p,
        'f2p_pass': f2p_pass,
        'p2p_pass': p2p_pass,
    }))


if __name__ == '__main__':
    main()
