#!/usr/bin/env python3
"""
Verifier for IvarK__AntimatterDimensionsSourceCode-2843-mm.

Parses the vitest JUnit XML report written by test.sh and computes a reward:
  1.0  — every f2p test passes AND every p2p test passes
  0.0  — anything else (a strict subset of f2p passing, or f2p all pass but a p2p regressed)

Reward policy is binary: partial f2p progress is not scored, since the four count keys
(f2p_passed/f2p_total/p2p_passed/p2p_total) already carry how close a submission got.
"""
import atexit
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

CONF   = json.load(open('/tests/config.json'))
F2P    = CONF['f2p']
P2P    = CONF['p2p']
REPORT = '/logs/verifier/report.xml'
REWARD = '/logs/verifier/reward.txt'

_CANON_JSON = "/logs/verifier/reward.json"
_CANON_TXT = "/logs/verifier/reward.txt"
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric):
    f, t = int(f2p_passed), int(f2p_total)
    p, q = int(p2p_passed), int(p2p_total)
    solved = bool(t) and f == t and p == q
    tests_passed = 1.0 if solved else 0.0
    _canon.clear()
    _canon.update({
        "reward": 0.0 if rubric == "fail" else tests_passed,
        "tests_passed": tests_passed,
        "f2p_passed": f, "f2p_total": t,
        "p2p_passed": p, "p2p_total": q,
        "rubric_passed": {"pass": 1, "fail": 0}.get(rubric, -1),
    })
    return _canon["reward"]


@atexit.register
def _canon_flush():
    if not _canon:
        return
    try:
        os.makedirs(os.path.dirname(_CANON_JSON), exist_ok=True)
        with open(_CANON_JSON, "w") as _h:
            json.dump(_canon, _h, indent=2)
        with open(_CANON_TXT, "w") as _h:
            _h.write(str(_canon["reward"]))
    except Exception as _exc:
        print("WARNING: could not write %s: %s" % (_CANON_JSON, _exc), file=sys.stderr)


def rubric_verdict(argv):
    if "--rubric" not in argv:
        return None
    i = argv.index("--rubric")
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ""
    return value if value in ("pass", "fail") else None


def load_results():
    """Return {test_identifier: 'pass'|'fail'|'skip'} from the JUnit XML."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError:
        return results
    for tc in tree.iter('testcase'):
        # JUnit name includes the describe block: "Suite > test name"
        name = f"{tc.get('classname', '')}::{tc.get('name', '')}".strip(':')
        failed  = any(c.tag in ('failure', 'error') for c in tc)
        skipped = any(c.tag == 'skipped' for c in tc)
        results[name] = 'skip' if skipped else ('fail' if failed else 'pass')
    return results


def matched(idents, results):
    """Match each configured identifier against reported names (substring/regex tolerant)."""
    out = {}
    for ident in idents:
        hit = next(
            (v for k, v in results.items() if ident in k or re.search(re.escape(ident), k)),
            None
        )
        out[ident] = hit or 'missing'
    return out


def main():
    r = load_results()

    f2p_matched = matched(F2P, r)
    p2p_matched = matched(P2P, r)

    f2p_passing = [k for k, v in f2p_matched.items() if v == 'pass']
    p2p_passing = [k for k, v in p2p_matched.items() if v == 'pass']

    reward = canon_reward(
        len(f2p_passing), len(F2P),
        len(p2p_passing), len(P2P),
        rubric_verdict(sys.argv[1:]),
    )

    # Per-test outcomes, flat f2p::<name>/p2p::<name> = 1.0/0.0. Without these,
    # a gate run (e.g. nop) can only see the aggregate pass count, so an f2p
    # test that is inert (passes with no fix at all) is invisible to it.
    for ident, verdict in f2p_matched.items():
        _canon[f"f2p::{ident}"] = 1.0 if verdict == 'pass' else 0.0
    for ident, verdict in p2p_matched.items():
        _canon[f"p2p::{ident}"] = 1.0 if verdict == 'pass' else 0.0

    print(json.dumps({
        'reward': reward,
        'f2p': f2p_matched,
        'p2p': p2p_matched,
        'all_results': r,
    }))


if __name__ == '__main__':
    main()
