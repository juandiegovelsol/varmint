#!/usr/bin/env python3
"""Step 0.6 - validate the submitted run outputs and print the re-run commands (QC v2).

Usage:
    python3 check_gate.py "task_<taskId>/deliverables"
    (Tasks/ or the bundle itself also work - the deliverables root is resolved from either)

Layouts: V2 (TASK101+) nests the bundle at Tasks/<task_id>/ and harbor names each trial dir
after that folder (<task_id>__<rand>); V1 had task.toml directly in Tasks/ (Tasks__<rand>).
Trial dirs are found by shape, so both layouts read the same way.

Aligned to **QC rubric v2**. Statically validates the submitted Oracle/Nop/Trials rewards:
  * each run's verifier/reward.txt == result.json -> verifier_result.rewards.reward
  * gate: Oracle = 1.0, Nop = 0.0  (v2 #16 Gate - Oracle/Nop   [Fail - Gate Broken])
  * Trials < 1.0                    (v2 #14 Hardening - Difficulty [Fail - Not Hard Enough])
  * all three task_checksum values identical (proves the runs used THIS exact Tasks/ bundle;
    a mismatch => stale/foreign runs => treat as Unauditable)

Run-output *layout* (old #30) is no longer a scored dimension in v2, so this script no longer
fails on missing scaffold files - it only reads what it needs to confirm the rewards. The rewards
are SELF-REPORTED (produced in the contributor's sandbox), so this only proves internal
consistency; it then prints the exact `harbor` commands to INDEPENDENTLY re-run the gate - your
reproduced Oracle=1.0 / Nop=0.0 must match. Standard library only.
"""
import json, sys, os

EXPECT = {"Oracle": ("== 1.0", lambda r: r == 1.0, "#16 Gate - Oracle/Nop"),
          "Nop": ("== 0.0", lambda r: r == 0.0, "#16 Gate - Oracle/Nop"),
          "Trials": ("< 1.0", lambda r: r is not None and r < 1.0, "#14 Hardening - Difficulty")}

problems = []


def load_json(path):
    try:
        return json.load(open(path))
    except Exception:
        return None


BUNDLE_MARKERS = ("task.toml", "instruction.md", "tests", "solution", "environment")


def looks_like_bundle(d):
    return any(os.path.exists(os.path.join(d, m)) for m in BUNDLE_MARKERS)


def task_dirs(tasks):
    """Every bundle in a Tasks/ folder: Tasks/ itself (V1) or each Tasks/<task_id>/ (V2)."""
    if looks_like_bundle(tasks):
        return [tasks]
    return sorted(os.path.join(tasks, d) for d in os.listdir(tasks)
                  if os.path.isdir(os.path.join(tasks, d)) and looks_like_bundle(os.path.join(tasks, d)))


def find_tasks_root(root):
    """Return (deliverables_root, bundle_dir); `root` may be the deliverables root, Tasks/, or
    the bundle itself. The bundle is Tasks/<task_id>/ in V2 (TASK101+) and Tasks/ in V1.
    bundle_dir is None when there is no bundle - or more than one, which is ambiguous."""
    root = os.path.normpath(root)
    tasks = root if os.path.basename(root) == "Tasks" else os.path.join(root, "Tasks")
    if os.path.isfile(os.path.join(root, "task.toml")) or (
            not os.path.isdir(tasks) and looks_like_bundle(root)):
        up = os.path.dirname(root)
        if os.path.basename(root) != "Tasks" and os.path.basename(up) == "Tasks":
            return os.path.dirname(up), root              # V2: <deliv>/Tasks/<task_id>
        return up, root                                   # V1 Tasks/, or a bare bundle
    if not os.path.isdir(tasks):
        return root, None
    found = task_dirs(tasks)
    return os.path.dirname(tasks), (found[0] if len(found) == 1 else None)


def resolve_deliv(arg):
    """The folder holding Oracle/ Nop/ Trials/, from whatever the user pointed at."""
    if os.path.isdir(os.path.join(arg, "deliverables")):
        arg = os.path.join(arg, "deliverables")
    return find_tasks_root(arg)


def trial_dir(run_path):
    """The trial dir inside a harbor job dir. harbor names it after the task folder
    (`<name[:32]>__<rand>`: V1 `Tasks__...`, V2 `<task_id>__...`), so find it by shape - the
    child dir with its own result.json (else a verifier/) - never by name. Newest wins."""
    if not os.path.isdir(run_path):
        return None
    kids = [os.path.join(run_path, n) for n in os.listdir(run_path)
            if os.path.isdir(os.path.join(run_path, n))]
    for has in ("result.json", "verifier"):
        hits = [k for k in kids if os.path.exists(os.path.join(k, has))]
        if hits:
            return max(hits, key=lambda k: os.path.getmtime(os.path.join(k, has)))
    hits = [k for k in kids if "__" in os.path.basename(k)]
    return max(hits, key=os.path.getmtime) if hits else None


def check_run(deliv, run):
    run_path = os.path.join(deliv, run)
    info = {"run": run, "reward_txt": None, "reward_json": None, "checksum": None}
    if not os.path.isdir(run_path):
        problems.append(f"{run}/ folder missing")
        return info
    td = trial_dir(run_path)
    if not td:
        problems.append(f"{run}/ has no <task>__<rand>/ trial dir - cannot read reward")
        return info
    # reward.txt
    rt = os.path.join(td, "verifier", "reward.txt")
    if os.path.exists(rt):
        try:
            info["reward_txt"] = float(open(rt).read().strip())
        except Exception:
            problems.append(f"{run} reward.txt unparseable")
    else:
        problems.append(f"{run}: verifier/reward.txt missing - cannot confirm reward")
    # result.json reward + checksum
    res = load_json(os.path.join(td, "result.json"))
    if res:
        info["reward_json"] = (((res.get("verifier_result") or {}).get("rewards") or {})
                               .get("reward"))
        info["checksum"] = res.get("task_checksum")
    # reward.txt vs result.json agreement
    if info["reward_txt"] is not None and info["reward_json"] is not None \
            and abs(info["reward_txt"] - info["reward_json"]) > 1e-9:
        problems.append(f"{run}: reward.txt ({info['reward_txt']}) != result.json reward "
                        f"({info['reward_json']})")
    # gate
    r = info["reward_json"] if info["reward_json"] is not None else info["reward_txt"]
    desc, ok, dim = EXPECT[run]
    if r is None:
        problems.append(f"{run}: no reward found")
    elif not ok(r):
        problems.append(f"{run}: reward {r} fails gate (expected {desc}) (v2 {dim})")
    return info


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    deliv, bundle = resolve_deliv(sys.argv[1])

    infos = [check_run(deliv, run) for run in ("Oracle", "Nop", "Trials")]

    # checksum agreement (proves all three runs used the same Tasks/ bundle)
    checks = {i["run"]: i["checksum"] for i in infos if i["checksum"]}
    if len(set(checks.values())) > 1:
        problems.append(f"task_checksum MISMATCH across runs: {checks} - runs are stale or were "
                        f"produced against a different Tasks/ bundle => treat as Unauditable")

    print(f"\nVarmint Sheriffs gate validation (QC v2) - {os.path.abspath(deliv)}\n")
    print("| run    | reward.txt | result.json | gate | task_checksum |")
    print("|--------|-----------|-------------|------|---------------|")
    for i in infos:
        r = i["reward_json"] if i["reward_json"] is not None else i["reward_txt"]
        desc, ok, dim = EXPECT[i["run"]]
        verdict = "OK" if (r is not None and ok(r)) else "FAIL"
        cs = (i["checksum"] or "")[:12]
        print(f"| {i['run']:<6} | {str(i['reward_txt']):>9} | {str(i['reward_json']):>11} "
              f"| {verdict:<4} | {cs} |")
    print()

    if problems:
        print("PROBLEMS:")
        for p in problems:
            print(f"  [FAIL] {p}")
    else:
        print("No static problems: rewards agree, gate holds, checksums match.")

    tasks = bundle or os.path.join(deliv, "Tasks")     # the folder holding task.toml
    print("\n--- Now REPRODUCE the gate yourself (KEYLESS - no API key/anonymizer needed) ---")
    print("Oracle+Nop run unit-tests only (no model call), so reproduce them in your OWN Cursor")
    print(f"with just Docker + harbor 0.18. Pointed at {tasks}:\n")
    mm = "~/.claude/skills/mmswe-runner/mm_run.sh"
    print(f"  bash {mm} \"{tasks}\" oracle   # expect 1.0  (keyless) -> v2 #16")
    print(f"  bash {mm} \"{tasks}\" nop      # expect 0.0  (keyless) -> v2 #16")
    print(f"  bash {mm} \"{tasks}\" oracle   # run AGAIN -> still 1.0 (idempotency -> v2 #13 Determinism)")
    print("  # no mmswe-runner skill? raw harbor does the same, still keyless:")
    print(f"  #   harbor run -p \"{tasks}\" -a oracle -e docker -o \"{deliv}\" --job-name Oracle --yes")
    print(f"  #   harbor run -p \"{tasks}\" -a nop    -e docker -o \"{deliv}\" --job-name Nop    --yes")
    print("  # The agent TRIAL needs a model endpoint (anonymizer proxy in the sandbox); do NOT")
    print("  # re-run it in review -> validate the shipped Trials/ run above + `harbor analyze` below.")
    print("\nYour reproduced Oracle=1.0 / Nop=0.0 must match the submitted rewards, and the "
          "verifier must reach completion (stage banners + a real `reward=`).")
    print("  # v3.1: if tests/rubrics.json is a real rubric, this same keyless run also writes the")
    print("  #       judge REQUEST under the run's verifier/judge/ (criteria_payload.json,")
    print("  #       source.txt, PROMPT.md). Audit the judge wiring with check_judge.py (Step 7.6).")

    # ---- Step 0.7 helper commands (via mmswe-runner skill; aids, not verdicts) ----
    print("\n--- Step 0.7: run the harbor helper commands via the mmswe-runner skill (aids) ---")
    print("(check/analyze call a model via the anonymizer default - no real key; endpoint must be reachable)")
    print(f"  bash {mm} \"{tasks}\" check      # -> harbor check <Tasks>")
    print("      -> test fairness feeds v2 #9 (Tests - Implementation Overfit)")
    print("      CAVEAT: its \"Behavior in Task Description\" flag CANNOT read images. If the flagged")
    print("      behavior is shown in the IMAGE, the tests are FAIR (#9 Pass) - do not fail #9 on it.")
    print(f"  bash {mm} \"{tasks}\" analyze    # -> harbor analyze <Trials/> (the whole dir, not one <task>__<rand>/)")
    print("      -> agent solved-vs-cheated feeds v2 #14; instruction sufficiency feeds v2 #15/#3")
    print("      CAVEAT: harbor analyze sometimes errors - retry ONCE before blaming the task.")


if __name__ == "__main__":
    main()
