---
description: Run harbor analyze on a finished MM SWE trial
---

Run `harbor analyze` over a finished trial for the MM SWE task the user names.

1. Path can be a task dir (analyzes the last `Trials/with_images/` run), a harbor job dir, or a single
   trial dir — the runner classifies it.
2. Run: `bash ~/.claude/skills/mmswe-runner/mm_run.sh "<path>" analyze`
   - `--passing` / `--failing` to filter, `-l N` to cap the number of trials.
3. If nothing has been run yet, say so — analyze needs a completed trial.
4. Output lands in `<ROOT>/Analyze/`. Report each check from `analysis.json`.
5. Warn the user that harbor also writes `analysis.json` into the analyzed trial dir, which a
   later `trial` run without `--keep` will delete.
