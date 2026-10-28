---
name: mmswe-runner
description: >
  Run an MM SWE Harbor task five ways — oracle, nop, a single agent trial on
  claude-opus-4-8, harbor check, and harbor analyze — and read the rewards. Use when
  the user says "run the oracle", "run nop", "run the trial", "run all three",
  "check the task", "analyze the trial", "sanity check this task", or asks whether an
  MM SWE / QH task passes. Tasks are single-container Harbor tasks whose verifier is
  unit tests -> JUnit -> reward.txt (no LLM judge), so oracle and nop run without any
  API key; the trial, check, and analyze commands use the anonymizer proxy by default
  so no real API key is ever needed.
version: 1.1.1
---

# MM SWE task runner — oracle, nop, trial, check, analyze

Validate an MM SWE Harbor task by running it on the local Docker provider:
the **oracle** (applies the golden `solution/fix.patch` — should score 1.0), the **nop**
(empty submission — should score 0.0), one **agent trial** (claude-code on
claude-opus-4-8 — the real measurement), **check** (`harbor check` for task quality),
and **analyze** (`harbor analyze` on the trial output).

## Layout

Four flat sibling folders — no per-task subfolder inside any of the run dirs. From TASK101 on
(V2) the task bundle itself sits one level down, in `Tasks/<task_id>/`:

    <ROOT>/Tasks/<task_id>/   the task (task.toml, environment/, solution/, tests/) — V2
    <ROOT>/Tasks/             the same files directly inside — V1 (before TASK101)
    <ROOT>/Trials/      agent trial output
    <ROOT>/Oracle/      oracle output
    <ROOT>/Nop/         nop output

harbor writes a job at `<-o>/<--job-name>`, so the runner passes `-o <ROOT>` and names
the job `Trials`, `Oracle`, or `Nop` — landing output exactly in that folder. Each one
holds harbor's own `config.json`, `result.json`, `job.log`, and a `<name>__<rand>/`
trial dir containing `verifier/reward.txt` — `<task_id>__<rand>` in V2, `Tasks__<rand>` in V1
(harbor names it after the task folder, cut to 32 chars).

Because the folders are fixed, **each run overwrites the previous one** for that mode.
Pass `--keep` to preserve an earlier run instead.

`ROOT` is inferred as the directory containing `Tasks/` — pointing at
`deliverables/Tasks/<task_id>` (V2) or `deliverables/Tasks` (V1) writes to
`deliverables/{Trials,Oracle,Nop}/`. Pointing at `Tasks/` itself, or at the root above it, also
works for V2: the runner descends into the single `Tasks/<task_id>/` bundle (and refuses,
listing them, if there are several). Override with `--root`. `tasks/` and `Tasks/` are both
recognized, and a legacy `project/` wrapper is still tolerated.

The task id (from `task.toml`'s `[metadata] task_id`, else the folder name) is printed
as `[mm_run] task <id>` for the log only — it no longer appears in any path.

## Credentials — trial, check, and analyze

The verifier runs unit tests and writes `reward.txt`; it never calls a model. So
**oracle and nop need no key** and the runner deliberately passes none. The **trial**,
**check**, and **analyze** modes all need credentials, resolved exactly the
ProjectBench way so a real key is never pasted into a command: **live env first, then
`~/.claude/settings.json`'s `.env`, then the anonymizer defaults**.

`harbor check` and `harbor analyze` read credentials from the shell environment, so
the runner injects them as `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` prefixes on
the command (no `--ae` flag needed).

Anonymizer defaults (the standard path):
- `ANTHROPIC_BASE_URL = http://localhost:8091` — the anonymizer proxy, Claude format
  (`:8090` is the OpenAI-format port).
- `ANTHROPIC_API_KEY = anonymizer-placeholder` — a placeholder token; CBs never handle
  a real key. It only authenticates THROUGH the anonymizer proxy.

The key is masked in all output. The **public Scale endpoint
(`https://litellm-proxy.ml.scale.com`) is not the default** — it is used only if you
explicitly export it, and the runner says so when that happens.

Because the anonymizer listens on the VM's loopback, the agent container can't reach it
by default. The runner solves this with **host networking**: it generates a small
docker-compose override putting harbor's environment service (`main`) on the host network
stack, so the container's `localhost` *is* the VM's localhost and `http://localhost:8091`
works with no address rewriting.

    services:
      main:
        network_mode: host

The file is written to a temp path, passed as `--extra-docker-compose`, and deleted on
exit. Use `--hostnet-file F` to supply your own override instead, or `--no-hostnet` to
fall back to the older **proxy bridge** (a TCP forwarder on a host-reachable gateway,
rootless-aware). If harbor's service is not named `main`, set `COMPOSE_SVC=<name>`.

The trial also passes `--ak disallowed_tools=WebSearch,WebFetch,EnterPlanMode` so the
agent can't reach the web or enter plan mode mid-trial. Disable with
`--no-disallow-tools`.

A **preflight** check confirms the resolved endpoint is reachable before spending a
trial (skip with `--no-preflight`).

## Run it

    bash mm_run.sh <task-dir> oracle     # or /run-oracle
    bash mm_run.sh <task-dir> nop        # or /run-nop
    bash mm_run.sh <task-dir> trial      # or /run-trial
    bash mm_run.sh <task-dir> check      # or /check-task
    bash mm_run.sh <task-dir> analyze    # or /analyze-trial

`<task-dir>` is the folder containing `task.toml` — `deliverables/Tasks/<task_id>` for V2 tasks
(`deliverables/Tasks` resolves to it too).

### Options

| Flag | Default | Purpose |
|------|---------|---------|
| `--model M` | `anthropic/claude-opus-4-8` | trial model |
| `--agent A` | `claude-code` | trial agent |
| `--root DIR` | dir containing the task | where Trials/Oracle/Nop are written |
| `--env E` | `docker` | harbor environment |
| `--no-preflight` | preflight on | skip the connectivity probe |
| `--no-hostnet` | host networking on | use the proxy bridge instead of the compose override |
| `--hostnet-file F` | generated | supply your own compose override |
| `--no-disallow-tools` | tools blocked | leave WebSearch/WebFetch/EnterPlanMode enabled |
| `--keep` | overwrite | keep a previous run dir instead of deleting it |

Single attempt by design — harbor's default `n_attempts` is 1, so no pass@k flags are
passed. Add `-n` only if you later want pass@k.

## Read the result

Reward comes from `verifier/reward.txt` (or `result.json` → `verifier_result.rewards`).

- **Oracle < 1.0** — the golden patch doesn't satisfy the tests: a broken `fix.patch`,
  a test asserting something the fix doesn't do, or an environment/build failure.
- **Nop > 0.0** — the verifier accepts an empty submission; the f2p tests aren't
  discriminating. Fix those before trusting any trial number.
- **Partial (e.g. 0.5)** — with this verifier shape, some but not all f2p tests passed;
  p2p failures score 0.0 outright.
