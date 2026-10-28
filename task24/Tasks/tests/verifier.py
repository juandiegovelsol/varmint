#!/usr/bin/env python3
"""
Reward verifier for tldraw__tldraw-9133-mm

Parses the JUnit XML produced by vitest and computes a reward:
  1.0 — all f2p pass AND all p2p pass
  0.0 — otherwise (no partial credit)

f2p (fail-to-pass): tests that FAIL on base, PASS after fix.
    These directly verify that menu-items.tsx now gates submenus on their actions.
p2p (pass-to-pass): tests that PASS on both base and fix.
    These guard against regressions (menus that should always show still do).

BEHAVIORAL CONTRACT: reward is derived entirely from the test report.
This verifier NEVER inspects source code for the fix string or any other token.
"""
import json, os, re, sys, xml.etree.ElementTree as ET

CONF        = json.load(open('/tests/config.json'))
F2P         = CONF['f2p']
P2P         = CONF['p2p']
REPORT      = '/logs/verifier/report.xml'
REWARD_OUT  = '/logs/verifier/reward.txt'
REWARD_JSON = '/logs/verifier/reward.json'


def load_results():
    """Return {combined_id: 'pass'|'fail'|'skip'} from the JUnit XML."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError as exc:
        print(f"[verifier] WARNING: could not parse {REPORT}: {exc}", file=sys.stderr)
        return results
    for tc in tree.iter('testcase'):
        # Vitest JUnit: classname = describe block(s), name = test title.
        # We combine them so substring matching catches both long and short forms.
        classname = tc.get('classname', '')
        name      = tc.get('name', '')
        combined  = f"{classname}::{name}".strip(':')
        failed    = any(c.tag in ('failure', 'error') for c in tc)
        skipped   = any(c.tag == 'skipped'            for c in tc)
        results[combined] = 'skip' if skipped else ('fail' if failed else 'pass')
    return results


def matched(idents, results):
    """Return {ident: 'pass'|'fail'|'skip'|'missing'}.
    Matching is substring-first, regex-fallback, to tolerate minor name changes."""
    out = {}
    for ident in idents:
        hit = next(
            (v for k, v in results.items()
             if ident in k or re.search(re.escape(ident), k)),
            None,
        )
        out[ident] = hit if hit is not None else 'missing'
    return out


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`.
    Anything that is not an explicit pass/fail — including "" when no rubric ships —
    means "not graded", which must never penalise the run."""
    if '--rubric' not in argv:
        return None
    i = argv.index('--rubric')
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ''
    return value if value in ('pass', 'fail') else None


def write_reward(f2p_bool, p2p_bool, rubric):
    """reward.json is a FLAT map of numbers, exactly the seven canonical keys
    (reward, tests_passed, f2p_passed, f2p_total, p2p_passed, p2p_total, rubric_passed),
    plus per-test detail riding along as extra scalar f2p::<name>/p2p::<name> keys —
    never a nested map. THE POLICY IS BINARY: a strict subset of f2p passing is 0.0,
    never partial credit — the count keys already carry how close it got. The rubric
    can only ever withhold a 1.0, never push the reward below what the tests earned."""
    f2p_passed = sum(1 for v in f2p_bool.values() if v)
    p2p_passed = sum(1 for v in p2p_bool.values() if v)
    solved = len(F2P) > 0 and f2p_passed == len(F2P) and p2p_passed == len(P2P)
    tests_passed = 1.0 if solved else 0.0
    reward = 0.0 if rubric == 'fail' else tests_passed

    detail = {
        'reward': reward,
        'tests_passed': tests_passed,
        'f2p_passed': f2p_passed, 'f2p_total': len(F2P),
        'p2p_passed': p2p_passed, 'p2p_total': len(P2P),
        'rubric_passed': {'pass': 1, 'fail': 0}.get(rubric, -1),
    }
    for k, v in f2p_bool.items():
        detail[f'f2p::{k}'] = 1.0 if v else 0.0
    for k, v in p2p_bool.items():
        detail[f'p2p::{k}'] = 1.0 if v else 0.0

    os.makedirs(os.path.dirname(REWARD_OUT), exist_ok=True)
    with open(REWARD_OUT, 'w') as fh:
        fh.write(str(reward))
    try:
        with open(REWARD_JSON, 'w') as fh:
            json.dump(detail, fh, indent=2)
    except Exception as exc:
        print(f"WARNING: could not write {REWARD_JSON}: {exc}", file=sys.stderr)
    print(json.dumps(detail, indent=2))


def main():
    argv = sys.argv[1:]
    rubric = rubric_verdict(argv)

    r   = load_results()
    f2p = matched(F2P, r)
    p2p = matched(P2P, r)

    # Each test is graded individually so the map, not just the aggregate, shows which passed.
    f2p_bool = {k: v == 'pass' for k, v in f2p.items()}
    p2p_bool = {k: v == 'pass' for k, v in p2p.items()}

    write_reward(f2p_bool, p2p_bool, rubric)


if __name__ == '__main__':
    main()
