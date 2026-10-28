#!/usr/bin/env python3
"""
Verifier for carbon-design-system__carbon-21854-mm (cds-tabs / cds-content-switcher manual
selection-mode event contract).

Reads the per-test JSON report produced by test.sh (a custom @web/test-runner reporter dumps
the REAL Mocha pass/fail/missing status for every test in the two harness test files) and
computes a scalar reward. Reward is BINARY: 1.0 only when every f2p passes AND every p2p
still passes; a strict subset of f2p passing or any p2p regression is 0.0, not partial
credit -- the four count keys in reward.json already carry how close it got. NEVER inspects
source for the fix -- reward derives solely from the test report.
"""
import atexit
import json
import os
import sys

CONF = json.load(open('/tests/config.json'))
F2P = CONF['f2p']
P2P = CONF['p2p']
REPORT = '/logs/verifier/results.json'   # keep in sync with test.sh's reporter output path
REWARD = '/logs/verifier/reward.txt'
CANON_JSON = '/logs/verifier/reward.json'
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric):
    """THE reward policy for the whole corpus. BINARY -- there is no partial credit."""
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
        os.makedirs(os.path.dirname(CANON_JSON), exist_ok=True)
        with open(CANON_JSON, 'w') as h:
            json.dump(_canon, h, indent=2)
        with open(REWARD, 'w') as h:
            h.write(str(_canon['reward']))
    except OSError as exc:
        print(f'WARNING: could not write {CANON_JSON}: {exc}', file=sys.stderr)


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`. Anything else means "not
    graded", which must never penalise the run."""
    if '--rubric' not in argv:
        return None
    i = argv.index('--rubric')
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ''
    return value if value in ('pass', 'fail') else None


def load_results() -> dict:
    """Return {full_test_title: 'pass'|'fail'|'skip'} from test.sh's JSON report."""
    if not os.path.exists(REPORT):
        return {}
    try:
        data = json.load(open(REPORT))
    except (OSError, json.JSONDecodeError) as e:
        print(f'[verifier] report parse error: {e}', file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def matched(idents: list, results: dict) -> dict:
    out = {}
    for ident in idents:
        # config.json identifiers are the plain "<describe> > <it>" full mocha title; the
        # reporter in test.sh keys results the same way, so this is an exact lookup, never
        # a substring scan.
        out[ident] = results.get(ident, 'missing')
    return out


def main() -> int:
    r = load_results()
    f2p = matched(F2P, r)
    p2p = matched(P2P, r)

    f2p_pass = [k for k, v in f2p.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p.items() if v == 'pass']

    reward = canon_reward(len(f2p_pass), len(F2P), len(p2p_pass), len(P2P),
                          rubric_verdict(sys.argv[1:]))

    print(json.dumps({
        'reward': reward,
        'f2p': f2p,
        'p2p': p2p,
        'f2p_pass_count': len(f2p_pass),
        'p2p_pass_count': len(p2p_pass),
        'testcases_total': len(F2P) + len(P2P),
        'testcases_seen': sum(1 for v in {**f2p, **p2p}.values() if v != 'missing'),
    }))
    return 0


if __name__ == '__main__':
    sys.exit(main())
