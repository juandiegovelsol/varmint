---
description: QC an MM SWE task, then fix what is safely fixable (asks before anything doubtful)
---

QC and repair the task the user names.

1. Locate the deliverables root (holding `Tasks/`, ideally with `Trials/ Oracle/ Nop/`).
2. Plan: `python3 ~/.claude/skills/mm-swe-qc-fix/fix.py plan "<root>" --out /tmp/qcfix_plan.json`
3. Present every fix grouped by AUTO / ASK / NEVER, each with evidence and trial class. Show BOTH
   trial verdicts from the plan (auto-only vs. also-approving-ASK).
4. Use `AskUserQuestion`:
   - one question per **ASK** item — never bundle them; assets especially get their own question,
     since an unreferenced image may still be the task's visual source;
   - one question for the **trial**, but only when the worst applied class is A or B. If any C is
     applied, state plainly that the trial must be re-run and do not offer a choice.
5. Apply only what was approved:
   `fix.py apply "<root>" --approve-all-auto --verify` (add `--approve id,id` for ASK items).
6. `--verify` runs oracle (expect 1.0) and nop (expect 0.0). Never run the trial. On regression
   the tool rolls back; report that rather than presenting a partial fix as success.
7. Report `FIX_REPORT.md`, and state what remains: rubric rewrites (NEVER items), the ACCURATE
   check against `solution/fix.patch`, and the behavioural half (judge request → `rescore`).
