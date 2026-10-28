---
description: Run one MM SWE agent trial (claude-code @ claude-opus-4-8)
---

Run a single agent trial for the MM SWE task the user names.

1. Locate the task dir (the folder containing `task.toml`; in the sandbox it is usually
   `/home/sandbox/Tasks`).
2. Run: `bash ~/.claude/skills/mmswe-runner/mm_run.sh "<task-dir>" trial`
   - Model defaults to `anthropic/claude-opus-4-8`; override with `--model`.
   - One attempt only (no pass@k).
3. Credentials resolve automatically: live env, then `~/.claude/settings.json`, then the
   anonymizer defaults (`http://localhost:8091` + `anonymizer-placeholder`). The run does
   not stop for a missing key — it falls back to those defaults, and bridges the loopback
   proxy so the agent container can reach it. If the log shows a bridge WARNING or the
   agent fails to reach the model, report the exact URL from the `[mm_run] creds` line.
4. Output lands in `<ROOT>/Trials/` (flat — no per-task subfolder), overwriting any
   previous trial unless `--keep` was passed. Report the reward and, if it is below the
   oracle's, point at the trajectory for why.
5. If `/run-nop` has not been run on this task, say so: the oracle passing does not prove
   the tests discriminate, so a trial reward is not yet meaningful.
