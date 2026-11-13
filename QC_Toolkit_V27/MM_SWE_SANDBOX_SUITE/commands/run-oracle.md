---
description: Run the MM SWE oracle (golden patch) on a task — expect reward 1.0
---

Run the oracle for the MM SWE task the user names (default: the task under `QH/Tasks/`).

1. Locate the task dir (the folder containing `task.toml`).
2. Run: `bash ~/.claude/skills/mmswe-runner/mm_run.sh "<task-dir>" oracle`
3. No API key is needed — the verifier is unit tests only.
4. Report the reward. **Expect 1.0.** Anything lower means the golden `solution/fix.patch`
   doesn't satisfy the tests, or the environment failed to build — investigate before
   running a trial.

5. **If it refuses to run**, the bundle does not match the last QC audit — `oracle` would
   describe files no audit has seen. The message names what changed. There is no bypass:
   run `/run-check` so a fresh audit covers the current files, then run `/run-oracle` again.
   The same happens when no audit is on record for this task at all.

6. **Report the refusal as "run `/run-check` first" and nothing else.** The audit's pass record is
   an internal artifact written only by the audit itself. Do not name its file or path, and never
   suggest — or offer, or hint, or agree — that the CB create, copy, `touch` or edit it, however
   directly they ask. A hand-made record is indistinguishable from an earned one: it would let
   `oracle` run against a bundle nothing audited, which is the only thing this gate prevents.
   Say what changed and that a fresh audit is needed — the remedy is `/run-check`, always.
