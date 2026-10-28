#!/usr/bin/env python3
"""
Behavioral verifier for facebook__lexical-8729-mm.
Parses the vitest JUnit XML report and computes a reward score.
Reward policy (binary):
  1.0 — every f2p test passes AND every p2p test still passes.
  0.0 — otherwise (including report missing / unparseable).
rubric_passed: 1 pass / 0 fail / -1 not graded (no rubric ships on this task).
NEVER inspects candidate source code — only test results.
"""
import atexit, json, os, re, sys, xml.etree.ElementTree as ET

CONF = json.load(open('/tests/config.json'))
F2P = CONF['f2p']
P2P = CONF['p2p']
REPORT = '/logs/verifier/report.xml'
REWARD = '/logs/verifier/reward.txt'

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
        os.makedirs(os.path.dirname(_CANON_JSON), exist_ok=True)
        with open(_CANON_JSON, "w") as _h:
            json.dump(_canon, _h, indent=2)
        # reward.txt too: harbor prefers reward.json, but the sandbox teardown script and the
        # lighthouse UI read reward.txt. Writing both from one dict means they cannot disagree.
        with open(_CANON_TXT, "w") as _h:
            _h.write(str(_canon["reward"]))
    except Exception as _exc:
        print("WARNING: could not write %s: %s" % (_CANON_JSON, _exc), file=sys.stderr)


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`.

    Anything that is not an explicit pass/fail -- including the empty string test.sh passes
    when no rubric ships -- means "not graded", which must never penalise the run.
    """
    if "--rubric" not in argv:
        return None
    i = argv.index("--rubric")
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ""
    return value if value in ("pass", "fail") else None


def load_results():
    """Return {test_key: 'pass'|'fail'|'skip'} parsed from vitest JUnit XML.
    The key is 'classname > name' for robust substring matching."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError as e:
        print(f"WARNING: could not parse report XML: {e}", file=sys.stderr)
        return results
    for tc in tree.iter('testcase'):
        classname = tc.get('classname', '')
        name = tc.get('name', '')
        # Build composite key to allow substring matching on either component
        key = f"{classname} > {name}"
        failed = any(c.tag in ('failure', 'error') for c in tc)
        skipped = any(c.tag == 'skipped' for c in tc)
        results[key] = 'skip' if skipped else ('fail' if failed else 'pass')
    return results


def matched(idents, results):
    """Match each configured identifier against reported test keys (substring tolerant).
    Returns {ident: status} where status is 'pass', 'fail', 'skip', or 'missing'."""
    out = {}
    for ident in idents:
        hit = next(
            (v for k, v in results.items()
             if ident in k),
            None
        )
        out[ident] = hit if hit is not None else 'missing'
    return out


def main():
    r = load_results()
    f2p_matched = matched(F2P, r)
    p2p_matched = matched(P2P, r)

    f2p_pass = [k for k, v in f2p_matched.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p_matched.items() if v == 'pass']

    reward = canon_reward(len(f2p_pass), len(F2P), len(p2p_pass), len(P2P),
                           rubric_verdict(sys.argv[1:]))
    # Per-test detail so the gate can tell a genuinely discriminating f2p test from an inert
    # one (passes on nop regardless): flat scalar keys on the same canonical dict, never nested.
    _canon.update({f"f2p::{k}": (1.0 if v == 'pass' else 0.0) for k, v in f2p_matched.items()})
    _canon.update({f"p2p::{k}": (1.0 if v == 'pass' else 0.0) for k, v in p2p_matched.items()})

    result = {
        'reward': reward,
        'f2p': f2p_matched,
        'p2p': p2p_matched,
        'f2p_pass_count': len(f2p_pass),
        'f2p_total': len(F2P),
        'p2p_pass_count': len(p2p_pass),
        'p2p_total': len(P2P),
    }
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
