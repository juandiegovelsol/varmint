---
name: mm-swe-qc-fix-sandbox
description: >
  QC and repair an MM SWE task from inside the sandbox, with no API key. Runs the four static
  checks, applies the safe fixes automatically, escalates only what needs a human, and
  reproduces the gate through the MM SWE runner (the same oracle/nop commands CBs already use).
  Use when a CB says "QC this task", "fix this task", "check my task before submitting",
  "run the QC checks", or hands over a task folder in the sandbox. Never runs the trial.
version: 1.0.0
---

# MM SWE QC FIX — sandbox

For CBs working in the sandbox. Same checks and fixes as the local skill, wired to the run
commands you already use.

```bash
FIX=~/.claude/skills/mm-swe-qc-fix-sandbox/fix.py

python3 $FIX qc     /home/sandbox/Tasks          # the full report, no edits
python3 $FIX auto   /home/sandbox/Tasks          # fix what is safe + ALWAYS verify the gate
python3 $FIX verify /home/sandbox/Tasks          # reproduce oracle 1.0 / nop 0.0 on its own
```

**`auto` always reproduces the gate** — oracle and nop — even when it fixed nothing. A task that
needed no repair can still have a broken gate, and "we changed nothing" is not evidence that it
holds. `--no-verify` opts out deliberately and says the gate is unproven.

Exit codes: **0** fixed and verified · **4** gate broken after fixing · **5** could not verify. Point them at the folder holding `Tasks/`, at
`Tasks/` itself, or at the V2 bundle `Tasks/<task_id>/` (TASK101+) — the bundle is found either
way, and `FIX_REPORT.md` always lands beside `Tasks/`, never inside it.

## No API key is needed — anywhere

This is the part that differs from the local flow, and it is worth being explicit about:

- the rubric judge is a **sub-agent** that makes no model call, so **oracle and nop run keyless**;
- the four checks are **stdlib-only with no network**;
- `--emit-graders` writes prompts for **your own agent** to grade — it does not call an API;
- **the trial is never run by this skill.** That is the only step that would need credentials, and
  re-running it is a human decision because it costs a real model call.

## Harbor is never called directly

Every run goes through the MM SWE runner — `mm_run.sh <task> oracle|nop` — resolved in order:

1. `$MM_RUNNER`
2. `~/.claude/skills/mmswe-runner/mm_run.sh`
3. the copy bundled in `runner/` (ships with this skill)

The bundled copy is the one **with `rescore`**, so a rubric verdict can actually be folded into
the reward. If a CB has an older runner installed without `rescore`, set `MM_RUNNER` to the
bundled path.

Runs are bounded by `$MM_RUN_TIMEOUT` (default 5400s). On timeout the skill says so rather than
hanging, and the reward is read from the `reward.txt` harbor wrote — not scraped from the log.

## What it fixes, and what it asks about

**Applied automatically** (no judgment needed): build junk and editor debris, a legacy
`[verifier.env]` in `task.toml`, a missing `rubric_file`, a drifted or missing `judge.py`, the
`test.sh` judge block, `rubrics.json` shape, a mismatched rubric task id.

**Escalated to you** — only two, both of which invalidate the trial:
an unrecognised non-canonical file, and an unreferenced asset. An unreferenced image may still be
the visual source the task depends on, so "unused" is never a safe inference.

**Reported, never fixed**: rubric criterion wording. Rewriting a criterion is authoring, and a
wrong "fix" silently changes what the task grades.

## The trial

Fixes are classed by whether the existing trial survives:

| Class | Meaning | Trial |
|---|---|---|
| **A** | verifier-side cosmetic | keep it |
| **B** | rubric/judge only | keep the trajectory, then `mm_run.sh <task> rescore` |
| **C** | agent-visible or measurement change | **must be re-run** |

`plan` prints the verdict for approving only AUTO versus also approving an escalated item, so the
cost of each choice is visible before you decide.

## Guarantees

- A snapshot is taken outside the bundle before any edit and restored on regression.
- The canonical-layout whitelist means a fix may add a file the layout allows (`judge.py`) but
  never anything outside it — otherwise it aborts and rolls back.
- Verification is unconditional and never optimistic: **4** if the gate broke, **5** if it could
  not be reproduced. It never reports success having checked nothing.
