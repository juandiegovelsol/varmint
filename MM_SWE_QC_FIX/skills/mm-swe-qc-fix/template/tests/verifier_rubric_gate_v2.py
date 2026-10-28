# --rubric gate for the V2 harness verifier (TASK101+ bundles, Tasks/<task_id>/tests/verifier.py).
# verifier.py carries TASK-SPECIFIC logic, so this is a PROPOSAL to merge by hand.
#
# The V2 verifier already writes what harbor needs: reward.json is a FLAT map of numbers, and the
# per-test outcomes go to reward_detail.json beside it (f2p::<name> = "pass" | "fail" | ...).
# So the gate is three small edits - nothing about the reward writer changes. As in V1, the
# rubric can ONLY withhold a 1.0 (-> 0.5); with no verdict the reward stays tests-only.
# test.sh must hand the verdict over:  python3 /tests/verifier.py --rubric "${RUBRIC:-}" 2>>...

# 1) next to `import json`:
import argparse

# 2) first lines of main(): read the verdict ("pass" | "fail" | anything else = not graded)
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rubric", default="", help='"pass" | "fail" | "" (not graded)')
    rubric = (ap.parse_args().rubric or "").strip().lower()
    rubric = rubric if rubric in ("pass", "fail") else None
    results = load_junit(REPORT)
    # ... the task's existing f2p / p2p resolution, unchanged ...

    # 3) replace the reward dict: same keys, the gate applied to "reward" only
    tests_passed = 1.0 if solved else 0.0
    reward = {
        "reward": 0.5 if (solved and rubric == "fail") else tests_passed,
        "tests_passed": tests_passed,
        "f2p_passed": f2p_ok, "f2p_total": len(F2P),
        "p2p_passed": p2p_ok, "p2p_total": len(P2P),
        "rubric_passed": {"pass": 1, "fail": 0}.get(rubric, -1),
    }
    # ... the existing reward.json / reward_detail.json / reward.txt writes, unchanged ...
