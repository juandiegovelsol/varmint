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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qc_layout

# THE REWARD SCHEMA, AS RECORDED. qc_rubric_format reads the same key set out of verifier.py's
# SOURCE; this reads it out of what a run actually STORED. Two witnesses, deliberately, because
# the static read can be defeated: a verifier that assembles the dict through a helper
# (`_canon_project(detail)`) or any other indirection gives the AST reader nothing to see, and
# on a task where that happened the source check had to fall back to a key-name regex. The run
# artifacts are literal, so they cannot be read wrong.
#
# `rubric_pass` is the pre-rename spelling of `rubric_passed` and the one legacy alias worth
# naming: it is close enough to look right in a table (harbor prints whatever keys it is given,
# so a run carrying it displays a tidy "Rubric 1.000") while being invisible to every consumer
# that reads the canonical name.
CANON_REWARD_KEYS = ["reward", "tests_passed", "f2p_passed", "f2p_total",
                     "p2p_passed", "p2p_total", "rubric_passed"]
LEGACY_ALIASES = {"rubric_pass": "rubric_passed", "rubric_graded": "rubric_passed"}

EXPECT = {"Oracle": ("== 1.0", lambda r: r == 1.0, "#16 Gate - Oracle/Nop"),
          # Nop's predicate is None on purpose: it is NOT decided by the reward. See nop_gate().
          "Nop": ("all f2p fail, all p2p pass", None, "#16 Gate - Oracle/Nop"),
          "Trials": ("< 1.0", lambda r: r is not None and r < 1.0, "#14 Hardening - Difficulty")}


def nop_gate(rewards):
    """(ok, want, got) for nop, decided by the f2p/p2p COUNTS rather than the reward.

    WHY NOT `reward == 0.0`. reward is 0.0 whenever ANY f2p test fails, so it says nothing about
    the others: a nop scoring 0 is equally consistent with "every f2p failed" and with "three
    failed and the fourth passed on an empty submission". That fourth test is INERT - it cannot
    detect the bug, so the task grades nothing real while the gate looks green - and it is the
    defect class this whole file exists to catch. The counts settle it; the reward cannot, at any
    value. It also stops a rubric task being failed for a nonzero nop reward that came from the
    judge rather than from the tests.

    The counts are guaranteed present: qc_rubric_format fails `verifier.reward_json.keys` as a
    BLOCKING bundle-tier finding when verifier.py's write site omits any of the canonical seven.
    Absence is still refused rather than assumed away - an audit can be skipped, and a run killed
    before the verifier's atexit flush leaves the file short.
    """
    want = "all f2p fail, all p2p pass"
    if not isinstance(rewards, dict):
        return False, want, "no reward.json to read counts from"
    fp, ft = _count(rewards, "f2p_passed"), _count(rewards, "f2p_total")
    pp, pt = _count(rewards, "p2p_passed"), _count(rewards, "p2p_total")
    if None in (fp, ft, pp, pt):
        return False, want, "reward.json carries no readable f2p/p2p counts"
    got = f"f2p {fp}/{ft} passed, p2p {pp}/{pt} passed"
    if ft <= 0:
        return False, want, f"f2p_total={ft} - no f2p test ran, so nothing was measured"
    if fp:
        return False, want, f"{fp} of {ft} f2p test(s) PASS on an empty submission"
    if pp != pt:
        return False, want, f"{pt - pp} of {pt} p2p test(s) FAIL on nop - they are really f2p"
    return True, want, got


def gate_ok(run, reward, rewards):
    """(ok, want, got) for one run's gate row. Oracle and Trials turn on the reward; Nop does not.

    One function so check_run() and main()'s table cannot reach different verdicts about the same
    run - they used to share a lambda, and this keeps that property now that Nop needs the dict.
    """
    if run == "Nop":
        return nop_gate(rewards)
    want, fn, _dim = EXPECT[run]
    return bool(reward is not None and fn(reward)), want, f"reward = {reward}"

# WHICH TIER EACH RUN BELONGS TO. Oracle and nop are KEYLESS - the verifier runs unit tests and
# never calls a model - so they are reproducible before the trial is ever spent, and the QC skill
# can produce them itself. Trials needs a real model call, so everything derived from it is tier
# `trial` and must never be able to fail a pre-trial run.
RUN_TIER = {"Oracle": "gate", "Nop": "gate", "Trials": "trial"}
RUN_CATEGORY = {"Oracle": "gate", "Nop": "gate", "Trials": "hardening"}

problems = []
records = []       # structured findings for --emit-findings


def rec(fid, msg, sev, tier="gate", category="gate", dim=None, evidence=None, needs=None,
        run=None):
    """`run` names the run whose OUTPUT this was read from, if any.

    That is what lets the aggregator drop a finding once the run goes stale: a reading out of
    Oracle/Nop/Trials describes those files, so it stops being true the moment the bundle moves on.
    A finding NOT read from run output (a static read of verifier.py, say) leaves run=None and is
    never suppressed."""
    records.append({"id": fid, "msg": msg, "sev": sev, "tier": tier, "category": category,
                    "dim": dim, "evidence": evidence or [], "needs": needs, "run": run})


def load_json(path):
    try:
        return json.load(open(path))
    except Exception:
        return None


def trial_dir(run_path):
    # The newest trial dir, whatever its name (a nested task's are `<task-name>__*`) and whether
    # it sits directly in the run folder or inside a timestamped job dir. See qc_layout.
    if not os.path.isdir(run_path):
        return None
    return qc_layout.trial_dir(run_path)


def check_reward_keys(run, td, tier, cat):
    """Do the keys this run RECORDED match the canonical reward schema?

    Read from both places a run stores them - the container's reward.json and the rewards dict
    harbor recorded in result.json - because they can disagree: reward.json is written inside
    the container and result.json only after harbor parses the result.

    Severity is a plain FAIL and not blocking: the gate arithmetic still holds, the run is
    auditable, and the repair is a rename at the write site. What it costs is every downstream
    consumer that reads the canonical name - the platform's reward schema, and the runner's own
    post-run report, which refuses the legacy spelling on purpose so an unmigrated task cannot
    read as correct. The visible symptom is a run whose rubric WAS graded reporting no verdict.
    """
    for label, path, extract in (
            ("reward.json", os.path.join(td, "verifier", "reward.json"), lambda d: d),
            ("result.json", os.path.join(td, "result.json"),
             lambda d: (d.get("verifier_result") or {}).get("rewards") or {})):
        doc = load_json(path)
        if not doc:
            continue
        rewards = extract(doc)
        if not isinstance(rewards, dict) or not rewards:
            continue
        # Per-test outcomes (f2p::<name>) are an expected extra, not a schema violation.
        present = {k for k in rewards if isinstance(k, str) and "::" not in k}
        missing = [k for k in CANON_REWARD_KEYS if k not in present]
        if not missing:
            continue
        aliased = {a: c for a, c in LEGACY_ALIASES.items() if a in present and c in missing}
        note = ""
        if aliased:
            note = ("  MIGRATION: this run carries the OLD key(s) "
                    + ", ".join(f"`{a}` (now `{c}`)" for a, c in sorted(aliased.items()))
                    + ". Rename at the write site in tests/verifier.py and re-run; runs "
                      "recorded before the rename are not retroactively wrong.")
        problems.append(f"{run}: {label} is missing canonical reward key(s) "
                        f"{missing} [FAIL - Broken Structure]{note}")
        rec(f"{run.lower()}_reward_keys_noncanonical",
            f"{run} {label} is missing canonical reward key(s) {missing}; the schema is exactly "
            f"{CANON_REWARD_KEYS}.{note} [Fail - Broken Structure]", "FAIL",
            tier=tier, category="gate",
            evidence=[f"{label} keys: {sorted(present)}"], run=run)


def check_run(deliv, run):
    run_path = qc_layout.run_path(deliv, run)
    info = {"run": run, "reward_txt": None, "reward_json": None, "checksum": None,
            "absent": False}
    tier, cat = RUN_TIER[run], RUN_CATEGORY[run]
    # A RUN THAT DOES NOT EXIST YET IS NOT A FAILURE. This used to append to `problems`, which
    # made a sound bundle QC'd before any run report `Oracle/ folder missing` … `Trials/ folder
    # missing` as three hard [FAIL]s and a VERDICT of FAIL. Absence is OPEN - it says what has
    # not been measured, and `needs` says what would measure it.
    if not os.path.isdir(run_path):
        info["absent"] = True
        rec(f"{run.lower()}_absent", f"{run}/ has not been produced yet", "OPEN",
            tier=tier, category=cat)
        return info
    td = trial_dir(run_path)
    if td:
        # The counts Nop's gate turns on. Loaded here rather than inside check_reward_keys so
        # both the verdict and the table read the same dict off one parse.
        info["rewards"] = load_json(os.path.join(td, "verifier", "reward.json"))
    if not td:
        info["absent"] = True
        rec(f"{run.lower()}_absent", f"{run}/ holds no trial dir - nothing to read",
            "OPEN", tier=tier, category=cat)
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
            rec(f"{run.lower()}_recorded_no_reward",
                f"{run} run FAILED with {exc} - harbor recorded no reward. reward.txt is written "
                f"inside the container before harbor parses the result, so it does NOT show the "
                f"gate held. [Fail - Unauditable]", "FAIL", tier=tier, category="gate",
                evidence=[f"exception_type = {exc}"], run=run)
        elif res.get("verifier_result") is None:
            problems.append(f"{run}: result.json has no verifier_result - the run never "
                            f"completed. reward.txt cannot stand in for it. "
                            f"[FAIL - Unauditable]")
            info["failed"] = True
            rec(f"{run.lower()}_recorded_no_reward",
                f"{run} result.json has no verifier_result - the run never completed; reward.txt "
                f"cannot stand in for it. [Fail - Unauditable]", "FAIL", tier=tier,
                category="gate", run=run)
    check_reward_keys(run, td, tier, cat)
    # reward.txt vs result.json agreement
    if info["reward_txt"] is not None and info["reward_json"] is not None \
            and abs(info["reward_txt"] - info["reward_json"]) > 1e-9:
        problems.append(f"{run}: reward.txt ({info['reward_txt']}) != result.json reward "
                        f"({info['reward_json']})")
        rec(f"{run.lower()}_reward_disagreement",
            f"{run}: reward.txt disagrees with result.json [Fail - Unauditable]", "FAIL",
            tier=tier, category="gate",
            evidence=[f"reward.txt {info['reward_txt']} != result.json {info['reward_json']}"],
            run=run)
    # gate
    # Only harbor's own recorded reward counts. reward.txt is corroboration, not evidence.
    r = info["reward_json"]
    if r is None and not info.get("failed"):
        r = info["reward_txt"]
    _want, _fn, dim = EXPECT[run]
    okv, want, got = gate_ok(run, r, info.get("rewards"))
    if r is None:
        # Only reachable when the dir exists but carries no reward - genuine, not an absence.
        if not info["absent"]:
            problems.append(f"{run}: no reward found")
    elif not okv:
        problems.append(f"{run}: gate not satisfied - {got} (expected {want}) (v2 {dim})")
        # #16 is a gate defect; #14 (Trials < 1.0) is a hardening one. Booking them to the same
        # category would put "the model solved it" next to "the verifier is broken".
        gate_dim = ("Fail - Not Hard Enough" if run == "Trials" else "Fail - Gate Broken")
        # Nop's id is NOT `nop_reward_wrong`: its reward can be a perfectly good 0.0 while the
        # gate fails, so an id naming the reward would send a CB looking in the wrong place.
        fid = ("trial_not_hard_enough" if run == "Trials"
               else "nop_gate_unsatisfied" if run == "Nop"
               else f"{run.lower()}_reward_wrong")
        rec(fid, f"{run}: gate not satisfied - {got} (expected {want}) — v2 {dim} "
                 f"[{gate_dim}]",
            "FAIL", tier=tier, category=cat, dim=gate_dim,
            evidence=[f"{run}: {got}, expected {want}"], run=run)
    return info


def check_staleness(deliv, tasks):
    """Is a run older than the bundle it claims to describe?

    harbor's own `task_checksum` is computed INSIDE harbor - it is not importable here and
    mm_run.sh does not compute it - so it can only ever be compared run-to-run, never against the
    current Tasks/. mtime is the one signal available locally: if any file in Tasks/ is newer than
    a run's config.json, that run predates the bundle on disk and its reward describes something
    else. Trial-independent, and it catches the case run-to-run agreement cannot: ALL runs stale
    by the same edit.
    """
    if not os.path.isdir(tasks):
        return
    newest, newest_f = 0, None
    for dp, _dn, fn in os.walk(tasks):
        for f in fn:
            try:
                m = os.path.getmtime(os.path.join(dp, f))
            except OSError:
                continue
            if m > newest:
                newest, newest_f = m, os.path.relpath(os.path.join(dp, f), tasks)
    for run in ("Oracle", "Nop", "Trials"):
        # The JOB's config.json - one level down when harbor named the job dir itself.
        cfg = os.path.join(qc_layout.job_dir(qc_layout.run_path(deliv, run)), "config.json")
        if not os.path.isfile(cfg):
            continue
        # 2-minute tolerance: a run touches files as it starts, and an editor save a few seconds
        # before launching is not evidence of staleness. Sub-tolerance drift is still caught by
        # the task_checksum comparison, which is exact - the two checks cover each other.
        if newest > os.path.getmtime(cfg) + 120:
            drift = (newest - os.path.getmtime(cfg)) / 60.0
            problems.append(f"{run}: run predates the current Tasks/ by ~{drift:.0f} min "
                            f"(newest bundle file: {newest_f}) - the reward describes an older "
                            f"bundle [FAIL - Unauditable]")
            rec(f"{run.lower()}_stale",
                f"{run} predates the current Tasks/ by ~{drift:.0f} min, so its reward describes "
                f"an older bundle [Fail - Unauditable]", "FAIL",
                tier=RUN_TIER[run], category="gate",
                evidence=[f"newest bundle file: {newest_f}", f"{run}/config.json is older"],
                run=run)


def main():
    argv = list(sys.argv[1:])
    emit = None
    next_steps = "--next-steps" in argv
    if next_steps:
        argv.remove("--next-steps")
    if "--emit-findings" in argv:
        i = argv.index("--emit-findings")
        emit = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i:i + 2]
    if not argv:
        print(__doc__)
        sys.exit(1)
    deliv = argv[0]
    if os.path.isdir(os.path.join(deliv, "deliverables")):
        deliv = os.path.join(deliv, "deliverables")
    # Accept a bare Tasks/ too: the checks want the deliverables root, but every doc example and
    # every CB points at Tasks/. Guessing wrong here is what produced phantom "folder missing".
    # A task dir in the nested layout (Tasks/<any-name>/) resolves to the same root.
    try:
        deliv, tasks = qc_layout.resolve_layout(deliv)
    except qc_layout.AmbiguousLayout as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    tasks = tasks or os.path.join(deliv, "Tasks")

    infos = [check_run(deliv, run) for run in ("Oracle", "Nop", "Trials")]
    present = [i for i in infos if not i["absent"]]

    # checksum agreement (proves the runs used the same Tasks/ bundle). Only over runs that
    # EXIST - comparing against an absent run is not a mismatch, it is nothing.
    checks = {i["run"]: i["checksum"] for i in infos if i["checksum"]}
    if len(set(checks.values())) > 1:
        problems.append(f"task_checksum MISMATCH across runs: {checks} - runs are stale or were "
                        f"produced against a different Tasks/ bundle => treat as Unauditable")
        # If Trials is one of the disagreeing parties the defect is only knowable post-trial.
        tier = "trial" if "Trials" in checks else "gate"
        rec("gate_checksum_mismatch",
            "task_checksum disagrees across runs - they were produced against different Tasks/ "
            "bundles [Fail - Unauditable]", "FAIL", tier=tier, category="gate",
            evidence=[f"{k} = {v[:12]}" for k, v in checks.items()])
        # A clear majority identifies WHICH run is the odd one out, so that run can be marked
        # stale and everything read out of it stops being reported as independently broken. A
        # 1-1 split identifies nothing, so nothing is marked - guessing would be worse than
        # leaving the mismatch as the only statement.
        from collections import Counter
        tally = Counter(checks.values())
        top, n_top = tally.most_common(1)[0]
        if n_top > 1 and list(tally.values()).count(n_top) == 1:
            for _run, _cs in checks.items():
                if _cs == top:
                    continue
                rec(f"{_run.lower()}_stale",
                    f"{_run} task_checksum {_cs[:12]} disagrees with the majority "
                    f"({top[:12]}), so it was produced against a different Tasks/ bundle "
                    f"[Fail - Unauditable]", "FAIL", tier=RUN_TIER[_run], category="gate",
                    evidence=[f"{_run} = {_cs[:12]}", f"majority = {top[:12]}"], run=_run)
    check_staleness(deliv, tasks)

    print(f"\nVarmint Sheriffs gate validation (QC v2) - {os.path.abspath(deliv)}\n")
    print("| run    | reward.txt | result.json | gate | task_checksum |")
    print("|--------|-----------|-------------|------|---------------|")
    for i in infos:
        # Same rule as check_run: a run that errored has no recorded reward, and the
        # container-side reward.txt must not be allowed to render it as OK.
        r = i["reward_json"]
        if r is None and not i.get("failed"):
            r = i["reward_txt"]
        okv, want, got = gate_ok(i["run"], r, i.get("rewards"))
        if i["absent"]:
            verdict = "—"          # not run yet: neither OK nor FAIL
        elif i.get("failed"):
            verdict = "ERR"
        else:
            verdict = "OK" if (r is not None and okv) else "FAIL"
        cs = (i["checksum"] or "")[:12]
        print(f"| {i['run']:<6} | {str(i['reward_txt']):>9} | {str(i['reward_json']):>11} "
              f"| {verdict:<4} | {cs} |")
    print()
    _nop = next((i for i in infos if i["run"] == "Nop" and not i["absent"]), None)
    if _nop:
        _ok, _want, _got = gate_ok("Nop", None, _nop.get("rewards"))
        print(f"Nop gate turns on the COUNTS, not the reward: {_got}")
    absent = [i["run"] for i in infos if i["absent"]]
    if absent:
        print(f"NOT RUN YET: {', '.join(absent)} - reported as OPEN, not as a failure. "
              f"Oracle/Nop are keyless and reproducible now; Trials costs a model call.")

    if problems:
        print("PROBLEMS:")
        for p in problems:
            print(f"  [FAIL] {p}")
    elif present:
        print("No static problems: rewards agree, gate holds, checksums match.")

    if not next_steps:
        return
    print("\n--- Now REPRODUCE the gate yourself (KEYLESS - no API key/anonymizer needed) ---")
    print("Oracle+Nop run unit-tests only (no model call), so reproduce them in your OWN Cursor")
    print(f"with just Docker + harbor 0.18. Pointed at {tasks}:\n")
    mm = "~/.claude/skills/mmswe-runner/mm_run.sh"
    print(f"  bash {mm} \"{tasks}\" oracle   # expect 1.0  (keyless) -> v2 #16")
    print(f"  bash {mm} \"{tasks}\" nop      # expect every f2p to FAIL and every p2p to "
          f"PASS (keyless) -> v2 #16")
    print(f"  bash {mm} \"{tasks}\" oracle   # run AGAIN -> still 1.0 (idempotency -> v2 #13 Determinism)")
    print("  # no mmswe-runner skill? raw harbor does the same, still keyless:")
    print(f"  #   harbor run -p \"{tasks}\" -a oracle -e docker -o \"{deliv}\" --job-name Oracle --yes")
    print(f"  #   harbor run -p \"{tasks}\" -a nop    -e docker -o \"{deliv}\" --job-name Nop    --yes")
    print("  # The agent TRIAL needs a model endpoint (anonymizer proxy in the sandbox); do NOT")
    print("  # re-run it in review -> validate the shipped Trials/ run above + `harbor analyze` below.")
    print("\nYour reproduced Oracle=1.0 and your reproduced Nop counts (f2p_passed=0 of "
          "f2p_total, p2p_passed==p2p_total) must match the submitted run, and the "
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
    print(f"  bash {mm} \"{tasks}\" analyze    # -> harbor analyze <Trials/> (the whole dir, not one trial dir)")
    print("      -> agent solved-vs-cheated feeds v2 #14; instruction sufficiency feeds v2 #15/#3")
    print("      CAVEAT: harbor analyze sometimes errors - retry ONCE before blaming the task.")




# ---------------------------------------------------------------- per-test nop check
# ADDED in MM_SWE_QC. An f2p test that PASSES on an empty submission cannot detect the bug (a
# golden-image test with no baseline auto-passes, for instance). The task then grades nothing real
# while every reward looks healthy. This is the defect class that got through review before, so it
# is a hard check, not advisory.
#
# WHICH AGGREGATE PROVES WHAT. This check used to demand per-test `f2p::` keys and hard-FAIL
# without them, on the stated grounds that "a 0.0 aggregate on nop is NOT sufficient". That is true
# of `reward`, which is 0.0 whenever ANY f2p fails and so says nothing about the others - and false
# of `f2p_passed`, which is a different key. `f2p_passed == 0` with `f2p_total == N` says no f2p
# test passed on the empty submission, which is exactly the claim this check exists to establish,
# for all N of them. Per-test detail adds something only when `0 < f2p_passed < f2p_total`: there
# the aggregate proves an inert test EXISTS and only the `f2p::` keys can name it.
#
# The demand was also unmeetable in practice. template/tests/verifier_reward_block.py calls the
# per-test keys optional ("if wanted"), the check needs Nop/ on disk to run at all, and during
# authoring Nop does not exist yet - so it reports OPEN, the audit passes, and the first machine
# that can execute it is the reviewer's. Contributors following the template to the letter shipped
# bundles that passed every gate they could run and failed one they structurally could not.
#
# So the requirement is now on the EVIDENCE, not on its format: prove inertness per-test if the
# keys are there, in aggregate if they are not, and FAIL only when neither is readable.
def _count(d, key):
    """`d[key]` as an int, or None when it is absent or not a number.

    reward.json is a flat map of numbers by contract, but this reads what a run actually STORED,
    and a bundle whose verifier wrote a string here is exactly the case that must not be mistaken
    for a proof. bool is rejected explicitly: it is an int subclass, and `f2p_passed: false` would
    otherwise read as a perfectly good 0.
    """
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return int(v)


def _nop_inertness_from_aggregate(d):
    """Settle inertness from the four count keys when no per-test `f2p::` keys were written.

    Returns the `problems` lines to append. The verdicts here are the same three the per-test path
    reaches, with one difference that has to stay visible in the wording: when the aggregate proves
    an inert test exists, it cannot name WHICH, so the finding says so and asks for the keys.
    """
    f_pass, f_total = _count(d, "f2p_passed"), _count(d, "f2p_total")
    p_pass, p_total = _count(d, "p2p_passed"), _count(d, "p2p_total")
    problems = []

    if f_pass is None or f_total is None:
        rec("gate_f2p_inertness",
            "Nop reward.json carries neither per-test f2p outcomes (f2p:: keys) nor readable "
            "f2p_passed/f2p_total counts, so an inert f2p test cannot be detected either way. "
            "Emit the canonical seven flat keys (template/tests/verifier_reward_block.py) "
            "[Fail - Gate Broken]", "FAIL", tier="gate", category="gate", run="Nop")
        return problems + ["Nop reward.json has no per-test f2p:: keys AND no readable "
                           "f2p_passed/f2p_total counts - cannot detect inert tests"]
    if f_total <= 0:
        # Not an inertness verdict: there is nothing to be inert. Declared-vs-run test names are
        # somebody else's finding, so this only records that the proof could not be made.
        rec("gate_f2p_inertness",
            f"Nop reward.json reports f2p_total={f2p_total_repr(f_total)}, so no f2p test ran and "
            "inertness cannot be established. Check the declared f2p names resolve "
            "[Fail - Gate Broken]", "FAIL", tier="gate", category="gate", run="Nop")
        return problems + [f"Nop reward.json reports f2p_total={f_total} - no f2p test ran, so "
                           "inertness cannot be established"]
    if f_pass > 0:
        # The aggregate PROVES an inert test exists; only the per-test keys can say which one.
        rec("gate_f2p_inert",
            f"{f_pass} of {f_total} f2p test(s) PASS on an empty submission, so they cannot detect "
            f"the bug and the task grades nothing real. Which one(s) is not recoverable from the "
            f"aggregate - add the per-test f2p::<name> keys to reward.json to name them "
            f"[Fail - Gate Broken]", "FAIL", tier="gate", category="gate",
            evidence=[f"Nop f2p_passed={f_pass}, f2p_total={f_total}"], run="Nop")
        problems.append(f"INERT f2p test(s) - {f_pass} of {f_total} PASS on an empty submission, "
                        f"so they cannot detect the bug and the task grades nothing real. Add the "
                        f"per-test f2p::<name> keys to reward.json to name which.")

    if p_pass is not None and p_total is not None and p_pass < p_total:
        rec("gate_p2p_mislabeled",
            f"{p_total - p_pass} p2p test(s) FAIL on nop - they are really f2p. Which one(s) is "
            f"not recoverable from the aggregate; add the per-test p2p::<name> keys to name them "
            f"[Fail - Bad Test IDs]", "FAIL", tier="gate", category="fix_tests",
            evidence=[f"Nop p2p_passed={p_pass}, p2p_total={p_total}"], run="Nop")
        problems.append(f"p2p test(s) FAILING on nop - {p_total - p_pass} of {p_total} are "
                        f"mislabeled and are really f2p. Add the per-test p2p::<name> keys to "
                        f"reward.json to name which.")

    if not problems:
        print(f"  [ok] no f2p test passes on nop (f2p_passed=0 of {f_total}, in aggregate); "
              f"no p2p fails on nop")
        rec("gate_f2p_inertness",
            f"no f2p test passes on nop (f2p_passed=0 of {f_total}) and no p2p fails, established "
            f"from the aggregate counts. Per-test f2p:: keys were not written; they are optional "
            f"and would only be needed to NAME an inert test, of which there are none",
            "OK", tier="gate", category="gate")
    return problems


def f2p_total_repr(n):
    """`f2p_total` as it should read in a finding: the number, or `missing` for a negative one."""
    return str(n) if n >= 0 else "missing"


def check_nop_per_test(root):
    import glob
    problems = []
    nop = os.path.join(root, "Nop")
    if not os.path.isdir(nop):
        # Nop is KEYLESS and the QC skill reproduces it itself, so this is OPEN with a cheap
        # remedy - never a failure of the task.
        rec("gate_f2p_inertness", "per-test f2p inertness not checked - Nop/ has not been run",
            "OPEN", tier="gate", category="gate")
        return []
    rj = None
    _td = qc_layout.trial_dir(nop)
    if _td and os.path.isfile(os.path.join(_td, "verifier", "reward.json")):
        rj = os.path.join(_td, "verifier", "reward.json")
    for cand in ([] if rj else glob.glob(os.path.join(nop, "**", "reward.json"), recursive=True)):
        rj = cand; break
    if not rj:
        rec("verifier_no_reward_json",
            "Nop/ has no reward.json - per-test f2p outcomes unavailable, so an inert f2p test "
            "cannot be detected. The verifier must write it (rubric-template snippet). "
            "[Fail - Gate Broken]", "FAIL", tier="gate", category="gate", run="Nop")
        return ["Nop/ has no reward.json - per-test f2p outcomes unavailable. The task's "
                "verifier must write reward.json (see the rubric-template verifier snippet); "
                "without it an inert f2p test cannot be detected."]
    try:
        d = json.load(open(rj))
    except Exception as exc:
        rec("gate_reward_json_unparseable", f"Nop reward.json unparseable: {exc} "
            "[Fail - Unauditable]", "FAIL", tier="gate", category="gate", run="Nop")
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
        # This was worded "NOTE:" but appended to `problems`, which the printer prefixes with
        # [FAIL] and the exit code counts - so it read as a note and behaved as a failure. It IS
        # a failure (it aborts the trial), so the wording is what was wrong, not the severity.
        # Same id as qc_judge's static read of verifier.py: one defect, two witnesses.
        problems.append("reward.json uses the legacy NESTED f2p/p2p maps. harbor parses "
                        "reward.json as dict[str, float] and prefers it over reward.txt, so a "
                        "nested value aborts the trial with a ValidationError while reward.txt "
                        "still gets written - the run looks scored but nothing is stored. "
                        "Flatten to f2p::<name> = 1.0/0.0. [FAIL - Gate Broken]")
        rec("reward_json_nonnumeric",
            "reward.json uses the legacy NESTED f2p/p2p maps - harbor parses it as "
            "dict[str, float] and prefers it to reward.txt, so this aborts the run with a "
            "ValidationError while reward.txt is still written. [Fail - Gate Broken]", "FAIL",
            tier="gate", category="gate",
            evidence=["observed in Nop/ reward.json as a nested map"], run="Nop")
    if not f2p:
        return problems + _nop_inertness_from_aggregate(d)
    inert = [k for k, v in f2p.items() if v]
    if inert:
        problems.append("INERT f2p test(s) - these PASS on an empty submission, so they cannot "
                        "detect the bug and the task grades nothing real:")
        problems += [f"    - {k}" for k in inert]
        rec("gate_f2p_inert",
            f"{len(inert)} f2p test(s) PASS on an empty submission, so they cannot detect the bug "
            f"and the task grades nothing real [Fail - Gate Broken]", "FAIL", tier="gate",
            category="gate", evidence=inert[:6], run="Nop")
    mislabeled = [k for k, v in (p2p or {}).items() if v is False]
    if mislabeled:
        problems.append("p2p test(s) FAILING on nop - mislabeled, these are really f2p:")
        problems += [f"    - {k}" for k in mislabeled]
        rec("gate_p2p_mislabeled",
            f"{len(mislabeled)} p2p test(s) FAIL on nop - they are really f2p "
            f"[Fail - Bad Test IDs]", "FAIL", tier="gate", category="fix_tests",
            evidence=mislabeled[:6], run="Nop")
    if not problems:
        print(f"  [ok] every f2p test fails individually on nop ({len(f2p)} checked); "
              f"no p2p fails on nop")
        rec("gate_f2p_inertness",
            f"every f2p test fails individually on nop ({len(f2p)} checked); no p2p fails on nop",
            "OK", tier="gate", category="gate")
    return problems




# ------------------------------------------------------------- trial model check
# ADDED in MM_SWE_QC. The trial must be run on the agreed model. Two independent records
# exist and both are checked:
#   * config.json  agent.model_name          - what was REQUESTED
#   * result.json  agent_info.model_info     - what the agent REPORTED actually running
# A disagreement between them matters as much as a wrong model: it means the run did not use
# what the config claims, so the reward cannot be attributed to the agreed model.
EXPECTED_MODEL = os.environ.get("MM_EXPECTED_MODEL", "claude-opus-5-5")


def _norm_model(m):
    """'anthropic/claude-opus-5-5' -> 'claude-opus-5-5'. Provider prefix is not identity."""
    if not m:
        return None
    return str(m).strip().split("/")[-1].lower()


def check_trial_model(root):
    import glob
    problems = []
    trials = qc_layout.run_path(root, "Trials")
    if not os.path.isdir(trials):
        rec("trial_model_mismatch", "trial model not confirmed - no trial has been run", "OPEN",
            tier="trial", category="gate")
        return []

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
        rec("trial_model_unrecorded",
            "Trials/ records no model (no agent.model_name, no agent_info.model_info) - the "
            "reward cannot be attributed to " + EXPECTED_MODEL + " [Fail - Unauditable]",
            "FAIL", tier="trial", category="gate", run="Trials")
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
    if problems:
        rec("trial_model_mismatch",
            "the trial did not run on the agreed model, so its reward does not describe "
            + want + " [Fail - Unauditable]", "FAIL", tier="trial", category="gate",
            evidence=problems[:4], run="Trials")
    else:
        print(f"  [ok] trial ran on {actual or requested} (expected {want})")
        rec("trial_model_mismatch", f"trial ran on {actual or requested} (expected {want})", "OK",
            tier="trial", category="gate")
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
    trials = qc_layout.run_path(root, "Trials")
    if not os.path.isdir(trials):
        rec("trial_not_hard_enough",
            "#14 hardening (difficulty + the 90-minute clause) not decidable - no trial has been "
            "run", "OPEN", tier="trial", category="hardening")
        return []
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
        rec("trial_90min_clause",
            f"trial duration unknown ({how}) - the 90-minute clause cannot be applied", "OPEN",
            tier="trial", category="hardening", needs="a trajectory with timing")
        return []
    mins = secs / 60.0
    print(f"  [note] trial duration ~{mins:.0f} min (CANDIDATE - derived from {how}; "
          f"confirm in the trajectory)")
    if reward is None:
        # A trial that recorded no reward leaves #14 genuinely undecided. Returning [] silently
        # made the dimension vanish from the report, which reads as "checked and clean".
        rec("trial_not_hard_enough",
            f"#14 difficulty undecided - the trial ran ~{mins:.0f} min but recorded no reward, so "
            f"there is nothing to compare against the 90-minute clause", "OPEN",
            tier="trial", category="hardening", needs="a trial that records a reward",
            evidence=[f"duration ~{mins:.0f} min, derived from {how}"])
        return []
    if reward >= 1.0 and secs > NINETY_MIN:
        print(f"  [ok] trial scored {reward} but ran ~{mins:.0f} min > 90 - acceptable via the "
              f"timeout clause. Record that explicitly; it is not a normal pass.")
        return []
    if reward >= 1.0:
        rec("trial_not_hard_enough",
            f"trial scored {reward} in ~{mins:.0f} min (<= 90) - the model SOLVED it inside the "
            f"budget, so the task does not stump [Fail - Not Hard Enough]", "FAIL",
            tier="trial", category="hardening",
            evidence=[f"reward {reward}", f"~{mins:.0f} min, derived from {how}"], run="Trials")
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
    trials = qc_layout.run_path(root, "Trials")
    tasks = qc_layout.find_task_dir(root) or os.path.join(root, "Tasks")
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
    rec("trial_timeout_unauditable",
        f"trial ended in {exc} after {mins} against an agent budget of "
        f"{('%.0f min' % (budget/60)) if budget else 'unknown'} - under 90 min, so the timeout "
        f"clause does not apply and there is no reward to audit [Fail - Unauditable]", "FAIL",
        tier="trial", category="gate", run="Trials")
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


def _print_probs(probs):
    for x in probs:
        print(f"  [FAIL] {x}" if not x.startswith("    ") else x)
    return len(probs)


def _mm_swe_qc_extra(root):
    n = _print_probs(check_nop_per_test(root))
    print("\n--- trial model (MM_SWE_QC) ---")
    n += _print_probs(check_trial_model(root))
    print("\n--- 90-minute trial rule (MM_SWE_QC) ---")
    tprobs = check_trial_time(root) + check_timeout_clause(root)
    _reconcile_timeout(root)
    n += _print_probs(tprobs)
    return n


SEV_MAP = {"FAIL": "FAIL", "CANDIDATE": "CANDIDATE", "OPEN": "OPEN", "OK": "OK",
           "NON-FAIL": "NON-FAIL"}


def export_findings(path):
    """Translate gate records into the shared Finding model.

    Every record already carries its own tier, so the aggregator can demote the trial-tier ones to
    OPEN at a pre-trial phase without this script needing to know which phase it is running at.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from qc_common import Finding, dump_findings, normalize_dim
    out = []
    for r in records:
        dim = r["dim"] or normalize_dim(r["msg"])
        out.append(Finding(r["id"], r["msg"], SEV_MAP[r["sev"]], category=r["category"],
                           rubric_dim=dim, tier=r["tier"], needs=r["needs"],
                           evidence=r["evidence"], source=["qc_gate"],
                           from_run=r.get("run")))
    dump_findings(out, path)
    return len(out)


if __name__ == "__main__":
    _argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    _emit = None
    if "--emit-findings" in sys.argv:
        _i = sys.argv.index("--emit-findings")
        _emit = sys.argv[_i + 1] if _i + 1 < len(sys.argv) else None
        _argv = [a for a in _argv if a != _emit]
    main()
    # MM_SWE_QC: the per-test inertness check is the one a reward aggregate cannot do.
    _root = _argv[0] if _argv else "."
    if os.path.basename(os.path.normpath(_root)) == "Tasks":
        _root = os.path.dirname(os.path.normpath(_root)) or "."
    print("\n--- per-test inertness (MM_SWE_QC) ---")
    _extra = _mm_swe_qc_extra(_root)
    if _emit:
        _n = export_findings(_emit)
        print(f"  wrote {_n} finding(s) -> {_emit}")
    # Exit non-zero only on real problems. `problems` no longer collects absent runs, so a bundle
    # with no runs yet exits 0 here instead of failing on three "folder missing" lines.
    sys.exit(1 if (_extra or problems) else 0)
