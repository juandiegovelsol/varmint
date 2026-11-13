# Changelog

All notable changes to the MM SWE sandbox suite (`mmswe-runner`, `mm-swe-qc-fix-sandbox` and
their slash commands) are recorded here.

## 1.0.8 — 2026-11-12

The cost ledger now reads the CB's Claude Code sessions after every trial, not only a passing
one, and no longer records oracle or nop. The QC instruction read works with current models
again; before this, every audit fell back to the static phrase scan.

### Cost ledger (`mmswe-runner` 1.6.0 -> 1.6.1)

- **The CB-session reading is taken after every trial that ran, pass or fail.** It used to be
  taken only when a trial passed. Each reading still **replaces** the previous one, since ccusage
  re-reads every session file and the newest reading already contains the older ones. A CB who
  keeps working after a pass is now counted at the end of the next trial, whatever its verdict.
  Before, that work was lost unless the next trial passed too.
  - That includes a trial that ended early: a text-only solve, an incomplete text-only phase,
    unreadable rewards, or a run killed after harbor started.
  - A trial refused before harbor ran leaves no job folder and takes no reading.
  - Chat after the last trial is still not counted.
- **Only `cb_sessions` replaces.** `runs` and `api_calls` still add: one row per harbor job id
  and one per paid call. Recording the same job twice still updates its one row.
- **`cb_sessions` fields:**
  - `trigger.result` is the trial's real outcome (it was always "passed"), and `trigger.passed`
    says whether it passed.
  - `readings` counts every reading, and `passes_seen` now counts passing trials only.
  - `last_passing_trial` (`taken_at`, `cost_usd`, `result`) keeps the value as of the latest pass.
  - A failed reading still never replaces a good one. It is noted in `last_failed_snapshot`,
    now with its trigger.
- **`summary`** shows the latest reading with that trial's outcome, plus the value at the last
  passing trial.
- **Oracle and nop are no longer recorded.** Neither runs an agent, so harbor has no model cost
  for them and every row read $0. A task with `tests/rubrics.json` can still pay for a judge
  during them. The host-side grader (`mm_grade_rubrics.py`) logs that itself as an `api_calls`
  row, so it is still counted. Oracle and nop rows already in an existing ledger are left in place.

### QC instruction read (`mm-swe-qc-fix-sandbox` 2.2.1 -> 2.2.2)

- **No `temperature`.** Current models reject it with HTTP 400 ("deprecated for this model"),
  which forced every audit onto the static phrase scan without saying so.
- **`max_tokens` 1024 -> 16000.** Current models think before they answer, and thinking counts
  against `max_tokens`. The instruction read spends about 4k tokens thinking, so a 1024 cap cut
  off every reply before its text.
- **HTTP errors include the API's own message**: the innermost `"message"` from a proxy-wrapped
  error, up to 200 characters.
- **When the static phrase scan is used, the reader label says why** the model read was not
  used, instead of a bare "static phrase scan".

### Files

- `skills/mmswe-runner/mm_run.sh`:
  - `cost_record()` skips oracle and nop. After every trial that left a job folder, it takes the
    CB-session reading, passing `--trial-result` and, on a pass, `--trial-passed`.
  - `COST_TRIAL_RESULT` is set at each exit of `post_trial_verdict` and at the three text-only
    early exits in `run_trial`.
- `skills/mmswe-runner/mm_cost.py`: `--trial-result` / `--trial-passed` on `record-run` and
  `snapshot-sessions`, the new `cb_sessions` fields and the `summary` lines.
- `skills/mm-swe-qc-fix-sandbox/checks/qc_llm.py` and `checks/qc_structure.py`.
- Both `SKILL.md` version fields bumped.

## 1.0.7 — 2026-11-11

The suite now records what each sandbox spends on models in a cost ledger,
`~/.mm_swe_cost/ledger.json`. Recording is silent. Runner output, exit codes and every check
are unchanged. The ledger stays in the sandbox and is never part of the deliverable.

### Cost ledger (`mmswe-runner` 1.5.0 -> 1.6.0)

- **Three sources, each counted once:**
  - **`runs`:** one row per harbor job: oracle, nop, the text-only and normal trial phases,
    pseudo-trial, check, analyze. Written after **every** run, pass or fail. The cost is
    harbor's own `stats.cost_usd`.
  - **`api_calls`:** direct Messages calls that are not Claude Code sessions: the QC instruction
    read and the host-side rubric grader. Raw `usage` is priced from LiteLLM's table. Cache hits
    cost nothing and are not logged.
  - **`cb_sessions`:** the CB's own Claude Code sessions (`~/.claude/projects`), read with ccusage
    **only when a trial passes** (0 of 3 text-only solved, exactly 1 of 4 normal solved).
- **A passing trial replaces the CB-session reading; it does not add to it.** ccusage re-reads
  every session file each time, so a later reading already includes the earlier one. Adding
  them would count the earlier work twice. Chat after the last passing trial is not counted.
  Runs and API calls after it (check, analyze, reviewer check) are.
- **Cross-check.** ccusage re-prices each run's copied agent sessions. A gap of more than 2% from
  harbor's figure is flagged `mismatch: true`. Tested on recorded trial, check and analyze runs,
  the two matched to the cent.
- **Killed runs are not lost.** `mm_run.sh` records before each mode runs as well as after. The
  before-run pass picks up a previous job that was killed before it could record itself, since
  the mode is about to delete that job's folder. It only adds missing rows.
- **One row per job.** Rows are keyed on harbor's job id, so recording a job twice updates one row.
- **Never fails a run.** All output goes to `/dev/null`, errors are swallowed and the exit code
  is untouched. A failed ccusage reading never overwrites a good one, and an unreadable ledger is
  moved aside, not overwritten. Writes are locked and atomic.
- **Reading it:** `python3 ~/.claude/skills/mmswe-runner/mm_cost.py summary` gives totals by
  source, mode and API caller. `--runs` lists every row (harbor's figure next to ccusage's),
  `--task ID` and `--since YYYY-MM-DD` filter, and `--json` gives machine-readable output.
- **Dependencies:** ccusage `20.0.45` on Node `22.20.0` (pip `nodejs-wheel`), installed with no
  output on first use into `~/.mm_swe_cost/`. The first recorded run in a fresh sandbox takes
  about 10 s longer.
- **Env:** `MM_COST=0` records nothing. `MM_COST_HOME=<dir>` moves the ledger (for testing).
- **Not captured:** a task whose own `tests/judge.py` calls a model from inside the verifier
  container (the template judge makes no calls), and CB chat after the last passing trial.
  Every Claude Code session under `~/.claude/projects` is counted, including ones unrelated to
  the task.

### Files

- **New:** `skills/mmswe-runner/mm_cost.py` (ledger, ccusage wrapper, `summary`).
- `mm_run.sh`: `cost_record()`, called before and after the mode dispatch; exports
  `MM_COST_TASK_ID` / `MM_COST_TASK_DIR` so API-call rows carry the task; marks a passing trial
  in `post_trial_verdict`.
- `mm_grade_rubrics.py` and `checks/qc_llm.py` (`mm-swe-qc-fix-sandbox` 2.2.0 -> 2.2.1) log each
  paid call.

## 1.0.6 — 2026-11-09

The instruction is now read by a model when one is reachable: one text-only call checks it against
the instruction, symptom-specificity and image-dependency requirements. Nothing new can block, and
the audit still runs with no API key.

### Instruction read (`mm-swe-qc-fix-sandbox` 2.1.0 -> 2.2.0)

- **One Sonnet 5 call, text only.** It reads `instruction.md` (title, headings and evidence captions
  included), the f2p test names and, when `task.toml` has one, the `difficulty_explanation`, as
  ground truth for what the task grades. No images, no fix, no test bodies. It replaces the
  vague-phrase and time-window lists when a model answers.
- **Every graded defect must be accounted for.** `instr_lint_undescribed_defect` names an f2p test
  whose behaviour the text neither states nor points to an image for, and
  `instr_lint_vouches_defect` flags a truth sentence or caption that vouches for what a graded
  defect changes. Calibrated on the pioneer_5999 fail: the injected moon numbering was graded but
  never described, and "what the screenshots show about this moon and its neighbours is correct"
  plus a caption calling the labels the game's own names vouched for it. A test name that is not in
  the f2p list is dropped, like an invented quote.
- **Instruction check.** The element must be named by type, without hinting at the fix. The defect
  and expected result may be shown through a comparison image the text points to; which instance
  may stay in the image.
- **Symptom specificity.** A general phrase passes when the same or the next sentence says what is
  affected, what kind of problem it is, or which image shows the correct result. It fails standing
  alone, or when a time window **or a region** (*in the frame centre*) is the only explanation.
- **Image dependency.** The text must say what kind of problem it is or point to the correct
  result, keep the clue to the cause in the image, and not describe the problem as the wrong kind.
- **New finding ids, model read only:** `instr_lint_hints_fix` (the prose describes the cause or the
  fix), `instr_lint_clue_leak` (gives away which instance, the trigger, the size, the timing, the
  error text, or an expected result that should point to a reference image instead) and
  `instr_lint_misdescribed`. `instr_lint_vague` now also covers an element named with no kind of
  problem and no pointer to the correct result.
- **Unchanged word scans:** leaks, cause words and `instr_lint_vague_truth` (a CB ruling, not part
  of these requirements). The *two readings* rule of the first draft is gone.
- **Regions in the fallback too.** The phrase scan's bare-window rule also catches a region of the
  frame given as the only explanation.
- **Falls back to the phrase lists** on no proxy, an HTTP error, a non-JSON reply, or `MM_QC_LLM=0`.
  The evidence line then says hints at the fix, clue leaks and misdescription were not checked. A
  refused connection gives up at once, so an offline audit is not slowed down.
- **Says who read it.** Each finding's first evidence line names the model or says
  `static phrase scan` and why. A clean read is pinned on the EVIDENCE & IMAGE line as
  `instruction read (<who>): clean` (new OK id `instr_lint_symptom_clean`).
- **Invented quotes are dropped.** A model finding whose quote is not in `instruction.md` is
  discarded and counted.
- **Cached outside the bundle** (`~/.cache/mm-swe-qc/llm/`, or `MM_QC_LLM_CACHE`), keyed on model,
  prompt, instruction and explanation. The `qc_gate()` re-audit and every post-fix re-audit of an
  unchanged task make no call and get the same answer.
- **New files:** `checks/qc_llm.py` (credentials, request, cache) and
  `checks/prompts/instruction_read.txt` (the prompt). Credentials resolve like `mm_run.sh`:
  env, then `~/.claude/settings.json`, then the anonymizer at `http://localhost:8091`.
- **Cost:** about $0.008–$0.019 per uncached call at Sonnet 5's $2/$10 per million tokens, so about
  $8–$19 per 1,000 new tasks.

## 1.0.5 — 2026-11-05

A new instruction wording scan checks `instruction.md` against the Lean Instruction Playbook, and
`/run-check` now reports its result every time, next to the "could this be fixed without the
screenshots?" read. Nothing new can block: every finding is advisory.

### Instruction wording scan (`mm-swe-qc-fix-sandbox` 2.0.0 -> 2.1.0)

- **New group L in `checks/qc_structure.py`** (`check_L`), reported under **3. EVIDENCE & IMAGE**.
  It reads text only (instruction dims 3/4/5 of the playbook, Official V25):
  - `instr_lint_leak`: the text or title names a URL, code host, issue/PR/commit, source file,
    `call()`, scoped or code-style identifier, a size with a unit, quoted error text, or the
    repository's own name.
  - `instr_lint_cause_word`: a word from the golden fix's changed lines appears in the text. Fine
    if it names the element that looks wrong; cut it if it names the cause.
  - `instr_lint_vague`: a generic phrase stands in for the defect (*something*, *broken*,
    *doesn't work*, *not … correctly*). This is the playbook's "unspecific symptom" Fail.
  - `instr_lint_time_window`: a timestamp is the whole explanation, with no element and defect
    word next to it.
  - `instr_lint_vague_truth`: a sentence says the images are *correct* about something generic
    (*what the screenshots show … is correct*, *everything else is correct*, *the screenshots are
    otherwise correct*) without saying **what** is correct. Naming it clears the finding (*the moon
    names, their numbering and the orbit order … are correct*).
  - `instr_lint_no_image_truth` / `instr_lint_no_reference`: images ship but no sentence says
    they are correct apart from the defect, or nothing points to what correct looks like.
- **Advisory by construction.** Every finding is a `CANDIDATE` and group L has no rubric dimension,
  so it cannot change the exit code, withhold the QC pass, or keep oracle/nop grounded.
- **Matches phrases, not words.** Only negated or generic forms of *correct* count as vague, because
  the playbook asks for a positive truth sentence. A positive one is judged by what it calls correct.
- **Calibration:** luanti_12770 comes out clean and the playbook's Dim 4 Fail example fires.
  pioneer_5999 comes out clean **except** `instr_lint_vague_truth`, on purpose: "what the screenshots
  show about this moon and its neighbours is correct" never says what is correct.

### Report

- **A clean scan is printed.** It used to be folded into "N check(s) clean", which left the CB no
  sign the scan had run. The category line now names it:
  `3. EVIDENCE & IMAGE  OK — 3 check(s) clean · instruction wording scan: clean` (`PINNED_OK` in
  `checks/qc_common.py`).
- **Wording findings are labelled** `Instruction wording · advisory` instead of leaving the
  dimension column blank.
- Display only: blocking, exit codes and the QC pass are unchanged.

### `/run-check`

- New section, **"Always report the two instruction reads together"**. The agent reports
  "could this be fixed without the screenshots?" and the wording scan side by side under *Worth your
  eye*, every time. Every `instr_lint_*` hit is given in plain words with the flagged phrase and
  what to write instead, and a clean scan is reported as clean, not left out.
- Worked example and glossary pointers updated (`FINDINGS_GLOSSARY.md` covers every new id).

`mmswe-runner` is unchanged (1.5.0).

## 1.0.4 — 2026-11-05

A trial phase now stops as soon as its outcome is decided, so you no longer pay for attempts that
cannot change the verdict. The trial rule itself is unchanged from 1.0.3.

### Circuit breaker (`mmswe-runner` 1.4.0 -> 1.5.0)

- **On by default, trial only.** Attempts run concurrently. While harbor runs, the runner polls
  the rewards and sends harbor SIGTERM once enough solves are in to decide the phase:
  - **text-only:** the first solve (any text-only solve fails the trial);
  - **normal:** `TRIAL_MAX_SOLVED + 1` solves, today the 2nd (one solve above the band is
    blocked as too easy, whatever the remaining attempts do).
  Both limits come from `text_only_rule()` / `trial_rule()`, so moving the band moves the breaker.
- **Cancelled attempts get no reward.** The tally covers only the finished attempts (e.g.
  `pass@3: 2/3`). That is a decided result, not an *incomplete* one: the existing rule already
  exempts solve-decided outcomes from the "every attempt must produce a reward" check.
- **What you see:** a `CIRCUIT BREAKER — <phase>: N of M finished attempt(s) solved the task` line,
  and the verdict notes how many attempts the breaker cancelled.
- **Teardown.** Harbor's own teardown is cut short by the SIGTERM, so after a trip the runner
  removes leftover containers, networks and volumes, scoped to that phase's own attempts only.
  Images are kept as build cache. If harbor is still running `MM_BREAKER_GRACE` seconds after
  SIGTERM (default 600), it gets SIGKILL and a warning to check `docker ps`.
- **Options.** `--no-circuit-breaker` runs every attempt to completion (e.g. to see the full
  distribution). `MM_BREAKER_POLL` sets the poll interval (default 15s).
- **Attempt listing.** An attempt cancelled after its verifier finished now shows its reward from
  `verifier/`, marked `[verifier reward; harbor cancelled the attempt before recording it]`, so the
  listing agrees with the tally. One cancelled before it produced a reward is listed as
  `cancelled`, not as "not an attempt".

### Docs

- `SKILL.md`, `/run-trial` and this `README.md` describe the circuit breaker.
- Fixed leftovers from the 1.0.3 rule change: the `SKILL.md` verdict table still said
  "normal (8)" (now "normal (4)"), and `SKILL.md` and `/run-trial` said 3+ normal solves block
  an incomplete phase (now 2+).

## 1.0.3 — 2026-11-04

The normal phase of the trial is back to a fixed pass@4, and a trial passes only when exactly 1 of
the 4 attempts solves the task.

### Trial rule (`mmswe-runner`)

- **Normal attempts: 8 -> 4.** `N_ATTEMPTS` in `mm_run.sh` (the `--n_trial` default) is now 4.
- **Pass band: 1 or 2 -> exactly 1.** `TRIAL_MAX_SOLVED` is now 1 (`TRIAL_MIN_SOLVED` stays 1).
  0 of 4 still blocks `check-reviewers` (no passing attempt); 2–4 of 4 is blocked as too easy.
- **Text-only phase unchanged:** 3 attempts with every image stripped, all must fail.
- `trial_rule()`, the reviewer path and every message read the two variables, so no logic changed.
  Both gates were exercised against simulated rewards for 0–4 of 4 solves, a crashed attempt, and
  old 8-attempt runs: only 1 of 4 is recorded and verified.
- A trial recorded under the 1.0.2 8-attempt rule is now refused on both the trial and reviewer
  paths: as *incomplete* (8 rewards where 4 are expected), or as too easy when 2+ attempts solved.
  Re-run the trial.
- `SKILL.md`, `/run-trial`, `/run-check-reviewers` and the suite `README.md` updated to match.

## 1.0.2 — 2026-10-30

The normal phase of the trial is now pass@8 with a pass band of 1–2 solves, and a task-root
`README.md` is no longer flagged by QC.

### Trial rule (`mmswe-runner`)

- **Normal attempts: 4 -> 8.** `N_ATTEMPTS` in `mm_run.sh` (the `--n_trial` default) is now 8.
- **Pass band: exactly 1 -> 1 or 2.** `TRIAL_MAX_SOLVED` is now 2 (`TRIAL_MIN_SOLVED` stays 1).
  0 of 8 still blocks `check-reviewers` (no passing attempt); 3–8 of 8 is blocked as too easy.
- **Text-only phase unchanged:** 3 attempts with every image stripped, all must fail.
- `trial_rule()`, the reviewer path and every message read the two variables, so no logic changed.
- A trial recorded under the old 4-attempt rule now reads as *incomplete* (4 of 8 attempts) on
  both the trial and reviewer paths: re-run the trial.
- `SKILL.md`, `/run-trial`, `/run-check-reviewers` and the suite `README.md` updated to match. The
  README's trial section also drops a stale "majority ceiling at `--n_trial=7`" description that
  no longer matched the code.

### QC: `README.md` is part of the canonical layout (`mm-swe-qc-fix-sandbox`)

- `README.md` at the task root is now **allowed, not required** (`CANON_EXACT` in `fix.py`,
  `template/CANONICAL_LAYOUT.txt`). It used to be reported as a `stray_files` candidate under
  "need your decision", with deletion as the offered fix, which stalled the QC flow on every task
  that ships one.
- Harbor hashes `README.md` together with `task.toml` and `instruction.md` (it is one of
  `qc_digest.HARBOR_ROOT_FILES`), so deleting it would also have moved the bundle digest.
- Any other file outside the layout is still reported as `stray_files`.

## 1.0.1 — 2026-10-30

QC now checks that `task.toml` carries the task's identity block.

### New check: task.toml identity (group K)

`mm-swe-qc-fix-sandbox` has a new group K in `checks/qc_structure.py` that requires:

```toml
[task]
name = "scale-ai/<task_id>"

[metadata]
task_id = "<task_id>"
title = "..."
repository_name = "<owner>/<repo>"
```

- **`[task]` name** must be `scale-ai/` followed by exactly `[metadata] task_id`
  (`toml_task_missing`, `toml_task_name_missing`, `toml_task_name_mismatch`).
- **`[metadata]`** must set `task_id`, `title` and `repository_name`, all non-empty
  (`toml_metadata_missing`, `toml_metadata_<key>_missing`). The title is checked for presence
  only, not for a fixed value.
- **`repository_name`** must be in `<owner>/<repo>` form and, when `repo_url` is set, name the same
  repository (`toml_repository_name_format`, `toml_repository_name_mismatch`). HTTPS, `ssh://` and
  `git@host:owner/repo` URLs are all understood, with or without `.git`.
- The finding ids are listed in `FINDINGS_GLOSSARY.md`.

The check reads `task.toml` per table, so it also works on the sandbox's Python 3.10, which has no
`tomllib`. It accepts single- and triple-quoted strings, comments, CRLF line endings, and
`[task]` before or after `[metadata]`. `[task.<sub>]` does not count as `[task]`.

### Compatibility

- **Group K findings are blocking.** They book against "Fail - Broken Structure", so a task
  without the `[task]` table now fails QC until it is added. `fix.py` does not insert it
  automatically; add it by hand.

### Known limitations

- `task.toml` is read with patterns, not a full TOML parser. A line starting with `[` inside a
  multi-line string would be taken as the start of a new table.

## 1.0.0 — 2026-10-28

First versioned release. The trial now writes its output in the delivery template's layout.

### Trial output layout

`/run-trial` used to write the normal attempts to `<ROOT>/Trials/` and the text-only attempts to
`<ROOT>/Trials_TextOnly/`. Both phases now live under `Trials/`, one flat harbor job per phase,
with no timestamped job dir in between:

```
<ROOT>/Trials/
  without_images/   config.json  lock.json  result.json  job.log  harbor_run.log
                    task_without_images__<rand>/   ×3   text-only attempts (images stripped)
  with_images/      config.json  lock.json  result.json  job.log  harbor_run.log
                    task_with_images__<rand>/      ×4   normal attempts
```

- **Job names.** harbor is called with `-o <ROOT>/Trials --job-name without_images` and
  `--job-name with_images`, so each job's `config.json` records `job_name: with_images` (or
  `without_images`) instead of a timestamp.
- **`harbor_run.log`.** harbor's console output is now kept in each job dir, as the template
  carries it.
- **Attempt dir names.** harbor names attempts after the task folder, so each phase now runs from
  a copy of the task named `task_with_images` or `task_without_images`. Folder names change no
  digest (harbor hashes contents and relative paths only) and no Docker image cache entry (keyed
  on a hash of the build context).
- **Where the copies live.** `~/.cache/mm_run/trial_tasks/<task-id>/`, rebuilt by every trial and
  outside `<ROOT>`, so it never ships. They are no longer temp dirs: each attempt's `result.json`
  records its task path, and `/run-analyze` reads the instruction, tests and solution from there.
  This also fixes the text-only copy being deleted right after phase 1, which left analysis of
  text-only attempts without the task.

### Everything that reads trial results follows the new layout

- **`mmswe-runner` (`mm_run.sh`)**: the trial verdict and record, `/run-check-reviewers`'
  verification of shipped runs (digests, rewards, counts and the text-only half),
  `/run-pseudo-trial`, `rescore` and `/run-analyze` (a task dir now analyzes
  `Trials/with_images`).
- **`/run-analyze` root detection.** Given a job or attempt dir under `Trials/<phase>/`, analyze
  now writes `Analyze/` at the root instead of inside the trial output.
- **`mm-swe-qc-fix-sandbox`**: a new `qc_layout.run_path()` resolves the `Trials` run to
  `Trials/with_images/`, so the QC checks (trial reward, trial model, 90-minute rule, timeout
  clause, phase detection) never count text-only attempts as normal ones. A `Trials/` without
  that split is still read as it is.
- **Timestamped deliveries.** The QC checks now also read `Trials/with_images/<timestamp>/`
  layouts. Before, they found no trials in them at all.
- **Docs.** `run-trial`, `run-check-reviewers`, `run-analyze` and `run-pseudo-trial`, plus both
  skills' `SKILL.md`, describe the new folders.

### Compatibility

- **`Trials_TextOnly/` is no longer read.** The runner deletes it when a new trial starts.
  Deliveries made in the old layout need a fresh `/run-trial` before `/run-check-reviewers` can
  verify them.
- **External gate scripts** that look for attempts directly under `Trials/`, or for
  `Trials_TextOnly/`, must be pointed at `Trials/with_images/` and `Trials/without_images/`.
  Attempts sit at `<job>/<attempt>/verifier/reward.txt`, one level deeper in timestamped jobs.
- **Text-only runs from other pipelines** cannot be verified by `/run-check-reviewers`: their
  image stripping differs from this runner's, so their recorded digest never matches the rebuilt
  one. Re-run the trial with this version.

### Known limitations

- Each job dir also holds `bridge.log` (proxy diagnostics), and `with_images/` holds
  `task_manifest.json` (the baseline `/run-pseudo-trial` needs). Neither is in the delivery
  template; remove them before delivery if an exact match is required.
- `task_name` in each attempt's `result.json` is `task_with_images` / `task_without_images`,
  where the template has `task`.
- `Oracle/` and `Nop/` are still written flat, without a `harbor_run.log`.
- On a cold Docker cache, harbor can fail concurrent attempts with a `Deadlock` error while
  building its egress-control sidecar image for the first time. This is a harbor issue; re-run
  once the image is cached.
- The layout has been checked with real harbor through attempt creation, but not yet through a
  complete trial, so the final contents of `harbor_run.log` are unverified.
