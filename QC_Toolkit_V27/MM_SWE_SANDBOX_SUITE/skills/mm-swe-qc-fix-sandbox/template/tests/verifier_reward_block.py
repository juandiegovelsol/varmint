# Canonical reward writer + --rubric gate. Proven against a real harbor run, and verified
# against all five outcome cases (perfect run, failed rubric, ungraded rubric, partial f2p,
# p2p regression).
#
# verifier.py carries TASK-SPECIFIC logic, so this is a PROPOSAL to merge by hand.
#
# CRITICAL - reward.json MUST be a FLAT map of numbers, and exactly these seven keys:
#     {reward, tests_passed, f2p_passed, f2p_total, p2p_passed, p2p_total, rubric_passed}
# harbor parses it as VerifierResult.rewards: dict[str, float | int] and takes it in
# PREFERENCE to reward.txt. A nested dict, list, string or None raises a pydantic
# ValidationError that aborts the trial BEFORE any reward is recorded - while reward.txt
# still gets written inside the container, so the run looks scored when harbor in fact
# stored nothing.
#   rubric_passed: 1 pass / 0 fail / -1 not graded (no rubric shipped, or judge unavailable).
#
# THE POLICY IS BINARY. tests_passed is 1.0 only when every f2p passes AND every p2p still
# passes; a strict subset of f2p passing is 0.0, NOT 0.5. Partial credit would let a half-fix
# read as "solved" to pass@k, and nothing is lost by collapsing it because the four count keys
# carry the detail. An earlier version of this template documented reward.txt as a float in
# {0.0, 0.5, 1.0} with a failed rubric capping at 0.5; both were wrong.
#
# Registered with atexit so it writes LAST and overrides whatever a pre-existing local reward
# block already wrote - which is what makes this a safe patch onto a task being repaired
# rather than a rewrite of its scoring.

import atexit, json as _cj, os as _co, sys as _cs

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
        _co.makedirs(_co.path.dirname(_CANON_JSON), exist_ok=True)
        with open(_CANON_JSON, "w") as _h:
            _cj.dump(_canon, _h, indent=2)
        # reward.txt too: harbor prefers reward.json, but the sandbox teardown script and the
        # lighthouse UI read reward.txt. Writing both from one dict means they cannot disagree.
        with open(_CANON_TXT, "w") as _h:
            _h.write(str(_canon["reward"]))
    except Exception as _exc:
        print("WARNING: could not write %s: %s" % (_CANON_JSON, _exc), file=_cs.stderr)


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


# --- call site, once, wherever the reward is decided -----------------------------
#     canon_reward(len(f2p_pass), len(F2P),
#                  len(P2P) - len(p2p_fail), len(P2P),
#                  rubric_verdict(sys.argv[1:]))
#
# Per-test detail, if wanted, rides along as extra `f2p::<name>` / `p2p::<name>` = 1.0/0.0
# SCALAR keys added to the same flat dict -- never as a nested map.
