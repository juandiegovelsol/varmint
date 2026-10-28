#!/usr/bin/env python3
"""Step 0.55 - verify the task's RUBRICS (`tests/rubrics.json`) - NEW in v3.

Usage:
    python3 check_rubrics.py "task_<taskId>/deliverables"    # the four-folder root
    python3 check_rubrics.py "path/to/Tasks"                 # a bare Tasks/
    python3 check_rubrics.py "path/to/Tasks/<task_id>"       # the bundle itself (V2)
    python3 check_rubrics.py "path/to/Tasks/<task_id>/tests/rubrics.json"   # a lone rubrics file

Layouts: V2 (TASK101+) nests the bundle at Tasks/<task_id>/; V1 kept it directly in Tasks/.

NEW COMPONENT (v3). Guidelines V3 add a rubric layer: some hardening targets can't be
caught by a behavioral test but *can* be judged by reading the candidate's code (e.g. a
button colour change - visible in code, several valid ways to write it, so a test would be
source-matching). Those go in `tests/rubrics.json` and are scored by an LLM judge, SEPARATELY
from the keyless f2p/p2p gate. This script statically verifies that file against the V3
"Rules for rubrics" (Step III-C of the Attempter Guidelines V3):

  * FILE       rubrics.json exists, is non-empty, parses as JSON.          [FAIL - Missing/Broken Rubrics]
  * SCHEMA     `schema` is a recognised rubrics schema value.              [FAIL - Bad Rubric Schema]
  * TASK       `task` == task_id in task.toml (== config.json task_id),    [FAIL - Rubric Task Mismatch]
               so every file in the bundle carries the same id.
  * CRITERIA   `criteria` is a non-empty list; each item has a unique      [FAIL - Malformed Criteria]
               non-empty `id` and non-empty `criterion`; `is_positive`
               (if present) is a bool.
  * RULES      per-criterion heuristics for the six style rules (atomic,   (candidates, not [FAIL])
               specific/objective, self-contained, positive wording,
               non-prescriptive, sensible grouping).
  * PLACEHOLDER detect the shipped always-pass stub and remind the         (candidate)
               reviewer to confirm the task is genuinely test-covered.

Heuristics only flag CANDIDATES (confirm by hand) unless marked `[FAIL]`. The one rule this
script CANNOT check is **Accurate** ("verify the criterion is factually true of your golden
solution") - that needs a human read of `solution/` against each criterion. It is printed as a
mandatory manual step. Standard library only; never runs the judge or the verifier.
"""
import json, sys, os, re

# Schema strings seen in the wild + the one written in the guidelines doc. A value outside
# this set is a hard fail (a typo would silently break the judge).
KNOWN_SCHEMAS = {"projectbench.rubrics/v1", "rubrics.schema/v1"}

# The shipped stub (guidelines "If the task needs no rubrics ...").
PLACEHOLDER_IDS = ("always_pass", "always-pass")
PLACEHOLDER_TEXT = "written in english"

# Rule heuristics ---------------------------------------------------------------
NEGATIVE = re.compile(r"\b(must not|should not|shouldn't|cannot|can't|does not|doesn't|"
                      r"do not|don't|never|no longer|without)\b", re.I)
VAGUE = re.compile(r"\b(properly|appropriately|correctly|good|nicely|reasonabl[ey]|clean(ly)?|"
                   r"as expected|as needed|well|robust(ly)?|gracefully|make sense)\b", re.I)
# words that usually signal the criterion is about CODE (so it should name a file/function)
CODE_HINT = re.compile(r"\b(function|method|class|variable|constant|import|module|file|"
                       r"component|css|selector|attribute|prop|parameter|argument|"
                       r"returns?|assigns?|defines?|declares?|calls?)\b", re.I)
# a file/function anchor: path-ish token, dotted name, or Foo()/foo_bar identifier
ANCHOR = re.compile(r"(`[^`]+`|\b[\w./-]+\.(?:py|js|jsx|ts|tsx|java|kt|kts|css|scss|go|rb|rs|c|cpp|h)\b"
                    r"|\b\w+\(\)|\b\w+_\w+\b|\b[a-z]+[A-Z]\w+\b)")
# multiple independent clauses -> possible non-atomic
CONJ = re.compile(r";|\band\b|\balso\b|\bas well as\b|\bin addition\b|\bplus\b", re.I)


def read(path):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def load_json(path):
    txt = read(path)
    if txt is None:
        return None, "missing"
    try:
        return json.loads(txt), None
    except Exception as e:
        return None, str(e)


def toml_value(txt, key):
    if not txt:
        return None
    m = re.search(rf'^\s*{key}\s*=\s*"([^"]*)"', txt, re.M)
    return m.group(1) if m else None


BUNDLE_MARKERS = ("task.toml", "instruction.md", "tests", "solution", "environment")


def looks_like_bundle(d):
    return any(os.path.exists(os.path.join(d, m)) for m in BUNDLE_MARKERS)


def task_dirs(tasks):
    """Every bundle in a Tasks/ folder: Tasks/ itself (V1) or each Tasks/<task_id>/ (V2)."""
    if looks_like_bundle(tasks):
        return [tasks]
    return sorted(os.path.join(tasks, d) for d in os.listdir(tasks)
                  if os.path.isdir(os.path.join(tasks, d)) and looks_like_bundle(os.path.join(tasks, d)))


def locate_bundle(root):
    """The bundle (the folder holding task.toml) for the deliverables root, Tasks/, or the
    bundle itself: Tasks/<task_id>/ in V2 (TASK101+), Tasks/ in V1. None if absent/ambiguous."""
    tasks = root if os.path.basename(root) == "Tasks" else os.path.join(root, "Tasks")
    if os.path.isfile(os.path.join(root, "task.toml")) or (
            not os.path.isdir(tasks) and looks_like_bundle(root)):
        return root
    if not os.path.isdir(tasks):
        return None
    found = task_dirs(tasks)
    if len(found) > 1:
        print(f"warning: {len(found)} task bundles under {tasks} - pass the one to check: "
              f"{[os.path.basename(f) for f in found]}", file=sys.stderr)
    return found[0] if len(found) == 1 else None


def locate(root):
    """Return (bundle_dir, rubrics_path)."""
    root = os.path.normpath(root)
    if os.path.isfile(root) and root.endswith(".json"):
        tasks = os.path.dirname(os.path.dirname(root))  # <bundle>/tests/rubrics.json
        return (tasks if os.path.isfile(os.path.join(tasks, "task.toml")) else None), root
    tasks = locate_bundle(root)
    return tasks, (os.path.join(tasks, "tests", "rubrics.json") if tasks else None)


findings = []      # (level, msg)   level in {FAIL, WARN, INFO, MANUAL}
fail_count = 0


def add(level, msg):
    global fail_count
    findings.append((level, msg))
    if level == "FAIL":
        fail_count += 1


# --------------------------------------------------------------- criterion rules
def check_criterion(idx, item, seen_ids):
    where = f"criteria[{idx}]"
    if not isinstance(item, dict):
        add("FAIL", f"{where} is not an object")
        return
    cid = item.get("id")
    crit = item.get("criterion")
    label = f"criterion `{cid}`" if cid else where

    # structural (hard)
    if not cid or not str(cid).strip():
        add("FAIL", f"{where} has an empty/missing `id`")
    elif cid in seen_ids:
        add("FAIL", f"duplicate criterion id `{cid}` (ids must be unique)")
    seen_ids.add(cid)
    if not crit or not str(crit).strip():
        add("FAIL", f"{label} has an empty/missing `criterion` text")
        return
    if "is_positive" in item and not isinstance(item["is_positive"], bool):
        add("FAIL", f"{label}: `is_positive` must be a boolean, got {item['is_positive']!r}")

    text = str(crit)
    low = text.lower()
    is_positive = item.get("is_positive", True)

    # placeholder stub
    if (cid in PLACEHOLDER_IDS or (cid and cid.startswith("always_pass"))
            or PLACEHOLDER_TEXT in low):
        add("INFO", f"{label} is the shipped ALWAYS-PASS placeholder - only valid if the task "
                    f"is genuinely 100% covered by behavioral tests. Confirm no code-only visual "
                    f"change was left un-graded; if one was, a real rubric is missing.")
        return  # style rules don't apply to the stub

    # positive wording
    if NEGATIVE.search(text) and is_positive is not False:
        add("WARN", f"{label}: negative phrasing ({NEGATIVE.search(text).group(0)!r}) but "
                    f"`is_positive` is not false. Rule: describe the behavior positively and set "
                    f"`is_positive=false`, don't write a 'must not'.")
    # specific & objective
    if VAGUE.search(text):
        add("WARN", f"{label}: vague/subjective wording ({VAGUE.search(text).group(0)!r}) - make "
                    f"it a measurable yes/no (Rule: Specific & objective).")
    # names a file/function when it judges code
    if CODE_HINT.search(text) and not ANCHOR.search(text):
        add("WARN", f"{label}: judges code but names no specific file/function/selector - add the "
                    f"anchor (Rule: Specific & objective / not response-specific).")
    # atomic
    if len(CONJ.findall(text)) >= 2 or low.count(" and ") >= 2:
        add("WARN", f"{label}: multiple conjunctions - may fold >1 check into one criterion "
                    f"(Rule: Atomic). OK only if the parts always fail together (Rule: Grouping).")
    # overly prescriptive: a quoted exact identifier is fine, but 'named `x`' pins one impl
    if re.search(r"\bnamed\s+`?\w+`?", low) or re.search(r"\bcalled\s+`?\w+`?", low):
        add("WARN", f"{label}: pins a specific name ('named/called X') - phrase around the "
                    f"property so an equally-valid differently-named fix still passes (Rule: "
                    f"Avoid overly prescriptive).")
    # self-contained (very rough): extremely short criteria rarely carry enough context
    if len(text.split()) < 5:
        add("WARN", f"{label}: very short ({len(text.split())} words) - may not be self-contained "
                    f"(a judge with only this text + the code must be able to decide).")


# --------------------------------------------------------------------- main
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    tasks, rpath = locate(sys.argv[1])

    print(f"\nVarmint Sheriffs rubric verification (v3.1) - {os.path.abspath(sys.argv[1])}")
    print(f"task bundle = {tasks or 'NOT FOUND'}")
    print(f"rubrics.json = {rpath or 'NOT FOUND'}\n")

    # FILE
    if not rpath or not os.path.exists(rpath):
        add("FAIL", "tests/rubrics.json is MISSING. v3 requires it in every bundle (a real rubric, "
                    "or the always-pass stub if fully test-covered). [FAIL - Missing/Broken Rubrics]")
        _report()
        return
    if os.path.getsize(rpath) == 0:
        add("FAIL", "tests/rubrics.json is EMPTY. [FAIL - Missing/Broken Rubrics]")
        _report()
        return
    data, err = load_json(rpath)
    if err:
        add("FAIL", f"tests/rubrics.json does not parse as JSON: {err}. [FAIL - Missing/Broken Rubrics]")
        _report()
        return

    # SCHEMA
    schema = data.get("schema")
    if not schema:
        add("FAIL", "`schema` key missing. [FAIL - Bad Rubric Schema]")
    elif schema not in KNOWN_SCHEMAS:
        add("FAIL", f"`schema` = {schema!r} is not a recognised value {sorted(KNOWN_SCHEMAS)} - a "
                    f"typo silently breaks the judge. [FAIL - Bad Rubric Schema]")
    else:
        add("INFO", f"schema = {schema!r} (recognised)")

    # TASK id consistency (rubrics.task == task.toml.task_id == config.json.task_id)
    rubric_task = data.get("task")
    toml_id = toml_value(read(os.path.join(tasks, "task.toml")), "task_id") if tasks else None
    conf, _ = load_json(os.path.join(tasks, "tests", "config.json")) if tasks else (None, None)
    conf_id = (conf or {}).get("task_id")
    if not rubric_task:
        add("FAIL", "`task` key missing - must equal task_id `{owner}__{repo}-{issue}-mm`. "
                    "[FAIL - Rubric Task Mismatch]")
    else:
        ids = {("rubrics.json", rubric_task), ("task.toml", toml_id), ("config.json", conf_id)}
        distinct = {v for _, v in ids if v}
        if len(distinct) > 1:
            add("FAIL", f"task_id disagrees across the bundle: "
                        f"rubrics.json={rubric_task!r}, task.toml={toml_id!r}, "
                        f"config.json={conf_id!r}. [FAIL - Rubric Task Mismatch]")
        else:
            add("INFO", f"task id `{rubric_task}` matches task.toml/config.json")

    # CRITERIA
    criteria = data.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        add("FAIL", "`criteria` must be a non-empty list. [FAIL - Malformed Criteria]")
        _report()
        return
    seen = set()
    for i, item in enumerate(criteria):
        check_criterion(i, item, seen)

    real = [c for c in criteria if isinstance(c, dict)
            and not (str(c.get("id", "")).startswith("always_pass")
                     or c.get("id") in PLACEHOLDER_IDS
                     or PLACEHOLDER_TEXT in str(c.get("criterion", "")).lower())]
    add("INFO", f"{len(criteria)} criterion(s): {len(real)} real, "
                f"{len(criteria) - len(real)} placeholder.")

    # ACCURATE - the one rule this script can't verify
    add("MANUAL", "ACCURATE (manual): read `solution/fix.patch` and confirm EACH real criterion is "
                  "factually true of the golden - the golden must satisfy every rubric, or oracle "
                  "would fail the judge. This script cannot check it.")
    add("MANUAL", "USE-A-RUBRIC (manual): each real criterion should cover a code-visible change "
                  "with multiple valid implementations (colour, spacing, class, attribute, copy). A "
                  "rubric must NOT stand in for a render-only check the code can't signal.")

    _report()


LEVEL_ORDER = {"FAIL": 0, "WARN": 1, "MANUAL": 2, "INFO": 3}
LEVEL_TAG = {"FAIL": "[FAIL]", "WARN": "[check]", "MANUAL": "[manual]", "INFO": "[ok]"}


def _report():
    print("-- Rubric findings (v3 Step 0.55)")
    for level, msg in sorted(findings, key=lambda f: LEVEL_ORDER[f[0]]):
        print(f"     {LEVEL_TAG[level]:>8} {msg}")
    warns = sum(1 for l, _ in findings if l == "WARN")
    print(f"\nSUMMARY: {fail_count} hard [FAIL], {warns} style candidate(s) to confirm by hand. "
          f"A rubric [FAIL] is a Structure-class defect (the judge can't score the task); the "
          f"style candidates map to the V3 'Rules for rubrics' - confirm each, then verify "
          f"ACCURATE against solution/ by hand. This audits rubric CONTENT; run check_judge.py "
          f"(Step 7.6) to audit the judge MECHANICS (the rubric-template wiring in tests/).")


if __name__ == "__main__":
    main()
