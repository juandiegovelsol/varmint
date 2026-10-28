#!/usr/bin/env python3
"""
Reward verifier for tldraw__tldraw-8821-mm
"Following indicator border is hidden behind menus and panels" (PR #9210 / issue #8821)

Parses the JUnit XML produced by vitest and computes a BINARY reward:
  1.0 — all f2p pass AND all p2p pass
  0.0 — anything else: a strict subset of f2p passing, a p2p regression,
        or a suite that failed to run. There is no partial credit; the
        f2p_passed / p2p_passed counts carry how close a run got.

f2p (fail-to-pass): tests that FAIL on base, PASS after fix.
    These directly verify that the FollowingIndicator slot renders inside the UI layout's own
    stacking context (.tlui-layout), after the panel groups, instead of inside the canvas's
    lower-stacking-context overlay (.tl-canvas__in-front) where panels always painted over it -
    including the focus-mode branch, which swaps out the panel chrome but must not swap out the
    follow border along with it.
p2p (pass-to-pass): tests that PASS on both base and fix.
    These guard against regressions to the sibling in-front-of-canvas slots (rich text/image/video
    toolbars, cursor chat bubble) that the fix's diff also touches (by removing FollowingIndicator
    from the same destructure), and against the fix accidentally rendering the indicator when
    nobody is being followed, or rendering it more than once.

BEHAVIORAL CONTRACT: reward is derived entirely from the test report.
This verifier NEVER inspects source code for the fix string or any other token.
"""
import json, os, re, sys, xml.etree.ElementTree as ET

CONF       = json.load(open('/tests/config.json'))
F2P        = CONF['f2p']
P2P        = CONF['p2p']
REPORT     = '/logs/verifier/report.xml'


# ── Canonical reward writer + --rubric gate ──────────────────────────────────
# reward.json MUST be a FLAT map of numbers with exactly these seven keys: harbor parses
# it as VerifierResult.rewards and PREFERS it over reward.txt. A nested dict, list or
# string raises a ValidationError that aborts the trial before any reward is recorded —
# while reward.txt still gets written in-container, so the run looks scored when harbor
# stored nothing. Registered with atexit so it writes last.
import atexit

_CANON_JSON = '/logs/verifier/reward.json'
_CANON_TXT  = '/logs/verifier/reward.txt'
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric):
    """THE reward policy. BINARY — there is no partial credit.

    tests_passed is 1.0 only when every f2p test passes AND every p2p test still passes.
    A strict subset of f2p passing is not partial progress worth scoring: the task is
    unsolved, so it is 0.0. A "pass" or "not graded" rubric verdict never lowers the score.
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
    return _canon['reward']


@atexit.register
def _canon_flush():
    if not _canon:
        return
    try:
        os.makedirs(os.path.dirname(_CANON_JSON), exist_ok=True)
        with open(_CANON_JSON, 'w') as fh:
            json.dump(_canon, fh, indent=2)
        # reward.txt too: harbor prefers reward.json, but the sandbox teardown script and
        # the lighthouse UI read reward.txt. One dict writes both, so they cannot disagree.
        with open(_CANON_TXT, 'w') as fh:
            fh.write(str(_canon['reward']))
    except Exception as exc:
        print(f"WARNING: could not write {_CANON_JSON}: {exc}", file=sys.stderr)


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`.

    Anything that is not an explicit pass/fail — including the empty string test.sh passes
    when no rubric shipped — means "not graded", which must never penalise the run.
    """
    if '--rubric' not in argv:
        return None
    i = argv.index('--rubric')
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ''
    return value if value in ('pass', 'fail') else None



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


def main():
    r    = load_results()
    f2p  = matched(F2P, r)
    p2p  = matched(P2P, r)

    f2p_pass = [k for k, v in f2p.items() if v == 'pass']
    p2p_pass = [k for k, v in p2p.items() if v == 'pass']

    # Reward policy: BINARY — 1.0 only if every f2p flipped AND every p2p still passes.
    # Anything less is 0.0; the counts below carry how close the run got.
    reward = canon_reward(len(f2p_pass), len(F2P),
                          len(p2p_pass), len(P2P),
                          rubric_verdict(sys.argv[1:]))

    print(json.dumps({
        'reward': reward,
        'f2p':    f2p,
        'p2p':    p2p,
        'f2p_pass_count': len(f2p_pass),
        'f2p_total':      len(F2P),
        'p2p_pass_count': len(p2p_pass),
        'p2p_total':      len(P2P),
    }, indent=2))


if __name__ == '__main__':
    main()
