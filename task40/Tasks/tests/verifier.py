#!/usr/bin/env python3
"""
Verifier for ClanGenOfficial__clangen-4837-mm.

Runs from the JUnit XML produced by pytest and writes both Harbor's reward.txt
and the canonical reward.json used by QC.
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

CONF = json.load(open("/tests/config.json"))
F2P: list = CONF["f2p"]
P2P: list = CONF["p2p"]

REPORT = "/logs/verifier/report.xml"
REWARD_TXT = "/logs/verifier/reward.txt"
REWARD_JSON = "/logs/verifier/reward.json"


def load_results() -> dict:
    """Return {test_identifier: 'pass'|'fail'|'skip'} parsed from JUnit XML."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError as exc:
        print(f"[verifier] WARNING: could not parse {REPORT}: {exc}", file=sys.stderr)
        return results

    for tc in tree.iter("testcase"):
        classname = tc.get("classname", "")
        name = tc.get("name", "")
        key = f"{classname}::{name}".strip("::")
        failed = any(c.tag in ("failure", "error") for c in tc)
        skipped = any(c.tag == "skipped" for c in tc)
        results[key] = "skip" if skipped else ("fail" if failed else "pass")
    return results


def match_ident(ident: str, results: dict) -> str:
    """Find the configured identifier in the JUnit results."""
    if ident in results:
        return results[ident]
    for key, verdict in results.items():
        if ident in key or key in ident:
            return verdict
    for key, verdict in results.items():
        try:
            if re.search(re.escape(ident), key):
                return verdict
        except re.error:
            pass
    return "missing"


def rubric_value(raw: str | None) -> int:
    """Return 1 pass, 0 fail, or -1 not graded."""
    if raw is None or raw.strip() == "":
        return -1
    verdict = raw.strip().lower()
    if verdict == "pass":
        return 1
    if verdict == "fail":
        return 0
    return -1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rubric", default="", help="Optional rubric verdict: pass/fail")
    args = parser.parse_args()

    results = load_results()

    f2p_map = {ident: match_ident(ident, results) for ident in F2P}
    p2p_map = {ident: match_ident(ident, results) for ident in P2P}

    f2p_passed = sum(1 for v in f2p_map.values() if v == "pass")
    p2p_passed = sum(1 for v in p2p_map.values() if v == "pass")
    f2p_total = len(F2P)
    p2p_total = len(P2P)

    all_f2p_pass = f2p_total > 0 and f2p_passed == f2p_total
    all_p2p_pass = p2p_passed == p2p_total
    tests_passed = 1.0 if all_f2p_pass and all_p2p_pass else 0.0

    rubric_passed = rubric_value(args.rubric)
    rubric_allows_reward = rubric_passed in (-1, 1)
    reward = 1.0 if tests_passed == 1.0 and rubric_allows_reward else 0.0

    payload = {
        "reward": reward,
        "tests_passed": tests_passed,
        "f2p_passed": f2p_passed,
        "f2p_total": f2p_total,
        "p2p_passed": p2p_passed,
        "p2p_total": p2p_total,
        "rubric_passed": rubric_passed,
    }

    os.makedirs(os.path.dirname(REWARD_TXT), exist_ok=True)
    with open(REWARD_TXT, "w") as fh:
        fh.write(str(reward))
    with open(REWARD_JSON, "w") as fh:
        json.dump(payload, fh)

    print(
        json.dumps(
            {
                **payload,
                "f2p": f2p_map,
                "p2p": p2p_map,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
