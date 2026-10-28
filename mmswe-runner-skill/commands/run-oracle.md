---
description: Run the MM SWE oracle (golden patch) on a task — expect reward 1.0
---

Run the oracle for the MM SWE task the user names (default: the task under `/home/sandbox/Tasks/`).

1. Locate the task dir (the folder containing `task.toml` — `Tasks/<task_id>/` from TASK101 on;
   passing `Tasks/` also works, the runner descends into the single task folder).
2. Run: `bash ~/.claude/skills/mmswe-runner/mm_run.sh "<task-dir>" oracle`
3. No API key is needed — the verifier is unit tests only.
4. Report the reward. **Expect 1.0.** Anything lower means the golden `solution/fix.patch`
   doesn't satisfy the tests, or the environment failed to build — investigate before
   running a trial.
