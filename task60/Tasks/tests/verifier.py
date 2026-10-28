#!/usr/bin/env python3
"""
Reward verifier for SR5-FoundryVTT__SR5-FoundryVTT-1746-mm.

Reads /logs/verifier/report.xml (JUnit XML written by test_modifiable_value_linked.mjs),
matches test results against config.json's f2p/p2p lists, and writes the scalar reward.

Reward policy (binary, no partial credit):
  1.0  - every f2p test passes AND every p2p test passes
  0.0  - anything else: a f2p still fails, a p2p regressed, or the suite failed to
         produce a report at all

A strict subset of f2p passing is 0.0, NOT a partial score: a half-fix must not read as
"solved" to pass@k, and the four count keys below already carry how close it got.

Output (canonical):
  /logs/verifier/reward.json - a FLAT map of numbers, exactly these seven keys:
        {reward, tests_passed, f2p_passed, f2p_total, p2p_passed, p2p_total, rubric_passed}
      harbor parses this as VerifierResult.rewards: dict[str, float | int] and prefers it
      over reward.txt. A nested dict, list, string or None raises a pydantic
      ValidationError that aborts the run BEFORE any reward is recorded -- so per-test
      detail goes to stdout (below), never into this file.
      rubric_passed: 1 pass / 0 fail / -1 not graded. This task ships no rubrics.json
      (Mode B), so it is always -1 and the reward is decided by the tests alone.
  /logs/verifier/reward.txt  - the bare scalar ("1.0" or "0.0"), written from the same
                                dict so the two files cannot disagree.

The --rubric gate is inert on this task (no rubric ships, so test.sh passes nothing), but
the plumbing is present to keep the verifier shape uniform across the corpus. It can only
ever withhold a 1.0, never raise a score.
"""
import atexit
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

CONF   = json.load(open('/tests/config.json'))
F2P    = CONF['f2p']
P2P    = CONF['p2p']
REPORT = '/logs/verifier/report.xml'


# --- canonical reward writer + --rubric gate --------------------------------------
# Proven against a real harbor run and verified against all five outcome cases (perfect
# run, failed rubric, ungraded rubric, partial f2p, p2p regression). Registered with
# atexit so it writes LAST and is the single source of truth for both reward files.

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
    when judge.py wrote no verdict -- means "not graded", which must never penalise the run.
    """
    if "--rubric" not in argv:
        return None
    i = argv.index("--rubric")
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ""
    return value if value in ("pass", "fail") else None


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

    f2p_pass = [k for k, v in f2p_res.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p_res.items() if v == 'pass']

    # Unchanged policy: every f2p must pass and every p2p must pass. A p2p reported as
    # 'skip' or 'missing' does NOT count as passing, exactly as before.
    reward = canon_reward(len(f2p_pass), len(F2P),
                          len(p2p_pass), len(P2P),
                          rubric_verdict(sys.argv[1:]))

    # Per-test detail rides along as extra FLAT SCALAR keys on the same dict -- never as a
    # nested map, which is what harbor cannot parse. The QC gate's f2p-inertness check reads
    # these out of the nop run: an f2p test that scores 1.0 with no fix applied is inert and
    # proves nothing, and without per-test keys that cannot be detected at all.
    for label, res in (('f2p', f2p_res), ('p2p', p2p_res)):
        for ident, status in res.items():
            _canon[f'{label}::{ident}'] = 1.0 if status == 'pass' else 0.0
            print(f'[verifier] {label} {status:<7} {ident}')
    print(json.dumps(_canon, indent=2))
    return reward


if __name__ == '__main__':
    main()
