---
description: QC and fix an MM SWE task in the sandbox (no API key), then reproduce the gate
---

QC and repair the task the CB names, then verify. No API key is needed for any of this.

1. Locate the task folder (usually `/home/sandbox/Tasks`, or the folder holding `Tasks/`). From
   TASK101 (V2) the bundle is `Tasks/<task_id>/`; any of the three paths finds it.
2. `python3 ~/.claude/skills/mm-swe-qc-fix-sandbox/fix.py qc "<path>"` — report every finding
   grouped by component, and say plainly what is not covered statically.
3. `python3 ~/.claude/skills/mm-swe-qc-fix-sandbox/fix.py auto "<path>"` — applies the safe fixes
   AND reproduces the gate (oracle 1.0 / nop 0.0) every time, even if nothing was fixed. Exit 4
   means the gate broke; exit 5 means it could not be verified. Never report either as success.
4. For each escalated item, ask the CB with `AskUserQuestion` — one question per item, never
   bundled. An unreferenced asset gets its own question: it may still be the task's visual source,
   and removing it invalidates the trial.
5. `fix.py verify "<path>"` re-runs the gate on its own if you need it again after an escalated
   fix. The trial is never run; if a class-C fix was
   applied, tell the CB the trial must be re-run and let them run it.
6. If the task has a real rubric, grade the judge request and fold it in with
   `mm_run.sh <task> rescore`. Report the final rewards and what is still outstanding.
