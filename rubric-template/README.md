# Rubric template — adding a sub-agent LLM judge to an MM SWE task

Drop-in pack for putting a **binary, unweighted** rubric on a Harbor/MM SWE task.

> **Handing this to an agent?** Give it `AGENT_INSTRUCTIONS.md` — imperative steps, exact
> edit anchors, and acceptance criteria. This README is the human overview.
> `reference/` holds a real applied example from `mui__material-ui-47967-mm`.

```
AGENT_INSTRUCTIONS.md        the handoff doc — steps + acceptance criteria
tests/judge.py               ADD, copy as-is, never edit
(tests/instruction.md)       ADD, a copy of the task's instruction.md
tests/rubrics.template.json  ADD as tests/rubrics.json, then write the criteria
snippets/1-task.toml         task.toml needs NO change (confirms what not to add)
snippets/2-config.json       EDIT — one key
snippets/3-test.sh           EDIT — judge invocation
snippets/4-verifier.py       EDIT — the 5 marked changes
snippets/*.v2.snippet        the same two edits for the V2 harness (TASK101+ bundles)
reference/                   a real applied example
```

Paths are relative to the task bundle — `Tasks/<task_id>/` from TASK101 on (V2), `Tasks/`
before. V2 bundles ship a newer `test.sh`/`verifier.py`; `AGENT_INSTRUCTIONS.md` Steps 5–6
say which snippet applies.

## The design in one paragraph

The judge is a **sub-agent**, so nothing in the verifier ever calls a model: no API key, no
proxy, no bridge, no `[verifier.env]`. During a run `judge.py` writes a judge *request*
(criteria + candidate diff + `PROMPT.md`) and the task scores on tests alone; afterwards a
judge sub-agent writes `verdict.json`, and `mm_run.sh <task> rescore` folds it into the
reward from the existing JUnit XML — no rebuild. Scoring is binary and unweighted: every
criterion is PASS/FAIL, every one is mandatory, and the rubric can only withhold a `1.0` and
turn it into `0.5` — never push a score toward `0.0`.

`reward.txt` keeps its exact contract: a bare float in `{0.0, 0.5, 1.0}`, so existing
validation is unaffected. Everything richer lives in `reward.json`.

## What the judge can see

The judge is handed the criterion text, the candidate **diff**, the **full text of every
changed file**, and the task's **instruction** (when the bundle ships `tests/instruction.md`).
It is deliberately NOT given the golden fix, the tests, the images, or the wider repo — a judge
that sees the reference grades similarity to it, which is the overfitting the rubric exists to
catch.

So "self-contained" means: **decidable from the diff + changed files + instruction.**
"Follows the repo's conventions" is not (nothing shows it the repo, and "no evidence" scores 0,
failing a correct fix). "New functions use camelCase" is.

## Rubric schema

```json
{
  "schema": "rubrics.schema/v1",
  "task": "{owner}__{repo}-{issue}-mm",
  "description": "",
  "criteria": [
    { "id": "unique_id", "criterion": "the rubric text that does the checking" }
  ]
}
```

Exactly two fields per criterion. No `category`, no `weight`.

## Writing criteria

- One failure fails the whole rubric, so only include criteria worth rejecting a submission
  over. No nitpicks — there is no optional tier.
- State the **approach**, never an identifier. "Fixes the paint order so the outline draws
  before its child" is good; "sets `borderOnForeground` to false" is bad — it fails any
  different-but-correct fix.
- Acceptance test: would a different but correct fix still pass this criterion?
- Never mention the rubric in `instruction.md`.

## Validating

```bash
mm_run.sh <task-dir> oracle    # 1.0, every f2p true
mm_run.sh <task-dir> nop       # 0.0, and every f2p FALSE individually
mm_run.sh <task-dir> trial     # < 1.0 — the task must stump the model
mm_run.sh <task-dir> rescore --run <dir>   # after a sub-agent writes verdict.json
```

Check the per-test `f2p` map, not the aggregate: an f2p test that *passes* on nop cannot
detect the bug and is inert, however clean the `0.0` looks. `validate_reward.sh` in the
parent folder automates this.
