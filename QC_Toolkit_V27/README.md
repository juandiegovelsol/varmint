# QC Toolkit: Official V27 spec

Use this to check whether a task meets the **Official V27 QC spec** before you submit it. You get
the same 19-dimension scorecard that QC uses.

## What's inside

| Path | What it is |
|---|---|
| `QC_Review/QC_System_Prompt.md` | The reviewer prompt. Give it to Claude Code as the instructions for a review. |
| `QC_Review/review_toolkit/build_report.py` | Turns `findings.json` into the HTML and Markdown report. |
| `QC_STUFF/…V27…-rubric.csv` | The official V27 spec. It decides every score. |
| `QC_STUFF/[External] Varmint Sheriffs - Attempter Guidelines (5).md` | What CBs are asked to do. |
| `MM_SWE_SANDBOX_SUITE/` | The runner (v1.0.8) for local oracle, nop and re-run. |

## Setup (once)

You need Docker, harbor and Claude Code.

```bash
bash MM_SWE_SANDBOX_SUITE/install.sh   # installs mmswe-runner into ~/.claude/skills/
```

## Review a task

1. Put the task's archives (`Tasks.tar.gz`, `Trials.tar.gz`, `Oracle.tar.gz`, `Nop.tar.gz`) in
   `QC_Review/<date>/<task-hash>/`, for example `QC_Review/11_13/6ae7.../`.
2. Open Claude Code in `QC_Review/` and ask it:
   *"Follow QC_System_Prompt.md and review 11_13/<task-hash>."*
3. It extracts the archives into `review_toolkit/workspace/`, runs oracle, nop and an oracle
   re-run locally, and grades all 19 dimensions. The report goes to
   `QC_Review/<date>/<task-hash>/QC_Report/QC_Report_<hash>.html`.

To rebuild the report after editing `findings.json`, run this from `QC_Review/`:

```bash
python3 review_toolkit/build_report.py <date>/<task-hash>
```

## What changed in V27

- **Symptom Specificity (dim 4)** no longer uses `[Fail - Mismatched Task Type]`. That label is
  used only on **Task Type (dim 5)**.
- **Real & Feasible (dim 17)** fails only when the task needs *a fix no real developer would
  write*. "No discoverable path" and "vague images" are no longer fail reasons on any dimension.
  The task is meant to give the model little information: it must not be completely vague, but it
  doesn't have to show everything.
- Difficulty is unchanged: **Option A**, 7 trials, 0/3 no-image and exactly 1/4 with-image pass;
  or **Option B**, 11 trials, 0/3 no-image and 1–2/8 with-image pass.

The `workspace/` folder fills up fast (Docker builds and extracted archives), so clear it out
between reviews.
