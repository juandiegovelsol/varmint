# Varmint Sheriffs - Task Review Toolkit (v3.1)

Everything needed to replicate the **Varmint Sheriffs** (Multimodal SWE hardening) task-review
process end to end, aligned to the **official QC rubric v2** (`QC_rubrics_v2.csv` - **16 scored
dimensions + 1 "Unauditable"**) **plus the v3 rubric layer** (`tests/rubrics.json`) added by
**Attempter Guidelines V3**. Start with `review_process_v3_1.md` and follow the steps in order.

> **New in v3.1 - the judge-mechanics component.** v3 audited the rubric *content*
> (`check_rubrics.py` at Step 0.55, inspection at Step 7.5). v3.1 adds a check for the *machinery
> that runs it* - the `rubric-template` plumbing wired into `tests/` (`judge.py`, the `test.sh`
> judge block, the `verifier.py` gate, `config.json`'s `rubric_file`). The judge is a **sub-agent**
> (the verifier never calls a model, so the task stays keyless), and its verdict is **compatible
> with, not a replacement for, the gate**: it runs separately at run time and is folded into
> `reward.txt`/`reward.json` only later via `rescore`, where it can only turn a `1.0` into `0.5`.
> The new **`check_judge.py`** (Step 7.6) statically audits that wiring. Nothing else in v3 changed.

> **New in v3 - the rubric-verification component.** Guidelines V3 add `tests/rubrics.json`: a
> **rubric** is a single yes/no criterion an LLM judge checks against the candidate's *code*, for
> hardening targets a behavioral test can't catch but a reader can (e.g. a button-colour change).
> Rubrics are scored by the **judge, separately from the keyless f2p/p2p gate**, so a bad rubric
> never shows up in `reward.txt` - it must be caught by inspection. This toolkit adds
> **`check_rubrics.py`** (Step 0.55) to audit `rubrics.json` against the six V3 "Rules for rubrics",
> a light **Group R** in `review_checks.py`, and a **Step 7.5** in the process + eval template. The
> 16 v2 scored dimensions and the keyless gate are otherwise unchanged.

> **Scope - review only, run locally.** This toolkit is for **reviewing a task that was already
> created** by a contributor, from your **local Cursor** (macOS + Docker + harbor 0.18). The rubric
> repeats a note on most dimensions: *"do not use the sandbox to assess. Download the 4 directories,
> inspect, run docker, patch, and test code locally."* You do **not** create tasks or run a fresh
> agent trial - you validate the *submitted* four folders and independently reproduce the **keyless
> gate** (Oracle=1.0 / Nop=0.0).

> **v2 hand-off - four folders, nothing else.** The reviewer is handed the **four tarred
> deliverables** (`Tasks/ Trials/ Oracle/ Nop/`). There is **no task JSON** and **no
> `justification.txt`** (the v1 justification dimension #29 was dropped).

> **What a Varmint Sheriffs task is.** Each task is one real, merged GitHub PR that fixed a
> *visually-diagnosed* issue, harvested into a self-contained **Harbor** bundle (`Tasks/`) with an
> image ("poster"), a golden fix, and behavioral tests. The contributor ("deputy") verifies the
> bundle, **hardens** it so a live model trial *fails*, updates the metadata, and re-runs the gate.
> The final submission is **four sibling folders, each tarred**: `Tasks/`, `Trials/`, `Oracle/`,
> `Nop/`. Your job is to review that submission against the QC rubric v2.

## What changed from v3 -> v3.1

v3 verified the rubric *content*; v3.1 adds verification of the rubric *judge mechanics* (the
`rubric-template` plumbing), integrated as **compatible with the keyless gate**:

- **New `check_judge.py` (Step 7.6)** - statically audits the judge wiring: `tests/judge.py`
  present + compiles + carries the template markers; `task.toml` is **keyless** (no `[verifier.env]`,
  no `ANTHROPIC_*` / `JUDGE_MODEL`); `config.json` sets `"rubric_file": "rubrics.json"`; `test.sh`
  invokes `judge.py` and passes `--rubric` (keeping the load-bearing `|| echo ""`); `verifier.py`
  parses `--rubric` and writes `reward.json`; and no `tests/` file shadows a stdlib module.
- **Separate at run time, folded in at rescore time.** The sub-agent judge writes a *request*
  during the run and scores on tests alone; a judge sub-agent later writes `verdict.json` and
  `rescore` folds it into the reward - and it can only turn a `1.0` into `0.5`, never toward `0.0`.
- **Step 7.6 in the process + eval template**, and a matching row in the appendix map. `review_
  process_v3.md` (the v3 doc) is superseded here by **`review_process_v3_1.md`**. The 16 v2 dims,
  `check_rubrics.py`, and the keyless gate are unchanged.

## What changed from v2.1 -> v3

Guidelines V3 introduced the **rubric layer**; the review process gained a matching component:

- **`tests/rubrics.json` is now part of every bundle** - a real rubric (a yes/no criterion an LLM
  judge checks against the candidate's *code*), or the always-pass stub when the task is fully
  covered by behavioral tests. `{schema, task, description, criteria[{id, criterion, is_positive?}]}`.
- **Judged separately from the keyless gate.** Oracle/Nop still score from f2p/p2p only, so a
  rubric fault is invisible in `reward.txt` - it is inspection-only (Step 0.55 + Step 7.5).
- **New `check_rubrics.py`** audits the six "Rules for rubrics" (atomic · specific & objective ·
  self-contained · positive wording · not overly prescriptive · sensible grouping) plus the
  structural FILE/SCHEMA/TASK-id/CRITERIA checks. **ACCURATE** (each criterion true of the golden)
  and *right-tool* (code-visible, not render-only) stay manual.
- **`review_checks.py` Group R** adds a light presence/parse cross-check; the **eval template** and
  **field reference** now carry the rubric row/entries. The 16 v2 dims and scoring are unchanged.

## What changed from v1.1 -> v2

The rubric collapsed **32 dimensions -> 16 scored + Unauditable**. Scores: **5** Pass · **3**
Non-Fail (offered on only #3 and #6) · **2** Fail · **1** Un-auditable. Each Fail carries a named
**error category** (e.g. `[Fail - Broken Structure]`). These v1 dimensions are **no longer scored**
and were **removed** from this toolkit's process and scripts: solution-leak (#1), repo-traceability
(#2), poster-matches-real-GitHub-PR (#6), solve.sh correctness (#11), test-patch scope (#12),
harness/reward logic (#14/#15), binary-baseline trap (#16), synthetic emptiness (#17),
localization hardening (#21), new-tests quality (#24), task.toml consistency (#25),
visual-essentiality honesty (#27), justification write-up (#29), run-output layout (#30). The
legacy task-JSON extractor and `justification.txt` handling were also removed.

## What's in here

| File | Purpose |
|---|---|
| `review_process_v3_1.md` | **The process** - step-by-step procedure (source of truth), aligned to the 16 v2 dims + Unauditable **+ the v3 rubric layer + the v3.1 judge-mechanics step (7.6)**. |
| `eval_template.md` | The evaluation skeleton you copy to `eval_<taskId>.md` and fill in (17-row scoring table + a v3 Rubrics row and Step 0.55/7.5/7.6 sections). |
| `review_checks.py` | **Step 0.5** - *static* mechanical pre-checks over the unpacked bundle (groups A/B/D/F/H/I + **R** = rubrics.json present/parses). Never runs the verifier. |
| `check_rubrics.py` | **Step 0.55 (NEW in v3)** - verifies `tests/rubrics.json` against the six V3 "Rules for rubrics": FILE/SCHEMA/TASK/CRITERIA hard checks + per-criterion style heuristics. Never runs the judge. |
| `check_judge.py` | **Step 7.6 (NEW in v3.1)** - statically audits the rubric *judge mechanics* (the `rubric-template` plumbing): `judge.py` present/keyless, `config.json` `rubric_file`, `test.sh` judge invocation, `verifier.py` `--rubric` gate, no stdlib-shadowing files. Never runs the judge. |
| `check_gate.py` | **Step 0.6** - validates the submitted Oracle/Nop/Trials rewards + `task_checksum`, and prints the **keyless** commands to independently re-run the gate. |
| `field_reference.md` | Where each reviewable value lives inside the four folders (incl. `tests/rubrics.json` and the judge harness `tests/judge.py`). |
| `mmswe-runner-skill/` | **Bundled skill** - installs `mm_run.sh` + `/run-oracle` `/run-nop` `/run-trial` `/check-task` `/analyze-trial`. Wraps `harbor run/check/analyze` with keyless oracle/nop and anonymizer-based trial/check/analyze. |

> The official QC rubric v2 lives at `../QC_rubrics_v2.csv`; the attempter guidelines live in
> `../guidelines/`. The process defers to both.

## Prerequisites

- **Python 3** (standard library only - for `review_checks.py`, `check_gate.py`).
- **git** and **Docker** (to *independently re-run* the gate - the rubric requires reproducing
  Oracle = 1.0 / Nop = 0.0 rather than trusting `reward.txt`).
- The **`harbor`** runner - **version `0.18`, matching the contributor sandbox** - driven through
  the bundled **`mmswe-runner`** skill (`mm_run.sh`, modes `oracle | nop | trial | check |
  analyze`). Reviewing on a different harbor version can cause tooling-drift mismatches.
- **Docker** running locally. The gate (Oracle=1.0 / Nop=0.0) is **keyless** - no API key or
  anonymizer needed. Only a *fresh agent trial* needs model credentials, and re-running the trial
  is **not** required to sign off (validate the shipped `Trials/` run + `harbor analyze` instead).

## What needs harbor vs. what doesn't

| Step | Needs harbor + Docker? |
|---|---|
| Step 0 - unpack the four tarballs | No - `tar` only |
| `review_checks.py` (Step 0.5, static checks) | No - Python only |
| `check_rubrics.py` (Step 0.55, rubric audit) | No - Python only |
| `check_judge.py` (Step 7.6, judge-mechanics audit) | No - Python only |
| `check_gate.py` (Step 0.6, validates submitted outputs + prints re-run commands) | No - Python only |
| Re-running the gate (`mm_run.sh oracle/nop` / raw `harbor run`) | **Yes** - harbor + Docker, **keyless** |
| `mm_run.sh check` / `analyze` (Step 0.7) | **Yes** - harbor + Docker **+ a reachable model endpoint** (anonymizer by default, no real key) |

To reproduce the gate, install the open-source Harbor framework
([harborframework.com](https://www.harborframework.com), `github.com/harbor-framework/harbor`):
`uv tool install 'harbor==0.18.*' --python 3.12` (needs Python 3.12+; uv fetches it). See
`review_process_v2_1.md` Step 0.6 for run commands, local-setup gotchas, and a Docker-only fallback.

## Local setup (Docker + harbor) - one time

You only need this to *reproduce the gate* (Step 0.6) and run the helper commands (Step 0.7). The
gate is **keyless**, so once these are in place you can review entirely in your own Cursor with no
API key.

1. **Docker** - install Docker Desktop (macOS) and make sure it's running.

```bash
docker info            # must succeed (daemon running) before any oracle/nop run
```

2. **harbor CLI** - install and pin **0.18** to match the contributor sandbox:

```bash
uv tool install 'harbor==0.18.*' --python 3.12
harbor --version       # expect 0.18.x
```

3. **`mmswe-runner` skill (bundled)** - installs `mm_run.sh` and the helper commands:

```bash
cd mmswe-runner-skill && bash install.sh && cd -
#   installs to ~/.claude/skills/mmswe-runner/ and ~/.claude/commands/
#   modes: oracle | nop | trial | check | analyze
```

4. **Smoke-test the keyless gate** on any unpacked task before trusting a review:

```bash
bash ~/.claude/skills/mmswe-runner/mm_run.sh "task_<taskId>/deliverables/Tasks" oracle   # -> 1.0
```

## Quick start (per task)

```bash
# 0.  Stage the four deliverables (NO JSON, NO justification):
mkdir -p task_<taskId>/deliverables
cp Tasks.tar.gz Trials.tar.gz Oracle.tar.gz Nop.tar.gz  task_<taskId>/deliverables/
for t in Tasks Trials Oracle Nop; do tar -xzf "task_<taskId>/deliverables/$t.tar.gz" -C "task_<taskId>/deliverables"; done
#     -> gives task_<taskId>/deliverables/{Tasks,Trials,Oracle,Nop}/

# 0.5  Static mechanical pre-checks - never runs the verifier
python3 review_checks.py "task_<taskId>/deliverables"

# 0.55 Verify the rubrics (NEW in v3) - audits tests/rubrics.json vs the six "Rules for rubrics"
python3 check_rubrics.py "task_<taskId>/deliverables"

# 7.6  Verify the judge mechanics (NEW in v3.1) - audits the rubric-template wiring in tests/
python3 check_judge.py "task_<taskId>/deliverables"

# 0.6  Validate the submitted runs, then re-run the gate yourself (KEYLESS - no API key)
python3 check_gate.py "task_<taskId>/deliverables"
MM=~/.claude/skills/mmswe-runner/mm_run.sh
bash "$MM" "task_<taskId>/deliverables/Tasks" oracle   # expect 1.0 (keyless)
bash "$MM" "task_<taskId>/deliverables/Tasks" nop      # expect 0.0 (keyless)
bash "$MM" "task_<taskId>/deliverables/Tasks" oracle   # again -> still 1.0 (idempotency -> #13)

# 0.7  Optional harbor helper commands (aids, not verdicts)
bash "$MM" "task_<taskId>/deliverables/Tasks" check      # harbor check: test fairness (#9)
bash "$MM" "task_<taskId>/deliverables/Tasks" analyze    # harbor analyze <Trials/>: solved-vs-cheated (#14), instr sufficiency (#15/#3)

# 1.  Start the eval
cp eval_template.md task_<taskId>/eval_<taskId>.md
#     then follow review_process_v3_1.md Steps 1-10 (incl. Step 7.5 Rubrics + Step 7.6 Judge
#     mechanics), recording every verdict.
```

Keep the folder layout intact - the scripts assume the four deliverables sit under
`task_<taskId>/deliverables/`.

## Scoring (from QC rubric v2 + the v3 rubric layer)

- **[5]** Pass · **[3]** Non-Fail (only #3 Instruction-Requires-Visual and #6 Evidence-Chain) ·
  **[2]** Fail (record the named error category) · **[1]** Un-auditable · **N/A**.
- v2 marks **no** dimension as auto-reject "critical". Use judgement in Step 10: a Structure fail
  (#1/#2), a Gate fail (#16), or an Un-auditable verdict are still effectively disqualifying.
- **v3 Rubrics** is scored as a Structure-class pass/fail (Step 7.5): a missing/broken/mismatched
  or inaccurate rubric is effectively disqualifying like #1; a rubric that only needs its wording
  tightened to satisfy the six rules is a Revise.
- **v3.1 Judge mechanics** (Step 7.6) is scored the same Structure-class way: broken judge wiring
  (missing/edited `judge.py`, no `rubric_file`, judge not invoked in `test.sh`) or a **credentialed**
  judge (any `[verifier.env]` / `ANTHROPIC_*` / `JUDGE_MODEL`) is disqualifying like #1.

## Version

- **v3.1** (current) - `review_process_v3_1.md`. Adds the **judge-mechanics layer** on top of v3: a
  new `check_judge.py` (Step 7.6) that statically audits the `rubric-template` wiring in `tests/`
  (keyless sub-agent `judge.py`, `config.json` `rubric_file`, `test.sh` judge invocation,
  `verifier.py` `--rubric` gate, no stdlib-shadowing files). The rubric is integrated as
  **compatible with the keyless gate** - separate at run time, folded into `reward.txt`/`reward.json`
  only via `rescore`, and only ever turning a `1.0` into `0.5`. The 16 v2 scored dims,
  `check_rubrics.py` (Step 0.55), Step 7.5, and the gate are unchanged. Previous version lives in
  `../review_toolkit_v3/`.
- **v3** - `review_process_v3.md` (in `../review_toolkit_v3/`). Adds the **rubric layer** on top of
  v2.1: a new `check_rubrics.py` (Step 0.55) auditing `tests/rubrics.json` against the six V3 "Rules
  for rubrics", a Group **R** in `review_checks.py`, and Step 7.5 in the process + eval template. The
  16 v2 scored dims, their scoring, and the keyless gate are unchanged. Previous version lives in
  `../review_toolkit_v2_1/`.
- **v2.1** - `review_process_v2_1.md` (in `../review_toolkit_v2_1/`), same 16 scored dims + Unauditable and same scoring
  as v2. Hardened **Step 2 (#3 Instruction requires the visual evidence)** to stop under-scoring
  text-solvable tasks: added a mandatory Trials trajectory audit, a "symptom vs. diagnosis" trap, a
  #3-vs-#15 conflation guard, and a tighter Pass bar. Scripts are unchanged from v2. Previous
  version lives in `../review_toolkit_v2/`.
- **v2** - `review_process_v2.md` (in `../review_toolkit_v2/`), aligned to `QC_rubrics_v2.csv` (16
  scored dims + Unauditable). harbor pinned to **0.18**. Dropped from v1.1: leak/repo-trace
  scanning, GitHub-PR verification, the legacy task-JSON extractor, `justification.txt` handling, and
  all script checks for now-unscored dimensions. v1.1 lives in `../vs_review_toolkit_v1_1/`.
