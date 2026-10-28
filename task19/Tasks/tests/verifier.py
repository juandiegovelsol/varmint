#!/usr/bin/env python3
"""
Behavioral verifier for recharts__recharts-6814-mm.

Reward policy (binary, no partial credit):
  1.0 - every f2p passes AND every p2p passes.
  0.0 - otherwise, or the suite failed to run.
"""
import atexit, json, os, re, sys, xml.etree.ElementTree as ET

CONF    = json.load(open("/tests/config.json"))
F2P     = CONF["f2p"]
P2P     = CONF["p2p"]
REPORT  = "/logs/verifier/report.xml"
REWARD  = "/logs/verifier/reward.txt"

_CANON_JSON = "/logs/verifier/reward.json"
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric):
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
        with open(_CANON_JSON, "w") as h:
            json.dump(_canon, h, indent=2)
        with open(REWARD, "w") as h:
            h.write(str(_canon["reward"]))
    except Exception as exc:
        print("WARNING: could not write %s: %s" % (_CANON_JSON, exc), file=sys.stderr)


def rubric_verdict(argv):
    if "--rubric" not in argv:
        return None
    i = argv.index("--rubric")
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ""
    return value if value in ("pass", "fail") else None


def load_results():
    """Return {test_id: 'pass'|'fail'|'skip'} from JUnit XML produced by Vitest."""
    results = {}
    if not os.path.exists(REPORT):
        return results
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError:
        return results
    for tc in tree.iter("testcase"):
        classname = tc.get("classname", "") or ""
        name      = tc.get("name", "") or ""
        ident     = f"{classname}::{name}".strip("::")
        failed    = any(c.tag in ("failure", "error") for c in tc)
        skipped   = any(c.tag == "skipped" for c in tc)
        results[ident] = "skip" if skipped else ("fail" if failed else "pass")
    return results


def matched(idents, results):
    """Match each configured identifier against reported test names (substring tolerant)."""
    out = {}
    for ident in idents:
        hit = next(
            (v for k, v in results.items()
             if ident in k or re.search(re.escape(ident), k)),
            None,
        )
        out[ident] = hit or "missing"
    return out


def main():
    r      = load_results()
    f2p    = matched(F2P, r)
    p2p    = matched(P2P, r)

    f2p_pass = [k for k, v in f2p.items() if v == "pass"]
    p2p_pass = [k for k, v in p2p.items() if v == "pass"]

    reward = canon_reward(
        len(f2p_pass), len(F2P),
        len(p2p_pass), len(P2P),
        rubric_verdict(sys.argv[1:]),
    )
    print(json.dumps({"reward": reward, "f2p": f2p, "p2p": p2p}))


if __name__ == "__main__":
    main()
