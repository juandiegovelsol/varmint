---
name: mmswe-runner
description: >
  Run an MM SWE Harbor task five ways — oracle, nop, an agent trial on
  claude-opus-5-5 (3 text-only + 4 normal attempts), a harbor check, and a post-hoc analyze — and read the results.
  Use when the user says "run the oracle", "run nop", "run the trial", "sanity check
  this task", "run harbor check", "harbor check fails", "run analyze", or asks whether
  an MM SWE / QH task passes. Tasks are single-container Harbor tasks whose verifier is
  unit tests -> JUnit -> reward.txt; oracle and nop run keyless UNLESS the task ships
  tests/rubrics.json, in which case its LLM judge needs credentials too. Trial, check
  and analyze always need credentials and go through the anonymizer proxy.
version: 1.6.1
---

# MM SWE task runner — oracle, nop, trial

Validate an MM SWE Harbor task by running it three ways on the local Docker provider:
the **oracle** (applies the golden `solution/fix.patch` — should score 1.0), the **nop**
(empty submission — every f2p must fail, every p2p must pass), and the **agent trial** (claude-code on
claude-opus-5-5 — the real measurement): 3 text-only attempts with every image stripped, which
must all fail, then 4 normal attempts, of which exactly 1 must pass.

## Layout

Flat sibling folders — no per-task subfolder inside any of the run dirs:

    <ROOT>/Tasks/       the task (task.toml, environment/, solution/, tests/)
    <ROOT>/Trials/without_images/  text-only trial output (images stripped)
    <ROOT>/Trials/with_images/     agent trial output (normal attempts)
    <ROOT>/Oracle/      oracle output
    <ROOT>/Nop/         nop output
    <ROOT>/Check/       harbor check output (rubric quality checks)
    <ROOT>/Analyze/     harbor analyze output (post-hoc trial analysis)

harbor writes a job at `<-o>/<--job-name>`, so the runner passes `-o <ROOT>` and names
the job `Oracle`, `Nop`, `Check`, or `Analyze` — landing output exactly in that folder.
The trial passes `-o <ROOT>/Trials` and names its two jobs `without_images` and
`with_images`, so neither gets a timestamped job dir. Each one
holds harbor's own `config.json`, `result.json`, `job.log`, and a `<name>__<rand>/`
trial dir containing `verifier/reward.txt`. The trial's two jobs also keep harbor's console
output as `harbor_run.log`, and run from copies of the task named `task_with_images` and
`task_without_images` (kept in `~/.cache/mm_run/trial_tasks/<task-id>/` so `analyze` can still
read them), so the attempt dirs are `task_with_images__<rand>` and `task_without_images__<rand>`.

Because the folders are fixed, **each run overwrites the previous one** for that mode.
Pass `--keep` to preserve an earlier run instead.

`ROOT` is inferred as the directory containing `Tasks/` — pointing at
`/home/sandbox/Tasks` writes to `/home/sandbox/{Trials,Oracle,Nop}/`. Override with
`--root`. `tasks/` and `Tasks/` are both recognized, and a legacy `project/` wrapper is
still tolerated.

Both task layouts work, with any task folder name:

    flat      <ROOT>/Tasks/task.toml
    nested    <ROOT>/Tasks/<any-task-name>/task.toml

Pass the task folder, `Tasks/`, or `<ROOT>` — with a single task under `Tasks/` the runner
descends into it. Several tasks there is an error (exit 2) naming them; pass the one you
mean. Trial dirs are then named `<task-folder>__<rand>`, not `Tasks__<rand>`; every reader
here and in the QC skill finds them by content, not by name.

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

### The judge has two channels, and the runner forwards both

A task's `tests/judge.py` grades in-band over whichever channel its `[verifier.env]` names,
and the two are not interchangeable:

| | Claude format | OpenAI format |
|---|---|---|
| task reads | `ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY` / `JUDGE_MODEL` | `EVAL_BASE_URL` / `EVAL_API_KEY` / `EVAL_MODEL` |
| `[verifier.env]` sources it from | the same names | `OPENAI_API_KEY` / `OPENAI_API_BASE` |
| anonymizer port | `:8091` | `:8090/v1` |
| model name | **plain** (`claude-sonnet-5`) | **proxy-qualified** (`anthropic/claude-opus-4-5-...`) |

The runner used to forward only the first, so an OpenAI-format judge worked or failed on
whether the CB's shell happened to carry `OPENAI_*`. Both are now resolved in `resolve_creds`
and exported together by `export_judge_env`, and the in-container URL is rewritten for **both**
(`resolve_eval_base` does for `EVAL_BASE_URL` what `build_agent_seal` does for
`ANTHROPIC_BASE_URL` — under host networking it passes loopback through untouched; under a seal
or `--no-hostnet` it relays through a second bridge, because the anonymizer binds both ports to
`127.0.0.1` only).

A `${VAR}` in `[verifier.env]` with no `:-` default is a **required** host var: harbor exits 1
with a bare "Missing Environment Variables" table before any container starts. `preflight_verifier_env`
now names those first, so the failure is actionable rather than a bare table arriving one line
after the runner said the creds were forwarded.

If the in-container judge still returns no verdict, `report()` grades host-side over the **same
channel and model**, and now writes `verdict.json` into the run's judge dir — so
`mm_run.sh <task> rescore --run <dir>` folds that grade into `reward.json`/`reward.txt`.
Previously the host-side verdict was printed and nothing else: it could never reach the reward,
and `rescore` (which reads `verdict.json`) had nothing to read.

Because the anonymizer listens on the VM's loopback, the agent container can't reach it
by default. The runner solves that with a **docker-compose override**. Oracle and nop get
a plain one with `TAR_OPTIONS` and host networking; the trial gets a **phase-scoped seal** (below).

`TAR_OPTIONS=--no-same-owner` matters for a reason unrelated to networking: under the
sandbox's nested-docker user namespace, GNU tar fails with "Cannot change ownership to
uid …" during extraction (e.g. flutter's gradle-wrapper fetch), which breaks the
**environment build** — so oracle and nop need it as much as the trial does.

Precedence: `--hostnet-file F` → the `tarfix.yaml` shipped beside the script → a generated
temp file (deleted on exit). If tar chown still fails, retry with `--userns-host`, which
adds `userns_mode: "host"` (only effective under userns-remap, harmless otherwise).
`--no-hostnet` falls back to the proxy bridge. If harbor's service isn't `main`, set
`COMPOSE_SVC=<name>`.

## The agent-phase seal — why the trial can't curl the answer

`network_mode: host` used to be the trial's route to the anonymizer. It worked, and it
was also a hole big enough to invalidate the measurement: the container inherited the
**VM's entire network stack**, so the agent could `pip install` the fixed package or
`curl` the upstream commit and "solve" the task without reasoning about it.

`task.toml`'s network policy did not stop this. Harbor enforces `no_network`/`allowlist`
with an egress-control sidecar, but `_egress_controlled_service_names()` in
`environments/docker/docker.py` **excludes any service that declares its own
`network_mode` or `networks`** — task-authored networking is respected by design. So the
override opted `main` out of the sidecar entirely, the policy was silently skipped, and
the sidecar still started and looked like it was working. A task declaring
`[agent] network_mode = "no-network"` got full internet.

### Why not a sealed docker network

The obvious fix is to put `main` on an `internal: true` network with a relay to the model
API. That does seal it — and it **seals the wrong window**. Harbor installs the agent
*inside* the container before the agent phase starts (`trial.py::_setup_agent` ->
`claude_code.py::install`, which curls `downloads.claude.ai`). A network sealed at compose
level is already sealed by then, so the install dies and the trial errors out as
`NetworkConnectionError` before the model is ever contacted:

    curl: (6) Could not resolve host: downloads.claude.ai
    Classified failed command as NetworkConnectionError

### What the runner does instead - phase-scoped enforcement

Harbor already models this correctly, per phase: the environment baseline
(`[environment] network_mode`, normally `public`) covers setup and agent installation, and
`[agent] network_mode` applies during `agent.run()` only. So the runner stops fighting the
sidecar and uses it:

- **The compose override declares no networking at all** — just `TAR_OPTIONS`. That keeps
  `main` inside the egress sidecar's netns, so harbor's per-phase policy actually applies
  to it. (Declaring `network_mode` or `networks` here is precisely what broke it before.)
- **The anonymizer is reached at a host address**, not loopback — the sidecar netns has its
  own loopback — via the same bridge `check`/`analyze` already use.
- **`--allow-agent-host <addr>`** merges that address into the agent-phase allowlist
  "during `agent.run()` only". Under a `no-network` or `allowlist` agent phase that
  collapses the reachable world to exactly the anonymizer.

Setup and agent install work; the moment the agent starts, the only reachable address is
the model API. `pip` and `curl` have nowhere to go.

### The model route must be HTTPS — gost kills slow plaintext turns at 15s

Moving `main` into the sidecar's netns puts **gost** in the path of the model traffic. gost
does not blindly tunnel: it *sniffs* each connection to match the allowlist, and for
plaintext HTTP it terminates the protocol and applies its own **15-second deadline to
reading the upstream response headers**. Measured on harbor's own sidecar image:

| upstream takes this long to send response headers | client sees |
|---|---|
| 5s / 10s / 14s | delivered normally (14.02s) |
| 16s / 20s / 30s | **clean EOF, zero bytes, at exactly 15.00s** |

The agent cannot tell that from a dead socket — no HTTP response ever arrives — so it logs
`API Error: Unable to connect to API (ECONNRESET)` with `error_status: null`, and every
retry dies identically for as long as the model stays slow. Streaming *bodies* are fine
(30s gaps between SSE chunks relay indefinitely), and so is a 900KB request body. It is
purely time-to-first-response-byte.

**So the bridge terminates TLS.** gost sniffs TLS as TLS, matches the allowlist by *address*
(a bare-IP target sends no SNI at all), then forwards raw TCP with no deadline — verified at
25s and 45s header latency where 16s failed in plaintext. The runner generates a self-signed
`CA:TRUE` cert covering every candidate host address as an IP SAN, mounts it into the
container via the seal override, and passes `NODE_EXTRA_CA_CERTS` so node trusts it (that
variable *adds* an anchor, so public TLS still works):

    bridge TLS cert: /tmp/mm_tls.XXXX/anonymizer-ca.crt (SAN IP:10.0.2.2,...)
    host bridge: 0.0.0.0:33723 -> localhost:8091 (TLS terminated at the bridge)
    in-container ANTHROPIC_BASE_URL=https://10.0.2.2:33723
    agent trusts the bridge cert via NODE_EXTRA_CA_CERTS=/etc/mm-anonymizer-ca.crt

Nothing hit this before the seal because the trial used host networking, and nothing hits it
in a real deployment because a real base URL is already `https`. It needs a **plaintext
loopback** proxy behind the sidecar. `--no-tls-bridge` restores plaintext for diagnostics.

`Trials/with_images/bridge.log` (and `without_images/bridge.log`) records every connection with byte counts, a close reason and the
time-to-first-upstream-byte, flagging any turn that would have died on the plaintext path.
A `TLS handshake failed ... (normal for a plain-TCP reachability probe)` line at startup is
the runner's own probe and is expected.

### Scope - this only bites when the task asks for it

Enforcement is harbor's, so it depends on `task.toml`. A task whose agent phase is `public`
or unset gets **no egress control at all** — harbor skips the sidecar entirely
(`_requires_egress_control`) and warns that extra allowlist hosts are ignored. That is the
correct semantics: `task.toml` is now honoured instead of silently overridden, which was
the original bug. The runner prints which case applies rather than implying a seal that
is not there:

    task.toml [agent] network_mode = 'no-network' -> harbor WILL enforce the agent phase
    WARNING: task.toml declares no [agent] network_mode, ... The trial is NOT sealed

Other things to know:

- **The allowlist is host-granular, and that is a real residual hole — including the host's
  LOOPBACK.** Allowlisting the address the agent needs for the anonymizer also exposes *every
  other port reachable at that address*. Measured from inside a sealed netns with `10.0.2.2`
  allowlisted: this sandbox's ttyd web terminal (`:8080`), a service on `:3000` and **sshd on
  `:22`** all answered, while `pypi.org` and off-allowlist raw IPs stayed blocked.

  Under **rootless docker with slirp4netns** it is worse than "that host's public ports":
  slirp4netns maps its gateway address `10.0.2.2` onto the host's **127.0.0.1**, so
  loopback-only services are reachable too. Verified both ways — `10.0.2.2:8091` returns real
  anonymizer bytes from inside a container while the *host itself* gets `ConnectionRefused`
  for the same address, and the listener is bound to `127.0.0.1` alone. So allowlisting that
  address hands the sealed container the host's entire loopback. `slirp4netns
  --disable-host-loopback` would close it, but that is the daemon's configuration, not
  something the runner can set per run.

  A useful corollary: because of that mapping the container can dial `http://10.0.2.2:8091`
  directly, so **the bridge is not required for reachability here** — its job in the sealed
  build is TLS termination (see above). Do not rely on the mapping in general: it is specific
  to slirp4netns's default and absent under pasta or rootful docker, which is why
  `resolve_host_addr` probes rather than assumes. A web terminal or an
  SSH login on the host is a far bigger cheat vector than pypi, so treat a "sealed" reward as
  sealed against *package registries and upstream git*, not against a VM that runs other
  listeners. Don't run trials on a VM exposing a shell service on its route-source IP.

  gost itself would fix this — its bypass file accepts `10.0.2.2:18080` and correctly blocks
  `:8080`/`:3000` when given one (measured). The blocker is upstream of it: harbor's
  `normalize_allowed_hosts` rejects any entry containing a port
  ("must be hostnames, IP addresses, or IP CIDR ranges, not URLs, ports, or paths"), so the
  runner cannot pass one. Narrowing the seal to the single bridge port needs that validator
  to allow `host:port` and to forward it through to the allowlist file.
- **The verifier phase has no equivalent flag.** Only `--allow-agent-host` and
  `--allow-environment-host` exist. If a task sets `[verifier] network_mode = "no-network"`
  *and* ships a rubric, the in-container judge cannot reach the model and the runner's
  host-side fallback (`mm_grade_rubrics.py`) grades instead. Expected, not a bug.
- The **environment build is unaffected** either way — it runs before any policy applies,
  so `apt`/`pip` in the Dockerfile still work.
- `--isolate-all` keeps oracle/nop inside the sidecar too, so their verifier policy is
  enforced. Off by default: neither runs an agent, so neither can cheat.
- `--no-isolate`, `--no-hostnet` and `--hostnet-file` all restore `network_mode: host` and
  disable enforcement. Any reward from such a run should be treated as unverified.

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

The file-name gate is check-only; `oracle`, `nop`, `trial`, and `analyze` do not run it.
They have gates of their own — see **the bundle digest gate** and **controls before a
trial** below.

### check runs a metadata gate second

`mm_check_integrity.py` follows the file-name gate and exits 2 on any failure. Names are cheap
to verify; so is whether the files **agree with each other**, and that is what this catches: a
`task.toml` `base_commit` the Dockerfile never checks out, a `files_edited` entry the golden
patch never touches, `f2p`/`p2p` disagreeing with `tests/config.json`, a poster the documents
promise at a path nothing copies to. Pure stdlib, no docker, no network, sub-second. 19 checks,
each reporting `PASS` / `FAIL` / `SKIP` independently — `SKIP` never affects the exit code.

Two of them grade the evidence documents themselves:

- **`evidence-schema-shape`** — `ASSET_MANIFEST.json` and `evidence_bundle.json` must each be a
  JSON **array** of poster objects with every required key non-empty (`file`/`role`/
  `container_path`; `role`/`local_path`/`description`). `url` (the poster's source link) is
  part of the shape but its value is optional: `""` when there is no link, and an empty or
  missing one is not a finding. `--fix` always writes the key, blank when no link is found. On failure it prints the golden
  format verbatim, then a **dry-run** conversion showing exactly what it would write and which
  keys it would drop. `--fix` applies it. `description` is written **blank**, never invented —
  only a human who has looked at the poster can write it. If something drafts it for you,
  prefix the text `DRAFT:` and the check keeps failing until a human clears the prefix.
- **`asset-entries-unique`** — no two entries in one document may name the same poster. Both
  documents are indexed by poster name downstream, so a repeat silently discards all but the
  last, and two entries disagreeing about one poster would otherwise pass unnoticed.
- **`assets-images-only`** — the Dockerfile must not ship `ASSET_MANIFEST.json` into the
  container. It names every poster's role, so it tells the agent what each image shows before it
  has looked — and a whole-directory `COPY assets/` (or `COPY .`) ships it silently. **Auto-fix
  (dry run, `--fix` writes):** the offending COPY/ADD source becomes image globs —
  `assets/*.png`, `assets/*.jpg`, … one per image extension actually present, case kept — plus
  any non-image evidence the documents list, by name; flags, JSON form and destination are kept,
  every other line is untouched, and a COPY that shipped only the manifest is removed. It
  declines `COPY .` (narrowing the whole context changes what else lands), posters in subfolders
  (a glob would flatten them) and `--from=` copies, and says so. Non-image files
  may ship only when the evidence documents list them (e.g. an audit `.json`); an undocumented
  one fails. Decided from the Dockerfile and the directory, so it runs even when the shape check
  fails — then only the manifest half is judged.

When the shape check fails, every check that reads those documents reports **SKIP**, not PASS —
a gate that reports a pass for a document it could not parse is worse than one with no such
check. Three others still answer from disk and keep running.

`--no-integrity-check` runs `harbor check` regardless.

A **third** pre-flight follows it: the MM SWE QC audit (`fix.py qc --phase bundle`), resolved via
`$MM_QC_FIX` -> `~/.claude/skills/mm-swe-qc-fix-sandbox/fix.py` -> the copy beside this runner. It
is read-only and calls no runner, so there is no recursion. It passes `--gate-tier bundle`, which
shows the CB **every** finding at the phase on disk while letting only bundle-tier FAILs stop
the run — `harbor check` grades the TASK, not the runs, so a stale Oracle is shown and does not
cost the run. A `GATE SCOPE:` line states how many were blocking versus shown-only.

On bundle FAILs it **asks** rather than deciding — the choice to pay for a run anyway is the
user's. With a terminal it prompts `[y/N]`. Without one (an agent, CI) it exits **7**, meaning
"findings above, ask the user and re-run with `--no-qc`" — it never guesses. `--no-qc` skips the
gate. If the QC skill is absent it says the gate was SKIPPED, not passed.

Whether a check run gets spent, by outcome:

| Outcome | run spent |
|---|---|
| audit clean | yes |
| finding(s) awaiting adjudication / exit 9 | no — rule on them, then re-run |
| nothing blocking, but no pass could be recorded | yes — warned loudly, oracle/nop still blocked |
| bundle FAILs, CB answers `y` | yes — the findings still stand |
| bundle FAILs, CB declines / exit 7 | no |
| `--no-qc` | yes — gate skipped, which is not the same as passed |
| QC skill not found | yes — reported as SKIPPED, not passed |

**Exit 9 is not a failure**, and it is not a quieter exit 7. The audit found no blockers but left a
`PENDING` finding that needs a code read to decide (`fix.py` exits 3; the gate maps it to 9). No run
is spent, because the correct action is cheap — adjudicate and re-run — and unlike exit 7 there is
deliberately no `y` override: proceeding would spend the run AND still record no QC pass, leaving
oracle/nop blocked by the digest gate below. See `/run-check` for how to rule.

`--no-file-check` skips the required-files pre-flight and runs `harbor check` regardless.

A clean audit writes **`/tmp/qc_check.md`** (`$MM_QC_MARKER`), and that file now carries a
content digest of the bundle it passed — see the next section.

### the bundle digest gate (oracle / nop)

`qc_check.md` records the task dir it audited plus two digests: harbor's own
`Packager.compute_content_hash` (the value harbor writes into every run's `lock.json`, so it
is directly comparable with any control) and an `extra-digest` covering everything harbor's
hash does not reach — `evidence_bundle.json` above all, which sits at the task root and is in
none of harbor's collected paths.

`oracle` and `nop` compare the bundle in front of them against that record and run **only on
an exact match**. There is no bypass flag.

| state | result |
|---|---|
| digest matches | runs, silently |
| bundle edited since the audit | **exit 2**, naming the changed files |
| no marker at all | **exit 2** |
| marker records a different task | **exit 2** |
| last check found blockers (marker deleted) | **exit 2** |
| harbor unreachable | runs, and says which half went unchecked |
| QC skill or `qc_digest.py` missing | runs, `WARNING … unverified` |

The last two are "the check itself is unavailable", never "the bundle looks fine". Since there
is no bypass, failing them would ground oracle and nop with no way back — the same reasoning
the trial's own digest check already applies to an uncomputable digest.

Every blocking message ends with the same instruction: run `/run-check` so a fresh audit covers
the current files. **A marker is not deleted by any run**; it stops being valid exactly when the
bundle it describes changes, which is what the digest is for.

The comparison lives in `qc_digest.py`, shipped beside `fix.py` in the QC skill so the writer
and the reader can never disagree about the algorithm. It is also usable directly:

    python3 ~/.claude/skills/mm-swe-qc-fix-sandbox/qc_digest.py <task-dir> --compare <marker>
    # exit 0 match, 3 mismatch (naming each changed/added/removed path), 4 nothing recorded

Two things to know about their output:

- Neither produces a `reward.txt` — they are rubric judges. The runner reads
  `Check/check_report.json` and `Analyze/analysis.json` and prints one line per
  criterion plus a tally and cost.
- **`analyze` writes back into what it analyzes**: harbor drops an `analysis.json`
  into each analyzed trial dir. A later `trial` run without `--keep` deletes
  `<ROOT>/Trials` (both phases) wholesale and takes those with it. The runner warns when this
  applies.

`analyze` takes a **trial dir, a job dir, or a task dir**. Given a task dir it analyzes
`<ROOT>/Trials/with_images` — so you can keep passing the task dir everywhere. Job dirs and trial
dirs both carry a top-level `result.json`, so they are told apart by whether a *child*
dir holds one; `<ROOT>` always ends up the dir that holds the job dir, never the job
dir itself.

## Run it

    bash mm_run.sh <task-dir> oracle     # or /run-oracle
    bash mm_run.sh <task-dir> nop        # or /run-nop
    bash mm_run.sh <task-dir> trial      # or /run-trial
    bash mm_run.sh <task-dir> analyze    # or /run-analyze  (analyzes <ROOT>/Trials/with_images)

    /run-check                           # check is CHAT-ONLY — see below

**`check` is not directly invocable.** `bash mm_run.sh <task-dir> check` exits **8** and runs
nothing; use `/run-check` in Claude Code chat. It is the one mode whose result a CB cannot act on
alone — it spends credentials and returns a task-quality rubric plus a QC audit that has to be read
back worst-finding-first, with a decision about whether to spend another run. `/run-check` carries
those instructions and passes the `MM_VIA=run-check` token the guard looks for; a bare shell has
nobody to give them.

`MM_ALLOW_DIRECT=1` invokes it directly anyway, for CI and scripted runs. The guard is a workflow
preference, not a security boundary — it makes the supported path the easy one and the bypass
deliberate. The other four modes are unaffected: `oracle` and `nop` in particular are keyless and
are the loop you run while repairing a task, which is where friction would cost the most.

**`trial` requires both controls first.** `bash mm_run.sh <task-dir> trial` exits **9** and runs
nothing — no model, no credentials — unless the task's two controls are already green on disk:

| Control | Required reward | Read from |
|---------|-----------------|-----------|
| `oracle` | exactly `1` | `<ROOT>/Oracle` |
| `nop` | exactly `0` | `<ROOT>/Nop` |

A trial's reward is uninterpretable without them: a 0 cannot be told apart from a broken task, and a
1 might be a task that scores 1 for doing nothing. The error names each control, what it scored, and
the exact command to run — and satisfying it means nothing more than running those two commands,
since they write the very dirs the gate reads. Missing, unreadable, disagreeing (`mixed`, when
attempts inside one control dir don't match), or simply wrong all fail the same way. A control that
scores wrong is a task to fix, not a gate to force: an oracle below 1 means the golden patch does not
pass its own tests, and a nop above 0 means the tests pass without the fix.

It is **also** a staleness check, so a green control is not enough on its own — it has to be green
*for this bundle*. Every harbor run records `trials[].task.digest` in its `lock.json`, and that value
is `sha256` over the sorted `relpath\0sha256(bytes)` of `task.toml`, `instruction.md`, `README.md` and
everything under `environment/`, `tests/`, `solution/` and `steps/`. **Content only** — no mtimes, no
run id, no timestamp — so it is stable across runs of an unchanged bundle and changes if and only if
one of those files changes. The gate recomputes it for the task dir and refuses a trial whose control
digests disagree, naming which control is stale and printing only the re-run commands that are
actually needed.

Two consequences worth knowing. `evidence_bundle.json` is **outside** the digest, so editing the
evidence documents alone cannot make a control stale — correctly, since it cannot change a reward
(use the QC audit for those files). And if the digest cannot be computed — no importable harbor, or a
task shipping its own `.gitignore` that the stdlib fallback declines to imitate — the gate says
`staleness NOT checked` and proceeds on the reward result alone, rather than grounding every trial
over a check that is an addition to the reward gate, not a replacement for it.

`MM_ALLOW_UNVERIFIED=1` skips the whole gate, rewards and digests alike, for CI and for sweeps whose
controls were collected elsewhere.

### after a trial: the hardening verdict

A trial measures whether the **agent** can solve the task, so `reward 0` is the wanted result: the
agent failed, and the task discriminates. A non-zero reward means the model solved it, and a task a
model already solves says nothing about the model being measured.

The record is cleared the moment a trial launches — after every gate has passed, immediately before
harbor starts — so it always describes the most recent trial and exists only because that trial
wrote it. A crash, a timeout, or a run that writes no reward therefore leaves nothing behind
claiming a result.

A trial is **two runs**, and both must hold. The rules live in one place — `trial_rule()`,
`text_only_rule()` and the `TRIAL_MIN_SOLVED` / `TRIAL_MAX_SOLVED` variables in `mm_run.sh` — and
both the post-trial verdict and the reviewer path (`check-reviewers`) decide from them, so they
cannot disagree about one bundle.

**Phase 1 — text-only** (`--n_text_only=N`, default 3) → `<ROOT>/Trials/without_images/`. The runner
copies the task and strips every image from it (`build_text_only_copy`): inline, reference-style
and `<img>` images in `instruction.md`; every image source (path, glob or URL) in the Dockerfile's
`COPY`/`ADD` instructions, including ones continued over several lines — an instruction keeps its
other sources, and goes only when none are left; and every image file under `environment/`
(otherwise the agent could `ls /app/.harbor_assets` and open it anyway). Prose and non-image
evidence (logs, text dumps) are kept. A `RUN` line that downloads an image is refused (rc 4). **Every text-only attempt must fail** — the image is really
needed. One solve ends the trial unrecorded and the normal phase is **skipped**, saving its cost.
A task with nothing to strip is refused before anything is spent. The strip is deterministic, so
the reviewer path rebuilds the copy and checks the text-only run's digest against it.

**Phase 2 — normal** (`--n_trial=N`, default 4) → `<ROOT>/Trials/with_images/`, on the real bundle:

| text-only | normal (4) | `/tmp/qc_trial.md` (`$MM_QC_TRIAL_MARKER`) | printed |
|---|---|---|---|
| any solved (breaker stops the phase at the first) | not run | none | `TRIAL FAILED` — the image is not needed; move what the fix depends on into it |
| missing, or stale (digest ≠ stripped bundle now) | not checked | none | `trial NOT RECORDED — the text-only half does not hold` |
| 0 of 3 | **0 of 4** | none | not recorded, and **`check-reviewers` refuses the bundle** — RL needs a passing attempt |
| 0 of 3 | **1 of 4** | written, with both distributions and the text-only digest | `TRIAL PASSED` — **ready to deliver** |
| 0 of 3 | **2–3 of 4** (breaker stops the phase at the 2nd solve) | none | **delivery blocked**; the task must be hardened |
| 0 of 3 | **all finished attempts** (4 of 4, or e.g. 2 of 2 when the breaker stops it) | none | `THE MODEL PASSED THE TRIAL` + must be hardened |
| unreadable / absent | | none | no verdict — "cannot tell" is not "the task held" |

**Every attempt must produce a reward.** A crashed attempt writes none and drops out of the
tally, so a phase with fewer rewards than `--n_text_only` / `--n_trial` is **incomplete** and not
recorded — "1 of 3" is not "1 of 4". A solve still decides early: one text-only solve fails the
trial, and 2+ normal solves block it, whatever is missing.

**Circuit breaker.** Attempts run concurrently, so each phase is watched while harbor runs
(`harbor_breaker` / `breaker_watch`). Once enough solves are in to decide the phase, the runner sends
harbor SIGTERM. Harbor then cancels the attempts still running (they get no reward) and tears down
their environments, so nobody pays for attempts that can't change the verdict:

| phase | trips at | why |
|---|---|---|
| text-only (pass@3) | **1 solve** | `text_only_rule`: any solve fails the trial |
| normal (pass@4) | **`TRIAL_MAX_SOLVED + 1` solves** (2 today) | `trial_rule`: above the band, delivery blocked |

Both limits come from the rules, so moving the band moves the breaker. A tripped phase reads like
an early decision: `CIRCUIT BREAKER — …` is printed, the tally covers only the finished attempts
(e.g. `pass@3: 2/3`), and the "incomplete" rule doesn't apply, because no missing attempt could
undo the result. Nothing is ever recorded from a tripped phase. Harbor 0.18 exits on SIGTERM
before its own `docker compose down` finishes, so after a trip `breaker_reap` removes the job's
leftover attempt containers, networks and volumes. It only touches compose projects named after
attempt dirs in that job, and it keeps images so the next phase still has its build cache. If harbor is still running
`MM_BREAKER_GRACE` seconds (default 600) after SIGTERM, it gets SIGKILL and a warning to check
`docker ps`. The poll interval is `MM_BREAKER_POLL` (default 15s). `--no-circuit-breaker` runs every
attempt to completion, e.g. to see the full distribution.

The allowed band is `TRIAL_MIN_SOLVED..TRIAL_MAX_SOLVED` — 1..1 today, i.e. exactly 1 of 4. Change
those two variables to move it; every message quotes the band from them.

`MM_FORCE_TRIAL_RECORD=1` overrides the normal half only (never the text-only half) and still
writes the real result with a `forced: true` line. The record carries `attempts:` / `failed:` /
`pass@N:` / `allowed:` / `text_only_attempts:` / `text_only_digest:`.

**Pseudo-trials** replay one submission, so they are incomplete by the rule above and never
write a trial record; they still report the replayed reward. Only `/run-trial` records.

**Tests:** `~/trial_tests/run_tests.sh` exercises all of this with a fake `harbor` (no model
calls) — the strip on sample tasks (with docker builds), the trial end to end, the reviewer path
and pseudo-trials.

`qc_trial.md` uses the same shape as `qc_check.md` — task dir plus both digests — so the same
`qc_digest.py --compare` reads either. That matters: a record that merely said "a trial passed
once" would survive every later edit and vouch for files the trial never saw. If `qc_digest.py`
cannot be found, nothing is written and the runner says so, because an unverifiable record is
worse than none.

Between them the two files state, checkably and about one specific bundle: **an audit passed
it**, and **a trial failed to solve it**.

`<task-dir>` is the folder containing `task.toml` (e.g. `QH/Tasks/6a68f9fb…`).
`analyze` also accepts a job or trial dir directly:

    bash mm_run.sh <ROOT>/Trials/with_images analyze
    bash mm_run.sh <ROOT>/Trials/with_images/Tasks__vp2kgTM analyze

### Options

| Flag | Default | Purpose |
|------|---------|---------|
| `--model M` | `anthropic/claude-opus-5-5` | trial model |
| `--check-model M` | `claude-sonnet-5` | check model — the name the anonymizer serves, not harbor's own default |
| `--analyze-model M` | `claude-sonnet-5` | analyze model — the name the anonymizer serves, not harbor's own default |
| `--rubric F` | harbor built-in | rubric file for check/analyze |
| `--check-prompt F` | harbor built-in | evaluator prompt for check/analyze |
| `--passing` / `--failing` | all trials | analyze only passing / only failing trials |
| `-l N` | all trials | analyze at most N trials |
| `--agent A` | `claude-code` | trial agent |
| `--root DIR` | dir containing the task | where Trials/Oracle/Nop are written |
| `--env E` | `docker` | harbor environment |
| `--no-preflight` | preflight on | skip the connectivity probe |
| `--no-file-check` | gate on | run harbor check even if required task files are missing |
| `--no-isolate` | seal on | **dangerous** — restore `network_mode: host`; agent gets the VM's full stack |
| `--isolate-all` | trial only | seal oracle/nop too (proves the task needs no run-time network) |
| `--no-hostnet` | override on | use the proxy bridge instead of the compose override (also unseals) |
| `--no-tls-bridge` | TLS on | **dangerous on a sealed run** — plaintext to the bridge, so gost kills any turn needing >15s for response headers (ECONNRESET, no HTTP status) |
| `--userns-host` | off | add `userns_mode: host` (retry aid for tar chown) |
| `--hostnet-file F` | generated | supply your own compose override |
| `--no-disallow-tools` | tools blocked | leave WebSearch/WebFetch/EnterPlanMode enabled |
| `--n_text_only=N` | `3` | **trial only**: text-only attempts on the image-stripped copy, run first. All must fail; one solve skips the normal phase. Minimum 1 — the phase cannot be switched off |
| `--n_trial=N` | `4` | **trial only**: normal attempts (pass@k → harbor `-k`), run up to `--n-concurrent` (harbor default 4) at a time. Each attempt is a full agent run, so N× the spend. Recorded only when the solves are in the band (exactly 1 today) and every text-only attempt failed — see the trial-record table above. Not to be confused with `-l`/`--n-trials`, which limits how many trials *analyze* reads |
| `--no-circuit-breaker` | off | **trial only**: run every attempt to completion. By default each phase is stopped once its verdict is decided (1 text-only solve, or `TRIAL_MAX_SOLVED+1` normal solves) — see "Circuit breaker" above |
| `--keep` | overwrite | keep a previous run dir instead of deleting it |

For each phase the runner prints **every** attempt's reward plus a `pass@N: k/N` tally, because a
single blended number would describe one attempt as if it were the run. Under the tally it names
the band the distribution falls in — inside, below or above — from the same `trial_rule()` /
`text_only_rule()` that decide the record, so the tally and the verdict below it never say
different things. 0 of 3 text-only + 1 of 4 normal is a **pass**: report it as ready to deliver,
not as an open question.

## Rubrics / LLM judge (optional)

If the task ships `tests/rubrics.json`, the runner treats it as having an LLM judge and
changes three things:

- **Credentials go to every mode, not just the trial.** The judge runs in the *verifier*
  phase, so oracle and nop need them too. The runner exports `ANTHROPIC_BASE_URL`,
  `ANTHROPIC_API_KEY` and `JUDGE_MODEL` into harbor's own environment, which is what
  `task.toml`'s `[verifier.env]` `${VAR:-}` entries expand from. With no rubrics file,
  oracle and nop stay strictly keyless as before.
- **`JUDGE_MODEL` defaults to `claude-sonnet-5`** — a *plain* name, which is what the
  anonymizer expects (not `anthropic/...`).
- **Rewards are reported per key, with per-test detail.** `reward=… tests_passed=… f2p=2/3
  rubric=pass|fail`, then each f2p/p2p test's own PASS/FAIL. A single test is binary, so an
  aggregate cannot show WHICH test passed — and the key QC question is "did this specific
  f2p test pass on the nop run?"

**Host-side fallback.** If the rubric verdict is missing while tests passed, the judge
probably never ran. The runner then grades the same rubric on the host with
`mm_grade_rubrics.py` (stdlib urllib, binary and unweighted — the rubric passes only if every
criterion passes) and prints the verdict. It grades the **candidate diff** with test/harness files
excluded, so it never scores the suite the agent may have edited.

Because the verifier shares the `main` container, it reaches the judge the same way the
agent does: on a sealed trial that is `https://<host-addr>:<bridge-port>` through the TLS
bridge, and on oracle/nop (unsealed by default) it is `http://localhost:8091` via host
networking. Either way the runner exports the value, so `[verifier.env]`'s
`${ANTHROPIC_BASE_URL:-}` expands correctly.

Two caveats for the in-container judge, both of which make `rubric_graded: 0` expected
rather than surprising:

- a task that declares **no `[verifier.env]` block at all** never receives the credentials,
  no matter what the runner exports — the judge has nothing to authenticate with;
- `[verifier] network_mode = "no-network"` blocks it regardless, and there is no
  `--allow-verifier-host` to open a hole. Python-based judges would also need the bridge CA
  (`SSL_CERT_FILE`), which the runner does **not** set, because that variable *replaces* the
  trust bundle and would break any other TLS the verifier does.

In all three cases the host-side fallback grades instead, which is the supported path.


**Not the same as `check`.** `harbor check` grades **the task** (is this well-built?);
this rubric grades **the submission** (was this a legitimate fix?). They are complementary.

## Read the result

Reward comes from `verifier/reward.txt` (or `result.json` → `verifier_result.rewards`).

- **Oracle < 1.0** — the golden patch doesn't satisfy the tests: a broken `fix.patch`,
  a test asserting something the fix doesn't do, or an environment/build failure.
- **Nop: an f2p test PASSES** — that test cannot detect the bug, so the task grades
  nothing real. The reward will not show this: `reward` is 0.0 whenever *any* f2p fails,
  so a 0.0 nop can still hide an inert test. The runner judges nop on the four count keys
  in `Nop/Tasks__*/verifier/reward.json` and prints the verdict on its `nop:` line.
- **Nop: a p2p test FAILS** — it is mislabeled; it is really f2p. Move it in
  `tests/config.json` (and task.toml) rather than deleting it.
  Either way, fix the tests before trusting any trial number — `trial` refuses to start
  until nop shows every f2p failing and every p2p passing.
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
and keeps `anthropic/claude-opus-5-5`.
