#!/usr/bin/env python3
"""
Reward verifier for tldraw__tldraw-9133-mm

Parses the JUnit XML produced by vitest and computes a reward:
  1.0 — all f2p pass AND all p2p pass
  0.5 — some f2p pass OR a p2p regressed
  0.0 — no f2p passes, or the suite failed to run

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
RUBRIC_JSON = '/logs/verifier/rubric.json'


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


def write_reward(value, tests_passed=None, f2p=None, p2p=None, rubric=None):
    """reward.txt stays a BARE FLOAT in {0.0, 0.5, 1.0}; reward.json carries the detail."""
    os.makedirs(os.path.dirname(REWARD_OUT), exist_ok=True)
    with open(REWARD_OUT, 'w') as fh:
        fh.write(f"{value}\n")

    detail = {'reward': value,
              'tests_passed': value if tests_passed is None else tests_passed}
    if f2p is not None:
        detail['f2p_passed'] = sum(1 for v in f2p.values() if v)
        detail['f2p_total'] = len(f2p)
        detail['f2p'] = f2p
    if p2p is not None:
        detail['p2p'] = p2p
    detail['rubric'] = rubric                      # "pass" | "fail" | None (unavailable)
    failed = []
    if os.path.isfile(RUBRIC_JSON):
        try:
            failed = json.load(open(RUBRIC_JSON)).get('failed', [])
        except Exception:
            failed = []
    detail['rubric_failed'] = failed
    try:
        with open(REWARD_JSON, 'w') as fh:
            json.dump(detail, fh, indent=2)
    except Exception as exc:
        print(f"WARNING: could not write {REWARD_JSON}: {exc}", file=sys.stderr)
    print(json.dumps(detail, indent=2))


def main():
    argv = sys.argv[1:]
    rubric = None                                  # None = judge unavailable
    if '--rubric' in argv:
        i = argv.index('--rubric')
        value = argv[i + 1].strip() if i + 1 < len(argv) else ''
        argv = argv[:i] + argv[i + 2:]
        rubric = value if value in ('pass', 'fail') else None

    r    = load_results()
    f2p  = matched(F2P, r)
    p2p  = matched(P2P, r)

    f2p_pass = [k for k, v in f2p.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p.items() if v == 'pass']

    all_f2p = len(F2P) > 0 and len(f2p_pass) == len(F2P)
    all_p2p = len(p2p_pass) == len(P2P)          # vacuously True if P2P == []

    # Test policy (one-line rationale):
    #   1.0 → full fix: every f2p flipped AND every p2p still passes
    #   0.5 → partial: some (but not all) f2p pass, or a p2p regressed
    #   0.0 → no f2p flipped, or suite didn't run
    if all_f2p and all_p2p:
        tests_passed = 1.0
    elif f2p_pass and (not all_f2p or not all_p2p):
        tests_passed = 0.5
    else:
        tests_passed = 0.0

    # Each test is graded individually so the map, not just the aggregate, shows which passed.
    f2p_bool = {k: v == 'pass' for k, v in f2p.items()}
    p2p_bool = {k: v == 'pass' for k, v in p2p.items()}

    # The rubric can ONLY withhold a 1.0, never push the reward toward 0.0.
    if tests_passed >= 1.0 and rubric == 'fail':
        reward = 0.5
    else:
        reward = tests_passed

    write_reward(reward, tests_passed=tests_passed, f2p=f2p_bool, p2p=p2p_bool, rubric=rubric)


if __name__ == '__main__':
    main()
