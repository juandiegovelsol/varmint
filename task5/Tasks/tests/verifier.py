#!/usr/bin/env python3
"""
Verifier for ivark__antimatterdimensionssourcecode-2808-mm
Parses the jest --json report and computes the SWE-bench-style reward.

Jest JSON schema (relevant for individual test access):
  {
    "testResults": [            ← array of test SUITES (one per .spec.js file)
      {
        "assertionResults": [   ← individual test cases (NOT "testResults"!)
          { "fullName": "...", "status": "passed" | "failed" | "pending" }
        ],
        "status": "passed" | "failed"
      }
    ]
  }

Reward policy:
  1.0 — every f2p test passes AND every p2p test passes (p2p vacuously true if [])
  0.5 — f2p partially passes OR f2p all pass but a p2p regressed
  0.0 — no f2p test passes, or report is missing / unparseable

CRITICAL: this script MUST write the reward to /logs/verifier/reward.txt.
Harbor reads that file; a print-only script yields RewardFileNotFoundError.
"""
import json
import os
import re
import sys

CONF_PATH = "/tests/config.json"
REPORT_PATH = "/logs/verifier/jest-results.json"
REWARD_PATH = "/logs/verifier/reward.txt"


def load_config():
    with open(CONF_PATH) as fh:
        return json.load(fh)


def load_results():
    """
    Parse jest's --json output and return a flat dict:
        { test_full_name: "pass" | "fail" | "skip" }

    Jest JSON schema (assertionResults, not testResults, for individual tests):
      {
        "testResults": [                     <- suites
          {
            "assertionResults": [            <- individual tests
              { "fullName": "...", "status": "passed"|"failed"|"pending" }
            ]
          }
        ]
      }
    """
    results = {}
    if not os.path.exists(REPORT_PATH):
        print(f"[verifier] WARNING: report not found at {REPORT_PATH}", file=sys.stderr)
        return results

    try:
        data = json.load(open(REPORT_PATH))
    except json.JSONDecodeError as exc:
        print(f"[verifier] ERROR: cannot parse report JSON: {exc}", file=sys.stderr)
        return results

    for suite in data.get("testResults", []):
        # Jest uses "assertionResults" for individual test cases within a suite.
        for tc in suite.get("assertionResults", []):
            name = tc.get("fullName", tc.get("title", ""))
            status = tc.get("status", "unknown")
            if status == "passed":
                results[name] = "pass"
            elif status == "pending":
                results[name] = "skip"
            else:
                results[name] = "fail"

    return results


def match_ident(ident, results):
    """
    Match a configured test identifier against reported test names.
    Tries exact match first, then substring, then regex.
    Returns the status string or "missing".
    """
    if ident in results:
        return results[ident]
    hit = next((v for k, v in results.items() if ident in k), None)
    if hit is not None:
        return hit
    try:
        hit = next((v for k, v in results.items() if re.search(re.escape(ident), k)), None)
    except re.error:
        hit = None
    return hit if hit is not None else "missing"


def main():
    conf = load_config()
    f2p_ids = conf.get("f2p", [])
    p2p_ids = conf.get("p2p", [])

    results = load_results()

    f2p_map = {ident: match_ident(ident, results) for ident in f2p_ids}
    p2p_map = {ident: match_ident(ident, results) for ident in p2p_ids}

    f2p_passed = [k for k, v in f2p_map.items() if v == "pass"]
    p2p_passed = [k for k, v in p2p_map.items() if v == "pass"]

    all_f2p = len(f2p_passed) == len(f2p_ids) and len(f2p_ids) > 0
    all_p2p = len(p2p_passed) == len(p2p_ids)  # vacuously true if p2p is []

    if all_f2p and all_p2p:
        reward = 1.0
    elif f2p_passed and (not all_p2p or not all_f2p):
        reward = 0.5
    else:
        reward = 0.0

    os.makedirs(os.path.dirname(REWARD_PATH), exist_ok=True)
    with open(REWARD_PATH, "w") as fh:
        fh.write(str(reward))

    report = {
        "reward": reward,
        "f2p": f2p_map,
        "p2p": p2p_map,
        "f2p_passed_count": len(f2p_passed),
        "f2p_total": len(f2p_ids),
        "p2p_passed_count": len(p2p_passed),
        "p2p_total": len(p2p_ids),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
