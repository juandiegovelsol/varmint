---
description: Re-score a recorded trial's submission against the current tests — no model call
---

Replay the submission a previous trial produced against the tests **as they are now**, and record
the trial verdict from the result. No agent runs, so no model call is spent.

1. Locate the task dir (the folder containing `task.toml`: `/home/sandbox/Tasks` in the flat layout, or
   `/home/sandbox/Tasks/<task-name>/` in the nested one - any folder name. Passing
   `/home/sandbox/Tasks` works for both when it holds a single task). The root is the folder holding `Tasks/`; it holds `Trials/with_images/`.
2. Run: `MM_VIA=run-pseudo-trial bash ~/.claude/skills/mmswe-runner/mm_run.sh "<task-dir>" pseudo-trial`
3. Output lands in `<ROOT>/PseudoTrial/`. Report the reward.

`MM_VIA` is required (exit 8 without it) for the same reason `/run-check-reviewers` requires it:
this mode writes the trial record other gates trust, and its refusals need reading back in words.

## What this is for

Editing `tests/` invalidates a recorded trial's reward — it was measured against tests that no
longer exist — but it does **not** invalidate the submission. The agent never saw the tests:
`test.patch` is mounted at `/tests/` and applied by the verifier, after the agent phase is over.
So the expensive half of that trial does not need repeating. The tests are re-run against the
saved submission and the reward is **measured again**, not assumed.

Say this plainly when you report: the number is fresh, not carried over.

## The gate, and how to report a refusal

Nothing is spent unless the replay is legitimate. It runs first and refuses if:

- **no submission was captured** — trials predating the capture block cannot be replayed. Say the
  capture must be wired (`/run-check` reports it; `fix.py` applies it) and a real trial run.
- **files the agent can see have changed** — `instruction.md`, `environment/`, `README.md`. The
  submission is then not what an agent would write for the current task, so its score would
  describe a different task. The refusal **names the files**; pass them on.
- **the recorded baseline does not verify** — it fails to recombine to the digest harbor recorded
  for that trial, so it does not describe the bundle that ran.

**Changes under `tests/` and `solution/`, and to `task.toml`, never block it.** That is the entire
point. If a CB asks why their test edit didn't stop the replay, the answer is that it cannot
change what the agent produced. Do not report a permitted replay as though the check were lenient.

`task.toml` is on that list because it is **coupled to `tests/`**: its `f2p`/`p2p` arrays have to
mirror `tests/config.json` or the bundle fails integrity, so adding or removing a test in
`test.patch` forces an edit to `task.toml` in the same breath. Pinning it made the one edit this
mode exists to permit impossible to perform. The agent never reads that file.

The trade, which you should pass on if `task.toml` did change: it also carries `[agent]` and
`[environment]` policy — `network_mode`, `timeout_sec`, resource limits — and those are no longer
checked. The reward is still measured, and still this submission against these tests. But if the
run policy moved, the submission was produced under the older one. The gate **says** when
`task.toml` changed instead of refusing; repeat that line rather than swallowing it.

When it refuses, the remedy is always a real trial (`/run-trial`) — never editing the bundle back.

## The record

On a reward of exactly 0 the runner writes the trial record, through the same single writer a real
trial uses and under the same condition. A pseudo-trial's record is stamped with the bundle's
current digest, which is accurate: these tests did just run against this bundle.

Report which happened — "replayed, scored 0, record written" or "replayed, scored N, no record" —
and never imply a record exists when it does not. As everywhere else: **do not name the record's
file or path, and never suggest anyone create one by hand.**

## Reward that is not 0

A pseudo-trial scoring above 0 means that submission now passes. Usually the tests were loosened.
Report it as a finding about the task, not as a failed command — and do not re-run hoping for 0.
