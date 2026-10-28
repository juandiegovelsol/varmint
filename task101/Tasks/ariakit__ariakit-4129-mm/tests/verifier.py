#!/usr/bin/env python3
"""Turn the JUnit report into the task reward.

The reward is binary: 1.0 only when every configured f2p and p2p test is found exactly once in the
report and passed; otherwise 0.0. f2p_passed / f2p_total and p2p_passed / p2p_total record how close
a run came. The verifier reads test outcomes only, never the candidate's source.
"""
import atexit
import json
import os
import sys
import xml.etree.ElementTree as ET

import json as _cj, os as _co, sys as _cs

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


CONF = json.load(open("/tests/config.json"))
F2P, P2P = CONF["f2p"], CONF["p2p"]
REPORT = os.environ.get("JUNIT_OUT", "/logs/verifier/junit.xml")
OUT_DIR = "/logs/verifier"


def load_junit(path):
    """Every reported test, keyed by "classname name" and by name; a key seen twice with different
    outcomes counts as failed."""
    results = {}
    if not os.path.exists(path):
        return results
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return results
    for tc in root.iter("testcase"):
        tags = {c.tag for c in tc}
        outcome = "skip" if "skipped" in tags else ("fail" if tags & {"failure", "error"} else "pass")
        full = f"{tc.get('classname', '')} {tc.get('name', '')}".strip()
        for key in {full, tc.get("name", "")}:
            if key in results and results[key] != outcome:
                results[key] = "fail"
            else:
                results[key] = outcome
    return results


def junit_key(test_id):
    """A pytest node id (tests/test_x.py::TestA::test_b[png]) as the JUnit report names it
    ("tests.test_x.TestA test_b[png]"); other ids unchanged."""
    if "::" not in test_id:
        return test_id
    parts = test_id.split("::")
    mod = parts[0][:-3] if parts[0].endswith(".py") else parts[0]
    return f"{'.'.join([mod.replace('/', '.')] + parts[1:-1])} {parts[-1]}"


def resolve(test_id, results):
    """The outcome of one configured test: an exact key match first (the id as written, or a
    pytest node id in JUnit form), else the single reported test whose key ends with it. Missing
    or ambiguous counts as not passed."""
    keys = [test_id, junit_key(test_id)]
    if " > " in test_id:  # "describe > test": jest-junit joins with a space, playwright with " › "
        head, rest = test_id.split(" > ", 1)
        keys += [test_id.replace(" > ", " "), test_id.replace(" > ", " › "), head + " " + rest.replace(" > ", " › ")]
    keys += [k.replace('"', "") for k in keys]  # jest-junit drops quotation marks from names
    keys = list(dict.fromkeys(keys))
    for key in keys:
        if key in results:
            return results[key]
    for key in keys:
        hits = {k: v for k, v in results.items() if k.endswith(key)}
        if hits and len(set(hits.values())) == 1:
            return next(iter(hits.values()))
        if hits:
            return "ambiguous"
    # "file > test" with a describe level left out: a test in that file whose name ends the same
    parts = test_id.split(" > ")
    if len(parts) >= 2 and ("." in parts[0] or "/" in parts[0]):
        hits = {k: v for k, v in results.items() if k.startswith(parts[0] + " ") and k.endswith(parts[-1])}
        if hits and len(set(hits.values())) == 1:
            return next(iter(hits.values()))
        if hits:
            return "ambiguous"
    return "missing"


def main():
    results = load_junit(REPORT)
    detail = {}
    f2p_ok = 0
    for t in F2P:
        r = resolve(t, results)
        detail[f"f2p::{t}"] = r
        f2p_ok += r == "pass"
    p2p_ok = 0
    for t in P2P:
        r = resolve(t, results)
        detail[f"p2p::{t}"] = r
        p2p_ok += r == "pass"
    canon_reward(f2p_ok, len(F2P), p2p_ok, len(P2P), rubric_verdict(sys.argv[1:]))
    reward = dict(_canon)
    os.makedirs(OUT_DIR, exist_ok=True)
    json.dump(detail, open(f"{OUT_DIR}/reward_detail.json", "w"), indent=2)
    print(json.dumps(reward))


if __name__ == "__main__":
    main()
