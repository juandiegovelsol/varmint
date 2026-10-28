# MM_SWE_QC_FIX

A fork of MM_SWE_QC that also **repairs** what is safely repairable, then re-verifies with
oracle and nop.

**Self-contained.** The four QC checks ship inside `skills/mm-swe-qc-fix/checks/`, so this works
on its own — nothing else needs to be installed. A bundled copy of `judge.py` travels with it too,
so the judge byte-identity check works standalone. If MM_SWE_QC is also installed it is ignored;
the bundled checks always win, so a fix is never planned against a different version of the
checks than the one that reported the finding.

That does mean the two skills carry duplicate check code. Treat **MM_SWE_QC as the source of
truth** and re-copy `checks/` into this skill when it changes, or they will drift.

```bash
bash install.sh                       # -> /qc-fix
python3 skills/mm-swe-qc-fix/fix.py qc   <root>                      # full QC report
python3 skills/mm-swe-qc-fix/fix.py plan <root> --out /tmp/plan.json
python3 skills/mm-swe-qc-fix/fix.py apply <root> --approve-all-auto --verify
```

## Design in one paragraph

It never edits a bundle the human has not seen a plan for, never adds a file outside the
canonical layout, never runs the trial, and asks before anything doubtful. Fixes are split into
**AUTO** (mechanical), **ASK** (a human decides first), and **NEVER** (reported only, because
fixing it would be authoring). Every applied fix carries a **trial class** — A verifier-side
cosmetic, B rubric/judge only, C agent-visible — and the worst class decides whether the
existing `Trials/` run survives, gets re-scored, or has to be re-run.

## Fix catalogue

| id | kind | class | what |
|---|---|---|---|
| `junk` | AUTO | A | `__pycache__`, `*.pyc`, `.DS_Store`, `node_modules` |
| `empty_noncanon` | AUTO | A | empty files outside the layout (e.g. a blanked `tests/instruction.md`) |
| `legacy_creds` | AUTO | A | `[verifier.env]` / `ANTHROPIC_*` / `JUDGE_MODEL` in `task.toml` |
| `rubric_file` | AUTO | A | missing `"rubric_file"` in `tests/config.json` |
| `judge_drift` | AUTO | B | `tests/judge.py` differs from the template — restored |
| `judge_missing` | AUTO | B | `tests/judge.py` absent — installed |
| `rubric_task_id` | AUTO | B | `rubrics.json` `task` ≠ `task.toml` `task_id` |
| `test_sh_judge` | AUTO | B | `test.sh` judge block missing / no `--rubric` / no `\|\| echo ""` — restored from the template |
| `rubrics_shape` | AUTO | B | `rubrics.json` missing `schema` / `description` — normalised |
| `verifier_rubric` | **ASK** | B | `verifier.py` lacks the `--rubric` gate or `reward.json` — the canonical block is **printed for manual merge**, never auto-applied |
| `stray_files` | **ASK** | C | non-canonical files that are not empty |
| `unused_assets` | **ASK** | C | assets referenced nowhere |
| `rubric_quality` | **NEVER** | B | criterion wording — rewrite by hand |

**Assets are never auto-removed.** An unreferenced image can still be the visual source the task
depends on; the reference may be implicit and the model may be expected to read it. "Not
mentioned" is not evidence it is dead, so a human confirms each one — and removing any makes the
trial invalid.

## The template

`skills/mm-swe-qc-fix/template/` holds the canonical shape, derived from a known-good golden
bundle, so repairs converge on one wiring instead of improvised text. `judge.py` and the
`test.sh` judge block are byte-restored; `verifier.py` is proposal-only because it carries
task-specific scoring. Details in `template/README.md`.

## Trial preservation

`plan` prints two verdicts, because the answer depends on what you approve:

```
approve AUTO only   -> class B: keep the trajectory; re-grade the rubric and `rescore`
+ any ASK item      -> class C: the trial is INVALID and must be re-run
```

Class B is the useful case: a rubric or judge fix leaves the trajectory valid, so `rescore`
recomputes the reward from the existing JUnit XML in seconds instead of a full container run.

## Safety, all verified

- **Canonical-layout whitelist** — a fix may add a path the layout allows (`judge_missing` adds
  `tests/judge.py`); anything outside it aborts with exit 3 and rolls back. Tested with a
  deliberately rogue fixer.
- **Snapshot** taken outside the bundle before any edit; restored on regression or violation.
- **NEVER items are refused** even if their id is passed to `--approve`.
- **ASK items require their explicit id**; `--approve-all-auto` never touches them.
- **oracle 1.0 / nop 0.0** re-verified after applying; the trial is never executed. If the runner
  is missing the run exits **5 (NOT VERIFIED)** instead of reporting a clean success — a
  "verified" that verified nothing is worse than an honest failure.

## Limits

Rubric wording, f2p/p2p labels, an inert f2p test, `instruction.md`, `environment/Dockerfile`,
`test.patch` and `fix.patch` are all out of scope — they are authoring decisions. The skill
reports them and stops.
