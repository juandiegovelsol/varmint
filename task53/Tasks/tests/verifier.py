#!/usr/bin/env python3
"""
Reward verifier for SR5-FoundryVTT__SR5-FoundryVTT-1462-mm.

Reads /logs/verifier/report.xml (JUnit XML written by test_sprite_power_sections.mjs),
matches test results against config.json's f2p/p2p lists, and writes the canonical
reward to /logs/verifier/reward.json and /logs/verifier/reward.txt.

Reward policy (BINARY - there is no partial credit):
  1.0  - every f2p test passes AND every p2p test passes
  0.0  - anything else, including a strict subset of f2p passing (e.g. only some of the
         defects marked on the screenshot were found) or a p2p regression

A half-finished fix is unsolved, so it scores zero rather than earning partial credit,
which would let it read as solved to pass@k. Nothing is lost by collapsing the middle,
because the f2p_passed / f2p_total / p2p_passed / p2p_total counts carry how close it got.
"""
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

# --- canonical reward writer + --rubric gate ---------------------------------------
# reward.json MUST be a FLAT map of numbers built on these seven canonical keys; harbor
# parses it as VerifierResult.rewards and takes it in PREFERENCE to reward.txt. A nested
# dict, list, string or None raises a ValidationError that aborts the run BEFORE any reward
# is recorded - while reward.txt still gets written inside the container, so the run would
# look scored when harbor in fact stored nothing.
#   rubric_passed: 1 pass / 0 fail / -1 not graded (no rubric shipped, or judge absent).
# Per-test outcomes ride along as extra FLAT scalar keys - f2p::<name> / p2p::<name> = 1.0
# for pass, 0.0 for anything else. They stay numbers and stay unnested, so they are an
# expected extra rather than a schema violation. The counts alone cannot show WHICH test
# did what, so without these an inert f2p test - one that passes even on an empty
# submission, and therefore gates nothing - cannot be detected from a nop run.
# Registered with atexit so it writes LAST and overrides any earlier local reward write.
import atexit

_CANON_JSON = '/logs/verifier/reward.json'
_CANON_TXT  = '/logs/verifier/reward.txt'
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric,
                 f2p_res=None, p2p_res=None):
    """THE reward policy. BINARY -- there is no partial credit.

    tests_passed is 1.0 only when every f2p test passes AND every p2p test still passes.
    A strict subset of f2p passing is not partial progress worth scoring: the reported tab
    is still broken, so it is 0.0.

    reward is the same value, zeroed when the rubric judge failed a criterion. A "pass"
    or "not graded" verdict never lowers the score -- the judge must never be able to
    penalise a run it could not grade.

    f2p_res / p2p_res are the per-identifier {name: 'pass'|'fail'|'skip'|'missing'} maps.
    They are flattened onto the same dict as f2p::<name> / p2p::<name> scalars so the
    reward stays a flat numeric map. Only 'pass' scores 1.0: a skipped or missing test
    did not pass, and recording it as anything else would hide a test that never ran.
    """
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
    for prefix, res in (('f2p', f2p_res), ('p2p', p2p_res)):
        for name, status in (res or {}).items():
            _canon['%s::%s' % (prefix, name)] = 1.0 if status == 'pass' else 0.0
    return _canon['reward']


@atexit.register
def _canon_flush():
    if not _canon:
        return
    try:
        os.makedirs(os.path.dirname(_CANON_JSON), exist_ok=True)
        with open(_CANON_JSON, 'w') as _h:
            json.dump(_canon, _h, indent=2)
        # reward.txt too: harbor prefers reward.json, but the sandbox teardown script and
        # the lighthouse UI read reward.txt. Writing both from one dict means they cannot
        # disagree.
        with open(_CANON_TXT, 'w') as _h:
            _h.write(str(_canon['reward']))
    except Exception as _exc:
        print('WARNING: could not write %s: %s' % (_CANON_JSON, _exc), file=sys.stderr)


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`.

    Anything that is not an explicit pass/fail -- including the empty string test.sh
    passes when no rubric shipped -- means "not graded", which must never penalise the
    run. This task is Mode B (no rubrics.json), so this always yields -1; the plumbing
    stays so the bundle matches the corpus-wide verifier contract.
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

    # Binary policy, applied in one place. canon_reward writes reward.json + reward.txt
    # at exit with the canonical seven keys.
    reward = canon_reward(len(f2p_pass), len(F2P),
                          len(p2p_pass), len(P2P),
                          rubric_verdict(sys.argv[1:]),
                          f2p_res, p2p_res)

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
