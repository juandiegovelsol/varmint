#!/usr/bin/env python3
"""
Verifier for vega__vega-4163-mm — tickMinStep enforcement in ticks.js.

Reward policy:
  1.0  — every f2p test passes AND every p2p test passes AND the rubric (if any) did not fail.
  0.5  — every f2p passes but a p2p regressed, OR a strict subset of f2p passes,
         OR every test passed but the rubric verdict is "fail" (the rubric can only
         withhold a 1.0, never force a 0.0 on its own).
  0.0  — no f2p passes, or the suite failed to run entirely.

Tests are matched by extracting the bare name from the tape('name', ...) hint.
No source-string matching is performed.
"""
import json, os, re, sys

CONF        = json.load(open('/tests/config.json'))
F2P         = CONF['f2p']
P2P         = CONF['p2p']
TAP_LOG     = '/logs/verifier/tap-output.txt'
REWARD      = '/logs/verifier/reward.txt'
REWARD_JSON = '/logs/verifier/reward.json'
RUBRIC_JSON = '/logs/verifier/judge/summary.json'


def extract_name(hint: str) -> str:
    m = re.match(r"""tape\(['"](.+?)['"]\s*,""", hint)
    return m.group(1) if m else hint.strip()


def parse_tap(path: str) -> dict:
    results = {}
    current = None
    failed  = False
    SUMMARY = re.compile(r'^# (tests|pass|fail|skip)\s+\d+')

    if not os.path.exists(path):
        return results

    with open(path, errors='replace') as fh:
        for raw in fh:
            line = raw.rstrip()
            if line.startswith('# ') and not SUMMARY.match(line):
                if current is not None:
                    results[current] = 'fail' if failed else 'pass'
                current = line[2:]
                failed  = False
            elif line.startswith('not ok '):
                failed = True

    if current is not None:
        results[current] = 'fail' if failed else 'pass'

    return results


def match_idents(hints: list, results: dict) -> dict:
    out = {}
    for hint in hints:
        name   = extract_name(hint)
        status = results.get(name)
        if status is None:
            status = next(
                (v for k, v in results.items() if name in k or re.search(re.escape(name), k)),
                None
            )
        out[hint] = status or 'missing'
    return out


def parse_rubric_arg(argv: list):
    """--rubric VALUE -> 'pass' | 'fail' | None (missing/pending/unrecognised)."""
    if '--rubric' not in argv:
        return None
    i = argv.index('--rubric')
    value = argv[i + 1].strip() if i + 1 < len(argv) else ''
    return value if value in ('pass', 'fail') else None


def write_reward_json(reward, tests_passed, f2p_map, p2p_map, rubric):
    """reward.json MUST be a FLAT map of numbers (harbor's VerifierResult.rewards)."""
    detail = {
        'reward': reward,
        'tests_passed': tests_passed,
        'f2p_passed': sum(1 for v in f2p_map.values() if v == 'pass'),
        'f2p_total': len(f2p_map),
        'p2p_passed': sum(1 for v in p2p_map.values() if v == 'pass'),
        'p2p_total': len(p2p_map),
        'rubric_pass': {'pass': 1, 'fail': 0}.get(rubric, -1),
    }
    failed = []
    if os.path.isfile(RUBRIC_JSON):
        try:
            failed = json.load(open(RUBRIC_JSON)).get('failed', [])
        except Exception:
            failed = []
    detail['rubric_failed_count'] = len(failed)
    for name, status in f2p_map.items():
        detail[f'f2p::{name}'] = 1.0 if status == 'pass' else 0.0
    for name, status in p2p_map.items():
        detail[f'p2p::{name}'] = 1.0 if status == 'pass' else 0.0
    try:
        with open(REWARD_JSON, 'w') as fh:
            json.dump(detail, fh, indent=2)
    except Exception as exc:
        print(f'WARNING: could not write {REWARD_JSON}: {exc}', file=sys.stderr)


def main():
    rubric = parse_rubric_arg(sys.argv[1:])

    results = parse_tap(TAP_LOG)
    f2p_map = match_idents(F2P, results)
    p2p_map = match_idents(P2P, results)

    f2p_pass = [k for k, v in f2p_map.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p_map.items() if v == 'pass']

    all_f2p = len(f2p_pass) == len(F2P) and len(F2P) > 0
    all_p2p = len(p2p_pass) == len(P2P)

    if all_f2p and all_p2p:
        tests_passed = 1.0
    elif f2p_pass and (not all_p2p or not all_f2p):
        tests_passed = 0.5
    else:
        tests_passed = 0.0

    # The rubric can only withhold a 1.0, never push an otherwise-passing run to 0.0.
    reward = 0.5 if (tests_passed >= 1.0 and rubric == 'fail') else tests_passed

    os.makedirs(os.path.dirname(REWARD), exist_ok=True)
    with open(REWARD, 'w') as fh:
        fh.write(str(reward))

    write_reward_json(reward, tests_passed, f2p_map, p2p_map, rubric)

    print(json.dumps({
        'reward': reward,
        'tests_passed': tests_passed,
        'rubric': rubric,
        'f2p': f2p_map,
        'p2p': p2p_map,
        'tap_blocks_found': len(results),
    }, indent=2))


if __name__ == '__main__':
    main()
