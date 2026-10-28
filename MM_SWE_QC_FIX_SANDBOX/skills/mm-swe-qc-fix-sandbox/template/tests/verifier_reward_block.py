# Canonical reward writer + --rubric gate. Proven against a real harbor run.
# verifier.py carries TASK-SPECIFIC logic, so this is a PROPOSAL to merge by hand.
#
# CRITICAL - reward.json MUST be a FLAT map of numbers. harbor parses it as
# VerifierResult.rewards: dict[str, float] and takes it in PREFERENCE to reward.txt.
# A nested dict, list, string or None raises a pydantic ValidationError that aborts the
# trial BEFORE any reward is recorded - while reward.txt still gets written inside the
# container, so the run looks scored when harbor in fact stored nothing. Per-test
# outcomes therefore ride along as `f2p::<name>` / `p2p::<name>` = 1.0/0.0 entries, and
# the rubric verdict as `rubric_pass` = 1 pass / 0 fail / -1 unavailable.

REWARD_JSON = "/logs/verifier/reward.json"
RUBRIC_JSON = "/logs/verifier/rubric.json"

def write_reward(value, tests_passed=None, f2p=None, p2p=None, rubric=None):
    """reward.txt stays a BARE FLOAT in {0.0, 0.5, 1.0}; reward.json carries the detail.

    reward.json MUST be a FLAT map of numbers. harbor parses it as dict[str, float|int]
    (VerifierResult.rewards) and takes it in PREFERENCE to reward.txt, so a nested object,
    a null or a list aborts the whole trial with a pydantic ValidationError before any
    reward is recorded -- reward.txt still gets written inside the container, which makes
    the run look scored when harbor in fact stored nothing.

    Per-test outcomes are therefore encoded as `f2p::<name>` / `p2p::<name>` entries
    (1.0 pass, 0.0 otherwise) instead of nested maps, so the detail an inert-test check
    needs survives in a shape harbor accepts. Only "reward" is read as the trial's score;
    the rest ride along as extra reward_stats entries.
    """
    os.makedirs(os.path.dirname(REWARD_PATH), exist_ok=True)
    with open(REWARD_PATH, "w") as handle:
        handle.write(f"{value}\n")

    detail = {"reward": value,
              "tests_passed": value if tests_passed is None else tests_passed}
    if f2p is not None:
        detail["f2p_passed"] = sum(1 for v in f2p.values() if v)
        detail["f2p_total"] = len(f2p)
    if p2p is not None:
        detail["p2p_passed"] = sum(1 for v in p2p.values() if v)
        detail["p2p_total"] = len(p2p)
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
        with open(REWARD_JSON, "w") as handle:
            json.dump(detail, handle, indent=2)
    except Exception as exc:
        print(f"WARNING: could not write {REWARD_JSON}: {exc}", file=sys.stderr)
    print(f"\nREWARD: {value}")


# --- in main(), before reading report paths -------------------------------------
#     argv = sys.argv[1:]
#     rubric = None
#     if "--rubric" in argv:
#         i = argv.index("--rubric")
#         value = argv[i + 1].strip() if i + 1 < len(argv) else ""
#         argv = argv[:i] + argv[i + 2:]
#         rubric = value if value in ("pass", "fail") else None
#     report_paths = argv
#
# --- the gate: the rubric can ONLY withhold a 1.0 --------------------------------
#     if tests_passed >= 1.0 and rubric == "fail":
#         reward = 0.5
#     else:
#         reward = tests_passed      # rubric None -> tests-only, NEVER 0
