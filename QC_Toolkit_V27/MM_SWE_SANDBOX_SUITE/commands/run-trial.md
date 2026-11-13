---
description: Run the MM SWE agent trial (claude-code @ claude-opus-5-5) — 3 text-only + 4 normal attempts
---

Run the agent trial for the MM SWE task the user names. A trial is **11 attempts in two phases**.

1. Locate the task dir (the folder containing `task.toml`: `/home/sandbox/Tasks` in the flat layout, or
   `/home/sandbox/Tasks/<task-name>/` in the nested one - any folder name. Passing
   `/home/sandbox/Tasks` works for both when it holds a single task).
2. Run: `bash ~/.claude/skills/mmswe-runner/mm_run.sh "<task-dir>" trial`
   - Model defaults to `anthropic/claude-opus-5-5`; override with `--model`.
   - **Phase 1 — text-only, pass@3** (`--n_text_only=N` to change). The runner copies the task,
     removes every image from it (inline, reference-style and `<img>` images in
     `instruction.md`; every image source in the Dockerfile's `COPY`/`ADD` lines; and the image
     files themselves, so the agent cannot find the picture in `/app/.harbor_assets` either), and
     runs 3 attempts on that copy into `<ROOT>/Trials/without_images/`. **All 3 must fail** — that
     shows the image is really needed. Everything that is not an image stays — the prose, and
     text evidence such as logs: the question is whether the words alone are enough.
   - **Phase 2 — normal, pass@4** (`--n_trial=N` to change), on the real bundle, into
     `<ROOT>/Trials/with_images/`. **Runs only if every text-only attempt failed**: one text-only solve
     already decides the trial, so the 4 normal attempts are not paid for.
   - **Circuit breaker** (on by default): attempts run concurrently, so the runner watches each
     phase and stops harbor once the verdict is decided. That is the **first text-only solve**
     (pass@3), or the **2nd normal solve** (pass@4, `TRIAL_MAX_SOLVED + 1`). Attempts still running
     are cancelled with no reward. Look for `CIRCUIT BREAKER` in the output. The tally then covers
     only the finished attempts (e.g. `pass@3: 2/3`), which is a decided result, not an
     incomplete one, so don't tell the CB to re-run because of the missing attempts. Pass
     `--no-circuit-breaker` only if the user wants every attempt run to completion.
   - Refused before anything is spent: a task with no image to strip, and a Dockerfile that
     downloads an image in a `RUN` line (it cannot be stripped safely; ship the image under
     `environment/assets/` and `COPY` it instead).
   - **Every attempt must produce a reward.** An attempt that crashes writes none; a phase with
     fewer rewards than attempts is *incomplete* and not recorded (re-run), unless a solve has
     already decided it — a text-only solve fails the trial, and 2+ normal solves block it.
3. Credentials resolve automatically: live env, then `~/.claude/settings.json`, then the
   anonymizer defaults (`http://localhost:8091` + `anonymizer-placeholder`). The run does
   not stop for a missing key — it falls back to those defaults, and bridges the loopback
   proxy so the agent container can reach it. If the log shows a bridge WARNING or the
   agent fails to reach the model, report the exact URL from the `[mm_run] creds` line.
4. Output lands in `<ROOT>/Trials/without_images/` and `<ROOT>/Trials/with_images/` — each a
   flat harbor job (its `config.json`, `lock.json`, `result.json`, `job.log`, a `harbor_run.log`
   of harbor's console output, and the attempt dirs; no per-task subfolder and no timestamped
   job dir). Attempt dirs follow the template: `task_with_images__<rand>` (normal) and `task_without_images__<rand>`
   (text-only) — both phases run from copies with those folder names under
   `~/.cache/mm_run/trial_tasks/<task-id>/`. A run overwrites any previous trial unless `--keep` was passed. Report every
   attempt's reward for both phases and, for anything unexpected, point at the trajectory.
5. If `/run-nop` has not been run on this task, say so: the oracle passing does not prove
   the tests discriminate, so a trial reward is not yet meaningful.
6. **Read the verdict the runner prints.** The thresholds live in one place in `mm_run.sh`
   (`TRIAL_MIN_SOLVED` / `TRIAL_MAX_SOLVED`, used by `trial_rule()`); today:

   | text-only (3) | normal (4) | outcome |
   |---|---|---|
   | any solved | — (not run) | **not recorded.** The words alone solve it, so the image is not needed. The CB must move what the fix depends on into the image (read the solving trajectory under `Trials/without_images/`), then re-run `/run-check`, the controls and the trial |
   | 0 of 3 | **1 of 4** | **recorded — a pass.** Say the task is ready to deliver |
   | 0 of 3 | 0 of 4 | **not recorded, and blocks `/run-check-reviewers`** — the task is RL training data, so one no attempt ever solves has no positive reward signal. The CB should read a trajectory and make the task solvable. Do **not** suggest re-running with fewer attempts to get a record |
   | 0 of 3 | 2+ solved (the breaker stops the phase at the 2nd solve) | **not recorded — delivery blocked.** The model solves it too often; the task must be hardened |

   The record itself is internal: **do not name its file or path, and never suggest the CB create
   or edit one.** Say "the trial is recorded / was not recorded" and what follows from that. A
   hand-made record would let a reviewer skip re-running a trial that never held.

   An unreadable reward in either phase is not a passing trial: report it as no verdict and point
   at the job dir.

   A pseudo-trial (`/run-pseudo-trial`) replays one submission, so it can no longer produce a
   trial record — only `/run-trial` can.
7. If the run is refused before starting, it is the controls gate (`exit 9`): oracle must be
   `1` and nop `0`, both produced from **this** bundle. The message names which control is
   stale and the exact command to re-run. Do not force it — a control that scores wrong is a
   task to fix.
