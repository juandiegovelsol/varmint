---
description: Run harbor check on an MM SWE task using the anonymizer proxy
---

Run `harbor check` on the MM SWE task the user names.

1. Locate the task dir (the folder containing `task.toml`: `Tasks/<task_id>/` from TASK101 on,
   e.g. `/home/sandbox/Tasks/<task_id>` — passing `Tasks/` also works, the runner descends into
   the single task folder).
2. Run: `bash ~/.claude/skills/mmswe-runner/mm_run.sh "<task-dir>" check`
3. Credentials resolve automatically via the same anonymizer approach used by the trial:
   live env first, then `~/.claude/settings.json`, then the anonymizer defaults
   (`http://localhost:8091` + `anonymizer-placeholder`). No real API key is needed.
4. Report any issues flagged by the check output.
