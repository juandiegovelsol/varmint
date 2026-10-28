---
name: mm-swe-qc-fix
description: >
  Self-contained QC + repair for an MM SWE / Varmint Sheriffs task. QC AND repair what is safely repairable — build junk,
  legacy credentials in task.toml, a missing rubric_file key, a drifted judge.py, a mismatched
  rubric task id — then re-verify with oracle and nop. Use when the user says "fix this task",
  "QC and fix", "repair the bundle", "clean up this submission", or asks to fix QC findings.
  Never edits without an approved plan, never adds a file outside the canonical layout, never
  runs the trial, and always asks a human before touching anything doubtful (assets especially).
version: 1.0.0
---

# MM SWE QC FIX

Everything MM_SWE_QC checks, plus repairs. **Self-contained** — the four QC checks ship in
`checks/`, so this works with nothing else installed. If MM_SWE_QC is also present it is
ignored: planning a fix against a different version of the checks than the one that produced
the finding is how two tools quietly drift apart.

```bash
python3 fix.py auto  <root> [--verify]          # THE NORMAL ENTRY POINT: apply every AUTO fix,
                                                # escalate only what needs a human
python3 fix.py qc    <root>                     # the full QC report, no edits
python3 fix.py plan  <root> --out /tmp/plan.json
python3 fix.py apply <root> --plan /tmp/plan.json --approve-all-auto --verify
python3 fix.py apply <root> --approve unused_assets,stray_files      # ASK items, one by one
python3 fix.py rollback <root> --snapshot /tmp/qcfix_snapshot_xxxx
```

`<root>` is the deliverables root, `Tasks/`, or the bundle itself. The bundle — the folder
holding `task.toml` — is `Tasks/<task_id>/` from TASK101 on (V2) and `Tasks/` before (V1);
every fix and the layout whitelist act on it.

## Normal use: `fix.py auto`

`auto` applies every AUTO fix without asking and then lists only what a human must decide. That is
the default because AUTO means *no judgment required* — gating it behind a prompt was friction, not
safety. Escalation is reserved for the two cases that genuinely need a person: an unrecognised
non-canonical file, and an unreferenced asset. Both are class C (they invalidate the trial), so the
question is worth asking.

Use `plan` / `apply` when a human wants to see the whole plan first, or to approve an ASK item.

## The full workflow (when you want the plan first)

0. **QC first** (optional but usual). `fix.py qc <root>` gives the full four-component report —
   the same output MM_SWE_QC produces — with `--emit-graders DIR` for the semantic rubric
   graders. Read-only.
1. **Plan.** Run `fix.py plan`. Nothing is written.
2. **Present.** Show the human every fix, grouped by kind, with its evidence and trial class.
3. **Ask — always.** Use `AskUserQuestion` for the trial decision and for **each ASK item
   separately**. Never bundle "fix everything?" into one question; the ASK items have different
   consequences and deserve individual answers.
4. **Apply** only what was approved.
5. **Verify** with `--verify`: oracle must be 1.0, nop 0.0. **The trial is never run.** If either
   regresses, the tool rolls back automatically. If it *cannot* verify — `mm_run.sh` not
   installed — it exits **5 (NOT VERIFIED)** with the fixes still applied, rather than reporting
   success having run nothing. Never treat a missing runner as a pass.
6. **Report** `FIX_REPORT.md` (written beside `Tasks/`, never inside it) and state what is still
   outstanding.

## Three kinds of fix

| Kind | Meaning |
|---|---|
| **AUTO** | mechanical, no judgment. Junk, legacy creds, `rubric_file`, `judge.py` restore, the `test.sh` judge block, `rubrics.json` shape, rubric task id. Applied when approved. |
| **ASK** | a human decides **before** anything happens — only two: an unrecognised non-canonical file, and an unreferenced asset. Both invalidate the trial. Unambiguous debris (`.log`, `.bak`, `.orig`, `.zip`, …) is AUTO, not a question. |
| **NEVER** | reported only. Rubric criterion rewrites — rewording is authoring, and a wrong "fix" silently changes what the task grades. |

**Assets are always ASK, never AUTO.** An unreferenced image may still be the visual source the
task depends on — the model may be expected to read it, and the reference can be implicit. "Not
mentioned anywhere" is not evidence that it is dead. Removing one also invalidates the trial.

## Trial classes — can the existing run survive?

| Class | Change | Trial |
|---|---|---|
| **A** | verifier-side cosmetic; the agent never saw it | keep as-is |
| **B** | rubric/judge only; trajectory still valid, rubric half stale | keep + `rescore` (no container run) |
| **C** | agent-visible or measurement-affecting | **invalid, must re-run** |

`plan` reports **two** verdicts — approving only AUTO, versus also approving ASK items — because
the answer depends on what the human picks. When the worst applied class is A or B, ask whether
to keep the trial. When it is C, do not offer a choice: state that a re-run is required.

Class B is why `rescore` exists: a rubric fix never needs the container again, only a re-grade.

## The template

Repairs are restored from `template/`, derived from a known-good golden bundle — the fixer never
improvises wiring. `judge.py` and the `test.sh` judge block are **byte-restored** (they are
identical in every task). `verifier.py` is **proposal-only**: it carries task-specific scoring, so
`verifier_rubric` prints the canonical block for a human to merge and edits nothing. See
`template/README.md`.

## Exit codes

| code | meaning |
|---|---|
| 0 | applied (and verified, if `--verify`) |
| 3 | whitelist violation — rolled back |
| 4 | oracle/nop regressed — rolled back |
| 5 | fixes applied but **not verified** (no `mm_run.sh`) |

## Guarantees

- **Canonical-layout whitelist**, not a no-new-files rule (`template/CANONICAL_LAYOUT.txt`).
  A fix may add a path the layout allows — `judge_missing` exists precisely to add
  `tests/judge.py`. Anything **outside** the layout aborts and rolls back, verified against a
  deliberately rogue fixer. (An earlier version compared only against the pre-fix path set,
  which made `judge_missing` impossible to apply and, since rollback is wholesale, also
  reverted innocent fixes approved in the same run.)
- **Snapshot first**, outside the bundle; restored on any regression or violation.
- **`tests/instruction.md` is not canonical.** The judge is deliberately not given the prompt, so
  if a task ships one it is removed as an empty/stray file.
- The trial is never executed by this skill.

## What it cannot fix

Rubric wording, f2p/p2p labels, an inert f2p test, `instruction.md`, `environment/Dockerfile`,
`test.patch`, `fix.patch`. All of these are authoring decisions; the skill reports and stops.
