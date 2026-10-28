---
name: mmswe-runner
description: >
  Run an MM SWE Harbor task five ways — oracle, nop, a single agent trial on
  claude-opus-4-8, a harbor check, and a post-hoc analyze — and read the results.
  Use when the user says "run the oracle", "run nop", "run the trial", "sanity check
  this task", "run harbor check", "harbor check fails", "run analyze", or asks whether
  an MM SWE / QH task passes. Tasks are single-container Harbor tasks whose verifier is
  unit tests -> JUnit -> reward.txt; oracle and nop run keyless UNLESS the task ships
  tests/rubrics.json, in which case its LLM judge needs credentials too. Trial, check
  and analyze always need credentials and go through the anonymizer proxy.
version: 1.4.0
---

# MM SWE task runner — oracle, nop, single trial

Validate an MM SWE Harbor task by running it three ways on the local Docker provider:
the **oracle** (applies the golden `solution/fix.patch` — should score 1.0), the **nop**
(empty submission — should score 0.0), and one **agent trial** (claude-code on
claude-opus-4-8 — the real measurement).

## Layout

From TASK101 on (V2) the task bundle sits one level down, in `Tasks/<task_id>/`. The run dirs
stay flat siblings of `Tasks/` — no per-task subfolder inside any of them:

    <ROOT>/Tasks/<task_id>/   the task (task.toml, environment/, solution/, tests/) — V2
    <ROOT>/Tasks/             the same files directly inside — V1 (before TASK101)
    <ROOT>/Trials/      agent trial output
    <ROOT>/Oracle/      oracle output
    <ROOT>/Nop/         nop output
    <ROOT>/Check/       harbor check output (rubric quality checks)
    <ROOT>/Analyze/     harbor analyze output (post-hoc trial analysis)

harbor writes a job at `<-o>/<--job-name>`, so the runner passes `-o <ROOT>` and names
the job `Trials`, `Oracle`, `Nop`, `Check`, or `Analyze` — landing output exactly in
that folder. Each one
holds harbor's own `config.json`, `result.json`, `job.log`, and a `<name>__<rand>/`
trial dir containing `verifier/reward.txt`. `<name>` is the task folder's name (cut to 32
chars), so it is `<task_id>__<rand>` in V2 (e.g. `ariakit__ariakit-4129-mm__AbC12xY`) and
`Tasks__<rand>` in V1.

Because the folders are fixed, **each run overwrites the previous one** for that mode.
Pass `--keep` to preserve an earlier run instead.

`ROOT` is inferred as the directory containing `Tasks/` — pointing at
`/home/sandbox/Tasks/<task_id>` (V2) or `/home/sandbox/Tasks` (V1) writes to
`/home/sandbox/{Trials,Oracle,Nop,Check,Analyze}/`. Pointing at `Tasks/` itself, or at the
root above it, also works for V2: the runner descends into the single `Tasks/<task_id>/`
bundle, and refuses (listing them) if there is more than one. Override with `--root`.
`tasks/` and `Tasks/` are both recognized, and a legacy `project/` wrapper is still tolerated.

The task id (from `task.toml`'s `[metadata] task_id`, else the folder name) is printed
as `[mm_run] task <id>` for the log only — it no longer appears in any path.

## Credentials — trial, check, and analyze

The verifier runs unit tests and writes `reward.txt`; it never calls a model. So
**oracle and nop need no key** and the runner deliberately passes none. The trial,
check, and analyze get credentials, resolved exactly the ProjectBench way so a real
key is never pasted into a command: **live env first, then
`~/.claude/settings.json`'s `.env`, then the anonymizer defaults**.

Anonymizer defaults (the standard path):
- `ANTHROPIC_BASE_URL = http://localhost:8091` — the anonymizer proxy, Claude format
  (`:8090` is the OpenAI-format port).
- `ANTHROPIC_API_KEY = anonymizer-placeholder` — a placeholder token; CBs never handle
  a real key. It only authenticates THROUGH the anonymizer proxy.

The key is masked in all output. The **public Scale endpoint
(`https://litellm-proxy.ml.scale.com`) is not the default** — it is used only if you
explicitly export it, and the runner says so when that happens.

Because the anonymizer listens on the VM's loopback, the agent container can't reach it
by default. The runner solves that with a **docker-compose override**, which does double
duty — so **all three modes get it**, not just the trial:

    services:
      main:
        network_mode: host              # container's localhost IS the VM's localhost
        environment:
          TAR_OPTIONS: --no-same-owner  # fixes tar chown failures in nested docker

`network_mode: host` means `http://localhost:8091` works with no address rewriting.
`TAR_OPTIONS` matters for a different reason: under the sandbox's nested-docker user
namespace, GNU tar fails with "Cannot change ownership to uid …" during extraction (e.g.
flutter's gradle-wrapper fetch), which breaks the **environment build** — so oracle and
nop need it as much as the trial does.

Precedence: `--hostnet-file F` → the `tarfix.yaml` shipped beside the script → a generated
temp file (deleted on exit). If tar chown still fails, retry with `--userns-host`, which
adds `userns_mode: "host"` (only effective under userns-remap, harmless otherwise).
`--no-hostnet` falls back to the proxy bridge. If harbor's service isn't `main`, set
`COMPOSE_SVC=<name>`.

The trial also passes `--ak disallowed_tools=WebSearch,WebFetch,EnterPlanMode` so the
agent can't reach the web or enter plan mode mid-trial. Disable with
`--no-disallow-tools`.

A **preflight** check confirms the resolved endpoint is reachable before spending a
trial (skip with `--no-preflight`).

## check and analyze — same proxy, different route

`harbor check` (rubric quality checks on a task) and `harbor analyze` (post-hoc
analysis of a finished trial) both run an agent in a container, so both need the
anonymizer. **Neither can use the host-network trick above**, for two reasons that are
worth knowing before you try:

- Neither subcommand has an `--extra-docker-compose` flag.
- Their `-c/--config` JobConfig looks like a way in, but both **overwrite**
  `config.environment` after loading it (`analyze/checker.py`, `analyze/analyzer.py`),
  so an `environment.extra_docker_compose` in that file is silently discarded.

So instead of making the container's localhost *be* the VM's localhost, these two
modes give the container **an address that routes back to the VM** and pass it as
`--ae ANTHROPIC_BASE_URL=...` (plus `--ae ANTHROPIC_API_KEY=...`). `--ae` wins over the
inherited host value: harbor's precedence is persistent < per-exec < `AgentConfig.env`.
Without it, the container inherits `ANTHROPIC_BASE_URL=http://localhost:8091` verbatim,
dials its own loopback, and the run dies with **`API Error: Unable to connect to API
(ConnectionRefused)`** after ten retries — which surfaces as `Check trial failed with
UnknownApiError` and a mean of 0.000.

The address is **probed, not guessed** (`resolve_host_addr`): candidates are
`$PB_HOST_ADDR`, the host's route-source IP, the docker bridge gateway, then
`host.docker.internal`, each tested by opening a socket *from a throwaway container*
with no `--add-host` — so the probe sees exactly what harbor's container will see. On
this sandbox's rootless docker only the route-source IP (`10.0.2.2`) works; the bridge
gateway and `host.docker.internal` are both refused. If no candidate reaches the proxy
port, the runner starts `sandbox_proxy_bridge.py` on `0.0.0.0` and re-probes for the
bridge's port instead.

These two modes need no compose override for the `TAR_OPTIONS` reason either: their
wrapper tasks run a prebuilt `python:3.13-slim` with no Dockerfile, so there is no
build to break.

### check runs a file-name gate first

Before spending a check run, `check` verifies the task carries all twelve required
files and exits 2 — printing every missing path, not just the first — if any is
absent:

    task.toml  instruction.md  evidence_bundle.json
    environment/Dockerfile  environment/assets/ASSET_MANIFEST.json
    solution/fix.patch  solution/solve.sh
    tests/config.json  tests/test.patch  tests/test.sh  tests/verifier.py  tests/rubrics.json

The rubric criteria assume these exist, so without the gate a missing file comes
back as a puzzling judge verdict — or a bare `error` — after the run has already
been paid for. Names cost nothing to verify locally, so they are checked first.

`instruction.md` is **singular**: that is harbor's canonical name
(`models/task/paths.py` → `instruction_path`). A plural `instructions.md` is
invisible to harbor.

The gate is check-only; `oracle`, `nop`, `trial`, and `analyze` are untouched.
`--no-file-check` skips it and runs harbor check regardless.

Two things to know about their output:

- Neither produces a `reward.txt` — they are rubric judges. The runner reads
  `Check/check_report.json` and `Analyze/analysis.json` and prints one line per
  criterion plus a tally and cost.
- **`analyze` writes back into what it analyzes**: harbor drops an `analysis.json`
  into each analyzed trial dir. A later `trial` run without `--keep` deletes
  `<ROOT>/Trials` wholesale and takes those with it. The runner warns when this
  applies.

`analyze` takes a **trial dir, a job dir, or a task dir**. Given a task dir it analyzes
`<ROOT>/Trials` — so you can keep passing the task dir everywhere. Job dirs and trial
dirs both carry a top-level `result.json`, so they are told apart by whether a *child*
dir holds one; `<ROOT>` always ends up the dir that holds the job dir, never the job
dir itself.

## Run it

    bash mm_run.sh <task-dir> oracle     # or /run-oracle
    bash mm_run.sh <task-dir> nop        # or /run-nop
    bash mm_run.sh <task-dir> trial      # or /run-trial
    bash mm_run.sh <task-dir> check      # or /run-check
    bash mm_run.sh <task-dir> analyze    # or /run-analyze  (analyzes <ROOT>/Trials)

`<task-dir>` is the folder containing `task.toml` — in the sandbox
`/home/sandbox/Tasks/<task_id>` for V2 tasks (`/home/sandbox/Tasks` resolves to it too).
`analyze` also accepts a job or trial dir directly:

    bash mm_run.sh <ROOT>/Trials analyze
    bash mm_run.sh <ROOT>/Trials/<task_id>__vp2kgTM analyze     # V1: Trials/Tasks__vp2kgTM

### Options

| Flag | Default | Purpose |
|------|---------|---------|
| `--model M` | `anthropic/claude-opus-4-8` | trial model |
| `--check-model M` | `claude-sonnet-5` | check model — the name the anonymizer serves, not harbor's own default |
| `--analyze-model M` | `claude-sonnet-5` | analyze model — the name the anonymizer serves, not harbor's own default |
| `--rubric F` | harbor built-in | rubric file for check/analyze |
| `--check-prompt F` | harbor built-in | evaluator prompt for check/analyze |
| `--passing` / `--failing` | all trials | analyze only passing / only failing trials |
| `-l N` | all trials | analyze at most N trials |
| `--agent A` | `claude-code` | trial agent |
| `--root DIR` | dir containing `Tasks/` | where Trials/Oracle/Nop are written |
| `--env E` | `docker` | harbor environment |
| `--no-preflight` | preflight on | skip the connectivity probe |
| `--no-file-check` | gate on | run harbor check even if required task files are missing |
| `--no-hostnet` | override on | use the proxy bridge instead of the compose override |
| `--userns-host` | off | add `userns_mode: host` (retry aid for tar chown) |
| `--hostnet-file F` | generated | supply your own compose override |
| `--no-disallow-tools` | tools blocked | leave WebSearch/WebFetch/EnterPlanMode enabled |
| `--keep` | overwrite | keep a previous run dir instead of deleting it |

Single attempt by design — harbor's default `n_attempts` is 1, so no pass@k flags are
passed. Add `-n` only if you later want pass@k.

## Rubrics / LLM judge (optional)

If the task ships `tests/rubrics.json`, it carries a rubric graded by a **sub-agent judge** —
binary and unweighted, so every criterion is PASS/FAIL, every one is mandatory, and the rubric
passes only if all pass.

**No credentials are involved.** The judge never calls a model from inside the verifier, so
there is no `[verifier.env]`, no API key, no proxy and no bridge on this path. It is two-phase:

1. During a run, `tests/judge.py` finds no verdict, writes a judge request
   (`criteria_payload.json`, `source.txt`, `PROMPT.md`) under the run's `verifier/judge/`,
   and the task scores on tests alone. The runner prints where the request landed.
2. A judge sub-agent reads `PROMPT.md` and writes `verdict.json` beside it. Then:

       mm_run.sh <task-dir> rescore --run <Oracle|Trials dir>

   folds the verdict into `reward.txt`/`reward.json` from the existing JUnit XML — no
   container, no rebuild.

The rubric is a **gate**: it can turn a `1.0` into `0.5`, never push a score toward `0.0`, and
a missing verdict means tests-only rather than zero.

**Not the same as `check`.** `harbor check` grades **the task** (is it well-built?); this
rubric grades **the submission** (was the fix legitimate?). They are complementary.

## Read the result

Reward comes from `verifier/reward.txt` (or `result.json` → `verifier_result.rewards`).

- **Oracle < 1.0** — the golden patch doesn't satisfy the tests: a broken `fix.patch`,
  a test asserting something the fix doesn't do, or an environment/build failure.
- **Nop > 0.0** — the verifier accepts an empty submission; the f2p tests aren't
  discriminating. Fix those before trusting any trial number.
- **Partial (e.g. 0.5)** — with this verifier shape, some but not all f2p tests passed;
  p2p failures score 0.0 outright.

For check and analyze there is no reward — read the per-criterion outcomes the runner
prints, or the reports themselves at `Check/check_report.json` and
`Analyze/analysis.json`. A `results[].error` there (rather than populated `checks`)
means the judge agent never produced a verdict — usually a connectivity or model
problem, not a verdict about the task, so check the `[mm_run] container will dial …`
line before reading anything into it.

`Check agent did not produce a valid result` / `missing result file: check-result.json`
with a mean of 0.000 is that same class of failure: the agent process ended without
writing its output. If the `container reaches the VM at …` probe passed, connectivity
is not the problem — suspect the **model name**. For check and analyze the anonymizer
serves `claude-sonnet-5`; harbor's own defaults (`claude-sonnet-4-6`,
`claude-haiku-4-5`) are not served, and an unserved name does not come back as a clean
404. The agent retries, dies, and you pay the full wall clock before seeing the missing
file. This is check/analyze-specific — the trial reaches the model by a different route
and keeps `anthropic/claude-opus-4-8`.
