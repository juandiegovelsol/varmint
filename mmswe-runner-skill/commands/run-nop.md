---
description: Run the MM SWE nop control (empty submission) — expect reward 0.0
---

Run the nop control for the MM SWE task the user names.

1. Locate the task dir (the folder containing `task.toml` — `Tasks/<task_id>/` from TASK101 on;
   passing `Tasks/` also works, the runner descends into the single task folder).
2. Run: `bash ~/.claude/skills/mmswe-runner/mm_run.sh "<task-dir>" nop`
3. No API key is needed.
4. Report the reward. **Expect 0.0.** Anything higher means the verifier passes an empty
   submission — the f2p tests aren't discriminating and must be fixed.
