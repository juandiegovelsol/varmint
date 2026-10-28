# Evaluation - Task `<taskId>` (v3.1)

Follow `review_process_v3_1.md`. Data source: `task_<taskId>/deliverables/` (four folders).
Verdict legend: **P** = Pass (5) · **NF** = Non-Fail (3, only #3 and #6) · **F** = Fail (2) ·
**U** = Un-auditable (1) · **N/A**. Assess **locally** - download the four directories, inspect,
run docker, patch, and test the code; do **not** rely on the sandbox.

- **Reviewer:**
- **Date:**
- **harbor version (`harbor --version`, expect 0.18.x):**
- **Task id (`task.toml`):**
- **task_type:**
- **Final decision:** Accept / Revise / Reject - (one-line rationale)

---

## Step 0.5 - Mechanical pre-check output (`review_checks.py`)

```
(paste review_checks.py output here)
```

- **A (v2 #2 packaging/layout):**
- **B (v2 #1 bundle files; + #4 poster decode):**
- **D (v2 #8 golden-fix source-only scope):**
- **F (v2 #10 f2p/p2p ids):**
- **H (v2 #5 task_type value):**
- **I (v2 #6 evidence chain):**
- **R (v3 rubrics present/parse; full audit -> Step 0.55):**

## Step 0.55 - Rubric verification (`check_rubrics.py`) - v3

```
(paste check_rubrics.py output here)
```

- **FILE / SCHEMA / TASK / CRITERIA (any [FAIL]?):**
- **Style rules (atomic / specific / self-contained / positive / not-prescriptive / grouping):**
- **ACCURATE (manual - each real criterion true of `solution/fix.patch`?):**
- **Right tool (manual - code-visible property, not a render-only check?):**
- **Placeholder only? (if so, is the task genuinely 100% test-covered?):**

## Step 7.6 - Judge-mechanics verification (`check_judge.py`) - v3.1

```
(paste check_judge.py output here)
```

- **JUDGE_FILE (judge.py present, compiles, template markers):**
- **NO_CREDS (task.toml keyless - no [verifier.env] / ANTHROPIC_* / JUDGE_MODEL):**
- **CONFIG (`"rubric_file": "rubrics.json"`):**
- **TEST_SH (invokes judge.py, passes --rubric, keeps `|| echo ""`):**
- **VERIFIER (parses --rubric, writes reward.json, gates 1.0 -> 0.5):**
- **NO_SHADOW (no tests/ file named after a stdlib module):**
- **Behavioural (manual - judge request appeared under verifier/judge/; oracle `rubric: "pass"` after rescore):**

## Step 0.6 - Gate reproduction (`check_gate.py` + manual re-run)

```
(paste check_gate.py output here)
```

- **Submitted rewards:** Oracle ___ / Nop ___ / Trials ___
- **task_checksum agreement (all 3 equal?):**
- **Independently re-run:** Oracle ___ (expect 1.0) / Nop ___ (expect 0.0)
- **Idempotent on 2nd oracle run? (feeds #13):**
- **Reproduced == submitted?:**

## Step 0.7 - harbor helper commands (aids, not verdicts)

### `mm_run.sh <Tasks/<task_id>> check`  (harbor check)
```
(paste check output here)
```
- **Test fairness / "Behavior in Task Description" (feeds #9):** (any flag? is the behavior shown in the IMAGE? if yes -> tests fair, #9 Pass)

### `mm_run.sh <Tasks/<task_id>> analyze`  (harbor analyze <Trials/>)  _(retry once if it errors)_
```
(paste analyze output here)
```
- **Solved vs cheated (feeds #14):**
- **Instruction sufficiency (feeds #15/#3):**

---

## QC Rubric scoring (Varmint Sheriffs v2 - 16 dimensions + Unauditable)

Scores: **5** Pass · **3** Non-Fail (only #3, #6) · **2** Fail · **1** Un-auditable · **N/A**.
On a Fail, record the named **error category** shown in the last column.

| # | Dimension | Score | Error category (on Fail) | Justification |
|---|---|---|---|---|
| 1 | Structure - Task Bundle Files | | [Fail - Broken Structure] | |
| 2 | Structure - Deliverables & Packaging | | [Fail - Deliverable Packaging] | |
| 3 | Instruction - Requires the Visual Evidence | | [Fail - Assets Not Needed] / [Non-Fail Assets misdirected] | |
| 4 | Image - Evidence Quality | | [Fail - Bad Evidence] | |
| 5 | Metadata - task_type Accuracy | | [Fail - Wrong task_type] | |
| 6 | Evidence - Chain Consistency | | [Fail - Evidence Mismatch] / [Non-Fail Evidence Minor Mismatch] | |
| 7 | Golden Fix - Applies Cleanly | | [Fail - Patch Won't Apply] | |
| 8 | Golden Fix - Source-Only Scope | | [Fail - Dirty Fix Scope] | |
| 9 | Tests - Implementation Overfit | | [Fail - Overfit Tests] | |
| 10 | Tests - f2p/p2p Identifier Validity | | [Fail - Bad Test IDs] | |
| 11 | Tests - p2p Classification | | [Fail - Mislabeled p2p] | |
| 12 | Tests - Discriminating (f2p) | | [Fail - Non-Discriminating] | |
| 13 | Tests - Determinism | | [Fail - Flaky Tests] | |
| 14 | Hardening - Difficulty (Model Trial Fails) | | [Fail - Not Hard Enough] | |
| 15 | Hardening - Real & Feasible | | [Fail - Unreal or Infeasible] | |
| 16 | Gate - Oracle/Nop | | [Fail - Gate Broken] | |
| v3 | Rubrics - rubrics.json (schema/task/criteria/rules/accurate) | | [Fail - Missing/Broken Rubrics] / [Fail - Bad Rubric Schema] / [Fail - Rubric Task Mismatch] / [Fail - Malformed Criteria] / [Fail - Inaccurate Rubric] / [Fail - Overfit or Misused Rubric] | |
| v3.1 | Rubrics - judge mechanics (wiring/keyless/rescore) | | [Fail - Missing/Broken Rubrics] / [Fail - Broken Structure] / [Fail - Inaccurate Rubric] | |
| - | Unauditable | | [Un-auditable] | (score 1 only if the task is unauditable/spam; else 5) |

**QC result:** _(x Pass, y Non-Fail, z Fail, Unauditable?)_

---

## Per-step notes

### Step 1 - Structure (#1, #2)
- **#1 Task bundle files:** (P/F + any missing/empty/invalid harness file)
- **#2 Deliverables & packaging:** (P/F + archive naming / capital-T / nesting)

### Step 2 - Instruction (#3)
- **#3 Requires the visual evidence:** (P/NF/F - could you solve from text alone? does it path to the asset?)

### Step 3 - Image (#4)
- **#4 Evidence quality:** (P/F - all required images present, correct, named for what they show; video -> still frame?)

### Step 4 - Metadata (#5)
- **#5 task_type accuracy:** (P/F - valid value AND matches the image)

### Step 5 - Evidence chain (#6)
- **#6 Chain consistency:** (P/NF/F - assets <-> ASSET_MANIFEST <-> evidence_bundle <-> instruction all agree; a lone evidence_bundle mismatch = NF)

### Step 6 - Golden fix (#7, #8)
- **#7 Applies cleanly:** (P/F - `git apply --check` on base_commit)
- **#8 Source-only scope:** (P/F - paths == files_edited, no test/doc/lock/changeset)

### Step 7 - Tests (#9, #10, #11, #12, #13)
- **#9 Implementation overfit:** (P/F - would a different correct fix still pass?)
- **#10 f2p/p2p identifier validity:** (P/F - each id resolves to exactly one test; config.json == task.toml)
- **#11 p2p classification:** (P/F - every p2p passes on untouched base)
- **#12 Discriminating (f2p):** (P/F - every f2p fails on base, passes on fix)
- **#13 Determinism:** (P/F - same result every run)

### Step 7.5 - Rubrics (v3 rubric layer)
- **Structure (file/schema/task/criteria):** (P/F - any [FAIL] from Step 0.55 = Structure-class fail)
- **Six rules (atomic/specific/self-contained/positive/non-prescriptive/grouping):** (P/F per real criterion)
- **ACCURATE:** (P/F - each real criterion factually true of `solution/fix.patch`)
- **Right tool / placeholder:** (P/F - code-visible property, not render-only; stub valid only if fully test-covered)

### Step 7.6 - Judge mechanics (v3.1)
- **Static wiring (`check_judge.py`):** (P/F - judge.py present+keyless, rubric_file wired, test.sh invokes judge + --rubric, no stdlib shadow)
- **Behavioural:** (P/F - judge request appeared under verifier/judge/; oracle `rubric: "pass"` after rescore, if the runner supports it)

### Step 8 - Hardening (#14, #15)
- **#14 Difficulty (trial fails):** (P/F - submitted Trials reward < 1.0)
- **#15 Real & feasible:** (P/F - coherent real issue, solvable from symptom + image)

### Step 9 - Gate (#16)
- **#16 Oracle/Nop:** (P/F - Oracle 1.0, Nop 0.0, verifier completed, idempotent)

---

## Overall summary

- **Strong points:**
- **Blocking issues (fails / gate):**
- **Minor / non-blocking:**

### Required fixes (if Revise)
1.
