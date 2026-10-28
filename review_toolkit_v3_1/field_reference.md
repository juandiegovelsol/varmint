# Field Reference - Varmint Sheriffs deliverable bundle (v3.1)

Where each reviewable value lives inside the **four deliverable folders**. The v2 hand-off is just
the folders - there is **no task JSON** and **no `justification.txt`**. Search by key - line numbers
drift between records. Dimension numbers below are the **v2** rubric numbers (`QC_rubrics_v2.csv`).

```
deliverables/
├── Tasks/            # capital T - V2 (TASK101+): holds the one task folder, the bundle:
│   └── <task_id>/    #   Tasks/<task_id>/task.toml ...  (V1: the bundle files directly in Tasks/)
├── Trials/           # the failing model trial run
├── Oracle/           # the golden-fix run  (reward = 1.0)
└── Nop/              # the untouched-base run (reward = 0.0)
```

> **The bundle is the source of truth, not `reward.txt`.** The four run folders are produced in the
> contributor's own sandbox, so their `reward.txt` / `result.json` are *self-reported*. Re-run the
> gate yourself (Step 0.6). Assess **locally** - do not rely on the sandbox.

---

## A - the Harbor task bundle (`Tasks/<task_id>/` in V2, `Tasks/` in V1)

Every path in this section is relative to the bundle - the folder holding `task.toml`.

```
Tasks/<task_id>/                  # V2 (TASK101+); V1: Tasks/
├── task.toml                     # metadata + runtime config
├── instruction.md                # the agent-facing prompt (the GitHub issue, scrubbed)
├── evidence_bundle.json          # [{role, url, local_path, description}]
├── environment/
│   ├── Dockerfile                # clones repo, checks out base_commit, tags harbor_base
│   └── assets/
│       ├── ASSET_MANIFEST.json   # [{file, role, container_path}]
│       └── bug.png ...           # the image(s) copied to /app/.harbor_assets/
├── solution/
│   ├── fix.patch                 # the human "golden" fix (source files only)
│   └── solve.sh                  # applies fix.patch
└── tests/
    ├── config.json               # {task_id, test_framework, test_files, f2p[], p2p[]}
    ├── test.patch                # the PR's test additions (+ binary baselines)
    ├── test.sh                   # reset from harbor_base -> apply test.patch -> run f2p+p2p -> reward
    ├── verifier.py               # parses report -> reward 1.0 / 0.5 / 0.0 (v3.1: also gates on --rubric)
    ├── rubrics.json              # v3: {schema, task, description, criteria[{id, criterion, is_positive?}]}
    │                             #     judged by an LLM, SEPARATELY from the f2p/p2p reward
    └── judge.py                  # v3.1: the keyless SUB-AGENT judge harness (rubric-template);
                                  #       writes a judge request during the run, reads verdict.json after
```

> **v3 rubric layer.** `tests/rubrics.json` is always present - a real rubric (a yes/no criterion a
> judge checks against the candidate's *code*), or the always-pass stub when the task is fully
> covered by behavioral tests. It is scored by a **judge, not by the keyless gate**, so a rubric
> fault never appears in `reward.txt` at run time - audit it with `check_rubrics.py` (Step 0.55) +
> Step 7.5.

> **v3.1 judge mechanics.** When the rubric is real, the `rubric-template` wiring runs it: a keyless
> **sub-agent** `tests/judge.py` (the verifier never calls a model), `"rubric_file": "rubrics.json"`
> in `config.json`, a judge block in `test.sh`, and a `--rubric` gate in `verifier.py`. During a run
> `judge.py` writes a **judge request** (`criteria_payload.json`, `source.txt`, `PROMPT.md`) under
> `/logs/verifier/judge/` and the task scores on tests alone; afterwards a judge sub-agent writes
> `verdict.json` and `rescore` folds it into `reward.txt`/`reward.json` (only ever `1.0` -> `0.5`).
> Audit the wiring with `check_judge.py` (Step 7.6). **`judge.py` must never be edited and the task
> must stay keyless** (no `[verifier.env]` / `ANTHROPIC_*` / `JUDGE_MODEL`).

| Value | Where | Feeds v2 |
|---|---|---|
| `task_type` (one of 7) | `task.toml [metadata].task_type` | #5 |
| `base_commit` | `task.toml [metadata]` (== Dockerfile `git checkout`) | #7 |
| `files_edited[]` | `task.toml [metadata]` (== `fix.patch` paths) | #8 |
| `f2p[]`, `p2p[]` | `task.toml [metadata]` **and** `tests/config.json` (must match) | #10, #11, #12 |
| agent-facing prompt | `instruction.md` | #3 |
| image reference(s) | `instruction.md` image refs (`/app/.harbor_assets/…`) | #3, #6 |
| image file(s) | `environment/assets/*.png` (or video/GIF + still frame) | #4 |
| asset manifest | `environment/assets/ASSET_MANIFEST.json` (`file`, `role`, `container_path`) | #6 |
| evidence manifest | `evidence_bundle.json` (`role`, `url`, `local_path`, `description`) | #6 |
| golden fix | `solution/fix.patch` | #7, #8 |
| test framework / files / f2p / p2p | `tests/config.json` | #9, #10 |
| test additions | `tests/test.patch` | #9 |
| harness / reward logic | `tests/test.sh`, `tests/verifier.py` | #11, #12, #13 |
| rubric schema / task id / criteria | `tests/rubrics.json` (`schema`, `task`, `criteria[]`) | v3 Rubrics (Step 0.55 / 7.5) |
| task id (cross-check) | `task.toml [metadata].task_id` == `tests/config.json.task_id` == `tests/rubrics.json.task` | v3 Rubrics (Rubric Task Mismatch) |
| judge harness (keyless sub-agent) | `tests/judge.py` (verbatim template) | v3.1 Judge mechanics (Step 7.6) |
| rubric wiring | `tests/config.json` `"rubric_file"` · `tests/test.sh` judge block · `tests/verifier.py` `--rubric` gate | v3.1 Judge mechanics (Step 7.6) |
| keyless (no judge creds) | `task.toml` has NO `[verifier.env]` / `ANTHROPIC_*` / `JUDGE_MODEL` | v3.1 Judge mechanics (Step 7.6) |
| required harness files present/valid (incl. `tests/rubrics.json`, `tests/judge.py`) | all of the above | #1 |

---

## B - the run folders (`Oracle/`, `Nop/`, `Trials/`)

Each run folder contains one trial dir, which harbor names after the task folder (cut to 32
chars): `<task_id>__<random>/` in V2, `Tasks__<random>/` in V1. The values the v2 review reads:

```
<Run>/
└── <task_id>__<random>/          # V1: Tasks__<random>/
    ├── result.json               # -> verifier_result.rewards.reward ; task_checksum
    └── verifier/
        └── reward.txt            # 1.0 / 0.5 / 0.0
```

| Value | Where | Feeds v2 |
|---|---|---|
| reward | `<Run>/<task_id>__*/verifier/reward.txt` **and** `<Run>/<task_id>__*/result.json -> verifier_result.rewards.reward` | #16 (Oracle/Nop), #14 (Trials) |
| per-test f2p/p2p outcomes (V2 harness) | `<Run>/<task_id>__*/verifier/reward_detail.json` (`f2p::<name>` = `"pass"` \| `"fail"` \| `"missing"` ...) | #10, #12 (inert f2p on Nop) |
| `task_checksum` (must match across all three runs) | `<Run>/<task_id>__*/result.json -> task_checksum` | Unauditable (mismatch => stale/foreign runs) |

**Gate expectations:** Oracle reward = **1.0**, Nop reward = **0.0**, Trials reward **< 1.0**, and
all three `task_checksum` identical (proves the runs were produced against the exact `Tasks/` you
are reviewing). `check_gate.py` reads these; you must still **reproduce** Oracle/Nop yourself
(Step 0.6). Run-output *layout* is no longer a scored dimension in v2, so a run that is missing
non-essential scaffold files is not itself a defect - what matters is the reward and the checksum.
