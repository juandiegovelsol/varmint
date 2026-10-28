#!/usr/bin/env python3
"""
Behavioral verifier for recharts__recharts-6937-mm.

Reward policy (binary, no partial credit):
  1.0 - every f2p passes AND every p2p passes.
  0.0 - a strict subset of f2p passes, or any p2p regressed, or the suite failed to run.

Identifiers are resolved EXACTLY. An earlier revision matched them by substring and
took the first hit, which lets one test be scored using a different test's result as
soon as one configured name is a prefix of another.
"""
import atexit, json, os, sys, xml.etree.ElementTree as ET

CONF   = json.load(open("/tests/config.json"))
F2P    = CONF["f2p"]
P2P    = CONF["p2p"]
REPORT = "/logs/verifier/report.xml"
REWARD = "/logs/verifier/reward.txt"

_CANON_JSON = "/logs/verifier/reward.json"
_CANON_TXT = "/logs/verifier/reward.txt"
_canon = {}


def canon_reward(f2p_passed, f2p_total, p2p_passed, p2p_total, rubric):
    """THE reward policy for the whole corpus. BINARY -- there is no partial credit."""
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
        with open(_CANON_TXT, "w") as _h:
            _h.write(str(_canon["reward"]))
    except Exception as _exc:
        print("WARNING: could not write %s: %s" % (_CANON_JSON, _exc), file=sys.stderr)


def rubric_verdict(argv):
    """The verdict test.sh hands in as `--rubric pass|fail|""`."""
    if "--rubric" not in argv:
        return None
    i = argv.index("--rubric")
    value = argv[i + 1].strip().lower() if i + 1 < len(argv) else ""
    return value if value in ("pass", "fail") else None


def load_results():
    """Return {full_id: status} and {test_name: [full_id, ...]} from Vitest's JUnit XML."""
    by_id, by_name = {}, {}
    if not os.path.exists(REPORT):
        return by_id, by_name
    try:
        tree = ET.parse(REPORT)
    except ET.ParseError:
        return by_id, by_name
    for tc in tree.iter("testcase"):
        classname = (tc.get("classname") or "").strip()
        name      = (tc.get("name") or "").strip()
        full_id   = f"{classname}::{name}".strip(":")
        failed    = any(c.tag in ("failure", "error") for c in tc)
        skipped   = any(c.tag == "skipped" for c in tc)
        status    = "skip" if skipped else ("fail" if failed else "pass")
        by_id[full_id] = status
        by_name.setdefault(name, []).append(full_id)
    return by_id, by_name


def resolve(idents, by_id, by_name):
    """Exact resolution only.

    Primary key is the fully-qualified `<file>::<suite chain> > <test>` id. If the
    reporter spells the classname differently (absolute path, for instance), fall back
    to the test name alone -- but only when that name identifies exactly one test, so a
    duplicated name is reported rather than silently scored against its twin.
    """
    out = {}
    for ident in idents:
        if ident in by_id:
            out[ident] = by_id[ident]
            continue
        name = ident.split("::", 1)[1] if "::" in ident else ident
        hits = by_name.get(name, [])
        if len(hits) == 1:
            out[ident] = by_id[hits[0]]
        elif len(hits) > 1:
            out[ident] = "ambiguous"
        else:
            out[ident] = "missing"
    return out


def main():
    by_id, by_name = load_results()
    f2p = resolve(F2P, by_id, by_name)
    p2p = resolve(P2P, by_id, by_name)

    f2p_pass = [k for k, v in f2p.items() if v == "pass"]
    p2p_pass = [k for k, v in p2p.items() if v == "pass"]

    reward = canon_reward(len(f2p_pass), len(F2P),
                           len(p2p_pass), len(P2P),
                           rubric_verdict(sys.argv[1:]))
    print(json.dumps({"reward": reward, "f2p": f2p, "p2p": p2p}, indent=2))


if __name__ == "__main__":
    main()
