---
name: mm-swe-qc-fix-sandbox
description: >
  QC and repair an MM SWE task from inside the sandbox, with no API key. Runs the five static
  checks and reports findings grouped by the six QC dimensions. Rubric FORMAT defects (an
  all-pass stub rubric, a half-wired rubric layer, a non-canonical reward.json) are BLOCKING
  and must be fixed. Works BEFORE the trial: anything
  needing artifacts that do not exist yet is reported as OPEN, never as a failure. Proposes fixes
  as a DRY RUN and changes nothing without explicit approval (--apply for writes, --run for the
  oracle/nop docker runs), then reproduces the gate through the MM SWE runner. Use when a CB says
  "QC this task", "fix this task", "check my task before submitting", "run the QC checks", or
  hands over a task folder in the sandbox. Never runs the trial.
version: 2.2.2
---

# MM SWE QC FIX — sandbox

For CBs working in the sandbox. Same checks and fixes as the local skill, wired to the run
commands you already use.

```bash
FIX=~/.claude/skills/mm-swe-qc-fix-sandbox/fix.py

python3 $FIX qc   /home/sandbox/Tasks                  # THE COMPLETE AUDIT, no edits
python3 $FIX auto /home/sandbox/Tasks                  # same audit + how to authorize
python3 $FIX auto /home/sandbox/Tasks --apply          # ...and now actually fix
python3 $FIX auto /home/sandbox/Tasks --apply --run    # ...and reproduce the gate too
python3 $FIX verify /home/sandbox/Tasks --run          # gate only: oracle 1.0, nop all-f2p-fail
```

## Folder layout — flat or nested, any task name

Both layouts work, and nothing depends on the task folder's name:

    flat      /home/sandbox/Tasks/task.toml
    nested    /home/sandbox/Tasks/<any-task-name>/task.toml

Point at the root, at `Tasks/`, or at the task folder itself — all three resolve to the same task.
The run folders (`Oracle/`, `Nop/`, `Trials/`) are always siblings of `Tasks/`, and their trial dirs
are found by content (a `verifier/` dir or `trial.log`), never by a `Tasks__*` name — so a nested
task's `<task-name>__<rand>` trials and a timestamped job dir (`Oracle/<timestamp>/<trial>/`) are
both read. `Trials/` holds the trial's two phases, `with_images/` and `without_images/`; the
checks read `Trials/with_images/` as the trial run (a `Trials/` without that split is read as is). If `Tasks/` holds several tasks the skill stops with exit 2 and names them; pass the one
you mean. The single source of this rule is `checks/qc_layout.py`; `mm_run.sh` applies the same
rule.

## One audit, not two

`qc` and a bare `auto` print the **same** report: every finding from the five checks **and** the
live repair plan, joined on finding id. `PROPOSED FIXES` is the authoritative preview of what
`--apply` would touch — not a guess.

These used to be separate commands, which meant neither was complete. `qc` never mentioned five of
the fixes at all (`debris`, `empty_noncanon`, `stray_files`, `unused_assets`,
`asset_not_in_instruction` are detected only by `fix.py`'s own detectors), and its `action:` column came from a static hint table rather than a fix
proven to apply to this bundle. Both commands are read-only, so the split bought nothing.

The join lives in `fix.py`, which drives `checks/` and never the reverse — so the five checks stay
standalone. `FIX_ID_ALIASES` in `qc_common.py` is the single place the two vocabularies meet; a
missing entry degrades gracefully (the finding keeps its hint instead of a live action).

## Nothing changes without you saying so

Two actions cost something, so each is authorized separately and **neither happens by default**:

| Flag | Authorizes |
|---|---|
| `--apply` | writes to `Tasks/` — create, delete, rewrite inside the bundle |
| `--run` | the oracle+nop docker runs (`$MM_RUN_TIMEOUT`, default 5400s) |

**Naming a fix is itself the approval.** `apply --approve judge_drift` identifies exactly what will
change, so it needs nothing more. A blanket selection identifies nothing, so `--approve-all-auto`
— and `auto`, which uses it — additionally needs `--apply`.

That `--apply` also covers the **agent repairs** (see below): they are part of the same "fix this
task" decision, not a separate one. What `--apply` never covers is a **deletion** or the **mode
choice** — those keep their own question.

`auto` used to apply every AUTO fix unprompted and then start docker. The snapshot and rollback
made that recoverable, but **recovery is not consent**: by the time they help, the files have
already changed.

Withholding `--run` never turns into a pass. The gate is reported as unproven (exit 5), because
"we did not check" must not be able to read as "it holds".

Exit codes: **0** everything asked for succeeded · **2** no `task.toml` · **3** layout violation,
rolled back · **4** gate broken after fixing · **5** applied but NOT VERIFIED · **6** dry run,
nothing changed. Point them at the folder holding `Tasks/`, or at `Tasks/` itself.

## It runs before the trial

Pre-trial is the normal case, so QC never depends on the trial. Each check declares the tier of
artifact it needs, and anything unavailable is reported as `OPEN [needs …]` — never as a failure,
and never affecting the exit code:

    bundle      Tasks/ only              free                  <- the default
    gate        + Oracle/ + Nop/         keyless, docker only
    trial       + Trials/                a real model call
    submission  + the four .tar.gz       packaging time

The verdict line always states what was skipped:

    VERDICT   BUNDLE: FAIL (2)  ·  GATE: not reproduced  ·  TRIAL: n/a (pre-trial)

## Can the harness still run in the image? (group E, BLOCKING)

Anti-cheat written into `environment/Dockerfile` can remove the things **harbor itself** needs, and
the gate cannot see it:

```
NonZeroAgentExitCodeError: Command failed (exit 127): ... curl -fsSL https://downloads.claude.ai/... | bash
stderr: bash: line 1: curl: command not found
```

harbor installs the agent CLI **into the task image** — over `curl` on glibc bases, over
`npm install -g @anthropic-ai/claude-code` on apk ones — diffs the candidate with `git`, and spawns
every phase under `bash`. An `rm -f /usr/bin/curl` deletes the only install path there is. **Oracle
and nop install no agent**, so they still score 1.0/0.0 on an image no agent can run in; `harbor
check` reads the bundle, not the built image; the build itself succeeds. The first observation is
the trial — the one step that costs a real model call. So group E hard-FAILs and marks itself
blocking, and it grades the whole class, not just curl:

| | |
|---|---|
| removes/masks `curl` `wget` `git` `bash` `node` `npm` | FAIL — `rm`, `apt-get purge`, `apk del`, `chmod 000`, `mv` |
| never *installs* a fetcher on a minimal base | FAIL — missing and deleted fail identically |
| BuildKit-only syntax: `COPY <<EOF` heredoc, `RUN --mount`, `COPY --link/--parents`, `ADD --checksum` | FAIL — the build dies on a builder without it, before any layer exists |
| `# syntax=docker/dockerfile:X` | FAIL — fetches a parser from docker.io before instruction one, against a floating tag |
| a `COPY`/`ADD` source that does not resolve under `environment/` | FAIL — `not found in build context` |
| npm registry → `127.0.0.1` / unroutable | FAIL **only where a consumer exists** — the apk install path, or an install in `tests/` |
| apk base with no `apk add bash` | FAIL — busybox ash is not bash |
| writes `/etc/hosts` from a `RUN` | FAIL — see below; the harness hosts it meant to blackhole ride along as evidence |

**Group E emits FAILs or nothing.** It is entitled to report only what nothing downstream catches —
the same bar `check_N` sets, and the reason `[environment]` is not graded at all ("a wrong value
there fails the build loudly and the oracle catches it"). Three findings were cut for failing that
bar, and the reasoning is in the source so they do not get re-added:

- **a swallowed `npm install`** — if deps do not resolve the runner cannot run and the **oracle
  reports 0.0**, loudly, pre-trial. Against a 1.0 oracle the finding is not just noise, it is wrong:
  a green oracle is positive proof the deps resolved.
- **`|| true` on a long chain** — real, but it is the *mechanism* a defect hides behind, not a defect.
  The only thing it hides here is already reported, in the same breath, by `env_hosts_build_write`.
- **"confirm no test-time `npm install` needs the registry"** — the bundle answers that. `test.sh`
  and `verifier.py` either invoke a registry-touching install or they do not, so the check reads them
  and decides. A check that can find the answer and asks the reviewer instead is spending their
  attention to save its own effort.

That last point generalizes: a group whose findings are mostly hedges gets skimmed, and the skimming
costs the FAILs sitting next to them. `rm -rf /app/.git` is likewise **not** a finding — every MM SWE
task must strip it, and a check that FAILs it is worse than no check.

### The heredoc trap — a build that only works on the author's builder

```
# syntax=docker/dockerfile:1.4
COPY <<'PYEOF' /tmp/obfuscate_harbor.py
```

A heredoc `COPY` does not copy a file, it **creates** one from the inline body — a *frontend*
feature, not core docker. Where the frontend lacks it, `COPY` falls back to its ordinary meaning,
`<<'PYEOF'` is read as a source path, and the build dies before any layer exists:

```
Step 2/3 : COPY <<'PYEOF' /tmp/obfuscate_harbor.py
COPY failed: no source files were specified          # DOCKER_BUILDKIT=0, docker 29.6
```

That is the "**it could not find that file**" symptom, and the usual reading of it is wrong: nothing
was mislocated. **The file never existed** — the instruction meant to create it was not understood.
Fixing a path fixes nothing.

`# syntax=` is a second, independent defect and not the cure. Measured: BuildKit does `resolve image
config for docker-image://docker.io/docker/dockerfile:1.4` **before instruction one** — a build-time
Docker Hub dependency (proxy, rate limit, air-gapped builder, pinned mirror) against a **floating
tag**, so the parser can change under a task whose purpose is reproducibility. Meanwhile the classic
builder *ignores* the directive, so it cannot rescue the heredoc it was added for — and a modern
BuildKit does heredocs without it (verified by deleting the line and rebuilding).

**The repair rewrites in place and adds no file.** `heredoc_to_run` reads the body out of the
Dockerfile at apply time and re-emits it as `RUN printf '%s\n' … > dest`, then drops `# syntax=` only
if nothing left needs a modern frontend:

```
RUN mkdir -p /tmp \
 && printf '%s\n' \
      'import re, pathlib' \
      ... \
      > /tmp/obfuscate_harbor.py
```

`printf '%s\n'` is exact for a quoted tag: `%s` applies no escape processing, so `\d` and `%` survive
verbatim, and single-quoted arguments suppress every expansion — which is what `<<'TAG'` means. It is
a shell builtin, so unlike `base64 -d` nothing needs installing, and unlike a base64 blob the script
stays readable, which matters when the thing being written is anti-cheat a reviewer must audit.
Verified byte-identical on **both** builders, including a body containing single quotes, `%`,
backslashes and tabs.

**Why it does not write a sidecar `environment/*.py`.** It cannot, and that is the point. The
canonical layout allows only `environment/Dockerfile` and `environment/assets/*`, so writing
`environment/obfuscate_harbor.py` trips fix.py's own whitelist guard — *"the fixer added
non-canonical path(s) …; rolling back"*, exit 3 — and had it survived, the **next** reviewer would
see it as a `stray_files` candidate whose offered action is to delete it, breaking the build again
with a genuinely missing source. Rewriting in place is legal everywhere and needs no policy change,
so the repair is identical for every worker.

It **declines** three shapes rather than guessing, and says which on the finding: an unquoted tag
(`<<TAG` expands ARG/ENV inside the body, single-quoted printf would not), a `RUN` heredoc (a script,
not a file — faithful conversion means deciding about shebangs and `set -e`), and multi-heredoc or
unterminated instructions. Those report as `heredoc_manual` — still a FAIL, just no auto-fix.

### The /etc/hosts trap — why a green local probe proves nothing

Measured on docker 29.6/BuildKit, both halves:

1. **`/etc/hosts` is read-only during a build** — `cannot create /etc/hosts: Read-only file system`.
   In `printf >> /etc/hosts && npm config set … && rm -f /usr/bin/curl`, that first failure
   **short-circuits the chain**: the registry redirect and the `rm` never run, and a trailing
   `|| true` makes the RUN exit 0, so the build log says DONE.
2. **Docker regenerates `/etc/hosts` per container**, so a write that *does* land in a layer is
   discarded at run time. Verified by commit+run: the entry is gone and the host resolves normally.

So the hosts blackhole never protects anything on any builder — and the same Dockerfile behaves two
ways: under BuildKit the chain aborts and curl survives (**the image looks fine and a local probe
PASSES**); under a builder that permits the write, curl is deleted and the trial dies with a 127.
That is why group E stays a static FAIL even when the probe is green.

The repair is subtraction, and it is only legal because `[agent] network_mode = "no-network"` (group
N) already seals the agent phase at the harness level — which also covers urllib, node fetch and
git-over-ssh, none of which deleting a binary touches. If the agent phase is **not** sealed, the fix
downgrades itself to `ask`: that fragment is then the only egress control there is, so seal the
phase first. An auto-fix that unseals a task while claiming to repair it is worse than no fix.

```bash
python3 $FIX qc   /home/sandbox/Tasks                            # group E, static, free
python3 $FIX auto /home/sandbox/Tasks --apply                    # un-strip the binaries
bash ~/.claude/skills/mm-swe-qc-fix-sandbox/checks/qc_env_probe.sh /home/sandbox/Tasks
```

`qc_env_probe.sh` builds the image and asks it directly — `command -v` for each harness binary, the
effective npm registry, `/etc/hosts` for the CLI download host, a writable `$HOME` for
`~/.local/bin`, the `harbor_base` tag the verifier diffs against, and (for group P) the mode of `/`
plus the same privilege drop the Dockerfile performs. No API key, no model call, no agent. It catches
what text cannot (a private base, a multi-stage `COPY`, a non-root `USER`, a rootfs the daemon hands
over at 0750), and it prints the portability caveat above whenever the Dockerfile touches
`/etc/hosts`. Its group-P section is the only check that can see the **shipped** image, which is where
the verify-time half of that defect lives.

## Can a non-root process run in the image? (group P, BLOCKING)

A second Dockerfile group, and a different question from E's. Measured on this sandbox's daemon,
docker 29.6: the rootfs a build is handed has **`/` at 0750** — `drwxr-x---` — even though the host's
own `/` is 0755. Nothing running as a non-root uid can traverse it, so the dynamic loader never opens
libc and the process dies before `main()`:

```
 > [2/2] RUN ls -ld / && useradd -m pg && su pg -c "echo NONROOT_OK":
0.254 drwxr-x---+ 1 root root 4096 /
0.416 su: failed to execute /bin/sh: Permission denied     # exit 126
```

The variant with a shell that gets further names libc instead — `error while loading shared
libraries: libc.so.6: cannot open shared object file: Permission denied` — and **libc is fine**. That
is what makes this expensive: the message accuses the base image, so the search starts in the wrong
place. Every `su`/`sudo -u`/`gosu`/`runuser`/`setpriv`/`su-exec` and every `USER <non-root>` is a site.

**Unlike group E, the gate is not blind here** — the build fails, so the oracle fails too. What the
oracle does not deliver is the *diagnosis*, and that is the whole value: a task died twice at the same
`initdb` line before this check existed. It is the same standard that keeps a swallowed `npm install`
out of group E (a 0.0 oracle explains itself; this does not).

### The repair is two-part, and the second half is the one that gets forgotten

| | |
|---|---|
| **build time** | `chmod a+rx /` in the **same `RUN`** as the drop |
| **verify time** | the generated starter script must repeat it, as root, before its first drop |

Both halves are measured, not reasoned about:

- **A separate `RUN` fixes nothing.** `RUN chmod a+rx /` followed by `RUN su pg …` → the second RUN
  sees `drwxr-x---` again and dies with 126. A mode change on `/` is not captured in a layer diff.
- **The shipped image still has `/` at 0750.** A build that succeeded *because* of its chmod produces
  an image where `docker run … su pg` fails. So a `harbor_pg_start`-style starter, an entrypoint, or
  any `test.sh` helper that drops privileges needs its own chmod — otherwise fixing the build merely
  moves the identical failure to the first verify run, where it reads as a broken test.

`chmod a+rx /` is additive and a **no-op on a normal daemon**, it removes no hardening and changes no
uid, so `nonroot_privilege_drop` is `auto` and class **A**. `USER <non-root>` is the one shape with no
in-image repair at all: whatever preceded it has reverted, and after it PID 1 is already non-root, so
there is no root process left to fix `/` with. That, an exec-form `RUN ["su", …]`, a drop in
`CMD`/`ENTRYPOINT` and a script assembled some other way are reported as `nonroot_manual` rather than
guessed at — the same line `heredoc_manual` draws.

### The check grades the ABSENCE of the repair, not the presence of a `su`

PostgreSQL aborts on `geteuid() == 0` with no override, so the drops are permanent and correct — "run
as root instead" is not among the repairs, and a check that FAILed a `su` forever would make its own
fix unprovable and leave a repaired bundle permanently red. So each site is graded on whether `/` is
already made traversable before it, **in the same layer** (build) or **inside the same script**
(verify), and a fully repaired Dockerfile reports `env_nonroot_guarded` as an OK line. The quote-ness
has to match too: a bare `chmod a+rx /` in the RUN that *writes* a script repairs the build layer, not
the script that runs later, and counting it would clear a defect the image still has.

### `setpriv --reuid` without `--regid` looks like a fix and is not

Worth knowing before anyone "fixes" this by swapping `su` for `setpriv`. `/` is `drwxr-x---`, so
**group root still has r-x**, and `setpriv --reuid=pg --clear-groups` keeps gid 0 — it traverses `/`
happily and prints OK, while `su pg`, which switches gid as well, dies on the same line. Measured in
one image:

```
su pg                              : su: failed to execute /bin/sh: Permission denied
setpriv --reuid=pg (gid kept = 0)  : OK
setpriv --reuid + --regid=pg       : libc.so.6: cannot open shared object file: Permission denied
```

This bit the probe first: its `setpriv` fallback omitted `--regid`, so it reported a green PASS on an
image where every `su` in the Dockerfile fails. `qc_env_probe.sh` now performs the same drop the
Dockerfile performs, and it reports a bare-drop failure as a **defect only when a runtime drop is
actually unguarded** — on this daemon a bare drop fails in every image, a correct one included, so
reporting that alone would fail the right shape just as surely.

## The rubric, checked against the golden fix

When a rubric-side fix lands (`judge_drift`, `test_sh_judge`, `rubrics_shape`, `rubric_task_id`,
`rubric_file`, `judge_missing`) and the rubric is **real**, one question reopens: does
`solution/fix.patch` still satisfy every criterion? A criterion it fails would fail **every**
correct submission — a Major "Incorrect Criterion" — and that is one of the six semantic issues the
static checks can only report as `OPEN`.

The oracle run answers it for free. It applies `solution/fix.patch`, so its candidate diff **is**
the golden fix, and `judge.py` writes a self-contained request beside it:

    judge request: <ROOT>/Oracle/Tasks__xxx/verifier/judge
      criteria_payload.json · source.txt (the golden diff) · changed_files.txt · PROMPT.md

The agent grades that and reports per criterion. Nothing is written and no model is called by the
skill — the judge is a sub-agent.

**There is deliberately no `rescore` step.** Re-running oracle regenerates the request but cannot
answer it: `judge.py` finds no verdict, takes phase 1, prints nothing, and the verifier scores on
tests alone — so the reward returns `1.0` whether or not the rubric is satisfiable. Folding a
verdict back into `reward.txt` only re-proves the `1.0 -> 0.0` gate arithmetic, which
`qc_rubric_format` already checks statically by reading `verifier.py`. So the grading is kept and
the fold-in dropped.

An always-pass stub short-circuits the grading — a stub can never fail, so there is no verdict to
establish. **That is the defect, not a pass.** It is reported as a blocking Fail; see below.

## The rubric layer has two legal shapes, and both are checked

`checks/qc_rubric_format.py` decides which shape a task is in and every finding it raises is a
**BLOCKING Fail** — the report marks the category ⛔ and the verdict line says so, because until
these are fixed no other number means anything.

| | **Mode A — RUBRIC** | **Mode B — NO RUBRIC** |
|---|---|---|
| `tests/rubrics.json` | present, ≥1 real criterion | absent |
| `tests/judge.py` | present (either backend) | absent |
| `config.json` → `rubric_file` | `"rubrics.json"` | key absent |
| `--rubric` gate in `verifier.py` | present, fires — **required** | present, never fires — recommended |
| `test.sh` judge block | present, runs | **present, no-ops** |
| `task.toml` → `[verifier] network_mode` | `"public"` — **required** | `"public"` — **required** |
| `task.toml` → `[verifier.env]` | three `EVAL_*` keys — **required** | **absent** |

The last two rows are the *only* difference the verifier phase makes between the two shapes: one
block, `[verifier.env]`. `[agent] network_mode = "no-network"` and `[environment]` are identical in
both and no fix touches them.

The `--rubric` plumbing is graded **mode-aware**, on the test "can its absence mis-score a run?".
In Mode A its absence is a blocking Fail: the judge's `fail` verdict never reaches the gate, so a
task that should record `0.0` records `1.0`. In Mode B it is a warning — golden 2 does ship it
(`verifier.py --rubric ""`), but measured against golden 2's own `_rubric_verdict()` an empty flag,
an omitted flag and no parsing at all all yield `rubric_passed = -1`, so nothing can be mis-scored.
An *unguarded* judge block stays a hard failure in both modes: in Mode B it would run `judge.py`
against a rubric that does not exist on every run.

Three things this changed, each of which used to let a bad task through or fail a good one:

- **An all-pass stub is no longer legal.** `{"id": "always_pass", "criterion": "The response is
  written in English."}` cannot fail any submission, yet it makes `rubric_passed` read `1` exactly as
  though a real rubric had been satisfied — so it fabricates a graded result. It is also
  unfalsifiable: with a zero denominator every rubric-quality percentage band passes. A task that
  needs no rubric ships **no rubric layer at all**; `qc_rubrics` used to print `[ok] … valid` here.
- **A task with no rubric is CORRECT.** `tests/rubrics.json` is no longer in
  `REQUIRED_TASK_FILES`, and `qc_rubrics` / `qc_judge` report "nothing to audit" instead of a
  missing-rubric Fail. Requiring the layer unconditionally failed sound bundles.
- **Stripping a rubric is not ripping out the gate.** The `--rubric` plumbing in `verifier.py` and
  the `[ -f /tests/rubrics.json ]`-guarded judge block in `test.sh` stay in **both** modes. With no
  rubric on disk the guard is false and `rubric_passed` records `-1` ("not graded"), which is the
  correct record. One verifier contract serves both shapes.

**Mode A must grade in-band.** The judge backend and `task.toml`'s `[verifier]` / `[verifier.env]`
blocks used to be out of scope — either backend counted as valid, and those blocks were held to
"vary legitimately across tasks". That reasoning does not survive one observation: a sub-agent-only
judge cannot grade during the run. It records `rubric_passed = -1` on every run until someone reads
`PROMPT.md`, writes `verdict.json` and reruns `rescore`, and that step is routinely skipped — so the
rubric is decorative in exactly the way an all-pass stub is. Requiring in-band grading collapses the
"legitimate variance", because an API-backend judge has **one** working configuration:

| Requirement | Applies to | Finding | Fix |
|---|---|---|---|
| `[verifier] network_mode = "public"` | **every task** | `rubfmt_verifier_network_mode` | **auto** |
| `tests/judge.py` with an API backend (`call_eval_api`) | Mode A | `rubfmt_judge_backend` | **auto** if it is the stock stub; **agent** if adapted |
| `[verifier.env]` maps `EVAL_API_KEY`/`EVAL_BASE_URL`/`EVAL_MODEL` | Mode A | `rubfmt_verifier_env` | **auto** |

`"public"` is not a style preference — it is the only value that works. Verified against harbor
0.18: `allowed_hosts` is rejected unless `network_mode == "allowlist"`, `normalize_allowed_hosts`
takes **literal** hostnames and never env-expands, and there is no `allow_verifier_hosts` override.
A run-time-injected endpoint cannot be expressed as an allowlist. It costs little: the verifier runs
after the agent phase, `test.sh` restores the tests from `harbor_base`, and public egress there
cannot help a submission cheat. The **agent** phase stays sealed.

No credential enters a bundle — `[verifier.env]` holds `${VAR}` references, expanded by harbor at
run time, and the value is the anonymizer placeholder rather than a real key. The sub-agent path
stays in `judge.py` **as the fallback**; what is barred is shipping it as the only route to a
verdict.

### `network_mode` is not a rubric requirement, and applies to every task

The first row was Mode A only, on the reasoning that a task with no judge has nothing to reach an
endpoint. True, and beside the point — the verifier phase also **installs what the tests need**.
`npm install`, `pip install`, or a bare `npx <runner>` resolving from the registry all fail under
`no-network`; the f2p test fails with them, and a **correct** submission records `0.0`. That is a
false negative whose reward looks perfectly legitimate, which is a mis-scored run by the same
standard that makes the Mode A findings blocking. So it is blocking in **both** modes.

Tasks that pre-stage their test dependencies at build time never exercise the permission, so it
costs them nothing to hold — and holding it stops the seal being a trap for every task that
installs at verify time. Pre-staging is still the better shape; the seal is not what should be
enforcing it.

`[verifier.env]` stays Mode A only, and the asymmetry is the whole point. Nothing reads `EVAL_*`
without a judge, and `EVAL_API_KEY`/`EVAL_BASE_URL` are **bare** `${VAR}` references — which harbor
treats as *required* host vars, exiting 1 with a "Missing Environment Variables" table
(`cli/jobs.py`) before any container starts. Writing that block into a rubric-less task would break
its keyless `oracle`/`nop` for credentials no judge would ever read. **That** is the false-failure
class this area was once pulled out of scope for, and it is a property of `[verifier.env]`, not of
`network_mode`.

One consequence worth knowing: `verifier_network_mode` is now a **class C** fix (the trial must be
re-run), where it was class B. Unsealing the verifier can change whether the tests pass at all, and
`rescore` recomputes only the rubric verdict — it cannot re-measure the tests.

`qc_rubrics` still owns rubric *content* quality; this check owns the *shape*.

**To fix one of these, read [`RUBRIC_MODES.md`](RUBRIC_MODES.md).** It is the wiring reference for
both shapes: what each of the six files must contain in each mode, the canonical `reward.json`, what
`rubric_passed` should read for every run outcome, and the four-step recipe for stripping a rubric
layer (Mode A → B). Every `rubfmt_*` finding is a wiring defect that doc describes the repair for.

## Does the task actually need its images?

MM SWE is a multimodal benchmark, so the poster is supposed to carry what the prose does not.
The audit raises `instr_solvable_without_image` on every task and gathers the evidence — word
count, whether `instruction.md` names the edited files or the values the fix introduces (a
deliberate code reference, not a bare English word), how often it defers to the poster, and how
many vague stand-in phrases it uses. It states a **lean**, never a verdict:

    LEAN: IMAGE-DEPENDENT - the prose defers the decisive detail to the poster and
    does not name the edited file(s)/values.
      → 159 words · 2 image asset(s) set aside: after.png, before.png
      → names 0/2 edited file(s) in prose
      → defers to the image 3 time(s), e.g. 'shown in the attached'

The agent then reads `instruction.md` with the assets set aside and reports **as a warning, never
a blocker** — severity `CANDIDATE`, which by construction cannot change the exit code. Both ends
are worth knowing: prose that suffices on its own means the poster is decorative and the task
never exercises perception; prose that does not suffice is the intended shape, provided the poster
supplies what it withholds.

A fix that introduces no distinctive symbols (a CSS-value change) leaves nothing to name, so that
signal is treated as **neutral** rather than as a strike — otherwise the test would be a 0/0
denominator that can never be satisfied.

## Instruction wording scan (Lean Instruction Playbook)

Group L in `checks/qc_structure.py` (`check_L`) scans `instruction.md` for what the Lean Instruction
Playbook (Official V25, instruction dims 3/4/5) says to keep out of the text, and for the two
sentences it asks for. It is **advisory by construction**: every finding is a `CANDIDATE`, and the
group has no rubric dimension (like group T), so it cannot change the exit code, withhold the QC
pass, or keep oracle/nop grounded. It reports under **3. EVIDENCE & IMAGE**.

Its result is always visible in the report. Hits print as `[CAND]` lines labelled *Instruction
wording · advisory*. A clean scan is named on the category line (`instruction wording scan: clean`)
instead of being folded into "N check(s) clean" (`PINNED_OK` in `checks/qc_common.py`). That way
`/run-check` can report it every time, next to the "could this be fixed without the screenshots?"
read.

| id | fires when |
|---|---|
| `instr_lint_leak` | the text (title included) names a URL, code host, issue/PR/commit, source file, `call()`, `scoped::name`, code-style identifier, a size with a unit, quoted error text, or the repository's own name |
| `instr_lint_cause_word` | a word from the golden fix's **changed** lines (identifiers split into parts, plus comment prose, minus keywords and common English) appears in the text |
| `instr_lint_vague` | a generic phrase stands in for the defect: *something*, *an issue*, *glitch*, *broken*, *doesn't work*, *wrong*, *not … correct(ly)/properly* — unless the same sentence explains it after `:` or a dash |
| `instr_lint_time_window` | a sentence with a timestamp or a region of the frame (*in the frame centre*, *top left*) is vague or has almost nothing besides it |
| `instr_lint_no_image_truth` | images ship but no sentence says they are correct apart from the defect |
| `instr_lint_vague_truth` | a sentence says `<subject> is/are correct` about a generic subject: *what the screenshots show*, *everything else*, *the rest*, *the screenshots*, *it* |
| `instr_lint_no_reference` | images ship but nothing points to what correct looks like |

It matches **phrases, not words**. The playbook asks for a sentence saying the images are correct
apart from the defect, so `instr_lint_vague` counts only negated and generic forms of *correct*. The
positive form is judged by **what** it calls correct. "Apart from the defect, the moon names, their
numbering and the orbit order … are correct" is fine. "Apart from the defect, what the screenshots
show … is correct" is `instr_lint_vague_truth`, because it never says what to trust. A change guard
like luanti's "Nothing that is already drawn correctly should change" isn't judged. Titles are
checked for leaks but not for vague phrases. Calibration: luanti_12770 comes out clean, and the Dim
4 Fail example ("Something does not render correctly in the frame centre (0:02–0:05)") fires.
pioneer_5999 comes out clean **except** for `instr_lint_vague_truth`, on purpose (CB ruling,
2026-11-05).

### The instruction read (one model call)

Whenever a model is reachable, **one text-only call to Sonnet 5** judges the three instruction
requirements together. It is given `instruction.md` (title, headings and the evidence captions
included), the f2p test names and, when `task.toml` has one, the `difficulty_explanation`. The test
names and the explanation are ground truth for what the task grades and what each defect really
is. No images, no fix, no test bodies.

- **Every graded defect is accounted for.** Each f2p test must match a defect the text states, or
  one the text points to an image for. A general truth sentence states no defect. This is the
  pioneer_5999 fail: the tests grade the moon's radius and the moons' numbering, the text describes
  only the radius, and "Apart from the defect, what the screenshots show about this moon and its
  neighbours is correct" plus a caption calling the labels "the game's own names" vouch for the
  wrong numbering.

- **Instruction check.** The element is named by type (*the shadow*, *the header labels*), without
  hinting at the fix. The defect and expected result may be in the text or in a comparison image the
  text points to. Which instance may stay in the image.
- **Symptom specificity.** A general phrase (*something does not render correctly*, *charts come out
  wrong*) passes when the same or the next sentence says what is affected, what kind of problem it
  is, or which image shows the correct result. It fails standing alone, or when a time window or a
  region is the only explanation.
- **Image dependency.** The text says what kind of problem it is, or points to where the correct
  result can be seen. The clue to the cause stays in the image: which instance, the trigger, the
  size, the timing, the error text. An expected result that would give the clue away must point to
  a reference image instead. The problem must not be described as the wrong kind.

| reason the model gives | reported as |
|---|---|
| `unnamed_element`, `generic_stand_in`, `no_problem_kind` | `instr_lint_vague` |
| `bare_window_or_region` | `instr_lint_time_window` |
| `hints_at_fix` | `instr_lint_hints_fix` |
| `clue_leak` (instance, trigger, size, timing, error_text, expected_result) | `instr_lint_clue_leak` |
| `misdescribed` | `instr_lint_misdescribed` |
| `vouches_for_defect` (a truth sentence or caption vouches for what a graded defect changes) | `instr_lint_vouches_defect` |
| a graded test the text neither states nor points to an image for | `instr_lint_undescribed_defect` |

Calibration example, from the requirements: *The shadow is missing under one of the objects on the
floor, while the other object has one. Every object should cast its shadow.* It names the element,
the defect and the expected result; which object, and why, stay in the image. It passes.

Leaks, cause words and `instr_lint_vague_truth` stay word scans: the vague "… is correct" sentence is
a CB ruling, not part of these requirements.

- **Same severity.** Every model finding is a `CANDIDATE`, exactly like the scan's. It cannot block.
- **Falls back.** No proxy, an HTTP error, a reply that isn't JSON, or `MM_QC_LLM=0`: the phrase
  scans for vague stand-ins and bare time windows or regions run instead, and the audit still needs
  no API key. Undescribed graded defects, vouching sentences, hints at the fix, clue leaks and
  misdescription have no scan; the evidence line says they were not checked. Group S's test-name
  overlap still asks the coverage question, more crudely.
- **Says who read it.** The first evidence line of each finding is `instruction read: read by
  claude-sonnet-5`, or `instruction read: static phrase scan; model read unavailable: <why>; …`. A
  clean read is pinned on the EVIDENCE & IMAGE line as `instruction read (<who>): clean`.
- **Quotes are checked.** A model finding whose quote is not in `instruction.md` is dropped, and so
  is an undescribed test whose name is not in the f2p list. The counts are printed.
- **Cached.** The reply is stored under `~/.cache/mm-swe-qc/llm/`, keyed on the model, prompt,
  instruction, test names and explanation, so re-audits of an unchanged task cost nothing and
  cannot change answer. The cache is outside the bundle so it never touches the digest.
- **Cost.** About $0.008–$0.019 per uncached call (roughly 3–5k input tokens, up to ~900 output).

The prompt is `checks/prompts/instruction_read.txt`; editing it invalidates the cache by itself.
Credentials resolve like `mm_run.sh`: `ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY` from the env, then
`~/.claude/settings.json`, then the anonymizer at `http://localhost:8091`. `MM_QC_LLM_MODEL` picks
another model (default `JUDGE_MODEL`, then `claude-sonnet-5`); `MM_QC_LLM_TIMEOUT` sets the seconds
per attempt (default 45, two attempts).

**It reads text only.** It cannot tell whether the text is true to the images, whether a defect
lives only in the pixels (pioneer's moon numbering — the Dim 4 = 3 case), or whether prose alone
would be enough (that is `instr_solvable_without_image`). In pioneer_5999 the screenshots carry the
pre-injection names; the read can say the text never states the numbering defect, but not that the
images fail to show it, unless a caption or the explanation says so. Report every hit to the CB in plain words
(`FINDINGS_GLOSSARY.md`); a `cause_word` hit on a word that names the *element* is expected and fine.

## Are the f2p tests agnostic, or golden-specific? (#9)

Checked in the audit itself — tier `bundle`, no credentials, no run. A green oracle and a nop
with every f2p failing only
prove the tests **discriminate** (fail with no fix, pass with the golden one). A test can
discriminate perfectly and still accept nothing but the golden implementation, and no reward
number can reveal that. So the assertion *form* is read statically:

| Signal | Verdict |
|---|---|
| snapshot assertion | **pinpointed** — encodes the golden output; no image can make it fair |
| strict equality on a colour literal | **pinpointed** — hex/rgb()/named are equivalent, so a valid fix expressing the same colour differently fails |
| asserts a symbol the golden fix *introduces* and `instruction.md` never names | **check the image** — if the poster shows the requirement the test may be fair (#9 Pass); if not, it only accepts the golden fix |
| one exact class/id selector, no fallback | **check the image** — a valid fix that renames or restructures would fail |

Never a hard `FAIL`, and **never a clearance either**. Two things this check cannot do, both of
them load-bearing under the rubric:

* it cannot see `environment/assets`, so a term absent from `instruction.md` may still be fair;
* it cannot see the REPOSITORY, and the rubric defines overfit against it — *"a plausible
  implementation is a valid implementation that also has any precedent in the repo"*. Precedent is
  read off a codebase, not inferred from a diff.

So every candidate here is a POINTER, and an empty list means "no signal in the test source", never
"the tests are fair". The audit always emits `overfit_not_settled_statically` saying so.

**Closing them, and the UNDERFIT direction that nothing static reaches, is `TEST_FITNESS.md`.**
Build the fact digest (`python3 fitness_digest.py <task>` — instruction text, base-verified symbol
table, test bodies, fixture-reuse map, ~6k tokens, no model), open both posters, and judge in a
container where an alternative implementation can be run in about two seconds. The image is the one
oracle and nop already use, so the build is amortised.

One correction that check has to carry, because it is the trap: **"the poster shows this value" does
not make an assertion fair.** A poster shows one correct rendering, not the space of them. Ask
whether the value is FORCED by the requirement (a computed figure every correct implementation
produces) or ONE OF MANY that satisfy it (`spacing === 10px` when the ask was merely "the borders
must be visible"). The second is overfit however faithfully it matches the reference.

Two suppressions keep it quiet on well-built tasks. A term named in `instruction.md` is fair by
definition. And explicit alternative-accepting markers — candidate-selector arrays, `getComputedStyle`,
`||` between acceptances, regex over equality — earn the benefit of the doubt on the
image-resolvable signals. Standard CSS/test vocabulary is stoplisted, so a fix whose whole diff is
`content: '""'` does not make the word `content` look implementation-specific.

## Test-name collisions are PROPOSED, and you decide (#10)

The verifier resolves each declared f2p/p2p identifier to one JUnit testcase, and *how* it matches
decides whether two similar names can collide. Under `k.endswith(ident)` a short name that is a
strict **prefix** of a longer sibling is perfectly safe — the leaf names differ. Under
`ident in k` the same pair collides. Under `results[ident]` neither does.

This check used to hardcode the substring answer without reading the verifier, so a sound bundle
got a blocking defect that no fix could clear — the report said "1 blocking defect(s) must be
fixed first" and "nothing to fix at this phase" in the same breath. A cleverer pattern would only
have postponed that, so the audit now separates **proposing** from **deciding**:

| | |
|---|---|
| the script | reads `tests/verifier.py`, reports how it matches, and proposes anything that *could* collide as severity **PENDING**, citing the line |
| **you** | open that line, decide whether both names can resolve to the same key, and record the verdict |

```
fix.py qc <root> --adjudicated <id>=cleared:"verifier.py:115 matches with endswith; the pair is
                                            prefix-related, so the two keys differ"
fix.py qc <root> --adjudicated <id>=confirmed:"both declared names end with this identifier"
```

`confirmed` promotes it to a blocking FAIL. `cleared` records the reason and drops it. A reason is
required either way and lands in `qc_report.json`, so the decision is auditable.

**A ruling is made once.** It is recorded outside the bundle and replayed by later audits — including
`mm_run.sh`'s gate, which invokes this command with a fixed argument list and would otherwise
recompute the finding as PENDING and delete the QC pass the ruling had just earned. Every replayed
ruling is reprinted with its reason and marked `(replayed from an earlier ruling)`, so a clean verdict
never hides a decision. It lapses on its own when `tests/` or `solution/` changes, because it was a
judgment about that code; an edit to `instruction.md` or the posters leaves it standing. Re-passing
`--adjudicated` for the same id overrides what was recorded, which is how a verdict gets corrected.

The record holds rulings only. It cannot create a finding, cannot clear a `FAIL`, and cannot stand in
for the QC pass — a stored verdict only ever re-resolves a finding the current audit independently
raised as PENDING.

**PENDING is not a failure, and it is not counted as a blocker.** What it does is withhold the
`.qc_passed` marker, and that half is deliberate: a headless audit (`mm_run.sh`'s check gate, cron)
has no one to adjudicate, and without this it would write a marker vouching for a bundle whose
identifiers may genuinely collide. A false positive costs an argument; that would ship a broken
task. So "nobody has looked yet" is a visible state rather than silence.

**It does, however, get its own exit code: 3.** It used to exit 0, on the reasoning that only a
FAIL may fail a run — but that made "clean" and "clean, and nothing may vouch for it" indis-
tinguishable to `mm_run.sh`'s gate, which reads the exit code and nothing else. The gate printed
"QC clean", spent a credentialed check run, and left no marker; `check_digest()` then grounded
oracle/nop with "no QC audit is on record — run `/run-check` first", which produced the same
verdict and the same missing marker, forever. Withholding the marker only works as a signal if the
caller can *see* that it was withheld, so the three states now reach the caller as three codes:

| exit | meaning | marker | gate |
|------|---------|--------|------|
| 0 | no blockers, nothing pending | written | proceeds — "QC clean" |
| 3 | no blockers, but a finding awaits adjudication | withheld | stops (9), spends no run |
| 4 | no blockers, but the pass could not be *recorded* | absent | proceeds, warns loudly |
| 1 | bundle-tier FAIL(s) | removed | stops (7) |

The code is derived from `update_qc_marker`'s own return value rather than re-deriving the PENDING
set, so the exit code and the marker cannot disagree by construction — two functions independently
computing "is this clean?" is how they drifted apart to begin with.

**4 covers `update_qc_marker`'s third return, `None`**, which re-opened the same livelock by a
different door: the judging block raised (a malformed tier, a failed import) or the marker write
raised (read-only or full `/tmp`, a stale marker owned by another user, `$MM_QC_MARKER` pointing
somewhere unwritable). No marker, exit 0, "QC clean" — then oracle/nop refuse forever. It does not
stop the gate, because nothing about the *task* is wrong and the oracle/nop digest gate has no
bypass flag to strand the CB behind; what it stops is the word "clean". `fix.py` stays silent about
the path (the marker is internal to this skill), so `mm_run.sh` says the actionable half.

Three returns, three codes, and no path where a missing marker is reported as a pass:

    True  -> 0    marker written
    False -> 3    judged, deliberately withheld    (or 1, when blockers withheld it)
    None  -> 4    could not judge, or could not record

**The marker carries a content digest of the bundle it passed.** A clean audit writes
`/tmp/qc_check.md` (`$MM_QC_MARKER`) with the audited `task_dir`, harbor's own
`Packager.compute_content_hash` — the value harbor records in every run's `lock.json`, so the
marker is comparable with any control — and an `extra-digest` covering everything harbor's hash
does not reach, `evidence_bundle.json` above all. Without it the marker asserts a pass against a
path and a timestamp, neither of which survives an edit: the files could change completely and it
would go on vouching for them.

`qc_digest.py`, beside `fix.py`, computes and compares it, and is usable standalone:

    python3 qc_digest.py <task-dir>                     # both digests
    python3 qc_digest.py <task-dir> --compare <marker>  # 0 match, 3 mismatch, 4 nothing recorded

A mismatch names each changed, added or removed path rather than reporting one opaque hash —
"`solution/fix.patch` changed" is a diagnosis; "digest mismatch" is a riddle. The runner reads
this before `oracle` and `nop`, which run only on an exact match.

Two collisions have real teeth and are worth reading carefully when proposed: a leaf name shared by
two `describe` blocks, and a loop that appends a suffix — in both, several *runtime* keys end with
one declared identifier, only one name need be declared, and the verifier's `next(...)` silently
takes whichever comes first. Where a parametrized name's parameter list is a literal array the
audit expands it and decides directly; where it is a variable or an import it says so instead of
guessing.

## Stale runs don't outlive the bundle

Everything `qc_gate` reads out of `Oracle/`, `Nop/` or `Trials/` describes *those files*. Once a
run predates the current bundle — by mtime, or by being the odd one out on `task_checksum` — those
readings stop being true, so they are downgraded to `OPEN [needs a re-run]` and the staleness
finding becomes the single accurate statement. On a real task that turned nine separate failures
into four.

A finding is only downgraded when **every** witness was a stale run. `dedup()` keeps the earliest
tier, so a defect that also has a static, bundle-tier witness (`qc_judge` reading `verifier.py`)
stays at `FAIL` — the static reading is true regardless of any run. The downgrade is always
printed, never silent:

    4 of the above were DOWNGRADED from FAIL, not dismissed:
      reward_json_nonnumeric   evidence comes only from Nop, which predates …

A 1-1 checksum split marks nobody stale: with no majority there is nothing to identify the odd
run, and guessing would be worse than leaving the mismatch as the only statement.

Findings are grouped into the six QC-rubric-v2 dimensions rather than by the tool that found them,
so one defect seen by two checks is one line (`↳ also seen by: …`), and a machine-readable
`qc_report.json` is written beside `Tasks/` (`qc --no-report` opts out). Override the tier with
`--phase bundle|gate|post-trial|submission`; forcing a lower phase says so in the header.

Finding ids are for `--approve` and for parsing `qc_report.json` — **they are not English**. Before
repeating one to a CB, get the plain-language wording from
[`FINDINGS_GLOSSARY.md`](FINDINGS_GLOSSARY.md), and add the id in parentheses only when they will
need to type it.

## No API key is needed — anywhere

This is the part that differs from the local flow, and it is worth being explicit about:

- the rubric judge is a **sub-agent** that makes no model call, so **oracle and nop run keyless**;
- the five checks are **stdlib-only with no network**;
- `--emit-graders` writes prompts for **your own agent** to grade — it does not call an API;
- **the trial is never run by this skill.** That is the only step that would need credentials, and
  re-running it is a human decision because it costs a real model call.

## Harbor is never called directly

Every run goes through the MM SWE runner — `mm_run.sh <task> oracle|nop` — resolved in order:

1. `$MM_RUNNER`
2. `~/.claude/skills/mmswe-runner/mm_run.sh`

**`--run` therefore requires the `mmswe-runner` skill.** `install.sh` installs both, so this holds
by construction; if neither candidate resolves, `--run` reports "no MM SWE runner found — oracle/nop
were NOT verified" and exits 2. It never reads as a pass.

This skill used to carry a third candidate: its own copy of the runner under `runner/`, as a
fallback for a standalone install. It was deleted, because a second copy of a 1500-line script is
a liability rather than a safety net — it drifted 626 lines behind the real one, missing every
judge fix (`EVAL_*` forwarding, the `[verifier.env]` preflight, a host-side fallback that hunted
for a `workspace/` directory harbor never creates), while the docs still told CBs to prefer it via
`$MM_RUNNER`. One copy cannot go stale against itself.

Runs are bounded by `$MM_RUN_TIMEOUT` (default 5400s). On timeout the skill says so rather than
hanging, and the reward is read from the `reward.txt` harbor wrote — not scraped from the log.

## One approval, every blocker

A CB is not a harbor expert. Asking them to hand-edit `verifier.py`'s reward arithmetic, or to wire
a judge's API backend, is asking the person with the least context to do the most delicate part —
and in practice it meant those defects went unfixed. So the skill asks **once**, and then clears
everything that stands between the task and the golden format.

Findings are classed by **who writes the bytes**, not by how important the fix is:

| Kind | Who | Needs |
|---|---|---|
| `auto` | `fix.py` | the one `--apply` |
| **`agent`** | **the agent, following `RUBRIC_MODES.md`** | **the same `--apply` — not a second question** |
| `ask` | the CB decides first | its own question |
| `never` | nobody; reported only | — |

`agent` exists because three blocking defects used to be `kind=never`: the `0.5` reward ladder, a
judge with no API backend, and the verifier reward block. The skill reported them and **stopped** —
`apply --approve` refused them outright. Each has exactly one correct repair, already written down
in [`RUBRIC_MODES.md`](RUBRIC_MODES.md); what was missing was permission to perform it.

They are not `auto` because `verifier.py` carries task-specific scoring and `judge.py` the grading
contract. A regex that floors a reward, or a blind block-merge, can silently change what the task
grades — and that is worse than the defect, because the number still looks like a score. A script
cannot read the surrounding logic to know it stayed correct; the agent can.

**The price of that permission is proof.** `fix.py qc` prints an `AGENT REPAIRS` section naming the
exact sites (from the check's own AST walk, not a text match) and the command that proves each one.
Run it and show the `[OK ]`. An unproven repair is reported as unproven, never as done.

### What still gets its own question

Two things, and they survive because they **destroy content** or need task knowledge the agent does
not have — not because of permission:

- **the rubric mode, in either direction.** A→B deletes `rubrics.json` and `judge.py`; B→A is
  authoring what the task grades. Put the question to the CB with your evidence and a lean. Once
  they pick, the *wiring* for that mode is yours and needs no second question.
- **deleting an asset or a stray file.** An unreferenced image may still be the visual source the
  task depends on, so "unused" is never a safe inference, and removing one invalidates the trial.

Rubric criterion *wording* stays `never`: unlike the three `agent` repairs there is no single
correct answer to point at, and a wrong rewrite silently changes what the task grades.

## What it fixes, and what it asks about

**Applied automatically** (no judgment needed): build junk and editor debris, `chmod a+rx /` at every
privilege drop (`nonroot_privilege_drop` — additive, a no-op on a normal daemon), a missing
`rubric_file`, a `judge.py` missing *while a rubric ships*, the `test.sh` judge block,
`rubrics.json` shape, a mismatched rubric task id, `[verifier] network_mode` **on every task**,
`[verifier.env]`'s `EVAL_*` mapping **when a real rubric ships**, the legacy `rubric_pass` →
`rubric_passed` rename, and `judge_backend` **when the shipped judge is the stock stub** — the sha
proves there is nothing task-specific to lose, and it is the same copy `judge_missing` already makes
when `judge.py` is absent.

"When a real rubric ships" means the same thing to `fix.py` as it does to the check: a
`rubrics.json` that parses and holds at least one non-stub criterion. It used to mean only that the
file *exists*, so a stub-only or unparseable rubric drew a proposed `verifier_env` fix while the
check — which routes those to Mode B — raised no matching finding, putting a repair in
`PROPOSED FIXES` for a defect the report never named. Those tasks are told to strip the layer, not
to wire it.

**Repaired by the agent** under that same approval: `verifier_reward_domain` (the `0.5` ladder),
`verifier_rubric` (the canonical reward block), and `judge_backend` **when the judge was adapted** —
a non-stub sha means someone changed it, so read the diff before copying over it.

The line between those two lists is *whether a hash can settle it*, not how small the edit looks.
A whole-file copy of task-agnostic boilerplate is decidable: either the bytes match the stub or
they do not. Flooring a reward never is — `reward = tests_passed * 0.5` floors to `* 0.0`, a
verifier that scores zero on every run including oracle, and no checksum can warn you.

**Escalated to the CB** — an unrecognised non-canonical file, an unreferenced asset, a `judge.py`
that *already has the API backend* yet differs from the reference, and the mode choice itself.

Three auto-fixes were **removed or downgraded** because they fought the two-shape policy:

- `legacy_creds` (deleted) stripped `[verifier.env]` from `task.toml` as a "retired api backend"
  leftover. But harbor expands that block's `${VAR:-}` entries from its own environment, which is
  where the runner exports the judge credentials — so stripping it is what breaks in-container
  grading. Under the in-band requirement above it is worse than that: the block is now **required**
  in Mode A, so the fix would have manufactured `rubfmt_verifier_env` on every task it touched.
  `qc_judge`'s `check_creds()`, which detected it, is **also deleted** — it was already unwired but
  kept "as a function for reference", and it failed a task for *having* the block Mode A now
  requires. An unwired check encoding a reversed rule is how the old policy comes back.
- `judge_missing` now fires only when a rubric actually ships. It used to install `judge.py` into
  Mode B tasks, manufacturing the half-wired state that is itself a blocking defect.
- `judge_drift` is now **ask**, not a byte-restore. There are two valid backends and the template
  is one of them, so overwriting on a hash mismatch replaced working judges — measured: the
  template matches neither reference task. It was narrowed again when `judge_backend` arrived: it
  now fires only on a judge that **already** grades in-band, so one stub judge stops producing two
  findings with different advice (a blocking "no backend" and an ask "it differs, have a look").

And one was **promoted**: `rubric_key_rename` (`rubric_pass` → `rubric_passed`) was held out of
bulk apply so a corpus-wide defect would stay visible. But the report shows it either way, so
withholding it bought no visibility and cost a round trip on a defect with one correct answer and
no grading consequence. It still declines to offer itself when other canonical keys are missing —
that guard, not the prompt, is what stops a rename from masking a larger hole.

**Reported, never fixed**: rubric criterion wording. Rewriting a criterion is authoring, and a
wrong "fix" silently changes what the task grades — unlike the three `agent` repairs, there is no
single correct answer to point at. Also `nonroot_manual`: a privilege drop in a shape the injector
declines (an exec-form `RUN ["su", …]`, a `CMD`/`ENTRYPOINT` drop, a `USER` stanza with no in-image
repair) — detected and named, but edited by hand.

## The trial

Fixes are classed by whether the existing trial survives:

| Class | Meaning | Trial |
|---|---|---|
| **A** | verifier-side cosmetic | keep it |
| **B** | rubric/judge only | keep the trajectory, then `mm_run.sh <task> rescore` |
| **C** | agent-visible or measurement change | **must be re-run** |

`plan` prints the verdict for approving only AUTO versus also approving an escalated item, so the
cost of each choice is visible before you decide.

## Guarantees

- **Consent first**: no write and no docker run without `--apply` / `--run`. Everything below is
  the net under that, not a substitute for it.
- A snapshot is taken outside the bundle before any edit and restored on regression.
- The canonical-layout whitelist means a fix may add a file the layout allows (`judge.py`) but
  never anything outside it — otherwise it aborts and rolls back.
- Verification is never optimistic: **4** if the gate broke, **5** if it was not reproduced —
  including when `--run` was simply withheld. It never reports success having checked nothing.
- A finding that cannot be decided yet is `OPEN`, never `FAIL`, and never changes the exit code.
- `qc_report.json`, `FIX_REPORT.md` and `plan.json` are derived output written **outside** `Tasks/`,
  so they are not gated. `qc --no-report` opts out for a strictly read-only run.
