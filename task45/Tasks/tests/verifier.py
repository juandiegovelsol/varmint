#!/usr/bin/env python3
"""Behavioral verifier for fabricjs__fabric.js-10805-mm.
Parses JUnit XML from vitest and computes reward from f2p/p2p.
NEVER greps source for the fix — scores from test results only.

Reward policy — BINARY, no partial credit:
  1.0 — every f2p PASS AND every p2p PASS
  0.0 — otherwise (any f2p missing/failing, any p2p regressed, or suite failed to run)

A strict subset of f2p passing scores 0.0, not partial credit: the task is unsolved, and
the f2p_passed / f2p_total / p2p_passed / p2p_total counts in reward.json carry the detail.

The rubric verdict arrives as `--rubric pass|fail|""` from test.sh and can only ever
withhold a 1.0: `fail` forces the reward to 0.0, while `pass` and "not graded" never lower
it — the judge must not be able to penalise a run it could not grade.

Outputs (both written from one dict, so they cannot disagree):
  /logs/verifier/reward.json — the canonical flat map of seven numeric keys
  /logs/verifier/reward.txt  — the same reward as a bare float
"""
import atexit, json, os, re, sys
try:
    import xml.etree.ElementTree as ET
except ImportError:
    pass

CONF = json.load(open('/tests/config.json'))
F2P, P2P = CONF['f2p'], CONF['p2p']
REPORT = '/logs/verifier/report.xml'
REWARD = '/logs/verifier/reward.txt'
REWARD_JSON = '/logs/verifier/reward.json'

_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric, detail=None):
    """THE reward policy for the whole corpus. BINARY -- there is no partial credit.

    tests_passed is 1.0 only when every f2p test passes AND every p2p test still passes. A
    strict subset of f2p passing is not partial progress worth scoring: the task is unsolved,
    so it is 0.0.

    reward is the same value, zeroed when the rubric judge failed a criterion. A "pass" or a
    "not graded" verdict never lowers the score -- the judge must never be able to penalise a
    run it could not grade.

    `detail` rides along as extra `f2p::<name>` / `p2p::<name>` = 1.0/0.0 SCALAR keys in the
    same flat dict -- never as a nested map, which harbor would reject. They are what makes an
    INERT f2p test detectable: a test that already passes on an empty submission shows up as
    f2p::<name> = 1.0 in the Nop run.
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
    for key, value in (detail or {}).items():
        _canon[str(key)] = float(value)
    return _canon["reward"]


@atexit.register
def _canon_flush():
    """Writes LAST, so it overrides anything a local reward block already wrote."""
    if not _canon:
        return
    try:
        os.makedirs(os.path.dirname(REWARD_JSON), exist_ok=True)
        with open(REWARD_JSON, "w") as _h:
            json.dump(_canon, _h, indent=2)
        # reward.txt too: harbor prefers reward.json, but the sandbox teardown script and the
        # lighthouse UI read reward.txt. Writing both from one dict means they cannot disagree.
        with open(REWARD, "w") as _h:
            _h.write(str(_canon["reward"]))
    except Exception as _exc:
        print("WARNING: could not write %s: %s" % (REWARD_JSON, _exc), file=sys.stderr)


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

    # Per-test outcomes, flat and scalar. An f2p test that reads 1.0 here on the Nop run is
    # inert: it passes without a fix, so it cannot be measuring the defect.
    detail = {f'f2p::{name}': 1.0 if state == 'pass' else 0.0
              for name, state in f2p.items()}
    detail.update({f'p2p::{name}': 1.0 if state == 'pass' else 0.0
                   for name, state in p2p.items()})

    rubric = rubric_verdict(sys.argv[1:])
    reward = canon_reward(len(f2p_pass), len(F2P),
                          len(p2p_pass), len(P2P),
                          rubric, detail)

    print(json.dumps({
        'reward': reward,
        'rubric': rubric or 'not graded',
        'f2p': f2p,
        'p2p': p2p,
        'f2p_pass': f2p_pass,
        'p2p_pass': p2p_pass,
        'reward_json': _canon,
    }))


if __name__ == '__main__':
    main()
