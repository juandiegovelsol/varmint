#!/usr/bin/env python3
"""Reward computation for Textualize__textual-5436-mm.

Parses the JUnit XML report emitted by test.sh and computes the reward from
config.json's f2p/p2p lists. NEVER inspects candidate source — only the test report.

Reward policy — BINARY, there is no partial credit:
  1.0  -- every f2p test passes AND every p2p test still passes.
  0.0  -- anything else: a strict subset of f2p passing, any p2p regression, no
          report at all, or a rubric verdict of "fail".

A half-finished fix is a fail, so it is floored to 0.0 rather than scored in the
middle: partial credit would let it read as "solved" to pass@k. Nothing is lost,
because the f2p_passed / f2p_total / p2p_passed / p2p_total counts in reward.json
carry how close the run got.
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

# --- canonical reward writer + --rubric gate -------------------------------------
# Merged from template/tests/verifier_reward_block.py. reward.json MUST be a FLAT map of
# numbers with exactly these seven keys: harbor parses it as dict[str, float | int] and
# takes it in PREFERENCE to reward.txt, so a nested value aborts the run before any reward
# is recorded — while reward.txt still gets written in-container, making the run look scored
# when nothing was stored. Registered with atexit so it writes LAST.
import atexit, json as _cj, os as _co, sys as _cs

_CANON_JSON = "/logs/verifier/reward.json"
_CANON_TXT = "/logs/verifier/reward.txt"
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric):
    """THE reward policy for the whole corpus. BINARY -- there is no partial credit.

    tests_passed is 1.0 only when every f2p test passes AND every p2p test still passes. A
    strict subset of f2p passing is not partial progress worth scoring: the task is unsolved,
    so it is 0.0.

    reward is the same value, zeroed when the rubric judge failed a criterion. A "pass" or a
    "not graded" verdict never lowers the score -- the judge must never be able to penalise a
    run it could not grade.
    """
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
        _co.makedirs(_co.path.dirname(_CANON_JSON), exist_ok=True)
        with open(_CANON_JSON, "w") as _h:
            _cj.dump(_canon, _h, indent=2)
        # reward.txt too: harbor prefers reward.json, but the sandbox teardown script and the
        # lighthouse UI read reward.txt. Writing both from one dict means they cannot disagree.
        with open(_CANON_TXT, "w") as _h:
            _h.write(str(_canon["reward"]))
    except Exception as _exc:
        print("WARNING: could not write %s: %s" % (_CANON_JSON, _exc), file=_cs.stderr)


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`.

    Anything that is not an explicit pass/fail -- including the empty string test.sh passes
    when judge.py wrote no verdict -- means "not graded", which must never penalise the run.
    """
    if "--rubric" not in argv:
        return None
    i = argv.index("--rubric")
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ""
    return value if value in ("pass", "fail") else None


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

    # Binary policy, applied by the canonical block: 1.0 only when every f2p passes and no
    # p2p regressed. canon_reward writes reward.json and reward.txt via atexit, so it is the
    # single writer and the two files cannot disagree.
    reward = canon_reward(len(f2p_pass), len(F2P),
                          len(p2p_pass), len(P2P),
                          rubric_verdict(sys.argv[1:]))

    # Per-test detail as extra FLAT SCALAR keys on the same dict (never a nested map, which
    # harbor would reject). The aggregate counts cannot answer "did THIS f2p test fail on nop?",
    # which is what proves no individual f2p test is inert.
    for prefix, outcomes in (('f2p', f2p), ('p2p', p2p)):
        for ident, outcome in outcomes.items():
            _canon['%s::%s' % (prefix, ident.split('::')[-1])] = 1.0 if outcome == 'pass' else 0.0

    print(json.dumps({'reward': reward, 'f2p': f2p, 'p2p': p2p}))


if __name__ == '__main__':
    main()
