# Rubric Modes — layout, files, and expected output

Reference for the two legal **shapes** of a task's rubric layer, and how to rewire a task into
one of them.

**Mode A** = the task ships a rubric. **Mode B** = the task ships no rubric layer at all.
Both are correct; anything in between is a blocking defect.

> Pick the mode with one question: **is there a defect class the behavioral tests structurally
> cannot catch?** Yes → A (the usual case: the tests pin exact numbers, so they can be satisfied by
> writing those numbers back as literals). No → B. If you can't name the loophole in one sentence,
> the answer is B.

**Scope.** This doc covers wiring only — which files exist, what each must contain, what the run
must emit. Criterion *content* quality (overfitting, underfitting, vagueness, contradiction,
whether a criterion is decidable from the diff) is a separate axis owned by `checks/qc_rubrics.py`;
see its `SEMANTIC` table for the six classes and their severities.

```bash
SK=~/.claude/skills/mm-swe-qc-fix-sandbox

python3 $SK/checks/qc_rubric_format.py <task-dir>   # rubric layer only
python3 $SK/checks/qc_all.py <root>                 # the whole audit; <root> CONTAINS Tasks/
# exit 0 = PASS, 1 = at least one FAIL
```

You do not have to run these by hand: the same audit runs automatically as a pre-flight before a
harbor check, and blocking defects stop the run.

---

## 1. Folder structure

```
<task-dir>/                         MODE A                      MODE B
├── task.toml                       ✓  [verifier.env] EVAL_*    ✓  NO [verifier.env]
│                                   ✓  [verifier] public        ✓  [verifier] public
├── instruction.md                  ✓                           ✓
├── evidence_bundle.json            ✓                           ✓
├── environment/
│   ├── Dockerfile                  ✓                           ✓
│   └── assets/                     ✓  ASSET_MANIFEST + posters ✓
├── solution/
│   ├── fix.patch                   ✓                           ✓
│   └── solve.sh                    ✓                           ✓
└── tests/
    ├── config.json                 ✓                           ✓
    ├── test.patch                  ✓                           ✓
    ├── test.sh                     ✓  judge block runs         ✓  judge block no-ops
    ├── verifier.py                 ✓  --rubric gate fires      ✓  --rubric gate never fires
    ├── rubrics.json                ✓  ≥1 real criterion        ✗  MUST NOT EXIST
    └── judge.py                    ✓                           ✗  MUST NOT EXIST
```

`rubrics.json` and `judge.py` travel together — one without the other is a blocking defect
(`rubfmt_judge_present` / `rubfmt_judge_absent`).

**All three are blocking, but they are not scoped alike.** `[verifier] network_mode = "public"` is
required of **every task**; the judge backend (`call_eval_api`) and `[verifier.env]` are Mode A
only. See §2b.

These were once "not graded, deliberately", on the grounds that both judge backends were valid and
the `[verifier]` blocks vary legitimately across tasks. That did not survive one observation: a
sub-agent-only judge cannot grade *during* the run, and the manual follow-up it depends on is
routinely skipped. Requiring in-band grading collapses the supposed variance, because an
API-backend judge has exactly one working configuration. Credentials still never live in a bundle —
`[verifier.env]` holds `${VAR}` references that harbor expands at run time.

`network_mode` then outgrew the rubric argument entirely. The verifier phase does not only reach a
judge, it **installs what the tests need** — `npm install`, `pip install`, a bare `npx <runner>`
resolving from the registry. Sealed, those fail, the f2p test fails with them, and a *correct*
submission records `0.0`. So it is graded on every task, Mode B included.

What Mode B is still untouched by is **`[verifier.env]`**, and for a concrete reason rather than a
stylistic one: nothing reads `EVAL_*` without a judge, and the block's bare `${VAR}` entries are
*required* host vars to harbor — so writing it into a rubric-less task breaks its keyless
`oracle`/`nop` for credentials that would never be read. That is the false-failure class this area
was pulled out of scope for.

---

## 2. Files

### `tests/rubrics.json` — Mode A only

```json
{
  "schema": "rubrics.schema/v1",
  "task": "<same task_id as task.toml and config.json>",
  "description": "<the defect class this guards, and why the tests can't>",
  "criteria": [
    { "id": "snake_case_property", "criterion": "<one decidable property>" }
  ]
}
```

Unweighted, all mandatory, strictly binary — **one `0` fails the whole rubric**. No `weight`,
`category` or `points` fields. Ids are descriptive snake_case, not numbers.

The `task` value must agree with `task.toml` and `tests/config.json` (`rubric_task_id`).

**Never legal:** a single all-pass criterion (`always_pass`, "The response is written in English").
It cannot fail any submission yet makes `rubric_passed` read `1` as though a real rubric had been
satisfied — it fabricates a graded result, and with a zero denominator every rubric-quality
percentage band passes unfalsifiably. That is Mode B written wrongly → strip the layer (§4).

### `tests/judge.py` — Mode A only

**The API backend is REQUIRED** — the judge must define `call_eval_api` and grade in-band. A
sub-agent-only judge is a blocking `rubfmt_judge_backend`; see §2b for why, and copy
[`reference/judge.py`](reference/judge.py) whole to fix it. The sub-agent path stays *as the
fallback inside that file* — it is what guarantees the judge can never fail a run.

Contract (also enforced):

| Must | Detail |
|---|---|
| print `pass` / `fail` / **nothing** | stdout is captured verbatim into `test.sh`'s `RUBRIC`; all diagnostics → stderr |
| write `<judge dir>/summary.json` | per-criterion detail |
| **always exit 0** | the judge can never fail the run |
| let an existing `verdict.json` win | makes `rescore` idempotent |

A missing `judge.py` while a rubric ships is `judge_missing`; `fix.py` installs
`reference/judge.py` — the API-backend one, so the repair does not trade one blocker for another.
A hash mismatch against that reference is `judge_drift`, still **ask** rather than auto-restore:
the task may have adapted the judge deliberately, and overwriting would replace a working one.

### `tests/config.json`

| Key | Mode A | Mode B |
|---|---|---|
| `task_id`, `verifier_mode`, `test_framework`, `test_files`, `f2p`, `p2p` | ✓ | ✓ |
| `rubric_file` | `"rubrics.json"` | **key absent** |

A `rubric_file` pointing at a file that isn't there — or missing while a rubric ships — is
`rubfmt_config_rubric_file`, blocking: the rubric never runs.

### `tests/verifier.py` — both modes

Reads `f2p`/`p2p` from `config.json` (never hardcoded), parses `--rubric`, and applies the
**binary** policy via a single `canon_reward(...)` call at whatever point the reward is decided.
`atexit` makes it write last, so it safely overrides an existing local reward block.

The canonical block is a file, not a snippet in this doc — copy it from there so the two cannot
drift:

```bash
cat $SK/template/tests/verifier_reward_block.py
```

`fix.py` never writes this one (`verifier_rubric`): `verifier.py` holds task-specific scoring, so a
blind insert could silently change what the task grades. The **agent** merges it by hand under the
CB's approval and proves it — see §2c.

Gate semantics — it can only ever withhold a `1.0`:

| `--rubric` | Effect on reward | `rubric_passed` |
|---|---|---|
| `fail` | forced to `0.0` | `0` |
| `pass` | none | `1` |
| `""`, absent, or unparsed | none, **ever** | `-1` |

Reward is binary. A strict subset of f2p passing is `0.0`, **not** `0.5` — partial credit would let
a half-fix read as solved to pass@k, and the four count keys already carry the detail. A verifier
that can emit `0.5` is `rubfmt_verifier_reward_domain`, blocking; the repair floors to `0`, never
rounds to nearest. The agent applies it — see §2c.

**Reword the docstring in the same edit.** The check is AST-only on purpose, so that prose
describing a legacy `0.5` rung ("reward.txt is a bare float in `{0.0, 0.5, 1.0}`") does not read as
code that emits one. The cost is that nothing catches a module docstring still documenting the
ladder after the code is floored: the file then documents a band it cannot produce, with every check
green. Grep the file for `0.5` after the repair and fix whatever the AST did not reach — including
any "`1.0 -> 0.5`" phrasing describing what a failed rubric does, which is now `1.0 -> 0.0`.

### `tests/test.sh` — byte-identical in both modes

The judge block is a file too:

```bash
cat $SK/template/tests/test_sh_judge_block.sh
```

`fix.py` inserts it **verbatim** (`test_sh_judge`), replacing the plain verifier invocation; it is
verified to reproduce the golden byte-for-byte. Three things about it are load-bearing:

- the `[ -f /tests/rubrics.json ]` guard — false in Mode B, so the block no-ops. An **unguarded**
  judge block is a hard failure in *both* modes; in Mode B it would run `judge.py` against a rubric
  that does not exist on every run.
- `|| echo ""` — the judge must never be able to fail the run.
- the verifier call keeps its report arguments **and** takes `--rubric` (singular). `--rubrics`
  (plural) is `judge.py`'s own flag and does not satisfy the contract.

In Mode B the `--rubric` plumbing is inert — an empty flag, an omitted flag and no parsing at all
all yield `rubric_passed = -1` — so its absence is a warning there rather than a blocker. Ship it
anyway: it is three lines, and it is what makes the two shapes one contract.

---

## 2b. The verifier phase must be able to work

Two separate requirements live here, and conflating them is what kept the first one Mode-gated
for too long. Missing either is a blocking finding.

| Requirement | Where | Applies to | Finding if missing |
|---|---|---|---|
| `network_mode = "public"` | `task.toml` `[verifier]` | **every task** | `rubfmt_verifier_network_mode` |
| `judge.py` has an API backend (`call_eval_api`) | `tests/judge.py` | Mode A | `rubfmt_judge_backend` |
| `EVAL_API_KEY` / `EVAL_BASE_URL` / `EVAL_MODEL` mapped | `task.toml` `[verifier.env]` | Mode A | `rubfmt_verifier_env` |

**Mode B — the whole `[verifier]` requirement, and it is the same as Mode A's:**

```toml
[verifier]
network_mode = "public"
```

**Mode A — the above, plus the credential block. This is the only task.toml difference between
the two shapes:**

```toml
[verifier]
network_mode = "public"

[verifier.env]
EVAL_API_KEY  = "${OPENAI_API_KEY}"
EVAL_BASE_URL = "${OPENAI_API_BASE}"
EVAL_MODEL    = "${EVAL_MODEL:-anthropic/claude-opus-4-5-20251101}"
```

`[agent] network_mode = "no-network"` and the `[environment]` block are identical in both modes and
no fix touches either. `timeout_sec` is task-specific and not graded — though a Mode A verifier
makes an LLM call per criterion and needs headroom a Mode B one does not.

**Why `network_mode` is not a rubric requirement.** The verifier phase does two things that need
egress, and only the first involves the judge:

1. **the judge dials the proxy** (Mode A). Sealed, it cannot, and every run records
   `rubric_passed = -1`.
2. **the tests install their dependencies** (both modes). `test.sh` routinely runs `npm install`,
   `pip install`, or `npx <runner>` that resolves from the registry when the binary is not already
   in the project tree. Sealed, those fail, the f2p test fails with them, and a **correct**
   submission records `0.0` — a false negative whose reward looks entirely legitimate.

The second is why this is graded on every task. A Mode B verifier that cannot install its test
runner mis-scores every submission it grades, which is the same defect class the Mode A findings are
blocking for. Tasks that pre-stage dependencies at build time never exercise the permission, so
holding it costs them nothing.

**What the seal was buying, and why it is not worth it.** `no-network` makes an *accidental*
registry dependency fail loudly at authoring time, which is real: a task pulling `vitest@latest` at
verify time passes today and rots when that version moves. Pre-staging into the image is still the
better shape. But the cure for an accidental dependency cannot be a permission that silently
mis-scores every task with a deliberate one.

**Why in-band grading is required.** A sub-agent-only judge is not wrong, it is incomplete. It
writes a request and prints nothing, so the verifier scores on tests alone and the run records
`rubric_passed = -1`. The verdict only ever exists if a human reads `PROMPT.md`, writes
`verdict.json` and reruns `rescore` — and that step is routinely skipped. A rubric that never
grades is decorative in exactly the way an all-pass stub is: the layer looks wired and measures
nothing. Same defect, same blocking severity.

**Why `"public"` and not an allowlist.** Verified against harbor 0.18, not assumed:
`NetworkPolicy.validate_allowed_hosts` rejects `allowed_hosts` unless `network_mode ==
"allowlist"`; `normalize_allowed_hosts` validates **literal** hostnames and never env-expands, so
a run-time-injected endpoint cannot be named; and the CLI exposes `allow_agent_hosts` /
`allow_environment_hosts` but **no** `allow_verifier_hosts`. There is no way to express "the
proxy, wherever it is today" as an allowlist. `"public"` is the only value that lets the judge
connect.

**What it costs: nothing an agent can reach.** The verifier runs after the agent phase is over and
`test.sh` restores the test files from `harbor_base`, so egress here cannot help a submission cheat.
A task that pre-stages its test dependencies never exercises the permission at all. The **agent**
phase stays sealed — leave `[agent] network_mode = "no-network"` alone.

**No credential enters the bundle.** `[verifier.env]` holds `${VAR}` *references*. Harbor expands
them from its own environment at run time, and the value is the anonymizer placeholder, not a
real key — the proxy on the VM holds the actual credential. A bare `${VAR}` with no `:-` default
is a **required** host var: harbor exits 1 with a "Missing Environment Variables" table before any
container starts if it is absent.

**Keep the sub-agent path.** It stays in `judge.py` as the fallback, and it is what guarantees the
judge can never fail a run. What is barred is shipping it as the only route to a verdict.

### How to repair each of the three

**`task.toml` (both findings) — auto.** These have one correct value each, so `fix.py` writes them:

    python3 fix.py apply <Tasks> --approve verifier_network_mode --approve verifier_env --apply

It edits `[verifier] network_mode` in place and appends only the `[verifier.env]` keys that are
missing, so `timeout_sec` and everything else in the file survive. It does **not** touch
`[agent] network_mode` — that must stay `"no-network"`.

`verifier_network_mode` is offered on **every** task; `verifier_env` only when a real rubric ships
(parses, ≥1 non-stub criterion — the same predicate the check uses for Mode A). On a Mode B task the
first is proposed alone, which is correct: there is no `[verifier.env]` to write.

Note `verifier_network_mode` is a **class C** fix — the trial must be re-run, not rescored.
Unsealing the verifier can change whether the tests pass at all, and `rescore` recomputes only the
rubric verdict. `verifier_env` remains class B, since it only ever affected the verdict.

**`judge.py` — never the CB's job.** Which of you does it turns on one sha (§2c):

| Situation | Who | Do this |
|---|---|---|
| no `judge.py`, or it is the **stock stub** (sha matches `template/tests/judge.py`) | `fix.py`, `auto` | nothing — `judge_missing` / `judge_backend` copy [`reference/judge.py`](reference/judge.py) for you |
| a judge with **local changes** worth keeping | the agent | merge [`template/tests/judge_api_block.py`](template/tests/judge_api_block.py) rather than copying over the adaptation |

`reference/judge.py` is byte-identical in both reference tasks (a TypeScript one and a JavaScript
one — same sha256), so there is nothing task-specific to strip. `fix.py`'s `judge_missing`
installs this same file, which is why that auto-fix no longer trades one blocker for another.

If you merge the snippet rather than copying the file, three things beyond pasting the code:

1. imports: `json`, `os`, `re`, `sys`, `time`, `urllib.error`, `urllib.request`
2. in `main()`, grade in-band *before* falling back to `write_request()`, and persist the scores
   so the verdict is auditable and a rescore is idempotent:

   ```python
   scores = call_eval_api(criteria, diff, changed)
   if scores is not None:
       (jdir / "verdict.json").write_text(json.dumps(scores, indent=2))
       res = read_verdict(criteria, jdir)      # ONE scoring path for BOTH backends
       if res is not None:
           return emit(*res)
   ```
3. keep the sub-agent `write_request()` fallthrough — it is what guarantees the judge can never
   fail a run, and it is what the host-side grader reads (`judge/source.txt`) if the API path dies.

**Keep the name `call_eval_api`.** The check greps for it, so renaming it fails the gate even
though the code works.

Verify with `python3 checks/qc_rubric_format.py <Tasks>` — all three should read `[OK ]`.

---

## 2c. Who performs each repair

Three kinds of finding, by who writes the bytes. The distinction is **not** how important the fix
is — it is whether a script can make it without reading the surrounding logic.

| Kind | Who | Which findings |
|---|---|---|
| `auto` | `fix.py`, under `--apply` | `verifier_network_mode` *(every task)*, `verifier_env` *(Mode A only)*, `rubric_key_rename`, `rubric_file`, `rubrics_shape`, `rubric_task_id`, `test_sh_judge`, `judge_missing`, `judge_backend` *when the judge is the stock stub*, the junk/debris sweep |
| **`agent`** | **you, following this doc** | `verifier_reward_domain` (§2) · `verifier_rubric` (§2) · `judge_backend` *when the judge was adapted* (§2b) |
| `ask` | the CB decides first | the mode itself (§4, either direction), deleting an asset or a stray file, rubric criterion wording |

The split is **whether a hash can settle it**. `judge_backend` is a whole-file copy of
task-agnostic boilerplate, so `sha(tests/judge.py) == sha(template/tests/judge.py)` proves outright
that nothing task-specific is destroyed — that case is `auto`, and it is the same copy
`judge_missing` already makes. A different sha means someone adapted the judge, so you read the
diff first. Nothing equivalent exists for `verifier_reward_domain`: `reward = tests_passed * 0.5`
floors to `* 0.0`, a verifier scoring zero on every run including oracle, and no checksum can warn
you. That is why it stays `agent` however small the edit looks.

**`agent` repairs are inside the CB's single approval** — do not ask again for each one. They are
not `auto` because `verifier.py` carries task-specific scoring and `judge.py` carries the grading
contract: a regex that floors a reward, or a blind block-merge, can silently change what the task
grades, and a wrong "fix" there is worse than the defect because the number still looks like a
score. A script cannot read the surrounding logic to know it stayed correct.

What you owe in exchange is proof. `fix.py qc` prints an `AGENT REPAIRS` section naming the exact
sites and the command that proves each one; run it and show the `[OK ]` before reporting the
blocker cleared. An unproven repair is reported as unproven, never as done.

    verifier_reward_domain   §2   →  qc_rubric_format.py | grep reward_domain
    verifier_rubric          §2   →  qc_rubric_format.py | grep -E 'verifier\.(gate|reward_json)'
    judge_backend (adapted)  §2b  →  qc_rubric_format.py | grep -E 'judge\.(backend|rubric_json)'

**Static proof is not runtime proof.** These commands confirm the *wiring* — that `call_eval_api`
exists, that the reward domain is closed, that `[verifier.env]` maps the three `EVAL_*` names. They
cannot confirm the judge actually reached its endpoint and graded, because that needs a real run.
The oracle is what settles it: it should record `rubric_passed = 1`, and a `-1` there means the
endpoint was unreachable or the env block did not arrive. Say which of the two you proved.

All three are **class B** — the rubric/judge layer only — so an existing trajectory survives. But
flooring the reward changes what a *partial* run scores, so a gate run predating the repair now
describes files that no longer exist: offer `fix.py verify <root> --run` and let the CB spend it or
not.

---

## 3. Expected output

All under `/logs/verifier/` in the container.

| Artifact | Mode A | Mode B |
|---|---|---|
| `report.xml` | JUnit from the test run | same |
| `reward.txt` | bare float, no trailing newline | same |
| `reward.json` | canonical 7 keys | same |
| `judge/` | judge request + verdict | **not created** |
| `rubric.json` | `{"failed": [...], "criteria_total": N}` — only if `judge.py` writes it | not created |

### `reward.json` — the canonical shape, both modes

Exactly seven keys, flat, every value numeric:

```json
{ "reward": 1.0, "tests_passed": 1.0,
  "f2p_passed": 9, "f2p_total": 9, "p2p_passed": 4, "p2p_total": 4,
  "rubric_passed": 1 }
```

`rubric_passed`: `1` pass · `0` fail · `-1` not graded.

**Nested values abort the trial.** harbor parses this as `dict[str, float | int]` and prefers it to
`reward.txt`; a dict, list, string or `None` raises a validation error *before* any reward is
recorded — while `reward.txt` is still written in-container, so the run looks scored when nothing
was stored. Per-test detail rides along as extra scalar `f2p::<name>` = `1.0`/`0.0` keys, never a
nested map. Wrong shape or wrong key set is `rubfmt_verifier_reward_json` / `…_keys`, blocking.

### What each run should produce

| Run | `reward` | `tests_passed` | `rubric_passed` (A) | `rubric_passed` (B) |
|---|---|---|---|---|
| **oracle** (golden patch) | `1.0` | `1.0` | `1` — graded in-band, no rescore needed | `-1` |
| **nop** (empty submission) | `0.0` | `0.0` | `-1` | `-1` |
| all f2p pass, rubric fails | `0.0` | `1.0` | `0` | n/a |
| some f2p pass | `0.0` | `0.0` | any | any |
| any p2p regresses | `0.0` | `0.0` | any | any |

`tests_passed` is the tests-only score, so a rubric-gated run is still legible as
"tests passed, rubric failed".

With the API backend required, **oracle records `rubric_passed = 1` on the run itself** — measured:
`[judge] graded via API model=anthropic/claude-opus-4-5-20251101` → `verdict=pass`, with
`verdict.json` and `summary.json` written inside the run. `-1` on an oracle now means something
went wrong, not "grading hasn't happened yet": the endpoint was unreachable, `[verifier.env]` did
not map the three `EVAL_*` names, or `[verifier] network_mode` was not `"public"`. The rescore
path still exists and still works, but it is the fallback, not the expected route.

### `judge/` contents — Mode A only

Written on the first pass, when no verdict exists yet:

| File | What it is |
|---|---|
| `criteria_payload.json` | `[{id, criterion}, …]` |
| `source.txt` | the candidate diff, test/spec/snapshot paths stripped |
| `changed_files.txt` | full current text of every file the diff touched |
| `PROMPT.md` | self-contained instructions for the judge sub-agent |
| `verdict.json` | **the sub-agent writes this**: `{"scores": {"<id>": {"score": 0\|1}}}` |
| `summary.json` | `{"rubric": "pass"\|"fail", "failed": [...], "criteria_total": N}` |

Then `rescore` folds the verdict into the reward. A pending judge prints nothing and never
penalises: scoring falls back to tests alone.

Note what the judge is **not** given — `instruction.md`, `solution/fix.patch`,
`tests/test.patch`, the screenshots, the wider repo. That is why a criterion has to be decidable
from the diff alone, and why `tests/instruction.md` is not part of the canonical layout.

---

## 4. Converting a Mode A task to Mode B

When the rubric turns out to be unnecessary (or is an all-pass stub):

1. delete `tests/rubrics.json` and `tests/judge.py`
2. remove `"rubric_file"` from `tests/config.json`
3. **leave `verifier.py` and `test.sh` alone** — the guarded judge block and the `--rubric` gate
   stay in both modes
4. in `task.toml`, **remove `[verifier.env]`** — nothing reads `EVAL_*` once the judge is gone, and
   its bare `${VAR}` entries would keep harbor demanding host credentials for a run that is now
   keyless. **Keep `[verifier] network_mode = "public"`**: that one is not part of the rubric layer
   at all — the verifier still has to install what the tests need (§2b)

Result: `rubric_passed = -1`, reward decided by tests alone, and the bundle stays byte-compatible
with the corpus-wide verifier contract.

This is never auto-applied: it deletes files, and choosing between the two shapes is a judgement.
The audit reports it as `rubfmt_mode` / `rubfmt_rubrics_stub_only` for you to decide.
