# Add a rubric to an MM SWE Harbor task — implementation instructions

Audience: the task-creation agent. Follow exactly. Everything needed is in this folder.

---

## What this addition is

MM SWE tasks are graded only by unit tests: `vitest`/`pytest` → JUnit XML → `reward.txt`.
Tests answer **"did the output change?"** They cannot distinguish a real fix from one that
special-cases whatever the test asserts.

The rubric adds a second grade — an LLM judge reading the **candidate diff** — answering
**"was this a legitimate fix?"**

- **Binary**: each criterion is PASS or FAIL. No partial credit, no 0.5.
- **Unweighted**: no weights, no thresholds. Every criterion is mandatory; the rubric passes
  only if **all** pass.
- **A gate, not a term in an average.** It can only withhold a `1.0` and turn it into `0.5`.
  It never pushes a score toward `0.0`.
- **Never fatal.** If no verdict exists, the task scores on tests alone.

### The judge is a SUB-AGENT — there are no credentials anywhere

This is the part to get right. The judge **never calls a model from inside the verifier**.
It is two-phase:

| Phase | What happens |
|---|---|
| 1 — during the run | `judge.py` finds no verdict and writes a judge **request** under `/logs/verifier/judge/` — `criteria_payload.json`, `source.txt` (the diff), `changed_files.txt` (full text of every changed file), `instruction.md` (when the bundle ships a copy), `PROMPT.md` — then prints nothing. The verifier scores on tests alone. |
| 2 — after the run | A judge sub-agent reads `PROMPT.md` and writes `verdict.json` beside it. `mm_run.sh <task> rescore` recomputes the reward from the existing JUnit XML — no container, no rebuild. |

Consequences, all of them deliberate:

- **No `[verifier.env]` block. No `ANTHROPIC_API_KEY`, no `ANTHROPIC_BASE_URL`, no
  `JUDGE_MODEL` in `task.toml`.** If you find them in a task, delete them — they belong to
  the legacy `api` backend.
- No proxy, no bridge, no network access needed by the verifier.

---

## What the judge can see — this defines "self-contained"

A criterion is only answerable from what the judge is handed. It receives:

| Given | Why |
|---|---|
| the criterion text | — |
| `source.txt` — the candidate diff | what changed |
| `changed_files.txt` — full current text of every changed file | a 3-line hunk is often too little to decide a true criterion |
| `instruction.md` — when shipped at `tests/instruction.md` | judge whether the change addresses what was asked |

It is **not** given, on purpose:

- **the golden `solution/fix.patch`** — a judge that sees the reference grades *similarity to
  it*, which reintroduces the exact overfitting the rubric exists to catch;
- **`tests/test.patch` or any test** — same failure mode, and the tests already score that;
- **the before/after images** — UI-evaluation criteria are out of scope by definition;
- **the rest of the repository** — unavailable at rescore time, so it would work in phase 1 and
  silently not in phase 2.

The principle: **the judge sees what the submission produced and what was asked — never how the
reference did it, and never how it was measured.**

So a criterion must be decidable from the criterion text + the diff + the changed files
(+ the instruction). *"Follows the repo's conventions"* is not — nothing shows the judge the
repo, and the contract turns "no clear evidence" into a 0, failing a correct fix. *"New
functions use camelCase"* is.

## Files

**3 added, 3 edited.** `task.toml` needs no change at all. No new Docker image.

| Action | Path | Source |
|---|---|---|
| ADD | `tests/judge.py` | `tests/judge.py` — copy byte-for-byte, never edit |
| ADD | `tests/rubrics.json` | `tests/rubrics.template.json` — copy, then write criteria |
| ADD | `tests/instruction.md` | a copy of the task's `instruction.md` (see Step 2b) |
| EDIT | `tests/config.json` | `snippets/2-config.json.snippet` — one key |
| EDIT | `tests/test.sh` | `snippets/3-test.sh.snippet` |
| EDIT | `tests/verifier.py` | `snippets/4-verifier.py.snippet` |
| — | `task.toml` | `snippets/1-task.toml.snippet` — confirms: no change |

`reference/` holds the applied result from `mui__material-ui-47967-mm`.

---

## Step 1 — `tests/judge.py` (ADD, verbatim)

```
cp tests/judge.py <task>/tests/judge.py
```

Never modify it; it is identical in every task. It strips its own directory from `sys.path`
(so nothing in `tests/` can shadow a stdlib module), excludes test/spec/snapshot hunks from
the diff it shows the judge, and always exits 0.

## Step 2 — `tests/rubrics.json` (ADD, then author)

Copy `tests/rubrics.template.json` and fill it in. **Exact schema:**

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

`task` must match `task_id` in `config.json`. Each criterion has **exactly two fields, `id`
and `criterion`** — no `category`, no `weight`, no anything else.

Rules, in priority order:

1. **One failure fails the whole rubric.** Only include criteria worth rejecting a submission
   over. No cosmetic checks — there is no optional tier to park them in.
2. **Decidable from the judge's inputs** (criterion + diff + changed files + instruction).
   Anything needing an untouched file, the repo at large, or a rendered UI is not.
3. **State the approach, never an identifier.** *"Fixes the paint order so the outline draws
   before its child"* is correct. *"Sets `borderOnForeground` to false"* is wrong: it fails
   any different-but-correct fix and recreates the overfitting the rubric exists to catch.
4. **Binary-answerable.** If a reviewer would say "sort of", rewrite it.
5. **Acceptance test for every criterion:** would a *different but correct* fix still pass it?
   If no, rewrite.
6. Never mention the rubric, its criteria, or the judge in `instruction.md`.

## Step 2b — `tests/instruction.md` (ADD, a copy)

```
cp <task>/instruction.md <task>/tests/instruction.md
```

`tests/` is mounted into the verifier and is **not** visible to the agent, so this is safe and
does not leak anything. It lets criteria be judged against what was actually asked. If the copy
is absent, `judge.py` simply omits it — nothing breaks, but "does this address the requirement"
criteria become undecidable.

Re-copy it whenever `instruction.md` changes, or the judge grades against a stale task.

## Step 3 — `task.toml` (NO CHANGE)

Confirm there is no `[verifier.env]` block and no `ANTHROPIC_*` / `JUDGE_MODEL` key. If a
previous draft added them, remove them.

## Step 4 — `tests/config.json` (EDIT)

Add `"rubric_file": "rubrics.json"` and nothing else. Keep every existing key.

Also re-check `f2p` / `p2p`: any test the PR *edited* — changed assertion, new snapshot, new
golden baseline — fails on base and is therefore **f2p, not p2p**.

## Step 5 — `tests/test.sh` (EDIT)

Replace the final `python3 /tests/verifier.py "${REPORTS[@]}"` with the block in
`snippets/3-test.sh.snippet`. Keep the existing `trap` and the `|| echo ""` — both are
load-bearing: the judge must never be able to fail the run.

## Step 6 — `tests/verifier.py` (EDIT)

Apply the five marked changes in `snippets/4-verifier.py.snippet`, keeping the task's existing
test-resolution logic. They are: import `json` and add the paths; replace the reward writer;
make per-group evaluation also return `{identifier: bool}`; parse `--rubric`; apply the gate.

**Record every test individually in `reward.json`.** A single test is binary, so an aggregate
`0.5` cannot say whether 1 of 3 or 2 of 3 f2p passed — and the decisive QC question, *"did
this specific f2p test pass on the nop run?"*, is unanswerable without the per-test map.

---

## Reward contract

`/logs/verifier/reward.txt` — one bare float, unchanged. Gating reads only this.

| Outcome | `reward.txt` |
|---|---|
| any p2p fails | `0.0` |
| some but not all f2p pass | `0.5` |
| all f2p pass, rubric FAILED | `0.5` |
| all f2p pass, rubric passed | `1.0` |
| all f2p pass, no verdict yet | `1.0` (tests-only) |

`/logs/verifier/reward.json` — detail, review only:

```json
{
  "reward": 0.5, "tests_passed": 0.5,
  "f2p_passed": 1, "f2p_total": 2,
  "f2p": {"test A": true, "test B": false},
  "p2p": {"test C": true},
  "rubric": "pass", "rubric_failed": []
}
```

`rubric` is `"pass"`, `"fail"`, or `null` (no verdict folded in yet).

---

## Running it

```bash
mm_run.sh <task-dir> oracle     # expect 1.0
mm_run.sh <task-dir> nop        # expect 0.0
mm_run.sh <task-dir> trial      # expect < 1.0 (the task must stump the model)
```

Each prints where the judge request landed. After a sub-agent writes `verdict.json` there:

```bash
mm_run.sh <task-dir> rescore --run <Oracle|Trials dir>
```

---

## Acceptance criteria

Static:

- [ ] `python3 -m py_compile tests/judge.py tests/verifier.py` succeeds.
- [ ] `bash -n tests/test.sh` succeeds.
- [ ] `tests/rubrics.json` parses; `schema` is `rubrics.schema/v1`; `task` matches
      `config.json`'s `task_id`; **every criterion has exactly `id` and `criterion`**.
- [ ] `grep -c ANTHROPIC task.toml` returns **0**.
- [ ] No file in `tests/` is named after a stdlib module (`select.py`, `json.py`, `types.py`,
      `io.py`, `queue.py`).
- [ ] `instruction.md` unchanged, and `tests/instruction.md` is a current copy of it.
- [ ] No `__pycache__/` or `*.pyc` committed under `tests/`.

Behavioural — read `reward.json`, not just the float:

- [ ] Oracle `1.0`, every f2p `true`.
- [ ] Nop `0.0`, and **every f2p `false` individually**. An f2p that is `true` on nop cannot
      detect the bug and is inert — fix or replace it. Check the map, not the aggregate.
- [ ] No p2p is `false` on nop; if one is, it is mislabeled and is really f2p.
- [ ] A judge request appeared under the run's `verifier/judge/`, containing
      `criteria_payload.json`, `source.txt`, `changed_files.txt`, `instruction.md`, `PROMPT.md`. If not, the rubric was
      never picked up — check `judge.log`.
- [ ] After grading + `rescore`: oracle shows `rubric: "pass"`.
- [ ] Trial reward `< 1.0`. A trial scoring `1.0` means the model solved the task, so it does
      not stump and needs reworking.

`validate_reward.sh` in the parent folder automates the reward-side checks, including
flagging inert f2p tests.
