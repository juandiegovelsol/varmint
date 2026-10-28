#!/usr/bin/env python3
"""
Reward verifier for SR5-FoundryVTT__SR5-FoundryVTT-1831-mm.

Reads /logs/verifier/report.xml (JUnit XML written by test_migrator_test_modifier_key.mjs),
matches test results against config.json's f2p/p2p lists, and writes the reward to
/logs/verifier/reward.json (and reward.txt, which the sandbox teardown script and the
lighthouse UI read instead).

Reward policy (binary -- there is no partial credit):
  1.0  - every f2p test passes AND every p2p test passes
  0.0  - otherwise (a partial f2p pass, a p2p regression -- e.g. the apply-to scoping was
         dropped, or the migration list lost one of its pre-existing entries -- or the
         suite failed to produce a report at all)
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
REWARD_JSON = '/logs/verifier/reward.json'

_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric):
    """THE reward policy. BINARY -- there is no partial credit."""
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
        os.makedirs(os.path.dirname(REWARD_JSON), exist_ok=True)
        with open(REWARD_JSON, 'w') as fh:
            json.dump(_canon, fh, indent=2)
        with open(REWARD, 'w') as fh:
            fh.write(str(_canon["reward"]))
    except Exception as exc:
        print(f'WARNING: could not write {REWARD_JSON}: {exc}', file=sys.stderr)


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`.

    Anything that is not an explicit pass/fail -- including the empty string test.sh
    passes when judge.py wrote no verdict -- means "not graded", which must never
    penalise the run.
    """
    if '--rubric' not in argv:
        return None
    i = argv.index('--rubric')
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ''
    return value if value in ('pass', 'fail') else None


def load_results():
    """Return {test_name: 'pass'|'fail'|'skip'} parsed from JUnit XML."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError as e:
        print(f'[verifier] XML parse error: {e}', file=sys.stderr)
        return results
    for tc in tree.iter('testcase'):
        name = tc.get('name', '')
        cls  = tc.get('classname', '')
        key  = f'{cls}::{name}' if cls else name
        tags = {c.tag for c in tc}
        if 'skipped' in tags:
            status = 'skip'
        elif tags & {'failure', 'error'}:
            status = 'fail'
        else:
            status = 'pass'
        results[key]  = status
        results[name] = status   # also index by bare name for easy matching
    return results


def match_idents(idents, results):
    """Match each configured identifier against reported test names.

    Matching strategy (in order):
      1. Exact key match.
      2. Substring match (ident contained in a reported key).
      3. Regex search (re.escape of ident against reported keys).
    Returns {ident: 'pass'|'fail'|'skip'|'missing'}.
    """
    out = {}
    for ident in idents:
        if ident in results:
            out[ident] = results[ident]
            continue
        hit = next((v for k, v in results.items() if ident in k), None)
        if hit is not None:
            out[ident] = hit
            continue
        try:
            pat = re.compile(re.escape(ident))
            hit = next((v for k, v in results.items() if pat.search(k)), None)
        except re.error:
            hit = None
        out[ident] = hit if hit is not None else 'missing'
    return out


def main():
    results = load_results()
    f2p_res = match_idents(F2P, results)
    p2p_res = match_idents(P2P, results)

    f2p_pass   = [k for k, v in f2p_res.items() if v == 'pass']
    p2p_pass   = [k for k, v in p2p_res.items() if v == 'pass']

    reward = canon_reward(len(f2p_pass), len(F2P), len(p2p_pass), len(P2P),
                           rubric_verdict(sys.argv[1:]))

    print(json.dumps({
        'reward': reward,
        'f2p':    f2p_res,
        'p2p':    p2p_res,
        'f2p_pass_count': len(f2p_pass),
        'f2p_total':      len(F2P),
        'p2p_pass_count': len(p2p_pass),
        'p2p_total':      len(P2P),
    }, indent=2))


if __name__ == '__main__':
    main()
