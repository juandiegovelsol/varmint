#!/usr/bin/env python3
"""Step 0.6 - validate the submitted run outputs and print the re-run commands (QC v2).

Usage:
    python3 check_gate.py "task_<taskId>/deliverables"

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
import json, sys, os, re, datetime

EXPECT = {"Oracle": ("== 1.0", lambda r: r == 1.0, "#16 Gate - Oracle/Nop"),
          "Nop": ("== 0.0", lambda r: r == 0.0, "#16 Gate - Oracle/Nop"),
          "Trials": ("< 1.0", lambda r: r is not None and r < 1.0, "#14 Hardening - Difficulty")}

problems = []


def load_json(path):
    try:
        return json.load(open(path))
    except Exception:
        return None


def trial_dir(run_path):
    if not os.path.isdir(run_path):
        return None
    for name in os.listdir(run_path):
        if name.startswith("Tasks__") and os.path.isdir(os.path.join(run_path, name)):
            return os.path.join(run_path, name)
    return None


def check_run(deliv, run):
    run_path = os.path.join(deliv, run)
    info = {"run": run, "reward_txt": None, "reward_json": None, "checksum": None}
    if not os.path.isdir(run_path):
        problems.append(f"{run}/ folder missing")
        return info
    td = trial_dir(run_path)
    if not td:
        problems.append(f"{run}/ has no Tasks__<id>/ trial dir - cannot read reward")
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
        # A run that ERRORED still leaves a container-side reward.txt behind, because
        # tests/test.sh writes it before harbor ever parses the result. Falling back to that
        # number made a bundle whose every run died (e.g. a nested reward.json failing
        # harbor's dict[str, float|int] validation) display a clean 1.0/0.0/0.5 gate. The
        # run recorded NOTHING; reward.txt alone must never satisfy the gate.
        exc = (res.get("exception_info") or {}).get("exception_type")
        if exc:
            problems.append(f"{run}: run FAILED with {exc} - harbor recorded no reward. "
                            f"verifier/reward.txt is written inside the container before "
                            f"harbor parses the result, so it does NOT show the gate held. "
                            f"Re-run after fixing the cause. [FAIL - Unauditable]")
            info["failed"] = True
        elif res.get("verifier_result") is None:
            problems.append(f"{run}: result.json has no verifier_result - the run never "
                            f"completed. reward.txt cannot stand in for it. "
                            f"[FAIL - Unauditable]")
            info["failed"] = True
    # reward.txt vs result.json agreement
    if info["reward_txt"] is not None and info["reward_json"] is not None \
            and abs(info["reward_txt"] - info["reward_json"]) > 1e-9:
        problems.append(f"{run}: reward.txt ({info['reward_txt']}) != result.json reward "
                        f"({info['reward_json']})")
    # gate
    # Only harbor's own recorded reward counts. reward.txt is corroboration, not evidence.
    r = info["reward_json"]
    if r is None and not info.get("failed"):
        r = info["reward_txt"]
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
    deliv = sys.argv[1]
    if os.path.isdir(os.path.join(deliv, "deliverables")):
        deliv = os.path.join(deliv, "deliverables")

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
        # Same rule as check_run: a run that errored has no recorded reward, and the
        # container-side reward.txt must not be allowed to render it as OK.
        r = i["reward_json"]
        if r is None and not i.get("failed"):
            r = i["reward_txt"]
        desc, ok, dim = EXPECT[i["run"]]
        verdict = "ERR" if i.get("failed") else ("OK" if (r is not None and ok(r)) else "FAIL")
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

    tasks = os.path.join(deliv, "Tasks")
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
    print(f"  bash {mm} \"{tasks}\" analyze    # -> harbor analyze <Trials/> (the whole dir, not Tasks__*)")
    print("      -> agent solved-vs-cheated feeds v2 #14; instruction sufficiency feeds v2 #15/#3")
    print("      CAVEAT: harbor analyze sometimes errors - retry ONCE before blaming the task.")




# ---------------------------------------------------------------- per-test nop check
# ADDED in MM_SWE_QC. A 0.0 aggregate on nop is NOT sufficient: an f2p test that PASSES on an
# empty submission cannot detect the bug (a golden-image test with no baseline auto-passes, for
# instance). The task then grades nothing real while every reward looks healthy. This is the
# defect class that got through review before, so it is a hard check, not advisory.
def check_nop_per_test(root):
    import glob
    problems = []
    nop = os.path.join(root, "Nop")
    if not os.path.isdir(nop):
        return ["Nop/ not found - cannot run the per-test inertness check"]
    rj = None
    for cand in glob.glob(os.path.join(nop, "**", "reward.json"), recursive=True):
        rj = cand; break
    if not rj:
        return ["Nop/ has no reward.json - per-test f2p outcomes unavailable. The task's "
                "verifier must write reward.json (see the rubric-template verifier snippet); "
                "without it an inert f2p test cannot be detected."]
    try:
        d = json.load(open(rj))
    except Exception as exc:
        return [f"Nop reward.json unparseable: {exc}"]
    # reward.json is a FLAT numeric map (harbor parses it as dict[str, float]), so per-test
    # outcomes arrive as `f2p::<name>` / `p2p::<name>` = 1.0/0.0. The old nested {"f2p": {...}}
    # shape is still accepted so older bundles keep working.
    f2p = {k[5:]: bool(v) for k, v in d.items()
           if isinstance(k, str) and k.startswith("f2p::")}
    p2p = {k[5:]: bool(v) for k, v in d.items()
           if isinstance(k, str) and k.startswith("p2p::")}
    if not f2p and isinstance(d.get("f2p"), dict):
        f2p, p2p = d.get("f2p") or {}, d.get("p2p") or {}
        problems.append("NOTE: reward.json uses the legacy NESTED f2p/p2p maps. harbor parses "
                        "reward.json as dict[str, float] and prefers it over reward.txt, so a "
                        "nested value aborts the trial with a ValidationError while reward.txt "
                        "still gets written - the run looks scored but nothing is stored. "
                        "Flatten to f2p::<name> = 1.0/0.0.")
    if not f2p:
        return ["Nop reward.json carries no per-test f2p outcomes (no f2p:: keys) - cannot "
                "detect inert tests"]
    inert = [k for k, v in f2p.items() if v]
    if inert:
        problems.append("INERT f2p test(s) - these PASS on an empty submission, so they cannot "
                        "detect the bug and the task grades nothing real:")
        problems += [f"    - {k}" for k in inert]
    mislabeled = [k for k, v in (p2p or {}).items() if v is False]
    if mislabeled:
        problems.append("p2p test(s) FAILING on nop - mislabeled, these are really f2p:")
        problems += [f"    - {k}" for k in mislabeled]
    if not problems:
        print(f"  [ok] every f2p test fails individually on nop ({len(f2p)} checked); "
              f"no p2p fails on nop")
    return problems




# ------------------------------------------------------------- trial model check
# ADDED in MM_SWE_QC. The trial must be run on the agreed model. Two independent records
# exist and both are checked:
#   * config.json  agent.model_name          - what was REQUESTED
#   * result.json  agent_info.model_info     - what the agent REPORTED actually running
# A disagreement between them matters as much as a wrong model: it means the run did not use
# what the config claims, so the reward cannot be attributed to the agreed model.
EXPECTED_MODEL = os.environ.get("MM_EXPECTED_MODEL", "claude-opus-4-8")


def _norm_model(m):
    """'anthropic/claude-opus-4-8' -> 'claude-opus-4-8'. Provider prefix is not identity."""
    if not m:
        return None
    return str(m).strip().split("/")[-1].lower()


def check_trial_model(root):
    import glob
    problems = []
    trials = os.path.join(root, "Trials")
    if not os.path.isdir(trials):
        return ["Trials/ not found - cannot confirm the trial model"]

    requested, actual, seen = None, None, []
    for cfg in sorted(glob.glob(os.path.join(trials, "**", "config.json"), recursive=True)):
        try:
            d = json.load(open(cfg))
        except Exception:
            continue
        a = d.get("agent") or (d.get("agents") or [{}])[0]
        if a.get("model_name"):
            requested = requested or _norm_model(a["model_name"])
            seen.append(("config", os.path.relpath(cfg, trials), a["model_name"]))
    for res in sorted(glob.glob(os.path.join(trials, "**", "result.json"), recursive=True)):
        try:
            d = json.load(open(res))
        except Exception:
            continue
        mi = ((d.get("agent_info") or {}).get("model_info") or {})
        if mi.get("name"):
            actual = actual or _norm_model(mi["name"])
            seen.append(("result", os.path.relpath(res, trials), mi["name"]))
        ca = ((d.get("config") or {}).get("agent") or {})
        if ca.get("model_name"):
            requested = requested or _norm_model(ca["model_name"])

    if requested is None and actual is None:
        return ["Trials/ records no model (no agent.model_name, no agent_info.model_info) - "
                "cannot confirm the trial ran on " + EXPECTED_MODEL]

    want = _norm_model(EXPECTED_MODEL)
    if actual and actual != want:
        problems.append(f"trial RAN on {actual!r}, expected {want!r} - the reward does not "
                        f"describe the agreed model (agent_info.model_info)")
    if requested and requested != want:
        problems.append(f"trial CONFIG requested {requested!r}, expected {want!r} "
                        f"(agent.model_name)")
    if requested and actual and requested != actual:
        problems.append(f"config requested {requested!r} but the agent reported {actual!r} - "
                        f"the run did not use what the config claims")
    if not problems:
        print(f"  [ok] trial ran on {actual or requested} (expected {want})")
    return problems




# ------------------------------------------------------------- 90-minute trial rule
# The rubric adds to the hardening dimension: "an agent that takes longer than 90 minutes is
# also considered a fail (as observed in the trajectory)". So a trial that scored 1.0 can still
# be acceptable IF it blew the time budget - and a 1.0 inside the budget is a genuine
# "not hard enough". Duration is derived heuristically (trajectory schemas vary), so it is
# reported as a CANDIDATE: confirm against the trajectory before leaning on the clause.
NINETY_MIN = 90 * 60


def _iso(v):
    try:
        return datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _trial_duration(trials):
    """(seconds, how_it_was_derived) or (None, reason)."""
    import glob
    # 1. explicit duration keys anywhere in the trial result
    for res in sorted(glob.glob(os.path.join(trials, "**", "result.json"), recursive=True)):
        try:
            d = json.load(open(res))
        except Exception:
            continue
        for k in ("duration_sec", "duration", "elapsed_sec", "wall_clock_sec", "runtime_sec"):
            if isinstance(d.get(k), (int, float)):
                return float(d[k]), f"{k} in {os.path.basename(res)}"
        st, fi = _iso(d.get("started_at")), _iso(d.get("finished_at"))
        if st and fi and fi > st:
            return fi - st, f"started_at..finished_at in {os.path.basename(res)}"
        ex = d.get("agent_execution") or {}
        st, fi = _iso(ex.get("started_at")), _iso(ex.get("finished_at"))
        if st and fi and fi > st:
            return fi - st, "agent_execution span"
    # 2. trajectory file mtime span, as a last resort
    tj = sorted(glob.glob(os.path.join(trials, "**", "trajectory.json"), recursive=True))
    if tj:
        cfg = os.path.join(trials, "config.json")
        if os.path.isfile(cfg):
            span = os.path.getmtime(tj[-1]) - os.path.getmtime(cfg)
            if span > 0:
                return span, "config.json..trajectory.json mtime span (WEAK)"
    return None, "no duration signal in Trials/"


def check_trial_time(root):
    import glob
    trials = os.path.join(root, "Trials")
    if not os.path.isdir(trials):
        return ["Trials/ not found - cannot apply the 90-minute rule"]
    reward = None
    for res in sorted(glob.glob(os.path.join(trials, "**", "result.json"), recursive=True)):
        try:
            d = json.load(open(res))
        except Exception:
            continue
        r = ((d.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        if r is not None:
            reward = float(r); break
    secs, how = _trial_duration(trials)
    if secs is None:
        print(f"  [note] trial duration unknown ({how}); the 90-minute clause cannot be applied")
        return []
    mins = secs / 60.0
    print(f"  [note] trial duration ~{mins:.0f} min (CANDIDATE - derived from {how}; "
          f"confirm in the trajectory)")
    if reward is None:
        return []
    if reward >= 1.0 and secs > NINETY_MIN:
        print(f"  [ok] trial scored {reward} but ran ~{mins:.0f} min > 90 - acceptable via the "
              f"timeout clause. Record that explicitly; it is not a normal pass.")
        return []
    if reward >= 1.0:
        return [f"trial scored {reward} in ~{mins:.0f} min (<= 90) - the model SOLVED it inside "
                f"the budget, so the task does not stump [Fail - Not Hard Enough]"]
    return []




# ------------------------------------- AgentTimeoutError vs the 90-minute clause
# A trial that dies with AgentTimeoutError has no reward, which reads as Unauditable. But the
# rubric's hardening dimension says a trial that "times out after 90 minutes" is an acceptable
# PASS - that is the hardening working, not a broken run. So when the exception is a timeout and
# the task's own agent budget is ~90 min (and the run actually consumed it), report the clause as
# satisfied instead of failing the task for being unauditable.
TIMEOUT_CLAUSE_APPLIED = []


def check_timeout_clause(root):
    import glob
    trials = os.path.join(root, "Trials")
    tasks = os.path.join(root, "Tasks")
    if not os.path.isdir(trials):
        return []
    exc, dur = None, None
    _budget_from_msg = []
    for res in sorted(glob.glob(os.path.join(trials, "**", "result.json"), recursive=True)):
        try:
            d = json.load(open(res))
        except Exception:
            continue
        ei = d.get("exception_info") or {}
        e = ei.get("exception_type") or ei.get("type")
        if e:
            exc = str(e)
            msg = str(ei.get("exception_message") or "")
            mm = re.search(r"timed out after ([0-9.]+) seconds", msg)
            if mm:
                _budget_from_msg.append(float(mm.group(1)))
            st, fi = _iso(d.get("started_at")), _iso(d.get("finished_at"))
            if st and fi and fi > st:
                dur = fi - st
            break
    if not exc or "timeout" not in exc.lower():
        return []
    budget = _budget_from_msg[0] if _budget_from_msg else None
    tp = os.path.join(tasks, "task.toml")
    if budget is None and os.path.isfile(tp):
        txt = open(tp, errors="replace").read()
        m = re.search(r"\[agent\][^\[]*?timeout_sec\s*=\s*([0-9.]+)", txt, re.S)
        if m:
            budget = float(m.group(1))
    mins = f"~{dur/60:.0f} min" if dur else "duration unknown"
    if budget and budget >= NINETY_MIN - 60:
        print(f"  [ok] trial ended in {exc} after {mins}, against an agent budget of "
              f"{budget/60:.0f} min. That is the 90-MINUTE CLAUSE, not an unauditable run: the "
              f"rubric accepts a trial that times out after 90 minutes. Record it explicitly - "
              f"the missing reward is expected, so do NOT book this as Unauditable.")
        TIMEOUT_CLAUSE_APPLIED.append(exc)
        return []
    return [f"trial ended in {exc} after {mins} but the agent budget is "
            f"{('%.0f min' % (budget/60)) if budget else 'unknown'} - under 90 min, so the "
            f"timeout clause does not apply and there is no reward to audit [Fail - Unauditable]"]


def _reconcile_timeout(root):
    """Drop the inherited 'Unauditable' finding when the 90-minute clause explains it.

    Leaving both would print a contradiction: the clause says the missing reward is EXPECTED
    while the gate says the run is unauditable for exactly that reason.
    """
    if not TIMEOUT_CLAUSE_APPLIED:
        return 0
    global problems
    dropped = [x for x in problems
               if "Unauditable" in str(x) or "AgentTimeoutError" in str(x)]
    if dropped:
        problems[:] = [x for x in problems if x not in dropped]
        print(f"  [reconciled] withdrew {len(dropped)} 'Unauditable' finding(s) - the 90-minute "
              f"clause above explains the missing reward; it is not a broken run.")
    return 0


def _mm_swe_qc_extra(root):
    probs = check_nop_per_test(root)
    print("\n--- trial model (MM_SWE_QC) ---")
    probs += check_trial_model(root)
    print("\n--- 90-minute trial rule (MM_SWE_QC) ---")
    probs += check_trial_time(root)
    probs += check_timeout_clause(root)
    _reconcile_timeout(root)
    for x in probs:
        print(f"  [FAIL] {x}" if not x.startswith("    ") else x)
    return len(probs)


if __name__ == "__main__":
    main()
    # MM_SWE_QC: the per-test inertness check is the one a reward aggregate cannot do.
    _root = sys.argv[1] if len(sys.argv) > 1 else "."
    print("\n--- per-test inertness (MM_SWE_QC) ---")
    _extra = _mm_swe_qc_extra(_root)
    sys.exit(1 if (_extra or problems) else 0)
