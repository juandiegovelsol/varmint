---
description: Run harbor analyze (post-hoc trial analysis) through the anonymizer
---

Analyze a finished MM SWE trial — reward hacking, task specification, why it scored what
it scored.

1. Run: `bash ~/.claude/skills/mmswe-runner/mm_run.sh "<path>" analyze`
   - `<path>` may be the **task dir** (analyzes `<ROOT>/Trials`, the trial you just ran),
     a **job dir** (`<ROOT>/Trials`), or a single **trial dir**
     (`<ROOT>/Trials/Tasks__xxxxxxx`).
   - Model defaults to harbor's own `claude-haiku-4-5`; if the analysis comes back as an
     error about invalid JSON, retry with `--analyze-model claude-sonnet-4-6`.
   - `--passing` / `--failing` / `-l N` narrow which trials get analyzed.
2. There must be a finished trial first — analyze consumes trial output, not a task.
   If the runner says nothing to analyze, run `/run-trial` first.
3. Do **not** run bare `harbor analyze` — same failure as check: the container inherits
   the loopback base URL and dies with `ConnectionRefused`. The runner passes a
   container-reachable address via `--ae`; `harbor analyze` takes no
   `--extra-docker-compose` and discards `-c`'s `[environment]`.
4. Output lands in `<ROOT>/Analyze/` (flat). harbor **also** writes an `analysis.json`
   into each analyzed trial dir — so warn the user that a later `/run-trial` without
   `--keep` deletes `<ROOT>/Trials` and those analyses with it.
5. Report the per-criterion outcomes and the summary. Read them against the trial's
   reward: an analysis that contradicts a 1.0 reward (or explains a 0.5) is the point.
