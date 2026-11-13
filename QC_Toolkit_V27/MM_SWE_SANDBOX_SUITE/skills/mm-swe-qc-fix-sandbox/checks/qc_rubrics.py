#!/usr/bin/env python3
"""MM SWE QC - rubric quality against the Rubric Quality Definitions appendix.

Grades tests/rubrics.json against the 11 named issues (Major / Moderate / Minor), tallies
them, and applies the appendix FAIL thresholds.

SEVERITY MODEL. The appendix ties four severities to ProjectBench weights (3 = must-follow,
1 = nice-to-have). MM SWE rubrics are UNWEIGHTED and every criterion is mandatory, so we grade
at the strict tier - as if every criterion were weight 3. Flip STRICT_TIER to False for the
milder reading. Two appendix issues cannot exist here and are dropped: "weight error (3<->1
swap)" and "Miscategorized Category" (no weight / category fields in rubrics.schema/v1).

THRESHOLDS (denominator = criteria the CB wrote, i.e. excluding the always-pass stub):
    FAIL if  >5% carry a Major, OR >15% Moderate-or-Major, OR >25% any issue.
At MM SWE criteria counts this is effectively zero-tolerance: with 2 criteria a single Major
is 50%. That is intended - a Major rubric defect fails a correct submission.

WHAT THIS SCRIPT CAN AND CANNOT DECIDE. Five issues are decidable from the rubric text alone
and are reported as findings. Six need the criterion read against the code and each other;
for those the script emits a grader request per issue (--emit-graders) for an LLM pass, and
otherwise lists them as MANUAL. It never guesses a semantic verdict.

Usage:
    qc_rubrics.py <Tasks dir | rubrics.json> [--emit-graders DIR] [--json OUT]
Stdlib only.
"""
import argparse, json, os, re, sys

STRICT_TIER = True          # MM SWE: every criterion mandatory -> grade as weight 3
# AGREED DENOMINATOR: contributor-written criteria only; the always-pass stub is EXCLUDED.
# The stub is a declaration ("no rubric needed"), not a criterion under evaluation - it can
# never fail, so grading it is meaningless, and counting it would DILUTE the denominator and
# make a real defect proportionally easier to pass. A stub shipped ALONGSIDE real criteria is
# self-contradictory and is reported as a defect rather than silently counted.
# The QC rubric CSV words the bands as "at least 5% / 15% / 25%", so the comparator is >=.
# The add-on appendix writes them as ">5% / >15% / >25%". They differ ONLY at exact equality,
# which is reachable at MM SWE criteria counts: N=4 with one issue and N=8 with two both land
# on exactly 25%. `>=` is the stricter reading and matches the instrument reviewers are graded
# against, so a creation-side tool using `>` would pass a task that review then fails. Set
# INCLUSIVE_BANDS = False to restore the appendix's strictly-greater reading.
INCLUSIVE_BANDS = True

# ---------------------------------------------------------------- the 11 issues
# id -> (title, severity_strict, severity_mild, decidable_statically)
ISSUES = {
    "not_self_contained": ("Criteria Not Self-Contained", "Major", "Major", True),
    "incorrect":          ("Incorrect Criterion",          "Major", "Major", False),
    "inaccurate_source":  ("Inaccurate Source / Asset",    "Major", "Major", True),
    "contradiction":      ("Active Contradiction",         "Major", "Major", False),
    "overfitting":        ("Overfitting",                  "Major", "Minor", False),
    "not_atomic":         ("Criteria Not Atomic",          "Major", "Moderate", True),
    "underfitting":       ("Underfitting",                 "Moderate", "Moderate", False),
    "negative_framing":   ("Negative Framing",             "Moderate", "Moderate", True),
    "missing":            ("Missing Criterion",            "Major", "Moderate", False),
    "vague":              ("Subjective / Vague Criterion", "Moderate", "Minor", True),
    "overlapping":        ("Overlapping / Redundant Criteria", "Minor", "Minor", False),
}
RANK = {"Major": 3, "Moderate": 2, "Minor": 1}

# ------------------------------------------------------------------- heuristics
# A criterion that defers to the prompt/instruction/golden instead of stating the standard.
# NOTE: the judge is given instruction.md, so such a criterion still PASSES at run time -
# the defect is invisible in results and must be caught here.
DEFERS = re.compile(r"\b(the (prompt|instruction|task|issue|ticket|request)s?\b|"
                    r"as (requested|specified|described|instructed)|per the (prompt|instruction)|"
                    r"the (golden|reference) (fix|solution|implementation)|"
                    r"(project|repo|repository|codebase)'?s? (conventions?|style|standards?|patterns?)|"
                    r"other (components?|files?|modules?)|elsewhere in the (repo|codebase))", re.I)
# Needs a rendered UI, not code.
# Needs a rendered UI, not code. Deliberately narrow: words like "pixel" or "px" are CODE
# signals (a literal width) and must not trip this - only phrases that require actually
# looking at a rendered page do.
UI_ONLY = re.compile(r"\b(overflow(s|ing)?\b|looks? (right|correct|good|off)|appears? (correct|right)|"
                     r"visually|on (mobile|desktop|a small screen)|renders? (correctly|properly)|"
                     r"is visible|alignment looks|pixel[- ]perfect)", re.I)
VAGUE = re.compile(r"\b(properly|appropriately|correctly|good|nicely|reasonabl[ey]|clean(ly)?|"
                   r"polished|readable|maintainable|idiomatic|sensible|adequate|acceptable|"
                   r"well[- ](written|structured|organi[sz]ed)|as needed|if necessary)\b", re.I)
NEGATIVE = re.compile(r"\b(must not|should not|shouldn't|cannot|can't|does not|doesn't|"
                      r"do not|don't|never|no longer|without|avoids?|refrains?)\b", re.I)
CONJ = re.compile(r";|\band\b|\balso\b|\bas well as\b|\bin addition\b|\bplus\b", re.I)
FILEREF = re.compile(r"\b([A-Za-z0-9_.\-/]+\.(?:js|jsx|ts|tsx|css|scss|py|java|rb|go|rs|"
                     r"html|json|md|yml|yaml))\b")

findings = []      # (criterion_id|None, issue_key, severity, message)
notes = []
EXTRA = []         # structural/threshold findings for --emit-findings
EMIT = None        # --emit-findings path, set by main()
_GRADED_CLEAN = set()   # semantic issues a grader returned clean, so they are no longer pending


def add(cid, key, msg, severity=None):
    title, strict, mild, _ = ISSUES[key]
    sev = severity or (strict if STRICT_TIER else mild)
    findings.append((cid, key, sev, f"{title}: {msg}"))


def note(msg):
    notes.append(msg)


# ------------------------------------------------------------------- discovery
# AGREED (2026-08-03): `rubrics.schema/v1` is the canonical id for MM SWE. Older tasks ship
# `projectbench.rubrics/v1`, so it is still ACCEPTED (rewriting a valid file would be worse)
# but flagged as legacy so new tasks converge on one id.
CANONICAL_SCHEMA = "rubrics.schema/v1"
LEGACY_SCHEMAS = {"projectbench.rubrics/v1"}
KNOWN_SCHEMAS = {CANONICAL_SCHEMA} | LEGACY_SCHEMAS


def locate(path):
    if os.path.isfile(path):
        return path, os.path.dirname(os.path.dirname(os.path.abspath(path)))
    # Flat Tasks/task.toml or nested Tasks/<any-name>/task.toml - see qc_layout.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from qc_layout import find_task_dir, AmbiguousLayout
    try:
        found = find_task_dir(path)
    except AmbiguousLayout as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    for cand in ([os.path.join(found, "tests", "rubrics.json")] if found else []) + [
                 os.path.join(path, "tests", "rubrics.json"),
                 os.path.join(path, "Tasks", "tests", "rubrics.json")]:
        if os.path.isfile(cand):
            return cand, os.path.dirname(os.path.dirname(cand))
    return None, None


STUB_IDS = {"always_pass", "always-pass", "alwayspass"}
STUB_TEXT = re.compile(r"written in english|no rubric needed", re.I)


def is_stub(c, doc=None):
    """The always-pass placeholder. NO LONGER A LEGAL SHAPE - recognised only so it can be called
    out (see the `if not real` branch) and kept out of the quality denominator.

    Keyed on the id first (the convention), with a text fallback so a stub with a renamed id is
    still recognised rather than graded as a real - and always-failing - criterion.
    """
    if str(c.get("id", "")).strip().lower() in STUB_IDS:
        return True
    if STUB_TEXT.search(str(c.get("criterion", ""))):
        return True
    if doc and len(doc.get("criteria") or []) == 1 and STUB_TEXT.search(str(doc.get("description", ""))):
        return True
    return False


# ------------------------------------------------------- static (decidable) checks
def static_checks(criteria, changed_files):
    for c in criteria:
        cid = c.get("id", "?")
        text = str(c.get("criterion", "")).strip()
        if is_stub(c):
            continue

        # Major - Not Self-Contained: defers elsewhere, or needs a rendered UI.
        m = DEFERS.search(text)
        if m:
            add(cid, "not_self_contained",
                f"defers to something outside the code ({m.group(0)!r}) instead of stating the "
                f"standard inline. The judge sees only the criterion, the diff and the changed "
                f"files - never the prompt - so this scores 0 and fails a correct submission.")
        m = UI_ONLY.search(text)
        if m and not FILEREF.search(text):
            add(cid, "not_self_contained",
                f"reads as a rendered-UI check ({m.group(0)!r}); a rubric must be decidable from "
                f"code. Re-phrase around the code signal (a colour value, a unit, a class).")

        # Major - Inaccurate Source / Asset: a named file must exist in the change.
        for ref in set(FILEREF.findall(text)):
            if changed_files is None:
                note(f"[{cid}] references {ref!r}; changed-file list unavailable, verify by hand")
            elif not any(ref.lower() == os.path.basename(p).lower() or p.lower().endswith(ref.lower())
                         for p in changed_files):
                add(cid, "inaccurate_source",
                    f"references {ref!r}, which is not among the files the golden change touches "
                    f"({sorted({os.path.basename(p) for p in changed_files})}).")

        # Moderate - Negative Framing.
        if NEGATIVE.search(text) and c.get("is_positive") is not False:
            add(cid, "negative_framing",
                f"negative phrasing ({NEGATIVE.search(text).group(0)!r}). State the expected "
                f"behaviour positively, or set is_positive=false deliberately.")

        # Major(strict) - Not Atomic. Only *unrelated* constraints count, so this is a candidate.
        if len(CONJ.findall(text)) >= 2:
            add(cid, "not_atomic",
                f"{len(CONJ.findall(text))} conjunctions - may bundle unrelated constraints. "
                f"NOT an issue if they are interdependent; confirm by reading.")

        # Moderate(strict) - Subjective / Vague.
        m = VAGUE.search(text)
        if m:
            add(cid, "vague", f"unmeasurable qualifier ({m.group(0)!r}) with no explicit "
                              f"definition inside the criterion.")


# ------------------------------------------------- semantic graders (LLM, per issue)
SEMANTIC = ["incorrect", "contradiction", "overfitting", "underfitting", "missing", "overlapping"]
GRADER_BRIEF = {
    "incorrect": "Does the criterion check something that does NOT align with what the task asks, "
                 "contain a factual error, or contradict the instruction? (e.g. the task asks for "
                 "a red button and the criterion demands green.)",
    "contradiction": "Across the whole criteria SET, are any two mutually incompatible - a "
                     "submission satisfying one necessarily fails the other? Report pairs.",
    "overfitting": "Is the criterion so specific it would reject a valid alternative implementation? "
                   "Naming an exact property AND value (color: red) rejects RGB/HEX equivalents. "
                   "Specific patterns are acceptable only as examples ('e.g.'). If the repo's logic "
                   "genuinely requires that exact location, it is NOT overfitting. Rule of thumb: "
                   "if it would pass a valid alternative, it may be Vague instead.",
    "underfitting": "Is it so broad it would accept genuinely poor code alongside good code? "
                    "A deliberately general criterion that still discriminates ('adds responsiveness') "
                    "is VALID - we want rubrics that allow multiple approaches.",
    "missing": "Is something the task asks for, and the tests do NOT cover, left ungraded? "
               "Not an issue if a criterion would trivially pass for any submission.",
    "overlapping": "Across the SET, is any criterion fully encompassed by another, or do several "
                   "check the same underlying standard? Count each overlap group once.",
}


def emit_graders(outdir, criteria, changed_files, instruction, diff):
    os.makedirs(outdir, exist_ok=True)
    payload = [{"id": c["id"], "criterion": c["criterion"]} for c in criteria if not is_stub(c)]
    (open(os.path.join(outdir, "criteria.json"), "w")).write(json.dumps(payload, indent=2))
    if instruction:
        open(os.path.join(outdir, "instruction.md"), "w").write(instruction)
    if diff:
        open(os.path.join(outdir, "golden.diff"), "w").write(diff)
    for key in SEMANTIC:
        title, strict, mild, _ = ISSUES[key]
        sev = strict if STRICT_TIER else mild
        scope = "the criteria SET as a whole" if key in ("contradiction", "overlapping", "missing") \
                else "EACH criterion independently"
        open(os.path.join(outdir, f"GRADER_{key}.md"), "w").write(f"""# Rubric QC grader - {title} ({sev})

Grade **{scope}** for exactly one issue: **{title}**.

## What counts
{GRADER_BRIEF[key]}

## Inputs in this directory
- `criteria.json` - the rubric criteria the contributor wrote ({len(payload)}).
- `instruction.md` - the task as given (present only if the bundle ships it).
- `golden.diff` - the reference fix, for judging whether a criterion is factually right.
  (This is a REVIEW-time input. The runtime judge never sees the golden.)

## Rules
- Judge ONLY {title}. Other defects are other graders' jobs; do not report them.
- Cite evidence: the criterion id, and the exact phrase you are objecting to.
- If nothing qualifies, say so explicitly. Do not invent findings to look thorough.

## Output - write ONLY this JSON to `verdict_{key}.json`
```json
{{"issue": "{key}", "severity": "{sev}",
  "findings": [{{"criterion_ids": ["id1"], "evidence": "...", "why": "...", "fix": "..."}}]}}
```
`criterion_ids` carries one id for per-criterion issues, or the group for set-level ones.
""")
    return len(payload)


# ------------------------------------------------------------------------ report
def tally_and_report(n_real, as_json=None):
    per_crit = {}
    for cid, key, sev, msg in findings:
        per_crit.setdefault(cid, []).append((key, sev, msg))
    # "do NOT double-count an item": one worst severity per criterion
    worst = {cid: max((RANK[s] for _, s, _ in v), default=0) for cid, v in per_crit.items()}
    n_major = sum(1 for r in worst.values() if r == 3)
    n_modplus = sum(1 for r in worst.values() if r >= 2)
    n_any = sum(1 for r in worst.values() if r >= 1)

    def pct(x):
        return (100.0 * x / n_real) if n_real else 0.0

    op = (lambda v, t: v >= t) if INCLUSIVE_BANDS else (lambda v, t: v > t)
    sym = ">=" if INCLUSIVE_BANDS else ">"
    verdict, reasons, boundary = "PASS", [], []
    for label, count, thr in (("Major", n_major, 5), ("Moderate+", n_modplus, 15),
                              ("Any", n_any, 25)):
        v = pct(count)
        if op(v, thr):
            verdict = "FAIL"
            reasons.append(f"{label} {count}/{n_real} = {v:.1f}% {sym} {thr}%")
        if abs(v - thr) < 1e-9:
            boundary.append(f"{label} sits EXACTLY on {thr}%")

    print("\n-- Rubric quality findings (appendix: Major / Moderate / Minor)")
    if not findings:
        print("     [ok] no statically-detectable rubric issues")
    for sev in ("Major", "Moderate", "Minor"):
        for cid, key, s, msg in findings:
            if s == sev:
                print(f"  [{sev:8}] [{cid}] {msg}")
    for m in notes:
        print(f"  [note    ] {m}")

    graded = {k for _, k, _, _ in findings if k in SEMANTIC} | set(_GRADED_CLEAN)
    pending = [k for k in SEMANTIC if k not in graded]
    if pending:
        print("\n-- Semantic issues still UNGRADED (thresholds below are therefore provisional):")
        for k in pending:
            t, strict, mild, _ = ISSUES[k]
            print(f"  [manual  ] {t} ({strict if STRICT_TIER else mild})")
    else:
        print("\n-- All six semantic issues have been graded; the tally below is complete.")

    print(f"\nTALLY over {n_real} contributor-written criterion(s) "
          f"(AGREED: the always-pass stub is excluded from the denominator):")
    print(f"  Major        {n_major}  ({pct(n_major):.1f}%)   threshold {sym}5%")
    print(f"  Moderate+    {n_modplus}  ({pct(n_modplus):.1f}%)   threshold {sym}15%")
    print(f"  Any          {n_any}  ({pct(n_any):.1f}%)   threshold {sym}25%")
    if boundary:
        print("  BOUNDARY: " + "; ".join(boundary) + ". The two source documents disagree at "
              "exact equality (CSV 'at least' vs appendix '>'), so say so explicitly in the eval.")
    print(f"\nSTATIC VERDICT: {verdict}" + (f"  ({'; '.join(reasons)})" if reasons else ""))
    if verdict == "PASS" and pending:
        print(f"  NOTE: PASS covers the statically-decidable issues only. {len(pending)} semantic "
              f"issue(s) are still ungraded and can still fail the task - grade them "
              f"(--emit-graders, then --verdicts DIR) before signing off.")
    # The appendix THRESHOLD verdict is the authoritative rubric outcome; the individual issues
    # are its evidence. Recording them separately is what stops a Major being double-counted -
    # once as its own FAIL and again inside the percentage band it produced.
    EXTRA.append({"id": "rubric_thresholds", "sev": "FAIL" if verdict == "FAIL" else "OK",
                  "msg": (f"rubric quality thresholds {verdict} over {n_real} contributor-written "
                          f"criterion(s)"),
                  "evidence": reasons or [f"Major {n_major} · Moderate+ {n_modplus} · Any {n_any}"],
                  "needs": None})
    for k in pending:
        t, strict, mild, _ = ISSUES[k]
        EXTRA.append({"id": f"rubric_semantic_{k}", "sev": "OPEN",
                      "msg": f"{t} ({strict if STRICT_TIER else mild}) not graded",
                      "evidence": [], "needs": "grader"})
    if as_json:
        json.dump({"verdict": verdict, "n_criteria": n_real,
                   "counts": {"major": n_major, "moderate_plus": n_modplus, "any": n_any},
                   "thresholds": {"major": 5, "moderate_plus": 15, "any": 25},
                   "strict_tier": STRICT_TIER, "reasons": reasons,
                   "findings": [{"criterion": c, "issue": k, "severity": s, "message": m}
                                for c, k, s, m in findings],
                   "semantic_pending": SEMANTIC}, open(as_json, "w"), indent=2)
        print(f"  wrote {as_json}")
    return 1 if verdict == "FAIL" else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--emit-graders", metavar="DIR")
    ap.add_argument("--json", metavar="OUT")
    # Adjudicated semantic verdicts. The six semantic issues cannot be decided statically, so
    # without a way to feed a grader's answer back in, the thresholds are only ever applied to
    # the static half - and a task failing purely on Overfitting would still read PASS here.
    ap.add_argument("--major", action="append", default=[], metavar="ID")
    ap.add_argument("--moderate", action="append", default=[], metavar="ID")
    ap.add_argument("--minor", action="append", default=[], metavar="ID")
    ap.add_argument("--verdicts", metavar="DIR",
                    help="a grader output dir; reads verdict_<issue>.json written by the graders")
    ap.add_argument("--emit-findings", metavar="OUT")
    a = ap.parse_args()
    global EMIT
    EMIT = a.emit_findings

    rp, tasks = locate(a.path)
    if not rp:
        # POLICY CHANGE. A task with no rubric layer is now CORRECT, not "missing rubrics": the
        # layer has exactly two legal shapes, and "no rubric at all" is one of them (Mode B).
        # This used to be a FAIL, which failed sound bundles - GoldenRubricFormat2 ships no
        # rubrics.json by design. qc_rubric_format.py owns the shape decision; there is simply
        # no CONTENT for this check to grade, which is not a defect.
        print(f"no tests/rubrics.json under {a.path} - Mode B (no rubric layer).")
        print("  [ok] nothing to grade here. The shape decision belongs to qc_rubric_format.py;")
        print("       if this task DOES need a rubric, that check is what says so.")
        EXTRA.append({"id": "rubrics_absent", "sev": "OK",
                      "msg": "no rubric layer - legal (Mode B); no rubric content to grade. "
                             "Whether this task SHOULD have one is qc_rubric_format's call",
                      "evidence": [], "needs": None})
        return 0
    print(f"\nMM SWE QC - rubric quality\nrubrics.json = {rp}")
    try:
        doc = json.load(open(rp))
    except Exception as exc:
        print(f"  [Major   ] rubrics.json does not parse: {exc}", file=sys.stderr)
        EXTRA.append({"id": "rubrics_parse", "sev": "FAIL",
                      "msg": f"tests/rubrics.json does not parse as JSON: {exc}",
                      "evidence": [], "needs": None})
        return 2

    sch = doc.get("schema")
    # printed immediately, not queued as a note: the stub-only path returns before the notes
    # are flushed, and a legacy schema is exactly as worth knowing on a stub rubric.
    if sch and sch not in KNOWN_SCHEMAS:
        print(f"  [note] schema {sch!r} is not one of {sorted(KNOWN_SCHEMAS)} - confirm intended")
    elif sch in LEGACY_SCHEMAS:
        print(f"  [note] schema {sch!r} is LEGACY; {CANONICAL_SCHEMA!r} is canonical for MM SWE. "
              f"Accepted as-is; new tasks should use the canonical id.")
    criteria = [c for c in (doc.get("criteria") or []) if isinstance(c, dict)]
    real = [c for c in criteria if not is_stub(c, doc)]
    if not criteria:
        print("  [Major   ] rubrics.json has no criteria")
        EXTRA.append({"id": "rubrics_no_criteria", "sev": "FAIL",
                      "msg": "rubrics.json has no criteria", "evidence": [], "needs": None})
        return 2
    if not real:
        # POLICY CHANGE. The always-pass stub is no longer a sanctioned shape - it is a BLOCKING
        # structural defect, and qc_rubric_format.py is what reports it as such. This check used
        # to print "[ok] ... Valid when the task is fully covered by behavioral tests", which is
        # how a stub came to pass QC: it cannot fail any submission, yet it makes rubric_passed read
        # 1 exactly as though a real rubric had been satisfied, so it fabricates a graded result.
        # A stub is unfalsifiable on top of that - with a zero denominator every percentage band
        # below passes automatically, so a MISSING criterion cannot surface in the arithmetic.
        print("  [Major   ] always-pass stub only - NOT a legal shape. The stub declares 'no rubric")
        print("             needed', so the rubric layer must be STRIPPED, not stubbed: delete")
        print("             tests/rubrics.json and tests/judge.py and drop \"rubric_file\" from")
        print("             tests/config.json. Leave the --rubric gate in verifier.py and the")
        print("             guarded judge block in test.sh in place.")
        print("             Reported as a BLOCKING Fail by qc_rubric_format.py.")
        # SHARED ID with qc_rubric_format on purpose. One defect, two witnesses: dedup() in
        # qc_common merges findings keyed on (id, category), keeping the worst severity and
        # recording the second check as "also seen by" - which is how the reward.json shape defect
        # already behaves across qc_judge and qc_gate. Emitting a differently-named finding for the
        # same stub would read as two defects and, worse, one of them non-blocking.
        EXTRA.append({"id": "rubfmt_rubrics_stub_only", "sev": "FAIL",
                      "msg": "always-pass stub only - an all-pass rubric grades nothing yet reports "
                             "rubric_passed=1 as though a real rubric had been satisfied. Strip the "
                             "rubric layer instead of stubbing it",
                      "evidence": [f"criteria: {[c.get('id') for c in criteria]}",
                                   f"description: {str(doc.get('description', ''))[:80]!r}"],
                      "needs": None})
        return 2

    # the golden change: file list for source checks, diff for the graders
    changed, diff = None, None
    fp = os.path.join(tasks or "", "solution", "fix.patch")
    if os.path.isfile(fp):
        diff = open(fp, errors="replace").read()
        changed = sorted({m for m in re.findall(r"^diff --git a/\S+ b/(\S+)", diff, re.M)})
    instruction = None
    ip = os.path.join(tasks or "", "instruction.md")
    if os.path.isfile(ip):
        instruction = open(ip, errors="replace").read()

    if real and len(real) != len(criteria):
        stubs = [c.get("id") for c in criteria if is_stub(c, doc)]
        add(str(stubs[0] if stubs else "stub"), "incorrect",
            f"the always-pass stub {stubs} ships ALONGSIDE {len(real)} real criterion(s). The "
            f"stub declares 'no rubric needed'; shipping both contradicts that. Remove the stub - "
            f"it is excluded from the denominator either way, so it only muddies the file.",
            severity="Moderate")

    static_checks(real, changed)

    # adjudicated verdicts, from flags and/or the graders' own JSON
    for sev, ids in (("Major", a.major), ("Moderate", a.moderate), ("Minor", a.minor)):
        for cid in ids:
            findings.append((cid, "incorrect", sev, f"adjudicated {sev} (supplied on the "
                                                    f"command line)"))
    if a.verdicts and os.path.isdir(a.verdicts):
        for key in SEMANTIC:
            vf = os.path.join(a.verdicts, f"verdict_{key}.json")
            if not os.path.isfile(vf):
                continue
            try:
                obj = json.load(open(vf))
            except Exception as exc:
                note(f"verdict_{key}.json unreadable ({exc})")
                continue
            title, strict, mild, _ = ISSUES[key]
            sev = obj.get("severity") or (strict if STRICT_TIER else mild)
            for f in obj.get("findings") or []:
                for cid in (f.get("criterion_ids") or ["(set)"]):
                    findings.append((cid, key, sev,
                                     f"{title}: {f.get('why') or f.get('evidence') or 'graded'}"))
            if not (obj.get("findings") or []):
                note(f"grader {key}: no findings")
            _GRADED_CLEAN.add(key)
    if a.emit_graders:
        n = emit_graders(a.emit_graders, criteria, changed, instruction, diff)
        print(f"  wrote {len(SEMANTIC)} grader request(s) for {n} criterion(s) -> {a.emit_graders}")
    return tally_and_report(len(real), a.json)


def export_findings(path):
    """Translate rubric findings into the shared model.

    Individual issues are CANDIDATEs carrying their appendix severity (Major/Moderate/Minor) in
    `rubric_severity`; the FAIL, if any, belongs to `rubric_thresholds`. That mirrors how the
    appendix actually works - a single issue does not fail a rubric, a percentage band does - and
    it keeps one defect from being counted twice.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from qc_common import Finding, dump_findings, CANDIDATE, OPEN, OK, FAIL
    RUBRIC_DIM = "Fail - Rubric Quality"
    out, by_issue = [], {}
    for cid, key, sev, msg in findings:
        by_issue.setdefault(key, {"sev": sev, "msgs": []})
        by_issue[key]["msgs"].append(f"[{cid}] {msg}")
        if RANK.get(sev, 0) > RANK.get(by_issue[key]["sev"], 0):
            by_issue[key]["sev"] = sev
    for key, d in by_issue.items():
        title = ISSUES[key][0] if key in ISSUES else key
        out.append(Finding(f"rubric_{key}", f"{title} — {len(d['msgs'])} criterion(s) affected",
                           CANDIDATE, category="rubric_judge", rubric_dim=RUBRIC_DIM,
                           evidence=d["msgs"], rubric_severity=d["sev"],
                           action="authoring", source=["qc_rubrics"]))
    for n in notes:
        sev = OK if "no findings" in n else OPEN
        out.append(Finding("rubric_note", n, sev, category="rubric_judge",
                           rubric_dim=RUBRIC_DIM, source=["qc_rubrics"],
                           needs=None if sev == OK else "manual read"))
    for e in EXTRA:
        out.append(Finding(e["id"], e["msg"], {"FAIL": FAIL, "OPEN": OPEN, "OK": OK}[e["sev"]],
                           category="rubric_judge", rubric_dim=RUBRIC_DIM,
                           evidence=e.get("evidence"), needs=e.get("needs"),
                           action="authoring" if e["sev"] == FAIL else None,
                           source=["qc_rubrics"]))
    dump_findings(out, path)
    return len(out)


if __name__ == "__main__":
    rc = main()
    if EMIT:
        n = export_findings(EMIT)
        print(f"  wrote {n} finding(s) -> {EMIT}")
    sys.exit(rc)
