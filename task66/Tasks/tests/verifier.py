#!/usr/bin/env python3
"""
Verifier for radix-ui__primitives-2049-mm (Select overflow positioning).
Synthetic test — authored in Step 1b per spec.
Parses jest --json output (not JUnit XML, since this base uses jest@27).

Reward policy is BINARY (see canon_reward): reward is 1.0 only when every f2p test
passes, every p2p test still passes, and the rubric verdict is not "fail" — otherwise
0.0. There is no partial credit; the f2p/p2p count keys in reward.json already carry
how close a partial run got.
"""
import argparse
import atexit
import json
import os
import re
import sys

CONF = json.load(open('/tests/config.json'))
F2P, P2P = CONF['f2p'], CONF['p2p']
REPORT = '/logs/verifier/report.json'
REWARD = '/logs/verifier/reward.txt'
REWARD_JSON = '/logs/verifier/reward.json'

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
        os.makedirs(os.path.dirname(REWARD_JSON), exist_ok=True)
        with open(REWARD_JSON, "w") as h:
            json.dump(_canon, h, indent=2)
        # reward.txt too: harbor prefers reward.json, but the sandbox teardown script and
        # the lighthouse UI read reward.txt. Writing both from one dict means they cannot
        # disagree.
        with open(REWARD, "w") as h:
            h.write(str(_canon["reward"]))
    except Exception as exc:
        print("WARNING: could not write %s: %s" % (REWARD_JSON, exc), file=sys.stderr)


def load_results():
    """Return {test_identifier: 'pass'|'fail'|'skip'} parsed from jest --json output."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        data = json.load(open(REPORT))
    except (json.JSONDecodeError, IOError) as e:
        print(f"JSON parse error: {e}", file=sys.stderr)
        return results

    # Jest JSON format: { testResults: [ { name, assertionResults: [ {fullName, status} ] } ] }
    # Note: jest uses 'assertionResults' (not 'testResults') for individual tests within a suite.
    for suite in data.get('testResults', []):
        for tc in suite.get('assertionResults', suite.get('testResults', [])):
            name = tc.get('fullName', tc.get('title', ''))
            status_raw = tc.get('status', 'unknown')
            # Jest statuses: 'passed', 'failed', 'pending', 'skipped', 'todo'
            if status_raw == 'passed':
                status = 'pass'
            elif status_raw in ('pending', 'skipped', 'todo'):
                status = 'skip'
            else:
                status = 'fail'
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
    ap = argparse.ArgumentParser()
    ap.add_argument('--rubric', default='', help='"pass", "fail", or "" (no verdict yet)')
    args = ap.parse_args()

    r = load_results()
    f2p_matched = matched(F2P, r)
    p2p_matched = matched(P2P, r)

    f2p_pass = [k for k, v in f2p_matched.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p_matched.items() if v == 'pass']

    rubric = args.rubric.strip().lower()
    rubric = rubric if rubric in ('pass', 'fail') else None

    # reward.json MUST be a FLAT map of numbers: harbor parses it as
    # VerifierResult.rewards: dict[str, float] and prefers it over reward.txt, so a
    # nested dict/string/None here raises a pydantic ValidationError that aborts the
    # trial before any reward is recorded, even though reward.txt was written correctly.
    # canon_reward() sets the canonical seven keys; per-test outcomes ride along as
    # extra flat f2p::<name> / p2p::<name> scalar entries, never a nested map.
    reward = canon_reward(len(f2p_pass), len(F2P), len(p2p_pass), len(P2P), rubric)
    for name, status in f2p_matched.items():
        _canon[f'f2p::{name}'] = 1.0 if status == 'pass' else 0.0
    for name, status in p2p_matched.items():
        _canon[f'p2p::{name}'] = 1.0 if status == 'pass' else 0.0

    print(json.dumps({'reward': reward, 'f2p': f2p_matched, 'p2p': p2p_matched,
                       'rubric': rubric or 'pending'}))


if __name__ == '__main__':
    main()
