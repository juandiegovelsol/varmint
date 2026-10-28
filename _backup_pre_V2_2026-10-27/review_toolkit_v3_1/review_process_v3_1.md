# Task Review Process (Varmint Sheriffs - v3.1)

Repeatable process for reviewing a **Varmint Sheriffs** (Multimodal SWE hardening) task, aligned
to the **official QC rubric v2** (`QC_rubrics_v2.csv` - **16 scored dimensions + 1 "Unauditable"**)
**plus the v3 rubric layer** introduced by **Attempter Guidelines V3**. Follow the steps in order.

> **What changed from v3 -> v3.1 (the judge-mechanics layer).** v3 audited the rubric *content*
> (Step 0.55 static, Step 7.5 inspection); v3.1 adds a new **Step 7.6** that audits the rubric
> **judge mechanics** - the `rubric-template` plumbing wired into `tests/` (`judge.py`, the
> `test.sh` judge block, the `verifier.py` gate, `config.json`'s `rubric_file`). The rubric is
> integrated as **compatible with the keyless gate, not a replacement for it: the judge runs
> SEPARATELY at run time and its verdict is folded into `reward.txt`/`reward.json` only later via
> `rescore`.** So Oracle/Nop (Step 0.6) are unchanged and stay keyless; a rubric verdict reaches
> the reward only after a judge sub-agent writes `verdict.json` and `rescore` runs, and even then it
> can only turn a `1.0` into `0.5`, never toward `0.0`. Nothing else in v3 changed: the 16 v2 scored
> dimensions, `check_rubrics.py` (Step 0.55), and Step 7.5 are identical.

> **What changed from v2.1 -> v3 (the rubric layer).** Guidelines V3 add
> **`tests/rubrics.json`** to every task bundle. A **rubric** is a single yes/no criterion an LLM
> judge checks against the candidate's *code* - it exists for hardening targets a behavioral test
> can't catch but a reader can (e.g. a button-colour change: visible in code, several valid ways
> to write it, so a test would be forbidden source-matching). Key facts for the reviewer:
> - Rubrics are scored by a **judge, SEPARATELY from the keyless f2p/p2p gate** - so Oracle/Nop
>   (Step 0.6) are unchanged and stay keyless, and a rubric defect does **not** show up in
>   `reward.txt` **at run time**. It must be caught by inspection (Steps 0.55 / 7.5). *(In v3.1: the
>   verdict is later folded into `reward.txt`/`reward.json` via `rescore` - compatible with, not a
>   replacement for, the gate. See Step 7.6.)*
> - `tests/rubrics.json` is **always present**: a real rubric, or a single **always-pass stub**
>   (`{"id":"always_pass...","criterion":"The response is written in English."}`) when the task is
>   fully covered by behavioral tests.
> - New tooling: **`check_rubrics.py` (Step 0.55)** audits `rubrics.json` against the six V3
>   "Rules for rubrics"; `review_checks.py` gains a light **Group R** presence/parse check; and a
>   new **Step 7.5** folds the rubric verdict into the review. The 16 v2 scored dimensions and
>   their scoring are otherwise **unchanged** (a rubric fault reads as a Structure-class defect).
>   *(v3.1 adds **Step 7.6** on top - the judge mechanics; see the v3 -> v3.1 note above.)*
> - `harbor check`/`analyze` commands and the keyless gate are identical to v2.1.

> **What changed from v2 -> v2.1.** Same 16 scored dimensions and scoring - only **Step 2 (#3
> Instruction requires the visual evidence)** was hardened to stop under-scoring text-solvable tasks
> as Non-Fail/Pass: (a) a **mandatory Trials trajectory audit** (did the trial agent actually open
> the image?), (b) a **"symptom vs. diagnosis" trap** (prose that states the diagnosis makes the
> image decorative -> Fail; there is no "helpful but not load-bearing" Non-Fail), (c) a **#3-vs-#15
> conflation guard** (undepicted cross-file scope is text-anchored, never proof the image is
> needed), and (d) a **tighter Pass bar** (a #3 Pass now requires *both* a failed text-only grep and
> a trial that could not solve image-blind). The appendix #3 pre-check row was updated accordingly.

> **What changed from v1.1 -> v2.** The rubric collapsed from 32 dimensions to **16 scored + an
> Unauditable check**. Scores are **5** Pass · **3** Non-Fail (offered on only two dims) · **2**
> Fail · **1** Un-auditable. Each Fail carries a named **error category** (e.g.
> `[Fail - Broken Structure]`). The following v1 dimensions are **no longer scored** and are
> **removed** from this process and the scripts: solution-leak (#1), repo-traceability (#2),
> poster-matches-real-GitHub-PR (#6), solve.sh correctness (#11), test-patch scope (#12), harness &
> reward logic (#14/#15), binary-baseline trap (#16), synthetic emptiness (#17), localization
> hardening (#21), new-tests quality (#24), task.toml consistency (#25), visual-essentiality honesty
> (#27), justification write-up (#29), run-output layout (#30). The hand-off is now just the **four
> deliverable folders** - no `justification.txt`, no task JSON.

> **How you assess (rubric NOTE, repeated on most dims): work locally, not in the sandbox.**
> *"Do not use the sandbox to assess. Download the 4 directories, inspect, run docker, patch, and
> test code locally."* Review from your **local Cursor** (macOS + Docker + harbor **0.18**). You do
> **not** create the task or run a *fresh* agent trial - you validate the *submitted* four folders,
> reproduce the **keyless gate** yourself (Step 0.6), and optionally run the Step 0.7 helpers.

> **What you are reviewing.** A contributor ("deputy") took a harvested Harbor bundle of one real
> merged GitHub PR (a visually-diagnosed fix), **hardened** it so a live model trial *fails*, and
> re-ran the gate. The submission is **four sibling folders, each tarred**: `Tasks/` (the task),
> `Trials/` (the failing model run), `Oracle/` (golden fix, reward 1.0), `Nop/` (untouched base,
> reward 0.0).

> **No "critical" flags in v2.** Unlike v1, the v2 rubric marks no dimension as auto-reject. Score
> each of the 16 items with its error category on a Fail. In practice a **Structure** Fail
> (#1/#2), a **Gate** Fail (#16), or an **Un-auditable** verdict are still effectively
> disqualifying - see Step 10.

Each task lives in its own folder `task_<taskId>/` containing:

- `eval_<taskId>.md` - the evaluation you fill in while reviewing.
- `deliverables/` - the unpacked `Tasks/` `Trials/` `Oracle/` `Nop/` folders.

---

## Step 0 - Stage the four deliverables (no justification, no JSON)

Goal: get the four deliverable folders on disk. You are handed **four tarballs** (or the four
already-unpacked folders):

```
mkdir -p task_<taskId>/deliverables
cp Tasks.tar.gz Trials.tar.gz Oracle.tar.gz Nop.tar.gz  task_<taskId>/deliverables/
for t in Tasks Trials Oracle Nop; do
  tar -xzf "task_<taskId>/deliverables/$t.tar.gz" -C "task_<taskId>/deliverables"
done
```

You should now have `task_<taskId>/deliverables/{Tasks,Trials,Oracle,Nop}/`. If you were given the
four folders already unpacked, just drop them under `deliverables/` and skip the `tar` loop.

> **Sanity checks (Step 0.5 formalizes these):** exactly four sibling deliverable folders; each
> unpacks to its correctly-cased name (`Tasks` capital-T); none nested inside another; each has a
> matching `.tar.gz`.

---

## Step 0.5 - Static mechanical pre-checks (every task)

```
python3 review_checks.py "task_<taskId>/deliverables"
```

Project-generic **static** checks over the unpacked bundle. It never runs the verifier (that is
Step 0.6). It reports only the groups that map to a **scored v2 dimension**; every finding is a
**candidate** unless marked `[FAIL]` - confirm by hand.

- **A -> #2 Deliverables & Packaging.** `Tasks/ Trials/ Oracle/ Nop/` exist as root-level siblings,
  each with a matching `.tar.gz`, `Tasks` capital-T, none nested. Any miss -> **#2 Fail
  `[Fail - Deliverable Packaging]`**.
- **B -> #1 Task-bundle files** (+ #4 poster decode). Every fixed harness file present, non-empty,
  machine-valid (`task.toml`, `instruction.md`, `evidence_bundle.json`, `environment/Dockerfile`,
  `environment/assets/ASSET_MANIFEST.json`, `solution/fix.patch`, `solution/solve.sh`,
  `tests/config.json`, `tests/test.patch`, `tests/test.sh`, `tests/verifier.py`); JSON parses,
  `verifier.py` compiles, posters decode. Any miss -> **#1 Fail `[Fail - Broken Structure]`** (a
  poster that won't decode also feeds **#4 `[Fail - Bad Evidence]`**).
- **D -> #8 Golden-fix source-only scope.** `diff --git` paths of `solution/fix.patch` are
  source-only and equal `task.toml.files_edited`. Any test/doc/lock/`.changeset` path, or a
  mismatch with `files_edited`, -> **#8 Fail `[Fail - Dirty Fix Scope]`**.
- **F -> #10 f2p/p2p identifier validity.** Every `f2p`/`p2p` id resolves to **exactly one** test
  (watch substring collisions), and `config.json` f2p/p2p == `task.toml` f2p/p2p. Zero/ambiguous
  match or a list mismatch -> **#10 Fail `[Fail - Bad Test IDs]`**.
- **H -> #5 task_type value.** `task_type` is one of the seven allowed values (`visual_bug_fix`,
  `visual_regression`, `design_reference`, `build_render_repair`, `temporal_interaction`,
  `accessibility_visual`, `data_viz_correctness`). Whether it *matches the image* is Step 4.
  Invalid value -> **#5 Fail `[Fail - Wrong task_type]`**.
- **I -> #6 Evidence-chain consistency.** For each asset the file in `environment/assets/`, its
  `ASSET_MANIFEST.json` entry (`container_path` under `/app/.harbor_assets/`), and the
  `instruction.md` image ref agree. A divergence among those three -> **#6 Fail
  `[Fail - Evidence Mismatch]`**; a lone `evidence_bundle.json` divergence is only a **#6 Non-Fail
  `[Non-Fail Evidence Minor Mismatch]`**.
- **S -> #15 Multi-subject scope (ADVISORY).** Aid for Step 8: flags when `fix.patch` /
  `files_edited` or the `f2p` ids span more than one distinct source *subject* (module stem, e.g.
  `infinity-points` **and** `eternity-points`; or `ip-*` **and** `ep-*` f2p prefixes), and whether
  each subject has a word anchored in `instruction.md`. It is **image-blind and never `[FAIL]`** -
  it only tells you where to build the Step 8 coverage table. A flagged subject that is anchored in
  **neither** the instruction **nor** the image is an unsolvable-by-perception cut -> **#15 Fail
  `[Fail - Unreal or Infeasible]`**.

> The script is an aid, not a substitute. It cannot open the image, judge whether a test is
> *implementation-agnostic* / *discriminating*, or run the gate. Those are Steps 3, 7, and 0.6.
> Group **R** here is only a presence/parse check on `rubrics.json` - the full rubric audit is
> **Step 0.55** below.

---

## Step 0.55 - Verify the rubrics (`check_rubrics.py`) - NEW in v3

```
python3 check_rubrics.py "task_<taskId>/deliverables"
```

Statically audits `Tasks/tests/rubrics.json` against the V3 **"Rules for rubrics"**. Rubrics are
judged by an LLM against the candidate's *code*, **separately from the keyless f2p/p2p gate**, so a
bad rubric never surfaces in `reward.txt` - it can only be caught here and in Step 7.5. Findings are
**candidates** unless marked `[FAIL]`.

`check_rubrics.py` checks:
- **FILE** - `tests/rubrics.json` exists, is non-empty, parses. Missing/empty/broken -> **Rubrics
  Fail `[Fail - Missing/Broken Rubrics]`** (Structure-class: the judge can't score the task).
- **SCHEMA** - `schema` is a recognised value (`projectbench.rubrics/v1`, or the doc's
  `rubrics.schema/v1`). A typo silently breaks the judge -> **`[Fail - Bad Rubric Schema]`**.
- **TASK** - `task` == `task_id` in `task.toml` == `task_id` in `config.json`
  (`{owner}__{repo}-{issue}-mm`), so every file carries the same id. A mismatch ->
  **`[Fail - Rubric Task Mismatch]`**.
- **CRITERIA** - `criteria` is a non-empty list; each item has a **unique**, non-empty `id` and
  non-empty `criterion`; `is_positive` (if present) is a bool. Otherwise ->
  **`[Fail - Malformed Criteria]`**.
- **RULES (candidates)** - per-criterion heuristics for the six style rules: *atomic*,
  *specific & objective* (flags vague words / a code criterion that names no file-function anchor),
  *self-contained*, *positive wording* (flags a "must not" that isn't marked `is_positive=false`),
  *avoid overly prescriptive* (flags "named/called X" that pins one implementation), and sensible
  *grouping*. Each is a candidate - confirm against the criterion text.
- **PLACEHOLDER** - detects the always-pass stub and reminds you it is valid **only if** the task
  is genuinely 100% covered by behavioral tests (no code-only visual change was left un-graded).

> **Two rules the script cannot check - do them by hand (Step 7.5):**
> - **ACCURATE** - each real criterion must be *factually true of the golden* (`solution/`). If the
>   golden doesn't satisfy a rubric, the oracle would fail the judge. Read the fix against every
>   criterion.
> - **Right tool** - a rubric must judge a *code-visible* property with multiple valid
>   implementations; it must **not** stand in for a render-only check the code gives no signal for
>   (e.g. "is it pixel-centered?") - that remains a no-go, not a rubric.

---

## Step 0.6 - Reproduce the gate (every task)

The rewards in the bundle are **self-reported** (produced in the contributor's sandbox). First
validate the submitted run outputs statically, then **re-run the gate yourself**.

```
python3 check_gate.py "task_<taskId>/deliverables"
```

`check_gate.py`:
- Reads each run's `Tasks__*/verifier/reward.txt` and `Tasks__*/result.json ->
  verifier_result.rewards.reward` and confirms they agree.
- Confirms the gate: **Oracle = 1.0**, **Nop = 0.0** (both -> **#16**), **Trials < 1.0** (-> **#14**).
- Confirms all three `task_checksum` values are **identical** (proves the runs used the exact
  `Tasks/` you are reviewing - a mismatch means stale/foreign runs -> **Unauditable**).
- Prints the exact commands to **independently re-run** oracle and nop and confirm idempotency.

Then reproduce it yourself. **The gate is keyless - no API key or anonymizer is needed** because
the verifier is unit-tests -> JUnit -> `reward.txt` with no model call. Run it on your own machine
(local Cursor + Docker + the `mmswe-runner` skill) exactly the way the sandbox does.

> **Use harbor `0.18`** - the same version the contributor sandbox runs (`harbor --version`). The
> gate rewards and the Step 0.7 helpers are version-sensitive; a different harbor can show
> mismatched rewards that look like task defects but are really tooling drift. Note the version you
> used in the eval.

```shell
# mm_run.sh installs to ~/.claude/skills/mmswe-runner/ - see README "Local setup"
MM=~/.claude/skills/mmswe-runner/mm_run.sh
bash "$MM" "task_<taskId>/deliverables/Tasks" oracle    # expect reward 1.0  (keyless) -> #16
bash "$MM" "task_<taskId>/deliverables/Tasks" nop       # expect reward 0.0  (keyless) -> #16
bash "$MM" "task_<taskId>/deliverables/Tasks" oracle    # run AGAIN -> still 1.0 (idempotency -> #13)
```

Under the hood it is `harbor run -a oracle|nop … --yes`, so a raw harbor invocation works too:

```shell
harbor run -p "…/Tasks" -a oracle -e docker -o "…/root" --job-name Oracle --yes   # expect 1.0
harbor run -p "…/Tasks" -a nop    -e docker -o "…/root" --job-name Nop    --yes   # expect 0.0
```

> **Installing harbor 0.18 (one-time).** harbor is the open-source Harbor framework
> ([harborframework.com](https://www.harborframework.com), `github.com/harbor-framework/harbor`).
> It needs **Python 3.12+**; the cleanest install is via [`uv`](https://github.com/astral-sh/uv):
>
> ```shell
> pip install uv                              # or: curl -LsSf https://astral.sh/uv/install.sh | sh
> uv tool install 'harbor==0.18.*' --python 3.12   # pin 0.18 to match the contributor sandbox
> harbor --version                            # expect 0.18.x
> ```
>
> **Gotchas (environment, not task defects):**
> - **CPU cap.** harbor honors `task.toml`'s `[environment] cpus`. If your Docker VM has fewer
>   cores, the build fails with *"range of CPUs is from 0.01 to 2.00…"*. Raise the VM's cores.
> - **Registry HEAD timeout.** Pre-pull the base image once (`docker pull node:18-bookworm`), retry.
> - **Run from a stable cwd.** harbor imports litellm (`sys.path.append(os.getcwd())`); `cd` into an
>   existing dir before running.
>
> **Fallback - no harbor? Reproduce the keyless gate with plain Docker.** harbor is just an
> orchestrator around `docker build` + `tests/test.sh` + `tests/verifier.py`. From `Tasks/`:
>
> ```shell
> cd "task_<taskId>/deliverables/Tasks"
> docker build -t vs-<id>-env ./environment
> # ORACLE - apply golden fix, run harness twice (idempotency -> #13)
> docker run --rm -v "$PWD/tests:/tests:ro" -v "$PWD/solution:/solution:ro" vs-<id>-env bash -c '
>   bash /solution/solve.sh >/tmp/solve.log 2>&1
>   bash /tests/test.sh >/tmp/t1.log 2>&1 || true; echo "oracle#1 = $(cat /logs/verifier/reward.txt)"
>   bash /tests/test.sh >/tmp/t2.log 2>&1 || true; echo "oracle#2 = $(cat /logs/verifier/reward.txt)"
> '   # expect 1.0 and 1.0
> # NOP - untouched base
> docker run --rm -v "$PWD/tests:/tests:ro" vs-<id>-env bash -c '
>   bash /tests/test.sh >/tmp/nop.log 2>&1 || true; echo "nop = $(cat /logs/verifier/reward.txt)"
> '   # expect 0.0
> ```

> **Scoring rule (feeds #16, #13, #14).** Your reproduced Oracle **must** be 1.0 and Nop **must**
> be 0.0, the verifier must reach completion (stage banners + a real `reward=`, not an `EXIT`-trap
> 0 or "could not apply test.patch"), and a re-run must be idempotent. A gate that doesn't
> reproduce is **#16 Fail `[Fail - Gate Broken]`**; if your reproduced reward doesn't match the
> submitted `reward.txt`, treat the submission as **Unauditable**.

> **When the task carries a real rubric, this same run also produces the judge request** (a
> sub-agent judge, so the gate stays keyless). Confirm a `verifier/judge/` request appeared and,
> after grading, that `rescore` folds a `rubric: "pass"` into the oracle - the full judge-mechanics
> audit is **Step 7.6**.

---

## Step 0.7 - Run the harbor helper commands (aids, not verdicts)

Two harbor commands automate several checks. Run **both** early, but treat them as **aids**: read
the feedback and confirm each flag by hand before recording a score. Run them through the
**`mmswe-runner` skill**, which resolves credentials via the anonymizer (no real API key):

```shell
MM=~/.claude/skills/mmswe-runner/mm_run.sh
bash "$MM" "task_<taskId>/deliverables/Tasks" check      # -> harbor check <Tasks>
bash "$MM" "task_<taskId>/deliverables/Tasks" analyze    # -> harbor analyze <Trials/>
```

> **Credentials.** Unlike the keyless oracle/nop, `check`/`analyze` call a model, so they need the
> anonymizer endpoint reachable. If it isn't, these two steps are optional - the manual Steps 3/7/8
> cover the same dimensions.

### `harbor check <Tasks/>`  (`mm_run.sh … check`)
- **Test fairness** - flags tests asserting behavior not in `instruction.md` (feeds **#9**
  Implementation Overfit).

> **"Behavior in Task Description" is expected to mis-fire - it cannot read images.** If the flagged
> behavior *is* shown in the image (`environment/assets/`), the tests are **fair** - score **#9
> Pass** ("behavior is established by the image, not the text"). Only if the behavior is in
> **neither** the text **nor** the images are the tests unfair -> **#9 Fail `[Fail - Overfit
> Tests]`**. Do **not** fail #9 solely because `harbor check` flagged it.

### `harbor analyze <Trials/>`  (`mm_run.sh … analyze`)
- **Solved vs cheated** - whether the agent genuinely failed or "passed" by editing the
  environment/verifiers (feeds **#14** difficulty is honest).
- **Instruction sufficiency** - whether the instruction was enough (feeds **#15** feasible / **#3**
  visual reliance).

> **`harbor analyze` sometimes errors out. Retry once before blaming the task.**

> **analyze is image-blind - never take its verdict as final on #3 or #15.** It reads only text, so
> it cannot tell whether the image was *needed* (#3) or whether a required edit is *discoverable*
> from the pixels (#15). An "instruction sufficient / not ambiguous / incomplete implementation"
> conclusion is compatible with **both** a #3 Fail (image decorative) **and** a #15 Fail
> (unsolvable-by-perception cut). Always confirm #3 with the Step 2 cover-the-image grep and #15
> with the Step 8 scope-coverage table before scoring either as Pass.

`mm_run.sh … analyze` points at the whole `<ROOT>/Trials/` directory (not a `Trials/Tasks__*`
subfolder). Use the **submitted** `Trials/` that shipped in the bundle.

---

## Step 1 - Structure & packaging (#1, #2)

Reconcile with Step 0.5 **A/B** and Step 0.6.

- **#1 Task bundle files** - all fixed harness files present, non-empty, JSON parses,
  `verifier.py` compiles, posters decode. In **v3** the harness set includes **`tests/rubrics.json`**
  (a real rubric or the always-pass stub). Only files inside `environment/assets/` may be
  renamed/replaced. Any miss -> **Fail `[Fail - Broken Structure]`**. (Step 0.5 **B**; the rubric's
  content is audited in Step 0.55 / Step 7.5.)
- **#2 Deliverables & packaging** - all four archives present and correctly named; each unpacks to
  its correctly-cased sibling top-level folder (`Tasks` capital-T); none nested inside another. Any
  miss -> **Fail `[Fail - Deliverable Packaging]`**. (Step 0.5 **A**.)

---

## Step 2 - Instruction requires the visual evidence (#3)

Read `instruction.md` **as the agent** - it is the only prompt the agent sees. Cover the image and
try to diagnose + localize the defect from the text **alone**.

> **Do the exercise, don't just describe it - and record it.** Actually perform the text-only
> localization: take each distinctive phrase in `instruction.md` and grep the repo for it. If any
> instruction phrase lands directly on the source file that must be fixed, the image is **not
> needed** to localize -> **#3 Fail**. Write the attempt into the eval verbatim, e.g. *"grepped
> instruction phrase `IP gain` -> matched `name: "Total IP Gained on Infinity"` in
> `multiplier-tab/infinity-points.js`, so the defect is text-localizable -> Fail."* A #3 Pass must
> be backed by a **failed** text-only attempt (you tried and could not localize without the pixels).
>
> **`harbor analyze` "instruction sufficiency: sufficient" is evidence AGAINST #3, not for it.**
> #3 (image required) and #15 (instruction feasible) read the *same* signal in opposite directions:
> "the instruction is enough to solve" means the image may be **decorative** -> pushes #3 toward
> **Fail**. Never cite an analyze "sufficient/feasible" verdict as support for a #3 Pass.

> **Second decisive check - audit the trial for actual image use (mandatory, record it).** The
> shipped `Trials/Tasks__*/agent/trajectory.json` is ground truth for whether the pixels were
> *actually* needed. If the trial agent **never opened the image** yet still restated the correct
> defect and (even partly) localized the fix, the image was decorative -> **#3 Fail**. Check it
> mechanically and paste the counts into the eval:
>
> ```shell
> T=$(ls task_<taskId>/deliverables/Trials/Tasks__*/agent/trajectory.json)
> grep -c '"type": *"image"' "$T"                    # image content blocks the agent saw
> grep -Eic 'harbor_assets|\.png|\.gif|\.mp4|\.webp' "$T"   # tool calls referencing the asset
> ```
>
> **Zero image blocks AND zero asset-referencing tool calls**, on a trial that nonetheless names the
> correct defect, is hard proof the instruction text alone localized it -> **Fail**. (Caveat: a
> trial that scored < 1.0 only because it missed an *undepicted* file does **not** rescue #3 - that
> is a #15 matter; see the next warning.)

> **Trap - a "symptom" that is really a diagnosis = Fail.** A sentence like *"the tier name is
> coloured by rarity but the percentage falls back to the default foreground, so the two disagree"*
> is a **diagnosis in words**, not a bare symptom: it already names which element is wrong and what
> the fix is (make them match), so an agent acts on it without the pixels. Prose that fully describes
> the visible defect makes the image **decorative -> #3 Fail**, *even when the instruction correctly
> links the asset*. There is **no "poster helpful but not load-bearing" Non-Fail bucket** - the only
> Non-Fail (3) is the *misdirected-pathing* case below. If you catch yourself writing "the image is
> useful but the prose largely specifies the defect," you are describing a **Fail**, not a 3.

> **Do not let cross-file / undepicted scope rescue a #3 Pass.** Behavior the screenshot never shows
> (e.g. a capped/"effective" rarity that must propagate to other surfaces) is **text-anchored, not
> image-anchored** - it is evidence *against* image-essentiality, not for it. Citing an unpictured
> second surface as "proof the render is needed" is backwards; that scope belongs to the #15
> coverage table (Step 8), never to a #3 Pass.

- **Fail (2) `[Fail - Assets Not Needed]`:** the task is fully solvable from the instruction text
  (the image is decorative), **or** the instruction never references the assets so the agent isn't
  even directed to them.
- **Non-Fail (3) `[Non-Fail Assets misdirected]`:** the instruction notes there is an image but
  gives no pathing, or incorrect pathing.
- **Pass (5):** the instruction points the agent to the asset(s) **and** the defect can only be
  diagnosed/localized by viewing them. A Pass must be backed by **both** a *failed* text-only grep
  (Step 2 exercise) **and** a trial that could not diagnose/localize the defect without opening the
  image (trajectory audit above). If either the grep lands on the fix file or the trial solved it
  image-blind, it is **not** a Pass.

---

## Step 3 - Image evidence quality (#4)

Confirm no required image/video/GIF is missing and that each filename/role **matches what the image
actually shows**. If the real evidence is a **video/GIF**, a representative still frame may be added
in addition to, or in place of, it.

- **Fail (2) `[Fail - Bad Evidence]`:** the image is wrong/cropped/corrupted, is missing a required
  image present in the real issue, or is misnamed (e.g. the "bug" image actually shows the fixed
  state).
- **Pass (5):** all required images present, correct, and named for what they show.

---

## Step 4 - Metadata: task_type accuracy (#5)

Found in `Tasks/task.toml`. Check how the contributor mapped the image asset to one of the seven
task types. **Do not penalize** if the selection was valid but another type was arguably a better
fit.

- **Fail (2) `[Fail - Wrong task_type]`:** the `task_type` does not match the image.
- **Pass (5):** `task_type` is a valid value **and** matches the image asset. (Step 0.5 **H** checks
  the value; you judge the image match.)

---

## Step 5 - Evidence chain consistency (#6)

Do all four evidence references agree? Trace **one** asset end-to-end: `environment/assets/<file>`
<-> its `ASSET_MANIFEST.json` entry <-> its `evidence_bundle.json` entry (`local_path` =
`/app/.harbor_assets/<file>`) <-> the `instruction.md` image ref.

- **Fail (2) `[Fail - Evidence Mismatch]`:** the file in `environment/assets/`, its
  `ASSET_MANIFEST.json` entry, and the `instruction.md` image ref do **not** all point to the same
  asset, or do not point to the asset location under `/app/.harbor_assets/…`.
- **Non-Fail (3) `[Non-Fail Evidence Minor Mismatch]`:** only the `evidence_bundle.json` entry
  (role/url/local_path/description) points to a different asset location/reference than the other
  three.
- **Pass (5):** all four references agree. (Step 0.5 **I**.)

---

## Step 6 - Golden fix (#7, #8)

- **#7 Applies cleanly** - `git checkout <base_commit> && git apply --check solution/fix.patch`
  succeeds. Failure (usually `base_commit` and the patch out of sync) -> **Fail
  `[Fail - Patch Won't Apply]`**.
- **#8 Source-only scope** - the patch touches **source files only** and its `diff --git` paths
  equal `task.toml.files_edited` exactly (no test/doc/changelog/lockfile/`.changeset`). Otherwise
  -> **Fail `[Fail - Dirty Fix Scope]`**. (Step 0.5 **D**.)

---

## Step 7 - Tests (#9, #10, #11, #12, #13)

Read `tests/` in full.

- **#9 Implementation overfit** - for **each** assertion ask: *would a differently-written but
  behaviorally-correct fix still pass?* A test that pins the golden's exact bytes/output,
  function/file names, layout, or asserts a literal CSS-rule/source string causes **invalid fails**
  -> **Fail `[Fail - Overfit Tests]`**. **Pass** if all tests assert observable behavior and match
  tolerantly. (`harbor check` pre-flags this - but its image-blind "Behavior in Task Description"
  flag mis-fires; if the behavior is in the image, the tests are fair.)
- **#10 f2p/p2p identifier validity** - every id exists in the test files and matches **exactly
  one** test (watch substring collisions), and `config.json` f2p/p2p == `task.toml` f2p/p2p.
  Otherwise -> **Fail `[Fail - Bad Test IDs]`**. (Step 0.5 **F**.)
- **#11 p2p classification** - every `p2p` genuinely **passes on the untouched base**. If the PR
  changed a test's baseline/snapshot, it fails on base and is really an f2p. A p2p that fails on
  base -> **Fail `[Fail - Mislabeled p2p]`**. (Confirm via the gate: **Nop**.)
- **#12 Discriminating (f2p)** - every `f2p` **fails on base and passes on fix**. Confirm via the
  gate: **Nop** (base) fails the f2p (-> 0.0) and **Oracle** (fix) passes it (-> 1.0). An f2p that
  passes on base tests nothing -> **Fail `[Fail - Non-Discriminating]`**.
- **#13 Determinism** - the tests give the same result on every run; no timing/animation/network/
  unpinned-font dependence. A reward that changes between runs -> **Fail `[Fail - Flaky Tests]`**.
  (Ties into the Step 0.6 idempotency re-run.)

---

## Step 7.5 - Rubrics (v3 rubric layer)

Reconcile with **Step 0.55** (`check_rubrics.py`) and Step 0.5 **R**. Rubrics are judged against
the candidate's *code* by an LLM, **separately from the keyless f2p/p2p gate**, so nothing here
shows up in `reward.txt` - it is inspection-only. Read `tests/rubrics.json` in full alongside
`solution/fix.patch`.

- **Structure/schema/task/criteria** - confirm the `[FAIL]` classes from Step 0.55 are clear:
  file present + parses, recognised `schema`, `task` id matches `task.toml`/`config.json`, and
  every criterion has a unique id + non-empty text (`is_positive` a bool if present). Any of these
  -> a Structure-class **Rubrics Fail** (treat like #1: the judge can't score the task).
- **The six "Rules for rubrics"** - for each **real** criterion confirm it is: *atomic* (one
  distinct check), *specific & objective* (a measurable yes/no; names the file/function when it
  judges code), *self-contained* (decidable from the criterion text + the code alone), *positively
  worded* (an anti-pattern is described plainly with `is_positive=false`, not a "must not"),
  *not overly prescriptive* (phrased around the property, so an equally-valid differently-named fix
  still passes), and *sensibly grouped* (only fold checks that always fail together). Step 0.55
  flags candidates; you make the call from the text.
- **ACCURATE (mandatory manual)** - read `solution/fix.patch` and verify **every** real criterion
  is factually true of the golden. If the golden does not satisfy a rubric, the task is broken (the
  oracle would fail the judge) -> Rubrics Fail.
- **Right tool (manual)** - each real criterion must judge a **code-visible** property with several
  valid implementations (colour, spacing token, class, attribute, copy text). A rubric that tries
  to stand in for a **render-only** check the code gives no reliable signal for ("is it
  pixel-centered?") is a misuse - that defect stays a browser-harness no-go, not a rubric.
- **Placeholder** - the always-pass stub is acceptable **only** when the task is genuinely 100%
  covered by behavioral tests. If a code-only visual change (that a test can't assert without
  source-matching) was left with only the stub, a **real rubric is missing** -> Rubrics Fail.

> This is a v3 addition on top of the 16 v2 scored dimensions. Score it as a Structure-class
> pass/fail (`[Fail - Missing/Broken Rubrics]` / `[Fail - Bad Rubric Schema]` /
> `[Fail - Rubric Task Mismatch]` / `[Fail - Malformed Criteria]` / `[Fail - Inaccurate Rubric]` /
> `[Fail - Overfit or Misused Rubric]`) and fold it into the Step 10 decision like a #1 fault.

---

## Step 7.6 - Verify the judge mechanics (rubric-template) - NEW in v3.1

Steps 0.55 and 7.5 audit the rubric *content*. This step audits the **judge plumbing** that
actually runs it - the `rubric-template` machinery wired into `tests/`. Confirm the task ships a
working, **sub-agent** judge, not a half-applied or credentialed one.

> **How the judge is wired (know this before you check it).** The judge is a **sub-agent**: the
> verifier **never calls a model**. It is two-phase - (1) *during* the run `tests/judge.py` finds
> no verdict, writes a self-contained judge **request** (`criteria_payload.json`, `source.txt` =
> the candidate diff, `PROMPT.md`) under `/logs/verifier/judge/`, prints nothing, and exits 0, so
> the run scores **on tests alone**; (2) *after* the run a judge sub-agent writes `verdict.json`
> beside the request and `mm_run.sh <task> rescore` folds it into the reward **from the existing
> JUnit XML** - no container, no rebuild.
>
> **Reconciles the Step 7.5 note.** The rubric is scored separately from the keyless f2p/p2p gate
> and is invisible in `reward.txt` **until a verdict is folded in via `rescore`**. Once it is, the
> rubric *can* withhold a `1.0` and turn it into `0.5` - but it can **never** push a score toward
> `0.0`, and with no verdict the task always scores tests-only. So a rubric fault is still caught
> by inspection (Steps 0.55 / 7.5), never by a raw `reward.txt`.

### Static wiring checks (`check_judge.py`, then confirm by hand)

Run the dedicated v3.1 component - it mechanizes every static check below:

```
python3 check_judge.py "task_<taskId>/deliverables"
```

`check_judge.py` audits `JUDGE_FILE / JUDGE_SHAPE / NO_CREDS / CONFIG / TEST_SH / VERIFIER /
NO_SHADOW`. Findings are **candidates** unless marked `[FAIL]`. What it checks, and why:

- **`tests/judge.py` present and byte-for-byte the template.** It is identical in every task and
  must **never** be edited. Missing/edited -> **`[Fail - Missing/Broken Rubrics]`** (Structure).
  (The script compiles it and checks the template's load-bearing markers; the byte-for-byte diff
  against the `rubric-template` copy stays a quick manual confirm.)
- **No credentials anywhere.** The judge never calls out, so there must be **no** `[verifier.env]`
  block and **no** `ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY` / `JUDGE_MODEL` in `task.toml`
  (leftovers from the legacy "api" backend). `grep -c ANTHROPIC task.toml` must return **0** ->
  otherwise **`[Fail - Broken Structure]`**.
- **`tests/config.json` has `"rubric_file": "rubrics.json"`** and nothing exotic (no `judge_model`,
  `source_paths`, `rubric_criteria`). Missing key -> the rubric is never picked up.
- **`tests/test.sh` invokes the judge and can't fail the run.** It runs `judge.py` before the
  verifier and the `|| echo ""` / `trap` are intact (the judge must never fail the run), then calls
  `verifier.py … --rubric "${RUBRIC:-}"`.
- **`tests/verifier.py` records every test individually** in `reward.json` and applies the gate as
  *"withhold 1.0 -> 0.5 only"*.
- **No file in `tests/` is named after a stdlib module** (`select.py`, `json.py`, `types.py`,
  `io.py`, `queue.py`) - it shadows the real module and fails somewhere unrelated.

The equivalent one-liners, if you want to spot-check without the script:

```shell
D=task_<taskId>/deliverables/Tasks
grep -c ANTHROPIC "$D/task.toml"                       # expect 0
grep -q '"rubric_file"' "$D/tests/config.json" && echo "rubric_file wired"
python3 -m py_compile "$D/tests/judge.py" "$D/tests/verifier.py" && bash -n "$D/tests/test.sh"
```

### Behavioural checks (read `reward.json`, not just the float)

Reuse the Step 0.6 keyless runs, then drive the judge loop:

```shell
MM=~/.claude/skills/mmswe-runner/mm_run.sh
bash "$MM" "$D" oracle     # 1.0, every f2p true; a judge request must appear under verifier/judge/
bash "$MM" "$D" nop        # 0.0, and every f2p FALSE individually
bash "$MM" "$D" rescore --run <Oracle run dir>   # after a sub-agent writes verdict.json
```

> **`rescore` availability.** The bundled `mmswe-runner` skill ships oracle/nop/trial/check/analyze;
> the `rescore` mode exists only on a judge-enabled runner (it folds a sub-agent's `verdict.json`
> into the reward). If your `mm_run.sh` has no `rescore`, the **static** audit above plus confirming
> the **judge request appeared** is sufficient for review - the verdict-folding is the grader's job,
> not the reviewer's, and the rubric is compatible with (never a replacement for) the keyless gate.

- A **judge request** (`criteria_payload.json`, `source.txt`, `PROMPT.md`) must land under the run's
  `verifier/judge/`. If it doesn't, the rubric was never picked up -> check `judge.log` and the
  wiring above.
- After grading + `rescore`, the **oracle shows `rubric: "pass"`** in `reward.json`. If the golden
  fails the judge, the rubric is inaccurate -> **`[Fail - Inaccurate Rubric]`** (ties Step 7.5
  ACCURATE).
- The reward stays inside its contract: `reward.txt` is always a bare float in `{0.0, 0.5, 1.0}`;
  a failing rubric on an all-f2p-pass run reads `0.5`, never `0.0`.

> Any wiring fault here is a **Structure-class Rubrics Fail** - fold it into the Step 10 decision
> like a #1 fault, using the matching category above.

---

## Step 8 - Hardening (#14, #15)

- **#14 Difficulty (model trial fails)** - the submitted `Trials/Tasks__*/verifier/reward.txt`
  shows the model scored **< 1.0**. A passing (reward = 1.0) or **missing** trial -> **Fail
  `[Fail - Not Hard Enough]`**. *(Satisfied whether the failure comes from the deputy's hardening
  or from a task that was already hard enough at base - what matters is that the submitted trial
  fails.)* You do **not** need to re-run the trial; use the shipped `reward.txt` and
  `harbor analyze` (Step 0.7) to confirm the trial genuinely failed rather than the agent
  **cheating** by editing the environment/verifiers.
- **#15 Real & feasible** - is the hardened task still a coherent real issue a capable agent could
  solve from **symptom + image alone**? **Fail `[Fail - Unreal or Infeasible]`** if hardening
  invented behavior the code doesn't have / a fix no real developer would write, a cut left no
  discoverable path to the fix (unsolvable-by-perception), or the image assets can't be used to
  solve the issue (extreme vagueness or irrelevance). **Pass** if it stays a genuine, coherent,
  image-solvable issue.

  > **Mandatory scope-coverage check (the common miss).** Build a coverage table: list **every**
  > `task.toml.files_edited` entry and **every** `f2p` id, and for each one point to the specific
  > sentence in `instruction.md` **or** the specific region of the image (`environment/assets/`)
  > that makes it discoverable. **Any fix file or f2p with no perceptual anchor is an
  > unsolvable-by-perception cut -> #15 Fail.** Watch for a golden that touches a *second subject*
  > the perception never names (e.g. fix edits both `infinity-points.js` and `eternity-points.js`
  > but the instruction + screenshot only ever mention Infinity Points, and its EP f2p have no
  > anchor). Record the table in the eval.
  >
  > **Do not conflate #15 with #14.** A trial scoring < 1.0 satisfies #14 (Step 8 below), but if it
  > scored low *because* it never touched a required-but-unreferenced file, that is a **#15 Fail**,
  > not evidence of good difficulty. Never reuse the same "trial missed file Z" fact as positive
  > evidence for both #14 and #15 - if file Z has no perceptual anchor, #14 may pass while #15
  > **fails**.
  >
  > **`harbor analyze` is an aid, not a verdict.** It cannot read the image, so its
  > "incomplete implementation, not ambiguous" conclusion cannot clear an undiscoverable cut.
  > Confirm the coverage table by hand before scoring #15 Pass.

---

## Step 9 - Gate (#16)

- **#16 Gate - Oracle/Nop** *(reproduce, don't trust)* - from Step 0.6: your independently re-run
  Oracle = 1.0, Nop = 0.0, the verifier reached completion, the run is idempotent on re-run, and
  your reproduced rewards match the submitted ones. Otherwise (Oracle != 1.0, Nop != 0.0, verifier
  didn't complete / "could not apply test.patch", or a non-idempotent re-run) -> **Fail
  `[Fail - Gate Broken]`**.

---

## Unauditable check

Score this only if the task is genuinely **unauditable or spam** - you cannot review it at all
(e.g. the runs' `task_checksum` don't agree so the folders don't correspond to the same `Tasks/`,
the bundle is unreadable, or the submission is spam). Score **1 `[Un-auditable]`** in that case;
otherwise score **5** (task is auditable).

---

## Step 10 - Score, record, decide

Score each of the 16 dimensions (+ Unauditable) in the "QC Rubric scoring" table of
`eval_<taskId>.md`: **5** Pass · **3** Non-Fail (only #3, #6) · **2** Fail · **1** Un-auditable ·
**N/A**. Record the named error category on every Fail.

Reconcile with Step 0.5: **#2**<-A · **#1**<-B (+#4 decode) · **#8**<-D · **#10**<-F · **#5**<-H ·
**#6**<-I · **Rubrics**<-R. Reconcile with Step 0.55 (`check_rubrics.py`) and Step 7.5 for the
rubric *content*, with **Step 7.6** for the rubric *judge mechanics*, and with Step 0.6:
**#16/#14/#11/#12/#13** <- the reproduced gate.

**Final decision (v2 marks no dimension "critical", but use judgement):**
- **Reject** if Structure fails (#1/#2), a **Rubrics** structural fault (Step 7.5:
  missing/broken/mismatched/inaccurate rubric; or Step 7.6: broken judge wiring / credentialed
  judge / oracle fails the judge), the **gate** can't be reproduced (#16), or the task is
  **Unauditable**.
- **Revise** - list the required fixes for any other Fail (including a rubric that only needs its
  wording tightened to satisfy the six rules).
- **Accept** - all 16 dimensions Pass (or a defensible Non-Fail on #3/#6), the rubric layer is clean
  (Step 7.5), the gate reproduces, and the task is auditable.

## Step 11 - Repeat

For the next task, copy this process from **Step 0** with the new task id.

---

## Appendix - v2 dimension -> step map

| # | Dimension | Non-Fail? | Reviewed in | Pre-check | Fail category |
|---|---|---|---|---|---|
| 1 | Structure - Task Bundle Files | no | Step 1 | B | [Fail - Broken Structure] |
| 2 | Structure - Deliverables & Packaging | no | Step 1 | A | [Fail - Deliverable Packaging] |
| 3 | Instruction - Requires the Visual Evidence | yes | Step 2 | grep + Trials trajectory audit (+`harbor analyze`) | [Fail - Assets Not Needed] |
| 4 | Image - Evidence Quality | no | Step 3 | B (decode) | [Fail - Bad Evidence] |
| 5 | Metadata - task_type Accuracy | no | Step 4 | H | [Fail - Wrong task_type] |
| 6 | Evidence - Chain Consistency | yes | Step 5 | I | [Fail - Evidence Mismatch] |
| 7 | Golden Fix - Applies Cleanly | no | Step 6 | (git apply) | [Fail - Patch Won't Apply] |
| 8 | Golden Fix - Source-Only Scope | no | Step 6 | D | [Fail - Dirty Fix Scope] |
| 9 | Tests - Implementation Overfit | no | Step 7 | `harbor check` (image caveat) | [Fail - Overfit Tests] |
| 10 | Tests - f2p/p2p Identifier Validity | no | Step 7 | F | [Fail - Bad Test IDs] |
| 11 | Tests - p2p Classification | no | Step 7 | Step 0.6 (Nop) | [Fail - Mislabeled p2p] |
| 12 | Tests - Discriminating (f2p) | no | Step 7 | Step 0.6 (gate) | [Fail - Non-Discriminating] |
| 13 | Tests - Determinism | no | Step 7 | Step 0.6 (re-run) | [Fail - Flaky Tests] |
| 14 | Hardening - Difficulty (Trial Fails) | no | Step 8 | Step 0.6 (Trials) · `harbor analyze` | [Fail - Not Hard Enough] |
| 15 | Hardening - Real & Feasible | no | Step 8 | `harbor analyze` | [Fail - Unreal or Infeasible] |
| 16 | Gate - Oracle/Nop | no | Step 9 | Step 0.6 | [Fail - Gate Broken] |
| v3 | Rubrics - rubrics.json (schema/task/criteria/rules/accurate) | no | Step 7.5 | Step 0.5 **R** + Step 0.55 `check_rubrics.py` | [Fail - Missing/Broken Rubrics] / [Fail - Bad Rubric Schema] / [Fail - Rubric Task Mismatch] / [Fail - Malformed Criteria] / [Fail - Inaccurate Rubric] / [Fail - Overfit or Misused Rubric] |
| v3 | Rubrics - judge mechanics (sub-agent wiring, no creds, judge request + rescore) | no | Step 7.6 | Step 0.6 (judge request) + `grep ANTHROPIC` / `py_compile` | [Fail - Missing/Broken Rubrics] / [Fail - Broken Structure] / [Fail - Inaccurate Rubric] |
| - | Unauditable | no | Unauditable check | check_gate (checksum) | [Un-auditable] |
