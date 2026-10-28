#!/usr/bin/env python3
"""Report -> reward for CesiumGS__cesium-12521-mm. Behavioral only: reads the JUnit report the
paired test.sh produced (Karma/Jasmine, real headless-Chromium DOM -- no WebGL needed) and the
f2p/p2p identifiers from config.json. NEVER inspects source -- only test outcomes.

Reward policy is BINARY, not partial credit: tests_passed is 1.0 only when every f2p test
passes AND every p2p test still passes; a strict subset of f2p passing is 0.0, not a fraction.
Partial credit would let a half-fix read as "solved" to pass@k, and nothing is lost by
collapsing it because f2p_passed/f2p_total and p2p_passed/p2p_total carry the detail. reward is
the same value, zeroed only when the rubric judge explicitly failed a criterion -- a "pass" or
"not graded" (-1) verdict never lowers the score, since the judge must never penalise a run it
could not grade. This task ships no rubric layer, so rubric is always "not graded" (-1) and
reward == tests_passed unconditionally.
"""
import argparse
import json
import os
import xml.etree.ElementTree as ET

CONF = json.load(open("/tests/config.json"))
F2P = CONF["f2p"]
P2P = CONF["p2p"]
REPORT = "/logs/verifier/karma-junit.xml"  # keep in sync with test.sh / run_karma.mjs
REWARD_TXT = "/logs/verifier/reward.txt"
REWARD_JSON = "/logs/verifier/reward.json"


def load_junit():
    """Return {test_identifier: 'pass'|'fail'|'skip'} parsed from the karma-junit report.

    karma-junit-reporter (2.0.1, pinned in this task's Dockerfile) can crash MID-WRITE for a
    SPECIFIC <testcase>'s <failure> element when that failure's own message contains a
    control character illegal in XML 1.0 -- confirmed empirically while authoring this task: a
    genuine GLSL shader-compile RuntimeError, whose driver-provided "Compile log:" text tripped
    node_modules/xmlbuilder's XMLStringifier.assertLegalChar. The crash is caught PER TESTCASE
    (unlike the whole-run captureConsole crash banked for this repo's other tasks -- the run
    continues to the next spec), but it leaves that one <testcase> with NO <failure> child at
    all, even though the enclosing <testsuite failures="N"> attribute still counts it correctly.
    A naive per-testcase-only scan then silently reports that spec as a PASS -- verified directly
    against this task's own ab2 anti-bandaid probe (a deliberately broken/uncompilable shader):
    all 6 testcases showed zero <failure> children while the suite attribute said failures="6".
    Guard: if the suite-level failure+error count exceeds what is actually visible per
    testcase, we cannot tell WHICH testcases lost their marker, so every testcase in that
    (corrupted) report is treated as a failure rather than risk crediting a spec that never
    actually passed.
    """
    results = {}
    if not os.path.exists(REPORT):
        return results
    tree = ET.parse(REPORT)
    root = tree.getroot()
    declared_bad = 0
    for suite in root.iter("testsuite"):
        for attr in ("failures", "errors"):
            try:
                declared_bad += int(suite.get(attr, 0) or 0)
            except (TypeError, ValueError):
                pass
    testcases = list(tree.iter("testcase"))
    observed_bad = sum(1 for tc in testcases if any(c.tag in ("failure", "error") for c in tc))
    corrupted = declared_bad > observed_bad
    for tc in testcases:
        name = f"{tc.get('classname', '')} {tc.get('name', '')}".strip()
        if any(c.tag == "skipped" for c in tc):
            results[name] = "skip"
        elif any(c.tag in ("failure", "error") for c in tc):
            results[name] = "fail"
        elif corrupted:
            results[name] = "fail"
        else:
            results[name] = "pass"
    return results


def matched(idents, results):
    """Match each configured identifier against reported test names (substring tolerant)."""
    out = {}
    for ident in idents:
        hit = next((v for k, v in results.items() if ident in k), None)
        out[ident] = hit or "missing"
    return out


def rubric_verdict(raw):
    """"pass"/"fail" (case-insensitive) -> that verdict; anything else -> None ("not graded").

    This task ships no rubric layer (tests/rubrics.json, tests/judge.py), so test.sh always
    passes an empty string here and this always resolves to None. Kept as an explicit gate,
    not dead code, in case a rubric is added back later.
    """
    value = (raw or "").strip().lower()
    return value if value in ("pass", "fail") else None


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric):
    """THE reward policy: binary, per the module docstring above."""
    solved = f2p_total > 0 and f2p_passed == f2p_total and p2p_passed == p2p_total
    tests_passed = 1.0 if solved else 0.0
    reward = 0.0 if rubric == "fail" else tests_passed
    return reward, tests_passed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rubric", default="", help='"pass" | "fail" | "" (not graded)')
    args = ap.parse_args()
    rubric = rubric_verdict(args.rubric)

    results = load_junit()
    f2p = matched(F2P, results)
    p2p = matched(P2P, results)
    f2p_passed = sum(1 for v in f2p.values() if v == "pass")
    p2p_passed = sum(1 for v in p2p.values() if v == "pass")

    reward, tests_passed = canon_reward(f2p_passed, len(F2P), p2p_passed, len(P2P), rubric)

    detail = {
        "reward": reward,
        "tests_passed": tests_passed,
        "f2p_passed": f2p_passed,
        "f2p_total": len(F2P),
        "p2p_passed": p2p_passed,
        "p2p_total": len(P2P),
        "rubric_passed": {"pass": 1, "fail": 0}.get(rubric, -1),
    }

    os.makedirs(os.path.dirname(REWARD_JSON), exist_ok=True)
    with open(REWARD_JSON, "w") as fh:
        json.dump(detail, fh, indent=2)
    with open(REWARD_TXT, "w") as fh:
        fh.write(str(reward))
    print(json.dumps({**detail, "f2p": f2p, "p2p": p2p}))


if __name__ == "__main__":
    main()
