#!/usr/bin/env python3
"""
Verifier for ClanGenOfficial__clangen-5225-mm.

Reward policy — BINARY, there is no partial credit:
  1.0 — every f2p passes AND every p2p passes
  0.0 — anything else: a strict subset of f2p passes, a p2p regressed, or the
        test suite failed to produce a report

A `--rubric fail` verdict forces the reward to 0.0. A `pass` or an ungraded
verdict never lowers it — the judge must never penalise a run it could not grade.

Reads /logs/verifier/report.xml (JUnit XML written by pytest --junitxml).
Writes /logs/verifier/reward.json (the canonical seven keys, which Harbor
prefers) and /logs/verifier/reward.txt, both from one dict so they cannot
disagree.
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

CONF = json.load(open("/tests/config.json"))
F2P: list = CONF["f2p"]   # identifiers that must FLIP base→fail, fix→pass
P2P: list = CONF["p2p"]   # identifiers that must remain passing on fix

REPORT = "/logs/verifier/report.xml"

# --- canonical reward writer + --rubric gate (corpus-wide contract) -------------
# reward.json MUST be a FLAT map of numbers with exactly these seven keys. Harbor
# parses it as dict[str, float | int] and takes it in preference to reward.txt; a
# nested dict, list, string or None raises a validation error that aborts the trial
# BEFORE any reward is recorded — while reward.txt is still written in-container, so
# the run would look scored when nothing was stored.
# Registered with atexit so it writes LAST.

import atexit  # noqa: E402

_CANON_JSON = "/logs/verifier/reward.json"
_CANON_TXT = "/logs/verifier/reward.txt"
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric):
    """THE reward policy for the whole corpus. BINARY — there is no partial credit.

    tests_passed is 1.0 only when every f2p test passes AND every p2p test still
    passes. A strict subset of f2p passing is not partial progress worth scoring:
    the task is unsolved, so it is 0.0.

    reward is the same value, zeroed when the rubric judge failed a criterion. A
    "pass" or a "not graded" verdict never lowers the score.
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
    passes when judge.py wrote no verdict — means "not graded", which must never
    penalise the run.
    """
    if "--rubric" not in argv:
        return None
    i = argv.index("--rubric")
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ""
    return value if value in ("pass", "fail") else None


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
        # Build a slash-style key matching pytest's nodeid format, and also a
        # dot-style key matching JUnit classname::name — both are checked during
        # identifier matching so authors can use either style in config.json.
        key = f"{classname}::{name}".strip("::")
        failed = any(c.tag in ("failure", "error") for c in tc)
        skipped = any(c.tag == "skipped" for c in tc)
        results[key] = "skip" if skipped else ("fail" if failed else "pass")
    return results


def match_ident(ident: str, results: dict) -> str:
    """
    Find the verdict for a configured identifier in the results dict.
    Tries: exact match, then substring, then regex-escaped substring.
    Returns 'missing' when nothing matches.
    """
    if ident in results:
        return results[ident]
    # substring / flexible match
    for key, verdict in results.items():
        if ident in key:
            return verdict
    # regex-escaped fallback (handles dots, brackets in node IDs)
    for key, verdict in results.items():
        try:
            if re.search(re.escape(ident), key):
                return verdict
        except re.error:
            pass
    return "missing"


def main() -> None:
    results = load_results()

    # --- match configured identifiers against the report ---
    f2p_map = {ident: match_ident(ident, results) for ident in F2P}
    p2p_map = {ident: match_ident(ident, results) for ident in P2P}

    f2p_passing = [k for k, v in f2p_map.items() if v == "pass"]
    p2p_passing = [k for k, v in p2p_map.items() if v == "pass"]

    rubric = rubric_verdict(sys.argv[1:])

    # Binary policy; canon_reward writes reward.json + reward.txt at exit.
    reward = canon_reward(
        len(f2p_passing), len(F2P),
        len(p2p_passing), len(P2P),
        rubric,
    )

    print(
        json.dumps(
            {
                "reward": reward,
                "rubric": rubric or "not graded",
                "f2p": f2p_map,
                "p2p": p2p_map,
                "f2p_passing": f2p_passing,
                "p2p_passing": p2p_passing,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
