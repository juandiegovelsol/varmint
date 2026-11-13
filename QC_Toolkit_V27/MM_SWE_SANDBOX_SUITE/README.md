# MM SWE sandbox suite

Both skills a CB needs in the sandbox, in one bundle:

```bash
bash install.sh
```

| Skill | Commands | What it does |
|---|---|---|
| `mm-swe-qc-fix-sandbox` | `/qc-fix-sandbox` | audits a task, proposes fixes, reproduces the gate |
| `mmswe-runner` | `/run-{oracle,nop,trial,check,analyze}` | runs the task through harbor |

## Task layout - flat or nested, any task name

Both skills accept either layout, and nothing depends on the task folder's name:

    flat      /home/sandbox/Tasks/task.toml
    nested    /home/sandbox/Tasks/<any-task-name>/task.toml

Point them at the root, at `Tasks/`, or at the task folder. `Oracle/`, `Nop/` and `Trials/` sit
beside `Tasks/`, and their trial dirs are found by content rather than by a `Tasks__*` name, so
`<task-name>__<rand>` trials and timestamped job dirs (`Oracle/<timestamp>/<trial>/`) are read
too. Several tasks under one `Tasks/` stops with exit 2, naming them. The rule lives in
`skills/mm-swe-qc-fix-sandbox/checks/qc_layout.py`; `mm_run.sh` applies the same one.

## Evidence documents and what `assets/` may ship

- `evidence_bundle.json` entries need `role`, `local_path` and a human-written `description`.
  `url` is part of the shape but its value is optional: `""` when the poster has no source link.
- `ASSET_MANIFEST.json` must never reach the container - it names every poster's role, telling
  the agent what each image shows before it has looked. The integrity check's
  `assets-images-only` fails a Dockerfile that ships it (a whole-dir `COPY assets/` does) and
  offers an auto-fix: `mm_check_integrity.py <task> --fix` rewrites the offending COPY/ADD to
  image globs (`assets/*.png`, `assets/*.jpg`, ... for the extensions present) plus any listed
  evidence by name; without `--fix` it only shows the change. It declines `COPY .`, posters in
  subfolders and `--from=` copies. Non-image files may ship only when the documents list them
  as evidence.

## They are designed to interlock

`mm_run.sh <task> check` runs the QC audit as a **third pre-flight**, beside the existing
file-name and metadata gates — because a check run costs credentials and wall clock, so anything
decidable locally is decided first. On bundle FAILs it **asks** whether to spend the run
(or exits 7 when there is no terminal to ask at). `--no-qc` skips it.

Installing both is what makes that gate live. With only the runner installed it reports itself
**SKIPPED, not passed**, and continues.

A clean audit writes `/tmp/qc_check.md`, carrying a content digest of the bundle it passed:
harbor's own `Packager.compute_content_hash` plus an `extra-digest` covering what that hash does
not reach — `evidence_bundle.json` above all, which sits at the task root and is in none of
harbor's collected paths.

### Adjudicated findings are remembered

Some findings are `PENDING` — proposed, not decided, because settling them needs a read the
script cannot perform. Ruling on one with `--adjudicated <id>=cleared|confirmed:"why"` (which
`mm_run.sh` forwards into the audit) records the verdict to `/tmp/qc_adjudications.json`, and
later audits replay it. Without that, `mm_run.sh`'s gate — which re-invokes the audit with a
fixed argument list — recomputed the finding as `PENDING` and deleted the pass the ruling had
just earned, so a task with a legitimately cleared finding could never satisfy the gate.

A recorded ruling is keyed to the task and to a digest of `tests/` + `solution/`, so it lapses by
itself when the code it was a judgment about changes; an edit to `instruction.md` or the posters
leaves it standing. It is strictly weaker than the pass record: a stored verdict can only
re-resolve a finding the current audit independently raised as `PENDING`, so it can never create
a finding, clear a `FAIL`, or stand in for `qc_check.md`. Like the other records it lives outside
the bundle, so it does not travel to a reviewer.

## oracle and nop need a matching audit

`mm_run.sh <task> oracle|nop` compares the bundle in front of it against `qc_check.md` and runs
**only on an exact match**, exiting **2** otherwise — whether the files were edited after the
audit, no audit is on record, or the marker describes a different task. There is no bypass flag;
the fix is always to run `/run-check` so a fresh audit covers the current files. The one case
that proceeds is the check being *unavailable* (QC skill absent, or harbor unreachable so only
half the digest can be compared) — reported loudly, never silently.

No run deletes the marker. It stops being valid exactly when the bundle it describes changes,
which is what the digest is for.

## after a trial, the task is graded on whether it held

A trial is **two phases**, and both must hold before anything is recorded:

1. **Text-only, pass@3** (`--n_text_only=N`, default 3) -> `<ROOT>/Trials/without_images/`. The
   attempts run on a copy of the task with every image stripped. **All of them must fail**: if the
   words alone solve it, the image is not really needed. One solve ends the trial unrecorded and
   the normal phase is skipped, so it is not paid for.
2. **Normal, pass@4** (`--n_trial=N`, default 4) -> `<ROOT>/Trials/with_images/`, on the real
   bundle. **exactly 1 of the 4 attempts must solve it**: solvable, but not reliably solved.

| text-only | normal | outcome |
|---|---|---|
| any solved | not run | not recorded — the image is not needed; move what the fix depends on into it |
| 0 of 3 | 0 of 4 | not recorded, **and it blocks `check-reviewers`** — see below |
| 0 of 3 | **1 of 4** | recorded against the bundle's digest; prints `TRIAL PASSED ... READY TO DELIVER` |
| 0 of 3 | 2–4 of 4 | not recorded — **delivery blocked**, the task must be hardened |

Every attempt must produce a reward. A crashed attempt drops out of the tally, so a phase with
fewer rewards than attempts is *incomplete* and not recorded, unless a solve already decides it
(any text-only solve, or 2+ normal solves).

**A phase stops once it is decided.** Attempts run concurrently, so the runner watches the rewards
while harbor runs. At the first text-only solve, or the 2nd normal solve (`TRIAL_MAX_SOLVED + 1`),
it prints `CIRCUIT BREAKER — …` and stops harbor, so the remaining attempts are not paid for.
Cancelled attempts get no reward, so the tally covers only the finished ones (e.g. `pass@3: 2/3`).
That is a decided result, not an incomplete one, so do not re-run because of the missing attempts.
After a trip the runner also removes that phase's leftover containers and networks; images are
kept. `--no-circuit-breaker` runs every attempt to completion. `MM_BREAKER_POLL` (default 15s)
sets how often it checks, and `MM_BREAKER_GRACE` (default 600s) sets how long harbor gets to shut
down before it is killed.

The band is `TRIAL_MIN_SOLVED..TRIAL_MAX_SOLVED` (1..1) in `mm_run.sh`, applied by `trial_rule()`;
the text-only rule is `text_only_rule()`. Both the post-trial verdict and the reviewer path call
them, so the two cannot disagree about one bundle.

Above the band — all 4 solved included — the task fails to discriminate, so nothing is recorded and
`check-reviewers` refuses it under its own `NOT VERIFIED — the model solved TOO MANY attempts`
header. Like the no-passing-attempt refusal below, that one is **not** answered by re-running the
controls: the digests match and the runs are real, so the task itself has to change.

**All 4 failed is not recorded AND it blocks `check-reviewers`** (`exit 9`, with its own
`NO PASSING ATTEMPT` header). The task is reinforcement-learning training data: one that no attempt
ever solves carries no positive reward signal, so it is unusable however cleanly its runs verify.
The digests matching and the controls being green do not save it, and the refusal says so, because
"re-run oracle/nop/trial" is the one piece of advice that does not apply. Dropping to a
lower `--n_trial` to dodge the gate does not get through review: `check-reviewers` counts over the
default 4 attempts, so a shorter run is refused there as incomplete.

The record states `attempts:`, `failed:`, `pass@N:`, `allowed:` and the text-only distribution and
digest, so the strength of the evidence is legible; `MM_FORCE_TRIAL_RECORD=1` writes the real
result with `forced: true` for the unrecorded cases (normal phase only — never the text-only one).
The reviewer path applies the same rule as a fresh trial, so a result inside the band mints a
record there instead of being refused. The record is cleared when a trial
launches, so a crash or an unreadable reward leaves nothing behind claiming a result.

Both files carry the same task dir + digest block, so `qc_digest.py --compare` reads either. Between
them they state, checkably and about one specific bundle: an audit passed it, and a trial failed to
solve it.

## a trial can be re-scored without re-running the agent

Editing `tests/` invalidates a recorded trial's **reward** — it was measured against tests that no
longer exist — but not its **submission**. The agent never sees the tests: `test.patch` is mounted
at `/tests/` and applied by the verifier, after the agent phase is over. So the expensive half of
that trial does not need repeating.

`tests/test.sh` therefore saves what the agent wrote to `/logs/verifier/submission.patch`, captured
after `cd /app` and before the restore loop — the one moment the tree is base + agent work.
`/run-check` reports a task that lacks the block (advisory, never blocking) and `fix.py` wires the
canonical block in mechanically.

`/run-pseudo-trial` then replays that submission against the tests **as they are now** and measures
the reward again. No model call. On reward 0 it writes the trial record through the same single
writer a real trial uses, under the same condition.

It runs only when the bundle's *agent-visible* half is byte-identical to what the recording trial
measured — `instruction.md`, `environment/`, `README.md`. Changes under `tests/` and `solution/`,
and to `task.toml`, are ignored by design; that is the entire point. The comparison uses harbor's
own per-file map, recorded beside the trial and refused unless it recombines to the digest harbor
put in that run's `lock.json`, so a baseline either describes the bundle that ran or does not exist.

`task.toml` is ignored because it is **coupled to `tests/`**: its `f2p`/`p2p` arrays must mirror
`tests/config.json` or the bundle fails integrity, so adding or removing a test forces an edit to
`task.toml` in the same breath — and pinning it made the one edit this mode exists to permit
impossible to perform. The agent never reads that file. The trade is that `[agent]`/`[environment]`
policy edits now pass unchecked, so the gate **says** when `task.toml` has changed rather than
refusing, and that line is meant to be repeated when reporting the replay.

Deliberately **no** oracle/nop check: those controls speak to the tests, which are the thing being
allowed to change. What the gate vouches for is only that the submission is still the submission —
the reward itself is freshly measured, not carried over.

Runs from before the capture existed cannot be replayed: the container is gone and its file state
with it. Re-run the trial once, and every later test edit is free to re-score.

## The trial needs its controls first

`mm_run.sh <task> trial` exits **9** without running anything unless the task's two controls are
already green on disk: **oracle = 1** in `<ROOT>/Oracle`, and in `<ROOT>/Nop` **every f2p test
failing and every p2p test passing** — read from the `f2p_passed`/`f2p_total`/`p2p_passed`/
`p2p_total` keys of the nop run's `reward.json`, not from its reward. A trial reward is
uninterpretable without them — a 0 cannot be told apart from a broken task, and a 1 might be a task
that scores 1 for doing nothing. The error names each control, what it scored, and the command to
run; satisfying it means running those two keyless commands and nothing else.

**Why nop is judged on the counts and not on `reward`.** `reward` is 0.0 whenever *any* f2p test
fails, so it says nothing about the others: a nop scoring 0 is equally consistent with "every f2p
failed" and with "three failed and the fourth passed without the fix". That fourth test is inert —
it cannot detect the bug, so the task grades nothing real while the gate looks green. The counts
settle it; the reward cannot, at any value. A p2p test failing on nop is refused for the mirror
reason: it is mislabeled, and is really f2p.

**And they must be green for the bundle as it is now.** Every harbor run records
`trials[].task.digest` in its own `lock.json` — a sha256 over the sorted `relpath\0sha256(bytes)` of
`task.toml`, `instruction.md`, `README.md` and everything under `environment/`, `tests/`, `solution/`
and `steps/`. Content only: no mtimes, no run id, so it is identical across runs of an unchanged
bundle and differs the moment one of those files changes. The gate recomputes it for the task dir
(with harbor's own `Packager.compute_content_hash`, so the definition cannot drift) and refuses a
trial whose controls disagree, naming which one is stale and printing only the re-run it needs. A
control with no recorded digest, or a job mixing two bundles, is refused the same way.

Two consequences. `evidence_bundle.json` sits **outside** the digest, so editing the evidence
documents alone cannot make a control stale — correctly, since it cannot change a reward. And if the
digest cannot be computed at all (no importable harbor, or a task shipping its own `.gitignore` that
the stdlib fallback declines to imitate) the gate prints `staleness NOT checked` and proceeds on the
rewards alone, rather than grounding every trial over a check that is an addition to the reward gate
rather than a replacement for it.

Because a trial can only start when both controls match, and harbor records the digest for the trial
too, all three runs end up carrying the same digest and are mutually verifiable afterwards. What the
gate cannot cover is an edit made *after* the trial, which staleness the runs are all equally, so
they still agree with each other — that one is the QC audit's job.

`MM_ALLOW_UNVERIFIED=1` skips the whole gate, rewards and digests alike, for CI and for sweeps whose
controls were collected elsewhere.

## Nothing changes without you saying so

| Flag | Authorizes |
|---|---|
| `--apply` | writes to `Tasks/` |
| `--run` | the oracle+nop docker runs (`$MM_RUN_TIMEOUT`, default 5400s) |

`fix.py auto <root>` with no flags is a **dry run**: it prints the complete audit plus the repair
plan and changes nothing (exit 6). Naming a fix — `apply --approve judge_drift` — is itself the
approval; a blanket `--approve-all-auto` additionally needs `--apply`.

## It works before the trial

Each check declares the tier of artifact it needs; anything unavailable is reported as
`OPEN [needs …]`, never as a failure, and never affects the exit code:

    bundle      Tasks/ only              free                  <- the default
    gate        + Oracle/ + Nop/         keyless, docker only
    trial       + Trials/                a real model call
    submission  + the four .tar.gz       packaging time

The verdict always names what was skipped, so "not checked" cannot read as "passed":

    VERDICT   BUNDLE: FAIL (2)  ·  GATE: not reproduced  ·  TRIAL: n/a (pre-trial)

Findings are grouped into the six QC-rubric-v2 dimensions. See
`skills/mm-swe-qc-fix-sandbox/SKILL.md` for the full behaviour, including the #9
implementation-overfit probe and how stale run evidence is downgraded rather than repeated.

**The instruction wording is scanned too.** `checks/qc_structure.py` group L checks `instruction.md`
against the Lean Instruction Playbook. It looks for leaks (repo, URLs, files, functions, error text),
words from the golden fix, unspecific symptoms ("Something does not render correctly"), bare time
windows, and a "… is correct" sentence that never says *what* is correct. It also asks for the
"images are correct apart from the defect" and "what correct looks like" sentences. Every finding is
advisory and never blocks. `/run-check` reports the result every time, hits or clean, next to the
"could this be fixed without the screenshots?" read. When a model is reachable, one cached,
text-only Sonnet 5 call reads the instruction with its captions, the f2p test names and the
difficulty explanation in `task.toml`, against the instruction, symptom-specificity and
image-dependency checks: every graded defect accounted for in the text, nothing vouching for one,
the element named by type, no general phrase or time window/region standing alone, no hint at the
fix, no clue the image should keep given away, and no problem described as the wrong kind. About
$0.008–$0.019 per new task.
Without a model, or with `MM_QC_LLM=0`, the phrase lists run as before.

**The image must still be able to host the harness.** `checks/qc_structure.py` group E is the second
blocking gate, and nothing upstream of the trial can stand in for it. harbor installs the agent CLI
*into* the task image — over `curl` on glibc bases, over `npm install -g @anthropic-ai/claude-code`
on apk ones — diffs the candidate with `git`, and spawns every phase under `bash`, so anti-cheat that
deletes or masks any of those removes the only install path there is. Oracle and nop install no agent
and still score 1.0/0.0; `harbor check` reads the bundle, not the built image; the build itself
succeeds. The first observation is the trial, the single most expensive step in the pipeline, so
group E hard-FAILs and grades the whole class: deleted or never-installed fetchers, BuildKit-only
`COPY <<EOF` heredocs and `# syntax=` directives that die on a builder without them, `COPY` sources
that do not resolve under `environment/`, an npm registry pointed at localhost, an apk base with no
`apk add bash`, and a `RUN` that writes `/etc/hosts`. `heredoc_to_run` rewrites a heredoc in place as
`RUN printf '%s\n' … > dest` rather than adding a non-canonical sidecar; un-stripping deleted
binaries downgrades itself to `ask` unless `[agent] network_mode = "no-network"` already seals the
agent phase, because a fix that unseals a task is worse than no fix. See the SKILL.md section "Can
the harness still run in the image?".

**A non-root process must be able to run in the image.** `group P` is the third blocking gate, and it
exists because the sandbox's docker daemon hands each build a rootfs whose root directory is `0750`
(`drwxr-x--- /`). No non-root uid can traverse it, so every `su` / `sudo -u` / `gosu` / `runuser` /
`setpriv` and every `USER <non-root>` dies before `main()` with `libc.so.6: cannot open shared object
file: Permission denied` — a message that accuses the base image, which is why it costs hours rather
than minutes. Unlike group E the gate is not blind here (the build fails, so the oracle fails), but
the *diagnosis* is what nothing else supplies. The repair is two-part and the second half is the one
that gets forgotten: `chmod a+rx /` must run in the **same `RUN`** as the drop, because a mode change
on `/` is not captured in a layer diff, **and** any script the Dockerfile generates must repeat it as
root, because the shipped image still has `/` at `0750`. Both halves are auto-fixed by
`nonroot_privilege_drop` (additive, a no-op on a normal daemon); `USER <non-root>` is reported and
never auto-fixed, since after it no root process remains to fix `/` with. The check grades the
*absence of the repair*, not the presence of a `su` — PostgreSQL cannot run as root, so a repaired
Dockerfile keeps its drops and reports clean. See the SKILL.md section "Can a non-root process run in
the image?".

`checks/qc_env_probe.sh <Tasks>` is the optional dynamic half: it builds the image and asks it
directly — `command -v` per harness binary, the effective npm registry, `/etc/hosts` for the CLI
download host, a writable `$HOME`, the `harbor_base` tag the verifier diffs against, and the mode of
`/` plus the same privilege drop the Dockerfile performs — which catches what reading the text cannot
(a private base, a multi-stage `COPY`, a non-root `USER`, a rootfs the daemon hands over at `0750`).
Its group-P half is the only check that can see the **shipped** image, where the verify-time drop
lives; it reports a bare-drop failure as a defect only when a runtime drop is actually unguarded,
since on this daemon a bare drop fails in every image, a correct one included.
Docker only, still no API key, no model call. It is deliberately **not** authoritative: `/etc/hosts`
is read-only under BuildKit, so the very chain group E flags can abort at its first link and leave
the probe green on your builder while the trial dies with exit 127 on another. The static finding
stays the gate; the probe prints that caveat itself.

**Rubric format is a blocking gate.** `checks/qc_rubric_format.py` decides which of the two legal
shapes a task's rubric layer is in — a real rubric (Mode A) or none at all (Mode B) — and every
finding it raises is a BLOCKING Fail that must be fixed. An all-pass "always_pass" stub rubric is
not a legal shape: it cannot fail any submission yet reports `rubric_passed = 1` as though a real
rubric had been satisfied. A task that needs no rubric ships no rubric layer, and that is correct
rather than "missing rubrics". See the SKILL.md section "The rubric layer has two legal shapes".

**Mode A must grade in-band.** The judge backend and `task.toml`'s `[verifier]` blocks used to be
out of scope; they are now graded, because a sub-agent-only judge cannot grade during the run — it
records `rubric_passed = -1` until someone grades `PROMPT.md` by hand and reruns `rescore`, a step
routinely skipped, leaving the rubric decorative in exactly the way a stub is. A Mode A task must
therefore ship a `judge.py` with an API backend, `[verifier] network_mode = "public"`, and a
`[verifier.env]` mapping `EVAL_API_KEY` / `EVAL_BASE_URL` / `EVAL_MODEL`. The last two are
auto-fixable (`--approve verifier_network_mode --approve verifier_env`); the backend is authoring.
`"public"` is not a preference — harbor rejects `allowed_hosts` outside allowlist mode, never
env-expands them, and has no `allow_verifier_hosts` override, so a run-time-injected endpoint
cannot be named. No credential enters a bundle: `[verifier.env]` holds `${VAR}` references, and
the value is the anonymizer placeholder. Mode B is untouched. See `RUBRIC_MODES.md` §2b.

## integration/

`mmswe-runner-qc-gate.patch` re-applies the `check` pre-flight to a **separately installed**
`mmswe-runner` after an upstream release overwrites it. Not needed if you install from this
bundle, which already contains the gated runner.
