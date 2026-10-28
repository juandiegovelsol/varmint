#!/usr/bin/env python3
"""Reward computation for trezor__trezor-suite-30548-mm.

Parses the JUnit XML report test.sh writes (jest + jest-junit) and computes the reward from
config.json's grounded f2p/p2p identifiers. NEVER inspects the candidate's source -- only the
test report.

Identifier format is "<classname> > <name>", where test.sh's JEST_JUNIT_* templates set
classname = the test file path as jest reports it (workspace-relative) and
name = the full ` > `-joined describe/it chain (confirmed empirically against this repo's own
report.xml).

Reward policy: BINARY. reward and tests_passed are 1.0 only when every f2p test passes AND
every p2p test still passes; reward is additionally zeroed if the rubric judge failed a
criterion (--rubric fail). rubric_passed is 1 pass / 0 fail / -1 not graded. There is no
partial credit -- a strict subset of f2p passing is 0.0, not 0.5.
"""
import atexit
import json
import os
import sys
import xml.etree.ElementTree as ET

CONF = json.load(open('/tests/config.json'))
F2P = CONF['f2p']
P2P = CONF['p2p']
REPORT = '/logs/verifier/report.xml'
REWARD_JSON = '/logs/verifier/reward.json'
REWARD_TXT = '/logs/verifier/reward.txt'

_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric):
    """THE reward policy for the whole corpus. BINARY -- there is no partial credit."""
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
        with open(REWARD_TXT, 'w') as fh:
            fh.write(str(_canon["reward"]))
    except Exception as exc:
        print("WARNING: could not write %s: %s" % (REWARD_JSON, exc), file=sys.stderr)


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`."""
    if "--rubric" not in argv:
        return None
    i = argv.index("--rubric")
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ""
    return value if value in ("pass", "fail") else None


def load_results():
    """Return {"<classname> > <name>": "pass"|"fail"|"skip"} parsed from the jest JUnit report."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError:
        return results
    for tc in tree.iter('testcase'):
        classname = tc.get('classname', '')
        name = tc.get('name', '')
        key = f"{classname} > {name}" if classname else name
        failed = any(c.tag in ('failure', 'error') for c in tc)
        skipped = any(c.tag == 'skipped' for c in tc)
        results[key] = 'skip' if skipped else ('fail' if failed else 'pass')
    return results


def match(idents, results):
    """Match each configured identifier to a reported test's status. Exact match first (our
    identifiers are literally `${classname} > ${name}` from the same report format), falling
    back to substring tolerance in case of minor formatting drift."""
    out = {}
    for ident in idents:
        if ident in results:
            out[ident] = results[ident]
            continue
        hit = next((v for k, v in results.items() if ident in k or k in ident), None)
        out[ident] = hit or 'missing'
    return out


def main():
    results = load_results()
    f2p = match(F2P, results)
    p2p = match(P2P, results)

    f2p_pass = [k for k, v in f2p.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p.items() if v == 'pass']

    canon_reward(len(f2p_pass), len(F2P), len(p2p_pass), len(P2P),
                 rubric_verdict(sys.argv[1:]))
    # Per-test detail, flat scalar keys alongside the 7 canonical ones -- lets the gate confirm
    # each f2p test fails individually on an empty submission, not just the aggregate count.
    _canon.update({f"f2p::{k}": 1.0 if v == 'pass' else 0.0 for k, v in f2p.items()})
    _canon.update({f"p2p::{k}": 1.0 if v == 'pass' else 0.0 for k, v in p2p.items()})

    print(json.dumps({**_canon, 'f2p': f2p, 'p2p': p2p}, indent=2))


if __name__ == '__main__':
    main()
