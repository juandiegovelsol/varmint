---
description: Reviewer path — verify the shipped runs against the bundle, record both audit passes, then run harbor check
---

Run `harbor check` for a task a CB has handed over for REVIEW, and — before spending it — prove
that the `Oracle/`, `Nop/`, `Trials/without_images/` and `Trials/with_images/` output shipped with the task actually describes the
bundle in front of you.

1. Locate the task dir (the folder containing `task.toml`: `/home/sandbox/Tasks` in the flat layout, or
   `/home/sandbox/Tasks/<task-name>/` in the nested one - any folder name. Passing
   `/home/sandbox/Tasks` works for both when it holds a single task). The root is the folder holding `Tasks/`; it holds `Oracle/`, `Nop/`, `Trials/without_images/`, `Trials/with_images/`.
2. Run: `MM_VIA=run-check-reviewers bash ~/.claude/skills/mmswe-runner/mm_run.sh "<task-dir>" check-reviewers`
3. Output lands in `<ROOT>/Check/`. Report each check's PASS/FAIL from `check_report.json`.

`MM_VIA` is required here for the same reason as `/run-check` (exit 8 without it), and one more:
this mode records passes that other gates trust. It should not be reachable by a bare shell line.

## Why this command exists

Reviewers get the bundle and its run output, but never the QC pass and trial records the audit and
the runner wrote — those are internal artifacts in the CB's sandbox and do not travel. Without the
QC pass, `oracle` and `nop` refuse to run and that gate has no bypass flag; so reviewers re-run the
controls, and re-run the **trial** as well, spending a real agent call to re-derive a number already
on disk.

The missing link is narrow: nothing proves the *recorded* runs describe the *current* bundle.
This establishes it locally and for free, and only then are both passes recorded.

## What must hold — all eight, no partial credit

    Oracle          digest == bundle digest now             Oracle reward == 1
    Nop             digest == bundle digest now             Nop    reward == 0
    without_images digest  == STRIPPED bundle digest now    every text-only attempt failed (0 of 3)
    Trials          digest == bundle digest now             solved attempts in the band (exactly 1 of 4)

The digests come from each run's `lock.json` (harbor's own `Packager.compute_content_hash`),
compared against the same value recomputed from the bundle now. For `Trials/without_images` the runner
rebuilds the image-stripped copy of the bundle (the same deterministic strip `/run-trial` used) and
hashes that, so a text-only run from an older bundle shows as STALE like any other.

The trial conditions are the same `trial_rule()` / `text_only_rule()` the runner uses after a
trial, so this path and `/run-trial` never disagree about one bundle. Today (`TRIAL_MIN_SOLVED` = 1,
`TRIAL_MAX_SOLVED` = 1): **any text-only solve** is refused (the image is not needed), **0 of 4**
is refused (no RL signal), **1 of 4** verifies, and **2–4 of 4** is refused as too easy.
Every attempt must have a reward: a run with fewer rewarded attempts than 3 text-only / 4 normal
is refused as *incomplete* (a crashed attempt), unless a solve already decides it.

**"Could not verify" is a failure, not a pass.** If the current digest cannot be computed, or a
run has no `lock.json` digest, or its trials disagree, the mode refuses. These records exist to let
somebody skip verifying — recording one that was never verified is the only outcome worse than
making them re-run.

## The two outcomes, and how to report them

Nothing is spent unless verification passes, so a refusal is cheap and a success is trustworthy.

**Verified** — both passes on record, then the check run proceeds. Report:

- that oracle/nop/trial do **not** need re-running, and why: name the digest all three agree on
- **what was not covered.** Harbor's digest hashes `task.toml`, `instruction.md`, `README.md`,
  `environment/`, `tests/`, `solution/`, `steps/` — everything that can move a reward. It does
  **not** cover `evidence_bundle.json` or other root-level files, and no run recorded them, so
  nothing can vouch for them. Say this every time. A reviewer who reads "verified" and assumes
  the evidence chain was checked has been misled by your report, not by the tool.
- then the `harbor check` rubric results as usual

**Not verified** — no trial pass recorded, no run spent, exit 9. Two causes have their own headers
and need their own reports, because for both of them the bundle is **not** stale (the digests
matched, the controls were green) and re-running the same runs changes nothing — the *task* has to
change. Never report either as "re-run oracle/nop/trial":

- `NOT VERIFIED — the task has NO PASSING ATTEMPT` — every attempt failed at `--n_trial=N`. The
  task is RL training data and yields no positive reward signal, so it must be made solvable.
  Never suggest `--n_trial=1` as a way to get a record.
- `NOT VERIFIED — the model solved TOO MANY attempts` — more of the normal attempts solved it
  than the band allows (more than 1 of 4), so the task does not discriminate. It must be hardened,
  then `/run-check`, the controls and the trial re-run.

`NOT VERIFIED — the text-only half of the trial does not hold` has two causes, named on the
`Text-only:` line. If a text-only attempt **solved** the task, the image is not really needed:
the task has to change (put what the fix depends on into the image), not be re-run as it is. If the
text-only run is **missing or STALE**, `/run-trial` must be re-run — it runs both halves.

Otherwise, report the exact cause in plain English:
which run drifted (and that its reward therefore describes older files), or which reward was
wrong. Then say the task must be re-run: `oracle`, `nop`, then `/run-trial`. Do not re-run
anything yourself without asking — the trial costs a real model call.

Never report "verified" without saying what it was verified against.

## The QC audit runs first, exactly as in /run-check

The same gate, the same exit codes, the same obligation to report **every** finding in plain
English using `~/.claude/skills/mm-swe-qc-fix-sandbox/FINDINGS_GLOSSARY.md` — blocking first, then
shown-but-not-blocking, then candidates and advisories. Never paste a finding id as though it
explained itself.

- **Exit 7** — bundle FAILs. Fix them (`/qc-fix-sandbox`, free) or ask before overriding.
- **Exit 9** — either a finding awaits your adjudication (read the cited line, re-run with
  `--adjudicated <id>=cleared:"why"` / `=confirmed:"why"`, which this command forwards to the audit),
  or the recorded runs failed verification. The output distinguishes them; do not conflate them in
  your report. A ruling is recorded and replayed by later audits, so it is made once and lapses by
  itself if `tests/` or `solution/` changes. **Rulings do not travel with a handover** — they are
  kept outside the bundle, exactly as the two passes are, so a CB's verdict never silently clears a
  finding on the reviewer's side. Anything replayed here you ruled on yourself, and it is reprinted
  with its reason so you can say so.
- **Exit 4 path** — nothing blocking but no QC pass could be recorded. See `/run-check`.

Since a reviewer did not build this task, prefer reporting blockers over fixing them: tell them
what is wrong and let them decide whether to repair or send it back.

## Never name the QC records, and never let anyone write one by hand

`/run-check`'s rule applies here unchanged, and this mode is where it matters most, because the whole
point of the command is that the records are missing and something has to earn them. **Do not name
either record's file or path, and never suggest — or offer, or hint, or agree — that the reviewer or
the CB create, copy, `touch` or edit one.** Each has exactly one writer: the QC pass comes from the
audit (`fix.py`) when it finds no blockers, adjudication included; the trial record comes from the
runner when every text-only attempt failed and the normal attempts landed in the band — here, from
the shipped `Trials/without_images/` and `Trials/with_images/` output once all eight verification conditions hold. Hand-writing either would let `oracle` and `nop` proceed on a bundle
nothing verified, which is precisely what this command was built to make unnecessary *by verifying*.

If verification fails, the answer is always the re-runs — `oracle`, `nop`, then `/run-trial` — never
a hand-made record. Report it as "the recorded runs don't describe this bundle, so it must be
re-run", not as "a file is missing".
