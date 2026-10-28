#!/usr/bin/env python3
"""Behavioral verifier: parses pytest JUnit XML report → computes reward.
NEVER inspects source code. Reward is purely from test outcomes; a rubric
verdict, when one has been folded in, can only withhold a 1.0 and turn it
into 0.5 — it never pushes a score toward 0.0.
"""
import json, os, re, sys
import xml.etree.ElementTree as ET

CONF        = json.load(open('/tests/config.json'))
F2P         = CONF['f2p']
P2P         = CONF['p2p']
REPORT      = '/logs/verifier/report.xml'
REWARD_PATH = '/logs/verifier/reward.txt'
REWARD_JSON = '/logs/verifier/reward.json'
RUBRIC_JSON = '/logs/verifier/rubric.json'

def load_results(report_paths):
    """Return ({identifier: 'pass'|'fail'|'skip'}, testcase_count) from JUnit XML.
    Normalises pytest's -contentN parametrize suffix so matching is stable.
    """
    results, count = {}, 0
    for path in report_paths:
        if not os.path.exists(path):
            continue
        try:
            tree = ET.parse(path)
        except ET.ParseError:
            continue
        for tc in tree.iter('testcase'):
            count    += 1
            classname = tc.get('classname', '')
            name      = tc.get('name', '')
            # Normalise: remove the "-contentN" pytest parametrize counter suffix
            # e.g. "test_foo[bar-content15]" -> "test_foo[bar]"
            norm_name = re.sub(r'-content\d+\]$', ']', name)
            key       = f"{classname}::{norm_name}" if classname else norm_name
            # Also store with original name for exact matches
            key_raw   = f"{classname}::{name}" if classname else name
            failed    = any(c.tag in ('failure', 'error') for c in tc)
            skipped   = any(c.tag == 'skipped' for c in tc)
            status    = 'skip' if skipped else ('fail' if failed else 'pass')
            results[key]     = status
            results[key_raw] = status
    return results, count

def matched(idents, results):
    """Match each config identifier against reported keys (substring tolerant)."""
    out = {}
    for ident in idents:
        hit = None
        # 1. Exact substring
        for k, v in results.items():
            if ident in k:
                hit = v
                break
        # 2. If ident ends with ], try without trailing ] (handles un-normalised keys)
        if hit is None and ident.endswith(']'):
            relaxed = ident[:-1]
            for k, v in results.items():
                if relaxed in k:
                    hit = v
                    break
        # 3. Regex fallback (with escaped special chars)
        if hit is None:
            try:
                pat = re.compile(re.escape(ident))
                for k, v in results.items():
                    if pat.search(k):
                        hit = v
                        break
            except re.error:
                pass
        out[ident] = hit or 'missing'
    return out

def write_reward(value, tests_passed=None, f2p=None, p2p=None, rubric=None):
    """reward.txt stays a BARE FLOAT in {0.0, 0.5, 1.0}; reward.json carries the detail.

    CRITICAL - reward.json MUST be a FLAT map of numbers. harbor parses it as
    VerifierResult.rewards: dict[str, float] and takes it in PREFERENCE to reward.txt,
    so a nested object, a list or a null raises a pydantic ValidationError that aborts
    the trial BEFORE any reward is recorded - while reward.txt still gets written inside
    the container, making the run look scored when harbor in fact stored nothing.

    Per-test outcomes therefore ride along as flat `f2p::<name>` / `p2p::<name>` entries
    (1.0 pass, 0.0 otherwise), so the decisive QC question - "did this specific f2p test
    pass on the nop run?" - stays answerable in a shape harbor accepts.
    """
    os.makedirs(os.path.dirname(REWARD_PATH), exist_ok=True)
    with open(REWARD_PATH, 'w') as handle:
        handle.write(f"{value}\n")

    detail = {"reward": value,
              "tests_passed": value if tests_passed is None else tests_passed}
    if f2p is not None:
        detail["f2p_passed"] = sum(1 for v in f2p.values() if v)
        detail["f2p_total"]  = len(f2p)
    if p2p is not None:
        detail["p2p_passed"] = sum(1 for v in p2p.values() if v)
        detail["p2p_total"]  = len(p2p)
    # "pass" -> 1, "fail" -> 0, None/unavailable -> -1
    detail["rubric_pass"] = {"pass": 1, "fail": 0}.get(rubric, -1)
    failed = []
    if os.path.isfile(RUBRIC_JSON):
        try:
            failed = json.load(open(RUBRIC_JSON)).get("failed", [])
        except Exception:
            failed = []
    detail["rubric_failed_count"] = len(failed)
    for name, passed in (f2p or {}).items():
        detail[f"f2p::{name}"] = 1.0 if passed else 0.0
    for name, passed in (p2p or {}).items():
        detail[f"p2p::{name}"] = 1.0 if passed else 0.0
    try:
        with open(REWARD_JSON, 'w') as handle:
            json.dump(detail, handle, indent=2)
    except Exception as exc:
        print(f"WARNING: could not write {REWARD_JSON}: {exc}", file=sys.stderr)
    print(f"\nREWARD: {value}")

def main():
    argv   = sys.argv[1:]
    rubric = None                                  # None = judge unavailable
    if "--rubric" in argv:
        i     = argv.index("--rubric")
        value = argv[i + 1].strip() if i + 1 < len(argv) else ""
        argv  = argv[:i] + argv[i + 2:]
        rubric = value if value in ("pass", "fail") else None
    report_paths = argv or [REPORT]

    results, case_count = load_results(report_paths)
    f2p_map = matched(F2P, results)
    p2p_map = matched(P2P, results)

    # Per-identifier booleans: each test is graded individually.
    f2p_results = {k: v == 'pass' for k, v in f2p_map.items()}
    p2p_results = {k: v == 'pass' for k, v in p2p_map.items()}

    all_f2p = bool(F2P) and all(f2p_results.values())
    all_p2p = all(p2p_results.values())
    any_f2p = any(f2p_results.values())

    # Reward policy (rubric-template contract):
    # 0.0 — any p2p fails (regression), or nothing passed / the suite failed to run
    # 0.5 — some but not all f2p pass
    # 1.0 — all f2p pass and no p2p regressed
    if not all_p2p:
        tests_passed = 0.0
    elif all_f2p:
        tests_passed = 1.0
    elif any_f2p:
        tests_passed = 0.5
    else:
        tests_passed = 0.0

    # The rubric is a gate, not a term in an average: it can only withhold a 1.0
    # and turn it into 0.5, and with no verdict the run scores on tests alone.
    if tests_passed >= 1.0 and rubric == "fail":
        reward = 0.5
    else:
        reward = tests_passed

    write_reward(reward, tests_passed=tests_passed, f2p=f2p_results,
                 p2p=p2p_results, rubric=rubric)
    print(json.dumps({
        'reward': reward,
        'tests_passed': tests_passed,
        'rubric': rubric,
        'f2p': f2p_map,
        'p2p': p2p_map,
        'all_results_count': case_count,
    }))

if __name__ == '__main__':
    main()
