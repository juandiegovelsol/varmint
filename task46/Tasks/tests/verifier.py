#!/usr/bin/env python3
"""Behavioral verifier for wxWidgets__wxWidgets-23046-mm.

Parses Catch2's native XML report format (NOT junit) for each f2p/p2p SECTION. Each identifier
was run as its own standalone `test_gui ... -c "<name>" --reporter xml` invocation (see test.sh
for why: the combined TEST_CASE run terminates early under this Catch2 build and silently misses
later SECTIONs), so this reads one report file per identifier and never inspects source -- only
actual test outcomes decide the score.

Reward policy is BINARY (see canon_reward): 1.0 only when every f2p test passes AND every p2p
test still passes; any strict subset of f2p passing is 0.0, not partial credit -- the four
count keys (f2p_passed/f2p_total/p2p_passed/p2p_total) already carry how close it got.
"""
import argparse
import atexit
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

REPORT_DIR = "/logs/verifier/reports"
CONFIG_PATH = "/tests/config.json"
REWARD_JSON_PATH = "/logs/verifier/reward_detail.json"

# Canonical reward writer + --rubric gate (verifier_reward_block.py). Registered with atexit
# so it writes LAST, after -- and in preference to -- anything above it.
_CANON_JSON = "/logs/verifier/reward.json"
_CANON_TXT = "/logs/verifier/reward.txt"
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric,
                  f2p_detail=None, p2p_detail=None):
    """THE reward policy for the whole corpus. BINARY -- there is no partial credit.

    tests_passed is 1.0 only when every f2p test passes AND every p2p test still passes.
    reward is the same value, zeroed when the rubric judge failed a criterion. A "pass" or a
    "not graded" verdict never lowers the score -- the judge must never be able to penalise a
    run it could not grade.

    f2p_detail/p2p_detail (name -> bool passed) ride along as extra flat `f2p::<name>` /
    `p2p::<name>` = 1.0/0.0 scalar keys, so a nop run's per-test outcomes are visible in
    reward.json itself -- never nested -- letting an inert f2p test be detected.
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
    for name, ok in (f2p_detail or {}).items():
        _canon["f2p::%s" % name] = 1.0 if ok else 0.0
    for name, ok in (p2p_detail or {}).items():
        _canon["p2p::%s" % name] = 1.0 if ok else 0.0
    return _canon["reward"]


@atexit.register
def _canon_flush():
    if not _canon:
        return
    try:
        os.makedirs(os.path.dirname(_CANON_JSON), exist_ok=True)
        with open(_CANON_JSON, "w") as fh:
            json.dump(_canon, fh, indent=2)
        with open(_CANON_TXT, "w") as fh:
            fh.write(str(_canon["reward"]))
    except Exception as exc:
        print("WARNING: could not write %s: %s" % (_CANON_JSON, exc), file=sys.stderr)


def sanitize(name):
    return re.sub(r"[^A-Za-z0-9]", "_", name)


def section_passed(path):
    """Return (passed: bool, reason: str|None) for one standalone `-c "<name>"` report."""
    if not os.path.isfile(path):
        return False, "report missing"
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return False, "unparsable report: %s" % exc
    # A standalone `-c "<name>"` invocation runs exactly one TestCase; its own
    # <OverallResult success="true|false"/> is the authoritative verdict for that SECTION.
    for tc in root.iter("TestCase"):
        ov = tc.find("OverallResult")
        if ov is not None:
            ok = ov.get("success") == "true"
            return ok, None if ok else "TestCase OverallResult success=false"
    # Fallback: top-level assertion tally.
    ov = root.find("OverallResults")
    if ov is not None:
        failures = ov.get("failures", "1")
        ok = failures == "0"
        return ok, None if ok else ("failures=%s" % failures)
    return False, "no OverallResult(s) element found"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rubric", default="", help='judge verdict: "pass", "fail", or empty/unset')
    args = ap.parse_args()

    cfg = json.load(open(CONFIG_PATH))
    f2p = cfg.get("f2p", [])
    p2p = cfg.get("p2p", [])

    detail = {}
    for name in f2p + p2p:
        path = os.path.join(REPORT_DIR, sanitize(name) + ".xml")
        ok, reason = section_passed(path)
        detail[name] = {"passed": ok, "reason": reason, "report": path}

    f2p_results = [detail[n]["passed"] for n in f2p]
    p2p_results = [detail[n]["passed"] for n in p2p]
    f2p_passed = sum(1 for ok in f2p_results if ok)
    p2p_passed = sum(1 for ok in p2p_results if ok)

    rubric = (args.rubric or "").strip().lower()
    if rubric not in ("pass", "fail"):
        rubric = None
    reward = canon_reward(
        f2p_passed, len(f2p), p2p_passed, len(p2p), rubric,
        f2p_detail={n: detail[n]["passed"] for n in f2p},
        p2p_detail={n: detail[n]["passed"] for n in p2p},
    )

    # Per-test detail, informational only -- reward.json (canon_reward's output) is the
    # canonical artifact harbor reads.
    with open(REWARD_JSON_PATH, "w") as fh:
        json.dump({
            "f2p": {n: detail[n] for n in f2p},
            "p2p": {n: detail[n] for n in p2p},
            "rubric_verdict": rubric,
        }, fh, indent=2)

    print("f2p: %s" % {n: detail[n]["passed"] for n in f2p})
    print("p2p: %s" % {n: detail[n]["passed"] for n in p2p})
    print("rubric_verdict=%r" % rubric)
    print("reward=%s" % reward)


if __name__ == "__main__":
    main()
