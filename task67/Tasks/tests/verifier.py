#!/usr/bin/env python3
"""
verifier.py — parses GoogleTest JUnit XML output and writes a reward.

Reward policy is BINARY, never partial credit:
  1.0 — every f2p test passes AND every p2p test still passes (or p2p is empty) AND the
        rubric (if any verdict is available) did not fail
  0.0 — anything short of that: no f2p passes, a strict subset of f2p passes, a p2p
        regression, report missing / failed to parse, or a failed rubric

The rubric can only ever withhold a 1.0, never turn a genuine 0.0 result into something
worse, and a missing/unavailable rubric verdict never blocks a 1.0.

This task has:
  f2p = ["ScenarioListBox.IconAreaRightClickDoesNotShowPopup"]
  p2p = []  (no pre-existing tests to guard)
"""
import atexit
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

CONF = json.load(open('/tests/config.json'))
F2P  = CONF['f2p']
P2P  = CONF['p2p']
REPORT = '/logs/verifier/report.xml'

# --- canonical reward writer + --rubric gate (see RUBRIC_MODES.md §2) --------------
# reward.json MUST be a FLAT map of numbers, exactly these seven keys:
#     {reward, tests_passed, f2p_passed, f2p_total, p2p_passed, p2p_total, rubric_passed}
# harbor parses it as dict[str, float | int] and prefers it over reward.txt; a nested
# value raises a validation error before any reward is recorded. rubric_passed: 1 pass /
# 0 fail / -1 not graded. Registered with atexit so it writes last.
_CANON_JSON = '/logs/verifier/reward.json'
_CANON_TXT = '/logs/verifier/reward.txt'
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric):
    f, t = int(f2p_passed), int(f2p_total)
    p, q = int(p2p_passed), int(p2p_total)
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
        print(f"WARNING: could not write {_CANON_JSON}: {exc}", file=sys.stderr)


def load_results():
    """Return {test_identifier: 'pass'|'fail'|'skip'} from JUnit XML."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError as exc:
        print(f"[verifier] XML parse error: {exc}", file=sys.stderr)
        return results
    for tc in tree.iter('testcase'):
        classname = tc.get('classname', '')
        name      = tc.get('name', '')
        # GoogleTest JUnit XML uses '.' as separator in classname; normalise to '::'
        dotted    = f"{classname}.{name}".strip('.')
        colon     = f"{classname}::{name}".strip(':')
        failed    = any(c.tag in ('failure', 'error') for c in tc)
        skipped   = any(c.tag == 'skipped' for c in tc)
        status    = 'skip' if skipped else ('fail' if failed else 'pass')
        results[dotted]  = status
        results[colon]   = status
    return results


def matched(idents, results):
    """Match each configured identifier to a result (substring / regex tolerant)."""
    out = {}
    for ident in idents:
        hit = next(
            (v for k, v in results.items()
             if ident in k or re.search(re.escape(ident), k)),
            None,
        )
        out[ident] = hit or 'missing'
    return out


def parse_rubric_arg(argv):
    """--rubric "pass"|"fail"|"" -> "pass"/"fail"/None. None (missing/unrecognised/empty)
    means no verdict is available yet and must never withhold a 1.0."""
    if "--rubric" not in argv:
        return None
    i = argv.index("--rubric")
    value = argv[i + 1].strip() if i + 1 < len(argv) else ""
    return value if value in ("pass", "fail") else None


def main():
    rubric = parse_rubric_arg(sys.argv[1:])

    r    = load_results()
    f2p  = matched(F2P, r)
    p2p  = matched(P2P, r)

    f2p_pass = [k for k, v in f2p.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p.items() if v == 'pass']

    reward = canon_reward(len(f2p_pass), len(F2P), len(p2p_pass), len(P2P), rubric)

    # per-test detail rides along as extra scalar keys on the same flat dict
    for name, v in f2p.items():
        _canon[f'f2p::{name}'] = 1.0 if v == 'pass' else 0.0
    for name, v in p2p.items():
        _canon[f'p2p::{name}'] = 1.0 if v == 'pass' else 0.0

    print(json.dumps({'reward': reward, 'rubric': rubric, 'f2p': f2p, 'p2p': p2p,
                       'report_keys': list(r.keys())}))


if __name__ == '__main__':
    main()
