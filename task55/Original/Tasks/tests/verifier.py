#!/usr/bin/env python3
"""
Behavioral verifier for facebook__lexical-7959-mm.

Parses the vitest JUnit XML report and computes the reward. It NEVER inspects
candidate source code -- only test results.

Reward policy (the corpus-wide binary policy):
  reward / tests_passed = 1.0  <=>  EVERY f2p test passes AND EVERY p2p test passes
  anything else                =>  0.0
There is no middle rung: a partially-repaired submission is unsolved, so it scores
0.0. How close it got is carried by the count keys (f2p_passed / f2p_total,
p2p_passed / p2p_total) and, per behaviour, by the `f2p::<name>` / `p2p::<name>`
scalar keys in reward.json -- which is what makes this task's nine independently
observable behaviours legible without inventing a fractional reward.

A rubric verdict handed in as `--rubric fail` can only ever withhold a 1.0; `pass`
and "not graded" never lower the score. This task ships no rubric layer, so the
gate is inert here and rubric_passed is always -1.
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
REWARD_TXT = '/logs/verifier/reward.txt'
REWARD_JSON = '/logs/verifier/reward.json'

_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric, detail):
    """THE reward policy. Binary -- there is no partial credit in `reward`."""
    f, t = int(f2p_passed), int(f2p_total)
    p, q = int(p2p_passed), int(p2p_total)
    solved = bool(t) and f == t and p == q
    tests_passed = 1.0 if solved else 0.0
    _canon.clear()
    _canon.update({
        'reward': 0.0 if rubric == 'fail' else tests_passed,
        'tests_passed': tests_passed,
        'f2p_passed': f,
        'f2p_total': t,
        'p2p_passed': p,
        'p2p_total': q,
        'rubric_passed': {'pass': 1, 'fail': 0}.get(rubric, -1),
    })
    # Per-behaviour detail rides along as flat scalar keys, never a nested map.
    _canon.update(detail)
    return _canon['reward']


@atexit.register
def _canon_flush():
    if not _canon:
        return
    try:
        os.makedirs(os.path.dirname(REWARD_JSON), exist_ok=True)
        with open(REWARD_JSON, 'w') as fh:
            json.dump(_canon, fh, indent=2)
        # reward.txt too: harbor prefers reward.json, but the sandbox teardown
        # script and the lighthouse UI read reward.txt. Writing both from one
        # dict means they cannot disagree.
        with open(REWARD_TXT, 'w') as fh:
            fh.write(str(_canon['reward']))
    except Exception as exc:
        print('WARNING: could not write %s: %s' % (REWARD_JSON, exc),
              file=sys.stderr)


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`."""
    if '--rubric' not in argv:
        return None
    i = argv.index('--rubric')
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ''
    return value if value in ('pass', 'fail') else None


def load_results():
    """Return {'classname > name': 'pass'|'fail'|'skip'} from the JUnit XML."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError as exc:
        print('WARNING: could not parse report XML: %s' % exc, file=sys.stderr)
        return results
    for tc in tree.iter('testcase'):
        key = '%s > %s' % (tc.get('classname', ''), tc.get('name', ''))
        failed = any(c.tag in ('failure', 'error') for c in tc)
        skipped = any(c.tag == 'skipped' for c in tc)
        results[key] = 'skip' if skipped else ('fail' if failed else 'pass')
    return results


def matched(idents, results):
    """{ident: 'pass'|'fail'|'skip'|'missing'} (substring tolerant)."""
    out = {}
    for ident in idents:
        hit = next((v for k, v in results.items() if ident in k), None)
        out[ident] = hit if hit is not None else 'missing'
    return out


def short(ident):
    """Last path-ish segment of an identifier, for the per-test reward keys."""
    return ident.rsplit(' > ', 1)[-1].strip()


def main():
    r = load_results()
    f2p_matched = matched(F2P, r)
    p2p_matched = matched(P2P, r)

    f2p_pass = [k for k, v in f2p_matched.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p_matched.items() if v == 'pass']

    detail = {}
    for ident, status in f2p_matched.items():
        detail['f2p::%s' % short(ident)] = 1.0 if status == 'pass' else 0.0
    for ident, status in p2p_matched.items():
        detail['p2p::%s' % short(ident)] = 1.0 if status == 'pass' else 0.0

    reward = canon_reward(len(f2p_pass), len(F2P),
                          len(p2p_pass), len(P2P),
                          rubric_verdict(sys.argv[1:]), detail)

    print(json.dumps({
        'reward': reward,
        'f2p': f2p_matched,
        'p2p': p2p_matched,
        'f2p_pass_count': len(f2p_pass),
        'f2p_total': len(F2P),
        'p2p_pass_count': len(p2p_pass),
        'p2p_total': len(P2P),
    }, indent=2))


if __name__ == '__main__':
    main()
