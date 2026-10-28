#!/usr/bin/env python3
"""
Verifier for IvarK__AntimatterDimensionsSourceCode-3020-mm.

Reads the JUnit XML report produced by vitest and computes a reward:
  1.0 — all f2p tests pass AND all p2p tests pass
  0.0 — anything else: a strict subset of f2p passing, a p2p regression,
        or the report is missing/unreadable

The policy is BINARY — there is no partial credit. A half-finished fix is
unsolved, so it scores 0.0; the per-test counts in reward.json carry how
close it got.

The report format is vitest's JUnit XML reporter:
  classname = test-file path  (e.g. src/__tests__/tickspeed-visibility.test.js)
  name      = describe > test name

IMPORTANT: this verifier NEVER checks source code for the fix — the reward
is derived entirely from test execution results.
"""

import atexit
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

CONF = json.load(open("/tests/config.json"))
F2P = CONF["f2p"]   # list of f2p test identifiers (substring-matched)
P2P = CONF["p2p"]   # list of p2p test identifiers (substring-matched)
REPORT = "/logs/verifier/report.xml"

# --- canonical reward writer + --rubric gate ------------------------------------
# harbor parses reward.json as VerifierResult.rewards: dict[str, float | int] and
# takes it in PREFERENCE to reward.txt, so it must stay a FLAT map of numbers with
# exactly these seven keys. Registered with atexit so it writes last.
_CANON_JSON = "/logs/verifier/reward.json"
_CANON_TXT = "/logs/verifier/reward.txt"
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric):
    """THE reward policy for the whole corpus. BINARY — there is no partial credit.

    tests_passed is 1.0 only when every f2p test passes AND every p2p test still
    passes. A strict subset of f2p passing means the task is unsolved, so it is 0.0.

    reward is the same value, zeroed when the rubric judge failed a criterion. A
    "pass" or "not graded" verdict never lowers the score.
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
        # reward.txt too: harbor prefers reward.json, but the sandbox teardown script
        # and the lighthouse UI read reward.txt. One dict means they cannot disagree.
        with open(_CANON_TXT, "w") as _h:
            _h.write(str(_canon["reward"]))
    except Exception as _exc:
        print("WARNING: could not write %s: %s" % (_CANON_JSON, _exc), file=sys.stderr)


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`.

    Anything that is not an explicit pass/fail — including the empty string test.sh
    passes when no verdict was written — means "not graded", which must never
    penalise the run.
    """
    if "--rubric" not in argv:
        return None
    i = argv.index("--rubric")
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ""
    return value if value in ("pass", "fail") else None


def load_results():
    """Return {test_identifier: 'pass'|'fail'|'skip'} from JUnit XML.

    Vitest's JUnit reporter puts:
      classname = the test-file path
      name      = "describe > it name"
    We construct the key as "{classname}::{name}".
    """
    results = {}
    if not os.path.exists(REPORT):
        print(f"[verifier] WARNING: report not found at {REPORT}", file=sys.stderr)
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError as exc:
        print(f"[verifier] WARNING: XML parse error: {exc}", file=sys.stderr)
        return results

    for tc in tree.iter("testcase"):
        classname = tc.get("classname", "")
        name = tc.get("name", "")
        key = f"{classname}::{name}".strip("::")
        failed = any(c.tag in ("failure", "error") for c in tc)
        skipped = any(c.tag == "skipped" for c in tc)
        results[key] = "skip" if skipped else ("fail" if failed else "pass")

    return results


def matched(idents, results):
    """Match each configured identifier against reported test names.

    Accepts substring match or regex match so the config value stays
    short without fragile path duplication.
    """
    out = {}
    for ident in idents:
        hit = None
        for k, v in results.items():
            if ident in k:
                hit = v
                break
        if hit is None:
            # Try regex as fallback
            try:
                pattern = re.compile(re.escape(ident))
                for k, v in results.items():
                    if pattern.search(k):
                        hit = v
                        break
            except re.error:
                pass
        out[ident] = hit or "missing"
    return out


def main():
    r = load_results()
    f2p_res = matched(F2P, r)
    p2p_res = matched(P2P, r)

    f2p_pass = [k for k, v in f2p_res.items() if v == "pass"]
    p2p_pass = [k for k, v in p2p_res.items() if v == "pass"]

    reward = canon_reward(len(f2p_pass), len(F2P),
                          len(p2p_pass), len(P2P),
                          rubric_verdict(sys.argv[1:]))

    print(json.dumps({
        "reward": reward,
        "f2p": f2p_res,
        "p2p": p2p_res,
        "f2p_pass_count": len(f2p_pass),
        "f2p_total": len(F2P),
        "p2p_pass_count": len(p2p_pass),
        "p2p_total": len(P2P),
    }))


if __name__ == "__main__":
    main()
