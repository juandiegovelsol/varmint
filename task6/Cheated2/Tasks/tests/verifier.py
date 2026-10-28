#!/usr/bin/env python3
"""
Verifier for fabricjs__fabric.js-10775-mm.
Parses vitest JUnit XML and computes reward:
  0.0 — any p2p fails, or no f2p passes, or the suite failed to run
  0.5 — some but not all f2p pass, OR all f2p pass but the rubric FAILED
  1.0 — all f2p pass and all p2p pass (rubric passed, or no verdict yet)

The rubric is a GATE, not a term in an average: it can only withhold a 1.0 and turn it into
0.5. It never pushes a score toward 0.0, and with no verdict the task scores on tests alone.
"""
import json, os, sys, xml.etree.ElementTree as ET

CONF = json.load(open('/tests/config.json'))
F2P, P2P = CONF['f2p'], CONF['p2p']
REPORT = '/logs/verifier/report.xml'
REWARD_PATH = '/logs/verifier/reward.txt'
REWARD_JSON = '/logs/verifier/reward.json'
REWARD_DETAIL_JSON = '/logs/verifier/reward_detail.json'
RUBRIC_JSON = '/logs/verifier/rubric.json'


def write_reward(value, tests_passed=None, f2p=None, p2p=None, rubric=None):
    """reward.txt stays a BARE FLOAT in {0.0, 0.5, 1.0}; reward_detail.json carries the detail.

    reward.json must stay scalar-only: Harbor's verifier feeds it straight into
    VerifierResult(rewards=...), which requires every top-level value to be float|int.
    """
    os.makedirs(os.path.dirname(REWARD_PATH), exist_ok=True)
    with open(REWARD_PATH, "w") as handle:
        handle.write(f"{value}\n")

    detail = {"reward": value,
              "tests_passed": value if tests_passed is None else tests_passed}
    if f2p is not None:
        detail["f2p_passed"] = sum(1 for v in f2p.values() if v)
        detail["f2p_total"] = len(f2p)
        detail["f2p"] = f2p
    if p2p is not None:
        detail["p2p"] = p2p
    detail["rubric"] = rubric                      # "pass" | "fail" | None (unavailable)
    failed = []
    if os.path.isfile(RUBRIC_JSON):
        try:
            failed = json.load(open(RUBRIC_JSON)).get("failed", [])
        except Exception:
            failed = []
    detail["rubric_failed"] = failed

    scores = {k: v for k, v in detail.items() if isinstance(v, (int, float))
              and not isinstance(v, bool)}
    try:
        with open(REWARD_JSON, "w") as handle:
            json.dump(scores, handle, indent=2)
        with open(REWARD_DETAIL_JSON, "w") as handle:
            json.dump(detail, handle, indent=2)
    except Exception as exc:
        print(f"WARNING: could not write {REWARD_JSON}: {exc}", file=sys.stderr)
    print(f"\nREWARD: {value}")


def load_results(report_paths):
    results = {}
    for path in report_paths:
        if not os.path.exists(path):
            continue
        try:
            tree = ET.parse(path)
        except ET.ParseError:
            continue
        for tc in tree.iter('testcase'):
            classname = tc.get('classname', '')
            name = tc.get('name', '')
            full = f"{classname} {name}".strip()
            failed = any(c.tag in ('failure', 'error') for c in tc)
            skipped = any(c.tag == 'skipped' for c in tc)
            results[full] = 'skip' if skipped else ('fail' if failed else 'pass')
    return results


def evaluate(idents, results):
    """Grade each identifier INDIVIDUALLY -> {identifier: bool}.

    An aggregate cannot answer the decisive QC question 'did this specific f2p pass on nop?'.
    """
    out = {}
    for ident in idents:
        # substring match (case-sensitive)
        hit = next((v for k, v in results.items() if ident in k), None)
        out[ident] = (hit == 'pass')
    return out


def main():
    argv = sys.argv[1:]
    rubric = None                                  # None = judge unavailable
    if "--rubric" in argv:
        i = argv.index("--rubric")
        value = argv[i + 1].strip() if i + 1 < len(argv) else ""
        argv = argv[:i] + argv[i + 2:]
        rubric = value if value in ("pass", "fail") else None
    report_paths = argv or [REPORT]

    results = load_results(report_paths)
    f2p_results = evaluate(F2P, results)
    p2p_results = evaluate(P2P, results)

    f2p_passed = sum(1 for v in f2p_results.values() if v)
    all_p2p = all(p2p_results.values())            # vacuously true if P2P is empty
    all_f2p = bool(f2p_results) and f2p_passed == len(f2p_results)

    if not all_p2p:
        tests_passed = 0.0                         # a p2p regression is never partial credit
    elif all_f2p:
        tests_passed = 1.0
    elif f2p_passed:
        tests_passed = 0.5
    else:
        tests_passed = 0.0

    # The rubric can ONLY withhold a 1.0, never push toward 0.0.
    if tests_passed >= 1.0 and rubric == "fail":
        reward = 0.5
    else:
        reward = tests_passed                      # rubric None -> tests-only, NEVER 0

    write_reward(reward, tests_passed=tests_passed, f2p=f2p_results, p2p=p2p_results,
                 rubric=rubric)
    print(json.dumps({'reward': reward, 'tests_passed': tests_passed,
                      'rubric': rubric, 'f2p': f2p_results, 'p2p': p2p_results,
                      'results_count': len(results)}))


if __name__ == '__main__':
    main()
