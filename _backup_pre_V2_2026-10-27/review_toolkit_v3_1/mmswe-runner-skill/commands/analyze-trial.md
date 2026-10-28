---
description: Run harbor analyze on the Trials output directory using the anonymizer proxy
---

Run `harbor analyze` on the Trials output for the MM SWE task the user names.

1. Locate the task dir (the folder containing `task.toml`; in the sandbox it is usually
   `/home/sandbox/Tasks`).
2. Run: `bash ~/.claude/skills/mmswe-runner/mm_run.sh "<task-dir>" analyze`
   - The analyze target is inferred as `<ROOT>/Trials/` (the same flat directory the
     trial writes to). Override the root with `--root`.
3. Credentials resolve automatically via the same anonymizer approach used by the trial:
   live env first, then `~/.claude/settings.json`, then the anonymizer defaults
   (`http://localhost:8091` + `anonymizer-placeholder`). No real API key is needed.
4. Report the analysis output. If no trial has been run yet (`Trials/` is absent), say so.
