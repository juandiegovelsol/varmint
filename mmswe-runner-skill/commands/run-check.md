---
description: Run harbor check (rubric quality checks) on an MM SWE task through the anonymizer
---

Run the rubric quality checks for the MM SWE task the user names.

1. Locate the task dir (the folder containing `task.toml`; in the sandbox it is
   `/home/sandbox/Tasks/<task_id>` from TASK101 on — passing `/home/sandbox/Tasks` also works,
   the runner descends into the single task folder).
2. Run: `bash ~/.claude/skills/mmswe-runner/mm_run.sh "<task-dir>" check`
   - Model defaults to harbor's own `claude-sonnet-4-6`; override with `--check-model`.
   - `--rubric F` / `--check-prompt F` swap harbor's built-in rubric or evaluator prompt.
3. Do **not** run bare `harbor check` — it inherits `ANTHROPIC_BASE_URL=http://localhost:8091`
   into the container, which dials the container's own loopback and fails with
   `API Error: Unable to connect to API (ConnectionRefused)` → `UnknownApiError`, mean 0.000.
   The runner exists to pass a container-reachable address via `--ae` instead. `harbor check`
   takes no `--extra-docker-compose` and discards `-c`'s `[environment]`, so host networking
   is not available to it.
4. Output lands in `<ROOT>/Check/` (flat), overwriting any previous check unless `--keep`
   was passed. There is no reward: report the per-criterion pass/fail the runner prints.
5. If a criterion's result is an `error` rather than a verdict, the judge never ran — check
   the `[mm_run] container will dial …` line and the proxy before treating it as a finding
   about the task.
