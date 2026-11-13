#!/usr/bin/env bash
###############################################################################
# mm_run.sh — run an MM SWE Harbor task as oracle, nop, a single agent trial, a
# rubric quality check, or a post-hoc analysis of a finished trial.
#
# Layout (mirrors the QH folder):
#   <ROOT>/Tasks/               the task (task.toml, environment/, solution/, tests/)
#   <ROOT>/Oracle/              oracle run output (no per-task subfolder)
#   <ROOT>/Nop/                 nop run output    (no per-task subfolder)
#   <ROOT>/Trials/with_images/     agent trial output, normal attempts    (flat job, no
#   <ROOT>/Trials/without_images/  agent trial output, text-only attempts  timestamped dir)
#   <ROOT>/Check/               harbor check output (rubric quality checks)
#   <ROOT>/Analyze/             harbor analyze output (post-hoc trial analysis)
#
# Credentials: the trial always needs them. If the task ships tests/rubrics.json the
# VERIFIER needs them too (its judge runs in the verifier phase), so every mode gets
# them; with no rubric the verifier is unit-tests -> JUnit -> reward.txt with no model
# call and oracle/nop stay strictly keyless.
# Resolution is the ProjectBench method: live env first, then
# ~/.claude/settings.json `.env`, then the ANONYMIZER DEFAULTS
# (http://localhost:8091 + key `anonymizer-placeholder`). CBs never handle a real
# key — the placeholder only authenticates THROUGH the anonymizer proxy. The key
# is masked in all output.
#
# Proxy: the anonymizer is the default path. A public HTTPS base URL is only used
# if you explicitly export one, and is passed straight through. For the LOOPBACK
# anonymizer (127.0.0.1/localhost),
# the container can't reach it, so a TCP bridge (sandbox_proxy_bridge.py) is
# started on the host-reachable gateway and the in-container URL is rewritten.
# Rootless docker is handled: docker0 (172.17.0.1) does not route to the host
# there, so the host route-source IP is used instead.
#
# Network isolation (trial, on by default): the compose override declares NO
# networking, so the service stays inside harbor's egress-control sidecar and
# task.toml's per-phase policy is actually enforced; the runner then passes
# --allow-agent-host <anonymizer> so the agent phase can reach the model API and
# nothing else. This replaces the old `network_mode: host` override, which handed
# the container the VM's entire network stack and silently defeated task.toml.
# Note it is PHASE-scoped on purpose: harbor installs the agent inside the
# container before the agent phase, so a network sealed at compose level breaks
# that install with "Could not resolve host". See build_agent_seal.
#
# The sealed path speaks HTTPS to the bridge, and must. Inside the sidecar's netns
# every connection is sniffed by gost, whose HTTP handler terminates the stream and
# caps the upstream response HEADERS at 15s — a slower model turn reaches the agent
# as an empty EOF, i.e. ECONNRESET with no HTTP status. TLS is sniffed as TLS and
# tunnelled raw with no deadline, so the bridge terminates TLS and the agent trusts
# its cert via NODE_EXTRA_CA_CERTS. See build_agent_seal / gen_bridge_tls.
#
# check/analyze reach the proxy differently. `harbor check` and `harbor analyze`
# accept no --extra-docker-compose, and both OVERWRITE config.environment when a
# -c JobConfig is given (analyze/checker.py, analyze/analyzer.py) — so the
# host-network override the trial relies on cannot be delivered to them at all.
# Instead the container dials the anonymizer at a host address it can actually
# reach, discovered by probing candidates from a throwaway container
# (resolve_host_addr), with the TCP bridge as a fallback. Their wrapper tasks run
# a prebuilt python:3.13-slim with no Dockerfile, so they need no TAR_OPTIONS.
#
# Usage:
#   mm_run.sh <task-dir> <oracle|nop|trial|check> [options]
#   mm_run.sh <task-dir> check-reviewers [options]     reviewer path: verify the SHIPPED
#                   Oracle/Nop/Trials against the bundle, mint qc_check.md + qc_trial.md when
#                   they match and the gate was green (oracle 1, nop 0, and a trial whose solves
#                   are inside the band and whose text-only run all failed -- see trial_rule),
#                   THEN run harbor check. Lets a
#                   reviewer skip re-running the controls and the trial. Refuses, spending
#                   nothing, if any run is stale or the gate was not green.
#   mm_run.sh <task-dir|job-dir|trial-dir> analyze [options]
#   mm_run.sh <task-dir> rescore --run <run-dir>       fold a judge verdict into that run
# Options:
#   --model M       model for the trial      (default anthropic/claude-opus-5-5)
#   --check-model M    model for check       (default claude-sonnet-5)
#   --analyze-model M  model for analyze     (default claude-sonnet-5)
#   --agent A       agent for the trial      (default claude-code)
#   --root DIR      where Trials/Oracle/Nop go   (default: dir containing tasks/)
#   --env E         harbor environment       (default docker)
#   --no-preflight  skip the connectivity probe before spending a trial
#   --no-isolate    DANGEROUS: drop the sealed network and give the trial container the
#    VM's whole network stack (the old --hostnet behaviour). The agent can then curl the
#    upstream commit or pip install the fixed package, so any reward it earns is suspect.
#   --isolate-all   seal oracle/nop too, not just the trial. Use it to prove the task
#    needs no network at RUN time; without it a sealed trial that fails for an
#    environment reason is hard to tell from a genuine model failure.
#   --no-tls-bridge  DANGEROUS on a sealed run: speak plaintext http to the bridge instead
#    of https. Harbor's egress sidecar then parses the model stream as HTTP and kills any
#    turn whose response headers take over 15s, which the agent reports as
#    "Unable to connect to API (ECONNRESET)" with no HTTP status. Diagnostics only.
#   --no-hostnet    do not use the host-network compose override; bridge the proxy instead
#    (also disables the seal)
#   --hostnet-file F  use this compose override instead of the generated one
#    (also disables the seal — you are supplying the networking yourself)
#   --no-disallow-tools  do not pass --ak disallowed_tools (web/plan tools stay enabled)
#   --no-idle-timeout-fix  trial only: do not pass API_FORCE_IDLE_TIMEOUT=0 /
#    CLAUDE_ENABLE_STREAM_WATCHDOG=0 / CLAUDE_ENABLE_BYTE_WATCHDOG=0, and do not raise the
#    subagent stall window. All four guard against "Stream idle timeout" aborting the
#    agent (and its recovery subagents) mid-response when going through a gateway/proxy
#    ANTHROPIC_BASE_URL — API_FORCE_IDLE_TIMEOUT alone is NOT sufficient for this, since
#    the event-level watchdog (CLAUDE_ENABLE_STREAM_WATCHDOG) is a separate, independent
#    5-min timer that is on by default for every provider including gateways.
#   --stall-timeout-ms N  ms for CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS (default: the task's
#    own [agent].timeout_sec from task.toml, so a stalled subagent is not killed sooner
#    than the whole trial would time out anyway; falls back to 5400000 = 90min if absent)
#   --userns-host   add userns_mode: host to the override (retry if tar chown still fails)
#   --keep          do not delete a previous run dir for this task+mode
#   (rubrics: if tests/rubrics.json exists, judge creds are exported for [verifier.env],
#    rewards are reported per key, and a failed in-container judge falls back to
#    host-side grading via mm_grade_rubrics.py)
#   --n_text_only=N trial only: text-only attempts, run FIRST on a copy of the task with
#                   every image stripped (build_text_only_copy). Default 3. ALL must fail
#                   (the image is really needed); one solve ends the trial unrecorded and
#                   the normal attempts are skipped. The circuit breaker stops the phase at
#                   that first solve. Output: <ROOT>/Trials/without_images.
#   --n_trial=N     trial only: normal attempts on the real bundle (pass@k). Default 4.
#                   Each attempt is a full agent run, so N times the spend. NOTE: this
#                   is NOT --n-trials/-l, which limits how many trials analyze reads.
#                   The trial is RECORDED only when the solves fall inside
#                   TRIAL_MIN_SOLVED..TRIAL_MAX_SOLVED (today exactly 1) AND every
#                   text-only attempt failed; all-failed also BLOCKS check-reviewers (RL
#                   needs one passing attempt). See trial_rule, post_trial_verdict, and
#                   MM_FORCE_TRIAL_RECORD. The circuit breaker stops the phase as soon as
#                   TRIAL_MAX_SOLVED+1 attempts solve (today 2): the trial is blocked anyway.
#   --no-circuit-breaker  trial only: run every attempt to completion instead of stopping a
#                   phase once its verdict is decided (env: MM_BREAKER_POLL=15 poll seconds,
#                   MM_BREAKER_GRACE=600 teardown seconds after SIGTERM before SIGKILL)
#   --no-qc         run harbor check even if the QC audit finds bundle FAILs
#   --no-file-check run harbor check even if required task files are missing
#   --no-integrity-check  run harbor check even if task metadata is internally inconsistent
#    (base_commit vs Dockerfile, files_edited vs fix.patch, f2p/p2p vs config.json, the
#     evidence posters vs both documents vs the Dockerfile's COPY, etc. — all offline; see
#     mm_check_integrity.py's own docstring for the full list)
#   --rubric F      rubric file for check/analyze     (default: harbor's built-in)
#   --check-prompt F  evaluator prompt file for check/analyze
#   --passing       analyze only passing trials (reward 1.0)
#   --failing       analyze only failing trials
#   -l N            analyze at most N trials
#
# `check` RUNS THROUGH CLAUDE CODE CHAT. Use /run-check, which reads the audit and the rubric
# findings back to you worst-first and asks before spending a credentialed run. Invoking
# `mm_run.sh <task> check` directly exits 8 without running anything. For CI and scripted runs:
#   MM_ALLOW_DIRECT=1   invoke check directly anyway
# The other modes (oracle, nop, analyze, rescore) are unaffected.
#
# `trial` REQUIRES BOTH CONTROLS FIRST. A trial number only means something once the task's
# own two controls agree: the oracle scored 1 (the tests CAN be passed) and nop scored 0
# (they are not passed for free). If either control is missing, unreadable, or scored
# something else, `mm_run.sh <task> trial` exits 9 without running anything and without
# spending credentials. Run them first — both are keyless unless the task ships
# tests/rubrics.json:
#   mm_run.sh <task> oracle     # expect reward 1
#   mm_run.sh <task> nop        # expect reward 0
# The controls are read from <ROOT>/Oracle and <ROOT>/Nop, the same dirs those modes write.
# A trial also requires both controls to have run against the CURRENT bundle: their recorded
# task digest (lock.json) must equal the task dir's digest now, or the stale one is named and
# must be re-run.
# For CI and scripted runs:
#   MM_ALLOW_UNVERIFIED=1   run the trial without the controls (skips rewards AND digests)
###############################################################################
set -uo pipefail

TASK_DIR=""; MODE=""
MODEL="anthropic/claude-opus-5-5"; AGENT="claude-code"
N_ATTEMPTS=4                          # normal trial attempts (pass@k); --n_trial=N overrides.
                                      # NB: distinct from N_TRIALS/-l, the analyze limit.
N_TEXT_ONLY=3                         # text-only attempts (images stripped); --n_text_only=N.
# THE TRIAL THRESHOLDS, in one place. The text-only attempts must ALL fail (the image is really
# needed); the normal attempts must solve between these two counts, inclusive. 1..1 = exactly 1
# of 4 passes. See trial_rule / text_only_rule.
TRIAL_MIN_SOLVED=1
TRIAL_MAX_SOLVED=1
# THE CIRCUIT BREAKER (trial only; see harbor_breaker). Attempts run concurrently, so a phase whose
# verdict is already decided would otherwise keep paying for attempts that cannot change it. The
# breaker watches the rewards while harbor runs and stops the phase the moment:
#   text-only: 1 attempt solves                    (text_only_rule: any solve fails the trial)
#   normal:    TRIAL_MAX_SOLVED + 1 attempts solve (trial_rule: above the band, too many solved)
# Both limits are DERIVED from the rules above, so changing the band moves the breaker with it.
# --no-circuit-breaker runs every attempt to completion (e.g. to see the full distribution).
BREAKER=1
BREAKER_POLL="${MM_BREAKER_POLL:-15}"     # seconds between reward polls
BREAKER_GRACE="${MM_BREAKER_GRACE:-600}"  # seconds harbor gets to tear down after SIGTERM before SIGKILL
BREAKER_TRIPPED=0; BREAKER_WATCH_PID=""
# check and analyze both default to claude-sonnet-5 — that is what the anonymizer
# serves for these two. Harbor's own defaults (claude-sonnet-4-6, claude-haiku-4-5) are
# NOT served, and an unserved name does not come back as a clean 404: the agent retries,
# dies, and the run reports "agent did not produce a valid result / missing result file"
# after burning the full wall clock. (The trial is a separate path — see MODEL above.)
CHECK_MODEL="claude-sonnet-5"; ANALYZE_MODEL="claude-sonnet-5"
RUBRIC=""; CHECK_PROMPT=""; ANALYZE_FILTER=""; N_TRIALS=""
ROOT=""; ROOT_GIVEN=0; HENV="docker"; PREFLIGHT=1; KEEP=0
# check-reviewers only: verify the SHIPPED Oracle/Nop/Trials against the bundle and mint both
# markers, so a reviewer need not re-run what the CB already paid for. See verify_recorded_runs.
REVIEWERS=0
FILE_CHECK=1                          # check mode verifies the task file names first
INTEGRITY_CHECK=1                     # check mode cross-checks task metadata for internal consistency
QC_CHECK=1                            # check mode runs the MM SWE QC audit first (--no-qc skips)
RUN_DIR=""                            # rescore: which run dir to fold a judge verdict into
HOSTNET=1; HOSTNET_FILE=""            # host-networking compose override (replaces the bridge)
HOSTNET_FILE_GIVEN=0                  # --hostnet-file was passed explicitly (disables isolation)
# ---- network isolation (the anti-cheat) -------------------------------------
# network_mode: host gives the agent container the VM's ENTIRE network stack, so a
# task.toml network policy of no_network/allowlist is silently unenforced and the agent
# can curl the upstream commit or pip install the fixed package. ISOLATE instead keeps the
# service inside harbor's egress sidecar and collapses the AGENT PHASE allowlist to the
# anonymizer — see the block above build_agent_seal for why the phase matters.
ISOLATE=1                             # trial: seal the agent phase to the model API only
ISOLATE_ALL=0                         # oracle/nop: also stay inside the egress sidecar
ALLOW_AGENT_HOST=""                   # passed to harbor as --allow-agent-host
ISO_COMPOSE=""                        # generated networking-free compose override
# ---- TLS on the bridge (required by the seal, see build_agent_seal) ----------
# Inside the sidecar's netns every connection is sniffed by gost, and gost's HTTP handler
# caps the upstream RESPONSE HEADERS at 15s — a slower model turn is delivered to the agent
# as an empty EOF, i.e. ECONNRESET with no HTTP status. TLS is sniffed as TLS and tunnelled
# raw instead, with no deadline. So the sealed path speaks https to the bridge.
TLS_BRIDGE=1                          # terminate TLS on the bridge when sealing
TLS_DIR=""; TLS_CERT=""; TLS_KEY=""   # generated per run, removed by cleanup()
CA_IN_CONTAINER="/etc/mm-anonymizer-ca.crt"   # where the seal compose mounts the cert
DISALLOW_TOOLS="WebSearch,WebFetch,EnterPlanMode"
IDLE_TIMEOUT_FIX=1                    # trial only: API_FORCE_IDLE_TIMEOUT=0 + a matching subagent stall window
STALL_TIMEOUT_MS=""                   # default: derived from the task's own [agent].timeout_sec; override with --stall-timeout-ms
USERNS_HOST=0                         # add userns_mode: host to the override (retry aid)
COMPOSE_SVC="${COMPOSE_SVC:-main}"    # harbor's environment service name
SETTINGS_JSON="${SETTINGS_JSON:-$HOME/.claude/settings.json}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_PID=""; BRIDGE_PORT=""; HOST_ADDR=""
BRIDGE_LOG="$(mktemp -t mm_bridge.XXXXXX.log)"
BRIDGE_LOG_KEEP=""                    # set per mode: where cleanup() copies the bridge log
GEN_COMPOSE=""
# ---- the OpenAI-format judge channel (see resolve_creds / resolve_eval_base) -------------
# A task whose tests/judge.py grades IN-BAND through an OpenAI-compatible endpoint reads
# EVAL_API_KEY / EVAL_BASE_URL / EVAL_MODEL, which task.toml's [verifier.env] sources from
# OPENAI_API_KEY / OPENAI_API_BASE. That is a SECOND channel: the anonymizer serves Claude
# format on 8091 and OpenAI format on 8090, and the runner used to forward only the first.
EVAL_KEY=""; EVAL_BASE=""; EVAL_MODEL_NAME=""; CEVAL_BASE=""
EVAL_BRIDGE_PID=""; EVAL_BRIDGE_PORT=""
EVAL_BRIDGE_LOG="$(mktemp -t mm_evalbridge.XXXXXX.log)"
cleanup(){ [ -n "$BREAKER_WATCH_PID" ] && kill "$BREAKER_WATCH_PID" 2>/dev/null
           [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null
           [ -n "$EVAL_BRIDGE_PID" ] && kill "$EVAL_BRIDGE_PID" 2>/dev/null
           rm -f "$EVAL_BRIDGE_LOG"
           # The bridge log is the only record of a mid-run teardown, so keep a copy next
           # to the run it belongs to before dropping the temp file.
           [ -n "${BRIDGE_LOG_KEEP:-}" ] && [ -s "$BRIDGE_LOG" ] && \
             cp -f "$BRIDGE_LOG" "$BRIDGE_LOG_KEEP" 2>/dev/null
           rm -f "$BRIDGE_LOG"; [ -n "$GEN_COMPOSE" ] && rm -f "$GEN_COMPOSE"
           [ -n "$ISO_COMPOSE" ] && rm -f "$ISO_COMPOSE"
           [ -n "$TLS_DIR" ] && rm -rf "$TLS_DIR"; return 0; }
trap cleanup EXIT INT TERM

ADJUDICATED=()
while [ $# -gt 0 ]; do
  case "$1" in
    --model) MODEL="$2"; shift 2;;
    --check-model) CHECK_MODEL="$2"; shift 2;;
    --analyze-model) ANALYZE_MODEL="$2"; shift 2;;
    --agent) AGENT="$2"; shift 2;;
    --root) ROOT="$2"; ROOT_GIVEN=1; shift 2;;
    --env) HENV="$2"; shift 2;;
    --rubric|-r) RUBRIC="$2"; shift 2;;
    --check-prompt) CHECK_PROMPT="$2"; shift 2;;
    --passing) ANALYZE_FILTER="--passing"; shift;;
    --failing) ANALYZE_FILTER="--failing"; shift;;
    -l|--n-trials) N_TRIALS="$2"; shift 2;;
    --no-preflight) PREFLIGHT=0; shift;;
    --no-file-check) FILE_CHECK=0; shift;;
    --no-integrity-check) INTEGRITY_CHECK=0; shift;;
    --no-qc) QC_CHECK=0; shift;;
    # Forwarded verbatim into qc_gate()'s audit. Repeatable, and the reason is quoted, so this
    # collects into an array rather than a string - "$2" holds `id=cleared:why like this` and
    # word-splitting it would hand fix.py a broken spec and a mystery parse error.
    --adjudicated) ADJUDICATED+=("$2"); shift 2;;
    --run) RUN_DIR="$2"; shift 2;;
    --n_trial=*) N_ATTEMPTS="${1#*=}"; shift;;
    --n_trial) N_ATTEMPTS="$2"; shift 2;;
    --n_text_only=*) N_TEXT_ONLY="${1#*=}"; shift;;
    --n_text_only) N_TEXT_ONLY="$2"; shift 2;;
    --no-circuit-breaker) BREAKER=0; shift;;
    --keep) KEEP=1; shift;;
    --no-hostnet) HOSTNET=0; ISOLATE=0; shift;;
    --hostnet-file) HOSTNET_FILE="$2"; HOSTNET=1; HOSTNET_FILE_GIVEN=1; ISOLATE=0; shift 2;;
    --no-isolate) ISOLATE=0; shift;;
    --isolate-all) ISOLATE_ALL=1; shift;;
    --no-tls-bridge) TLS_BRIDGE=0; shift;;
    --no-disallow-tools) DISALLOW_TOOLS=""; shift;;
    --no-idle-timeout-fix) IDLE_TIMEOUT_FIX=0; shift;;
    --stall-timeout-ms) STALL_TIMEOUT_MS="$2"; shift 2;;
    --userns-host) USERNS_HOST=1; shift;;
    -h|--help) sed -n '3,/^####/p' "$0" | sed '$d'; exit 0;;  # whole header, minus its banner
    *) if [ -z "$TASK_DIR" ]; then TASK_DIR="$1"; elif [ -z "$MODE" ]; then MODE="$1"; fi; shift;;
  esac
done
case "$N_ATTEMPTS" in
  ''|*[!0-9]*) echo "--n_trial must be a positive integer (got: '$N_ATTEMPTS')" >&2; exit 2;;
esac
[ "$N_ATTEMPTS" -ge 1 ] || { echo "--n_trial must be >= 1 (got: $N_ATTEMPTS)" >&2; exit 2; }
case "$N_TEXT_ONLY" in
  ''|*[!0-9]*) echo "--n_text_only must be a positive integer (got: '$N_TEXT_ONLY')" >&2; exit 2;;
esac
# No way to switch the text-only phase off: a trial without it cannot show the image is needed,
# and the record and the reviewer path both require it.
[ "$N_TEXT_ONLY" -ge 1 ] || { echo "--n_text_only must be >= 1 (got: $N_TEXT_ONLY)" >&2; exit 2; }
[ -n "$TASK_DIR" ] && [ -n "$MODE" ] || { echo "usage: mm_run.sh <task-dir> <oracle|nop|trial|pseudo-trial|check|check-reviewers|analyze|rescore> [opts]" >&2; exit 2; }
[ -d "$TASK_DIR" ] || { echo "error: no such directory: $TASK_DIR" >&2; exit 2; }

# ---- helpers (defined before first use: bash resolves functions at call time) ----
say(){ printf '[mm_run] %s\n' "$*" >&2; }
mask(){ [ -n "${1:-}" ] && printf '%s…%s' "${1:0:6}" "${1: -4}" || printf '(none)'; }
TASK_DIR="$(cd "$TASK_DIR" && pwd)"

# Nested layout: <root>/Tasks/<any-task-name>/task.toml. Pointed at Tasks/ (or the root above
# it), descend into the ONE task there, whatever its folder is called — same rule as the QC
# skill's qc_layout.find_task_dir. Several tasks is ambiguous: name them rather than pick one.
if [ ! -f "$TASK_DIR/task.toml" ] && [ ! -f "$TASK_DIR/project/task.toml" ]; then
  _cands=("$TASK_DIR/Tasks" "$TASK_DIR/tasks")
  case "$(basename "$TASK_DIR")" in [Tt]asks) _cands=("$TASK_DIR" "${_cands[@]}");; esac
  for _c in "${_cands[@]}"; do
    [ -d "$_c" ] || continue
    if [ -f "$_c/task.toml" ]; then TASK_DIR="$_c"; break; fi
    mapfile -t _kids < <(find "$_c" -mindepth 2 -maxdepth 2 -name task.toml -printf '%h\n' 2>/dev/null | sort)
    if [ "${#_kids[@]}" -eq 1 ]; then TASK_DIR="${_kids[0]}"; break; fi
    if [ "${#_kids[@]}" -gt 1 ]; then
      echo "error: $_c holds ${#_kids[@]} tasks ($(printf '%s ' "${_kids[@]##*/}")) - point at one of them" >&2
      exit 2
    fi
  done
fi

# Locate task.toml. The task lives under tasks/<id>/ with task.toml at its top.
# A legacy project/ wrapper (tasks/<id>/project/task.toml) is still tolerated.
# analyze is the exception: it consumes a FINISHED TRIAL, so its path may be a
# harbor job dir or a single trial dir with no task.toml anywhere in sight. Its
# input is classified (and resolved) below, after ROOT is known.
ANALYZE_SRC=""
if [ "$MODE" = analyze ]; then
  # A job dir carries a result.json of its own (the JobResult) exactly like a
  # trial dir does, so presence of that file cannot tell them apart. What can:
  # a job dir is a dir OF trial dirs, so one of its children holds a result.json.
  if   [ -f "$TASK_DIR/task.toml" ] || [ -f "$TASK_DIR/project/task.toml" ]; then ANALYZE_SRC=task
  elif compgen -G "$TASK_DIR/*/result.json" >/dev/null 2>&1;                 then ANALYZE_SRC=job
  elif [ -f "$TASK_DIR/result.json" ];                                       then ANALYZE_SRC=trial
  else                                                                            ANALYZE_SRC=job
  fi
fi
if   [ -f "$TASK_DIR/task.toml" ];          then :
elif [ -f "$TASK_DIR/project/task.toml" ];  then TASK_DIR="$TASK_DIR/project"
elif [ "$MODE" = analyze ];                 then :
else echo "error: no task.toml in $TASK_DIR (nor in $TASK_DIR/project)" >&2; exit 2; fi

# Task label — used ONLY for log output; every run dir is flat, so this affects no
# path. Prefer task_id from task.toml's [metadata] (the real identity), else the
# folder name. ID_DIR is what ROOT inference keys off, and skips a project/ wrapper.
ID_DIR="$TASK_DIR"
[ "$(basename "$TASK_DIR")" = "project" ] && ID_DIR="$(dirname "$TASK_DIR")"
TASK_ID="$(sed -n 's/^[[:space:]]*task_id[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$TASK_DIR/task.toml" 2>/dev/null | head -1)"
[ -n "$TASK_ID" ] || TASK_ID="$(basename "$ID_DIR")"
# Read by mm_cost.py's log_api_call (via qc_llm.py and mm_grade_rubrics.py) to tag the row.
export MM_COST_TASK_ID="$TASK_ID" MM_COST_TASK_DIR="$TASK_DIR"
COST_TRIAL_PASSED=0   # set by post_trial_verdict on a pass; honoured only in trial mode
COST_TRIAL_RESULT=""  # one-line outcome of the trial, stored with the CB-session cost reading

# Does this task carry a rubric (LLM judge)? If so the VERIFIER needs credentials too,
# so we export them for every mode — task.toml's [verifier.env] "${VAR:-}" entries expand
# from harbor's own environment. With no rubric, oracle/nop stay strictly keyless.
RUBRICS_FILE="$TASK_DIR/tests/rubrics.json"
HAS_RUBRICS=0; [ -f "$RUBRICS_FILE" ] && HAS_RUBRICS=1

# ROOT = the dir CONTAINING tasks/. If the task sits directly in tasks/ (no <id>
# subfolder), that is the parent of tasks/ too.
if [ -z "$ROOT" ]; then
  parent="$(dirname "$ID_DIR")"
  case "$(basename "$parent")" in
    [Tt]asks) ROOT="$(cd "$parent/.." && pwd)";;   # …/<root>/tasks/<id>  -> <root>
    *)        ROOT="$(cd "$parent" && pwd)";;      # task dir IS tasks/   -> its parent
  esac
fi

# The trial's two harbor jobs, laid out as the delivery template: one flat job dir per phase
# under Trials/, each holding harbor's config/lock/result/job.log, a harbor_run.log and the
# attempt dirs -- no timestamped job dir in between.
TRIALS_DIR="$ROOT/Trials/with_images"        # normal attempts, on the real bundle
TEXT_ONLY_DIR="$ROOT/Trials/without_images"  # text-only attempts, every image stripped

# analyze: decide WHAT gets analyzed, and keep ROOT above the job dir. Pointing at
# a single trial dir would otherwise infer ROOT=<the job dir> and harbor would
# write Analyze/ INSIDE Trials/. A task dir means "the trial I just ran".
ANALYZE_PATH=""
if [ "$MODE" = analyze ]; then
  case "$ANALYZE_SRC" in
    trial) [ "$ROOT_GIVEN" = 1 ] || ROOT="$(cd "$(dirname "$ID_DIR")/.." && pwd)"
           ANALYZE_PATH="$ID_DIR";;
    job)   ANALYZE_PATH="$ID_DIR";;
    task)  ANALYZE_PATH="$TRIALS_DIR";;
  esac
  # A job or trial under Trials/<phase>/ would otherwise leave ROOT at Trials/ or the phase dir,
  # and harbor would write Analyze/ inside the trial output. Climb back out to the root.
  if [ "$ROOT_GIVEN" != 1 ]; then
    while case "$(basename "$ROOT")" in Trials|with_images|without_images) true;; *) false;; esac; do
      ROOT="$(dirname "$ROOT")"
    done
  fi
fi


read_settings_env(){ [ -f "$SETTINGS_JSON" ] || return 0
  python3 - "$SETTINGS_JSON" "$1" <<'PY'
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: sys.exit(0)
v=(d.get("env") or {}).get(sys.argv[2])
if v: print(v)
PY
}

# ------------------------------------------------ credentials + proxy addressing
# Shared by check and analyze (the trial resolves its own inline). Order is the
# ProjectBench one: live env, then settings.json's .env, then the anonymizer
# defaults. Sets BASE and KEY.
resolve_creds(){
  KEY="${ANTHROPIC_API_KEY:-$(read_settings_env ANTHROPIC_API_KEY)}"
  BASE="${ANTHROPIC_BASE_URL:-$(read_settings_env ANTHROPIC_BASE_URL)}"
  : "${BASE:=http://localhost:8091}"
  : "${KEY:=anonymizer-placeholder}"
  JUDGE_MODEL="${JUDGE_MODEL:-$(read_settings_env JUDGE_MODEL)}"
  : "${JUDGE_MODEL:=claude-sonnet-5}"   # the anonymizer wants PLAIN model names

  # The OpenAI-format channel, resolved the same way. Defaults are derived from BASE rather
  # than hardcoded: the anonymizer exposes both formats on adjacent ports (Claude 8091,
  # OpenAI 8090), so a CB who moved the proxy keeps a working default. EVAL_MODEL is a
  # PROXY-QUALIFIED name ("anthropic/claude-...") because that channel is LiteLLM-style,
  # unlike JUDGE_MODEL which the anonymizer wants plain -- they are not interchangeable.
  EVAL_KEY="${OPENAI_API_KEY:-$(read_settings_env OPENAI_API_KEY)}"
  EVAL_BASE="${OPENAI_API_BASE:-$(read_settings_env OPENAI_API_BASE)}"
  : "${EVAL_KEY:=$KEY}"
  if [ -z "$EVAL_BASE" ]; then
    EVAL_BASE="$(printf '%s' "$BASE" | sed -E 's#:8091(/|$)#:8090\1#')"
    case "$EVAL_BASE" in */v1|*/v1/) ;; *) EVAL_BASE="${EVAL_BASE%/}/v1";; esac
  fi
  EVAL_MODEL_NAME="${EVAL_MODEL:-$(read_settings_env EVAL_MODEL)}"
  : "${EVAL_MODEL_NAME:=anthropic/claude-opus-4-5-20251101}"
  CEVAL_BASE="$EVAL_BASE"               # rewritten per mode by resolve_eval_base

  case "$BASE" in
    https://litellm-proxy.ml.scale.com*)
      say "NOTE: using the PUBLIC Scale endpoint ($BASE) because it was explicitly set."
      say "      Unset ANTHROPIC_BASE_URL (and the settings.json entry) to use the anonymizer.";;
  esac
}

# Which [verifier.env] entries does THIS task require from our environment, and are they here?
# harbor treats a "${VAR}" with no ":-" default as a REQUIRED host var and exits 1 with a bare
# "Missing Environment Variables" table (cli/jobs.py) before the container ever starts. Saying
# so ourselves turns that into an actionable message, and -- more importantly -- stops the
# runner announcing "judge creds forwarded" one line before harbor aborts for want of them.
preflight_verifier_env(){
  [ -f "$TASK_DIR/task.toml" ] || return 0
  local missing
  missing="$(python3 - "$TASK_DIR/task.toml" <<'PY'
import re, os, sys
txt = open(sys.argv[1], encoding="utf-8", errors="replace").read()
# the [verifier.env] block only, up to the next top-level table header
m = re.search(r"^\[verifier\.env\]\s*$(.*?)(?=^\[|\Z)", txt, re.M | re.S)
need = []
for line in (m.group(1).splitlines() if m else []):
    line = line.split("#", 1)[0]
    for var, default in re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:?-[^}]*)?\}", line):
        # a ":-"/"-" default means harbor can always expand it; only a bare ${VAR} is required
        if not default and var not in os.environ:
            need.append(var)
print(" ".join(sorted(set(need))))
PY
)"
  [ -n "$missing" ] || return 0
  say "ERROR: task.toml [verifier.env] requires host variables that are NOT set: $missing"
  say "       harbor validates these BEFORE the run and exits 1 without starting a container."
  say "       These carry the in-container rubric judge's credentials. Export them, e.g.:"
  say "         export OPENAI_API_KEY=\"\$ANTHROPIC_API_KEY\"   # anonymizer accepts either"
  say "         export OPENAI_API_BASE=\"$EVAL_BASE\""
  return 1
}

# Can a CONTAINER dial the OpenAI-format endpoint, and if not, what address can it dial?
#
# This is the same problem build_agent_seal solves for ANTHROPIC_BASE_URL, and it needs the
# same answer -- the runner used to solve it for one channel and pass the other through
# verbatim. The anonymizer binds BOTH ports to 127.0.0.1 only, so an in-container
# "localhost:8090" is the CONTAINER's loopback and connects to nothing.
#
#   host networking (the default)  the container shares the VM's stack, so localhost works
#                                  and no rewrite is wanted -- rewriting would be churn.
#   sealed / --no-hostnet          it does NOT, so relay through a bridge on an address the
#                                  container can actually reach.
#
# Sets CEVAL_BASE. Never fatal: the judge's own API backend falls through to the sub-agent
# request, and report() then grades host-side, so a failure here degrades rather than breaks.
resolve_eval_base(){  # $1 = 1 when the run is sealed (outside the host netns)
  local sealed="${1:-0}" host port upath
  CEVAL_BASE="$EVAL_BASE"
  case "$EVAL_BASE" in
    *://localhost*|*://127.0.0.1*) ;;
    *) return 0;;                       # already routable from anywhere; leave it alone
  esac
  if [ "$sealed" != 1 ] && [ "$HOSTNET" = 1 ]; then
    say "  in-container EVAL_BASE_URL=$CEVAL_BASE (host networking: the VM's loopback IS the container's)"
    return 0
  fi
  read host port upath < <(python3 - "$EVAL_BASE" <<'PY'
import sys, urllib.parse as u
p = u.urlparse(sys.argv[1] if "://" in sys.argv[1] else "http://" + sys.argv[1])
print(p.hostname or "127.0.0.1", p.port or 80, p.path or "-")
PY
)
  [ "$upath" = "-" ] && upath=""
  EVAL_BRIDGE_PORT=""
  python3 "$HERE/sandbox_proxy_bridge.py" --upstream-host "$host" --upstream-port "$port" \
    --listen-host 0.0.0.0 --listen-port 0 --gateway 0.0.0.0 >"$EVAL_BRIDGE_LOG" 2>&1 &
  EVAL_BRIDGE_PID=$!
  local _i
  for _i in $(seq 1 12); do grep -q '^BRIDGE_' "$EVAL_BRIDGE_LOG" 2>/dev/null && break; sleep 0.3; done
  if ! grep -q '^BRIDGE_READY ' "$EVAL_BRIDGE_LOG"; then
    say "WARNING: judge bridge failed ($(tr '\n' ' ' <"$EVAL_BRIDGE_LOG")) — the in-container"
    say "         judge will fall back to a sub-agent request and report() grades host-side."
    EVAL_BRIDGE_PID=""; return 0
  fi
  EVAL_BRIDGE_PORT="$(sed -n 's/^BRIDGE_READY //p' "$EVAL_BRIDGE_LOG" | sed 's#.*:##')"
  say "judge bridge: 0.0.0.0:$EVAL_BRIDGE_PORT -> $host:$port (OpenAI format, plaintext)"
  # Reuse an address already proven reachable; only probe when we do not have one. The probe
  # is per-port, so a HOST_ADDR proven for the model bridge is not assumed for this one.
  if ! resolve_host_addr "$EVAL_BRIDGE_PORT"; then
    say "WARNING: no address reaches the VM from a container on port $EVAL_BRIDGE_PORT —"
    say "         leaving EVAL_BASE_URL unrewritten; the judge will fall back."
    return 0
  fi
  CEVAL_BASE="http://$HOST_ADDR:$EVAL_BRIDGE_PORT$upath"
  say "  in-container EVAL_BASE_URL=$CEVAL_BASE"
  return 0
}

# Everything the VERIFIER phase needs, on BOTH judge channels.
#
# harbor expands [verifier.env]'s "${VAR}" entries from OUR environment, so the only way to
# reach the in-container judge is to export the names the task actually references. Tasks
# differ: some read ANTHROPIC_*/JUDGE_MODEL (Claude format), some EVAL_*/OPENAI_* (OpenAI
# format). Exporting both costs nothing and removes the coin-flip.
export_judge_env(){  # $1 = in-container Claude base, $2 = in-container OpenAI base
  export ANTHROPIC_BASE_URL="$1" ANTHROPIC_API_KEY="$KEY" JUDGE_MODEL="$JUDGE_MODEL"
  export OPENAI_API_BASE="$2" OPENAI_API_KEY="$EVAL_KEY"
  export EVAL_BASE_URL="$2" EVAL_API_KEY="$EVAL_KEY" EVAL_MODEL="$EVAL_MODEL_NAME"
}

# Echo a harbor command with any API-key value masked. The key has to be passed
# to harbor via --ae, but it must never be echoed into a log.
# harbor, with its console output also kept in the job dir as harbor_run.log, the way the
# delivery template carries it. harbor accepts a job dir that exists but holds no config.json,
# so the dir is made first and the log lands beside the job's own files.
harbor_logged(){  # $1 = job dir, rest = harbor args -> harbor's rc
  local jd="$1"; shift
  mkdir -p "$jd"
  harbor "$@" 2>&1 | tee -a "$jd/harbor_run.log"
  return "${PIPESTATUS[0]}"
}

# ---- circuit breaker (trial phases) -----------------------------------------------------------
# harbor_logged plus a watcher that stops harbor once <limit> attempts have solved the task.
# harbor stays in the FOREGROUND exactly as in harbor_logged, so Ctrl-C reaches it as before; the
# watcher is the background job. The subshell writes its own PID and then execs harbor, so that
# PID IS harbor's. SIGTERM is harbor's graceful stop (cli/jobs.py maps it to KeyboardInterrupt):
# running attempts are cancelled (CancelledError, no reward), their environments are torn down
# under asyncio.shield, and the job dir keeps every finished attempt. A cancelled attempt has no
# reward, so the tally afterwards holds only the attempts that finished, and the existing verdict
# logic reads it unchanged: a solve-decided outcome (any text-only solve; too-many/all-solved in
# the normal phase) is exempt from the "incomplete" rule because no missing attempt could undo it.
# Sets BREAKER_TRIPPED=1 when it fired; returns harbor's rc, or 0 when the breaker stopped it.
harbor_breaker(){  # $1 = job dir, $2 = solves that decide the phase, $3 = phase label, rest = harbor args
  local jd="$1" limit="$2" label="$3"; shift 3
  BREAKER_TRIPPED=0
  if [ "$BREAKER" != 1 ]; then harbor_logged "$jd" "$@"; return $?; fi
  mkdir -p "$jd"
  local ctl rc
  ctl="$(mktemp -d -t mm_breaker.XXXXXX)" || { say "circuit breaker unavailable (no temp dir) — running without it"; harbor_logged "$jd" "$@"; return $?; }
  breaker_watch "$jd" "$limit" "$label" "$ctl/harbor.pid" "$ctl/tripped" &
  BREAKER_WATCH_PID=$!
  ( printf '%s\n' "$BASHPID" > "$ctl/harbor.pid"; exec harbor "$@" ) 2>&1 | tee -a "$jd/harbor_run.log"
  rc="${PIPESTATUS[0]}"
  kill "$BREAKER_WATCH_PID" 2>/dev/null; wait "$BREAKER_WATCH_PID" 2>/dev/null; BREAKER_WATCH_PID=""
  if [ -f "$ctl/tripped" ]; then BREAKER_TRIPPED=1; rc=0; breaker_reap "$jd"; fi
  rm -rf "$ctl"
  return "$rc"
}

# After a trip, finish the teardown harbor started. Measured on harbor 0.18: the breaker fires the
# moment an attempt's verifier writes its reward, which is BEFORE harbor has torn that attempt's
# environment down. SIGTERM then interrupts the teardown ("Cleanup interrupted ... shielded and
# will complete") but the process exits before `docker compose down` runs, leaving each attempt's
# container stopped-but-present and its <project>_default network behind. Scoped strictly to THIS
# job: harbor names an attempt's compose project <sanitized attempt-dir name>__env (docker.py:
# _sanitize_docker_compose_project_name), and only projects for attempt dirs under $jd are touched.
# Images are kept: they are the build cache the next phase reuses.
breaker_reap(){  # $1 = job dir
  local jd="$1" d p ids n=0
  command -v docker >/dev/null 2>&1 || return 0
  for d in "$jd"/*/; do
    [ -d "$d" ] || continue
    p="$(basename "$d" | tr '[:upper:]' '[:lower:]' | sed -e 's/[^a-z0-9_-]/-/g' -e 's/^[^a-z0-9]/0&/')__env"
    ids="$(docker ps -aq --filter "label=com.docker.compose.project=$p" 2>/dev/null)"
    [ -n "$ids" ] && { docker rm -f $ids >/dev/null 2>&1; n=$((n + $(wc -w <<<"$ids"))); }
    ids="$(docker network ls -q --filter "label=com.docker.compose.project=$p" 2>/dev/null)"
    [ -n "$ids" ] && docker network rm $ids >/dev/null 2>&1
    ids="$(docker volume ls -q --filter "label=com.docker.compose.project=$p" 2>/dev/null)"
    [ -n "$ids" ] && docker volume rm $ids >/dev/null 2>&1
  done
  [ "$n" -gt 0 ] && say "circuit breaker: removed $n leftover attempt container(s) and their networks."
  return 0
}

breaker_watch(){  # $1 = job dir, $2 = limit, $3 = label, $4 = harbor pid file, $5 = trip flag file
  local jd="$1" limit="$2" label="$3" pidf="$4" flag="$5" hpid="" t solved total waited=0
  while :; do
    sleep "$BREAKER_POLL"
    [ -n "$hpid" ] || hpid="$(cat "$pidf" 2>/dev/null)"
    [ -n "$hpid" ] || continue
    kill -0 "$hpid" 2>/dev/null || return 0
    t="$(trial_tally "$jd")"; [ -n "$t" ] || continue
    total="${t##* }"; solved=$(( total - ${t%% *} ))
    [ "$solved" -ge "$limit" ] || continue
    : > "$flag"   # before the kill, so the caller sees the trip even if harbor exits instantly
    say ""
    say "CIRCUIT BREAKER — $label: $solved of $total finished attempt(s) solved the task, which already"
    say "  decides this phase. Stopping harbor (SIGTERM) so the remaining attempts are not paid for."
    kill -TERM "$hpid" 2>/dev/null
    while kill -0 "$hpid" 2>/dev/null && [ "$waited" -lt "$BREAKER_GRACE" ]; do sleep 5; waited=$((waited + 5)); done
    if kill -0 "$hpid" 2>/dev/null; then
      say "CIRCUIT BREAKER — harbor still running ${BREAKER_GRACE}s after SIGTERM; sending SIGKILL."
      say "  Its environments may not have been torn down: check  docker ps  for leftover containers."
      kill -KILL "$hpid" 2>/dev/null
    fi
    return 0
  done
}

say_harbor(){
  local out="" a
  for a in "$@"; do
    case "$a" in ANTHROPIC_API_KEY=*) a="ANTHROPIC_API_KEY=$(mask "${a#*=}")";; esac
    out="$out $a"
  done
  say "harbor$out"
}

probe_image(){  # prefer an already-local image so a fresh sandbox does not pull
  local img
  img="$(docker image ls --format '{{.Repository}}:{{.Tag}}' 2>/dev/null \
         | grep -E '^(python|alpine/python|docker\.io/library/python):' | head -1)"
  printf '%s' "${img:-python:3-slim}"
}

container_can_reach(){  # $1 image  $2 host  $3 port
  # No --add-host here: harbor does not add one either, so the probe must see
  # exactly what the check/analyze container will see. -i is required or the
  # heredoc is never forwarded and python exits 0 without opening a socket —
  # a probe that "passes" silently.
  docker run --rm -i "$1" python3 - "$2" "$3" >/dev/null 2>&1 <<'PY'
import sys, socket
s = socket.socket(); s.settimeout(6)
s.connect((sys.argv[1], int(sys.argv[2]))); s.close()
PY
}

# Which address can a CONTAINER dial to reach <port> on this VM? Probe, do not
# guess: under rootless docker the bridge gateway (172.17.0.1) does not route to
# the host and host.docker.internal does not resolve, while the host's own
# route-source IP does. Sets HOST_ADDR.
resolve_host_addr(){  # $1 = port on the VM
  local port="$1" img cand; img="$(probe_image)"
  local -a cands=()
  [ -n "${PB_HOST_ADDR:-}" ] && cands+=("$PB_HOST_ADDR")
  cand="$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p' | head -1)"
  [ -n "$cand" ] && cands+=("$cand")
  cand="$(docker network inspect bridge -f '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null | grep -E '^[0-9]' | head -1)"
  [ -n "$cand" ] && cands+=("$cand")
  cands+=(host.docker.internal)
  HOST_ADDR=""
  for cand in "${cands[@]}"; do
    if container_can_reach "$img" "$cand" "$port"; then
      HOST_ADDR="$cand"; say "container reaches the VM at $cand:$port (probed via $img)"; return 0
    fi
    say "  probe: $cand:$port not reachable from a container"
  done
  return 1
}

# Point the check/analyze container at the anonymizer. Neither subcommand accepts
# --extra-docker-compose, and both overwrite config.environment when given a -c
# JobConfig, so host networking is not an option: the container must dial an
# address that routes back here. Falls back to the TCP bridge when the proxy port
# itself is unreachable (proxy bound to the VM's loopback only). Sets CBASE.
setup_anon_route(){
  local host port upath
  read host port upath < <(python3 - "$BASE" <<'PY'
import sys, urllib.parse as u
p = u.urlparse(sys.argv[1] if "://" in sys.argv[1] else "http://" + sys.argv[1])
print(p.hostname or "127.0.0.1", p.port or (443 if p.scheme == "https" else 80), p.path or "-")
PY
)
  [ "$upath" = "-" ] && upath=""
  CBASE="$BASE"
  case "$BASE" in
    *://localhost*|*://127.0.0.1*) ;;
    *) say "base URL is not loopback — passing $CBASE through unchanged"; return 0;;
  esac

  if resolve_host_addr "$port"; then
    CBASE="http://$HOST_ADDR:$port$upath"
    say "container will dial the anonymizer directly at $CBASE"
    return 0
  fi

  say "no address reached $host:$port — starting the TCP bridge and re-probing"
  python3 "$HERE/sandbox_proxy_bridge.py" --upstream-host "$host" --upstream-port "$port" \
    --listen-host 0.0.0.0 --listen-port 0 --gateway 0.0.0.0 >"$BRIDGE_LOG" 2>&1 &
  BRIDGE_PID=$!
  for _ in $(seq 1 12); do grep -q '^BRIDGE_' "$BRIDGE_LOG" 2>/dev/null && break; sleep 0.3; done
  if ! grep -q '^BRIDGE_READY ' "$BRIDGE_LOG"; then
    BRIDGE_PID=""
    say "WARNING: bridge failed ($(tr '\n' ' ' <"$BRIDGE_LOG")) — the agent will not reach the model."
    return 0
  fi
  local bport; bport="$(sed -n 's/^BRIDGE_READY //p' "$BRIDGE_LOG" | sed 's#.*:##')"
  if resolve_host_addr "$bport"; then
    CBASE="http://$HOST_ADDR:$bport$upath"
    say "bridged: container will dial $CBASE -> $host:$port"
  else
    say "WARNING: not even the bridge on port $bport is reachable from a container —"
    say "         the agent will not reach the model. Check the proxy is up on the VM"
    say "         (curl -s \$ANTHROPIC_BASE_URL)."
  fi
}

# ============================================ agent-phase seal (the anti-cheat)
# THE PROBLEM. The old override put harbor's environment service on `network_mode: host`,
# purely so the container's localhost would be the VM's localhost and it could reach the
# anonymizer. The side effect is total: the container inherits the VM's ENTIRE network
# stack, so `curl`, `pip install` and `git fetch` all work and the agent can just fetch
# the upstream fix. task.toml does not save you — harbor's egress-control sidecar only
# captures services that do NOT declare their own networking
# (docker.py::_egress_controlled_service_names), and `network_mode: host` is exactly such
# a declaration. So a task asking for `[agent] network_mode = "no-network"` silently got
# the whole internet, with the sidecar still running and looking like it worked.
#
# THE FIX — and why it is NOT a sealed docker network. The obvious move is to put `main`
# on an `internal: true` network with a relay to the model API. That does seal it, but it
# seals the WRONG WINDOW: harbor installs the agent INSIDE the container before the agent
# phase begins (trial.py::_setup_agent -> claude_code.py::install, which curls
# downloads.claude.ai). A network sealed at compose level is already sealed then, so the
# install dies with "Could not resolve host" and the trial errors as NetworkConnectionError
# before the model is ever contacted.
#
# harbor already models this correctly, per PHASE: the environment baseline
# (`[environment] network_mode`, normally public) covers setup and agent installation, and
# `[agent] network_mode` applies during agent.run() only. So the right fix is to stop
# fighting the sidecar and let it do its job:
#
#   * DON'T declare networking on `main` — that puts it back inside the sidecar's netns,
#     so harbor's per-phase policy actually applies to it.
#   * Point the agent at a host ADDRESS rather than localhost — the sidecar netns has its own
#     loopback, so an in-container http://localhost:8091 is ConnectionRefused (measured).
#     resolve_host_addr probes for an address that actually works.
#   * Terminate TLS on that hop (the bridge). This is the part that is NOT optional: gost
#     parses plaintext HTTP and kills any turn needing >15s for response headers. Note the
#     bridge is not required for mere REACHABILITY here — slirp4netns maps 10.0.2.2 onto the
#     host's loopback — so TLS is its real justification. See start_host_bridge.
#   * Pass `--allow-agent-host <addr>`, which harbor merges into the agent-phase allowlist
#     "during agent.run() only". Under a no-network/allowlist agent phase that collapses
#     the reachable world to exactly the anonymizer.
#
# Result: setup and agent install work (baseline is public), and the moment the agent
# starts, the only reachable address is the model API. pip and curl have nowhere to go.
#
# WHY THE MODEL ROUTE MUST BE HTTPS (the ECONNRESET this seal originally caused).
# Moving `main` into the sidecar's netns puts gost in the path of the model traffic for the
# first time — previously the trial reached the anonymizer over host networking, untouched.
# gost does not blindly tunnel: it SNIFFS each connection to match the allowlist, and for
# plaintext HTTP it terminates the protocol and applies a 15-SECOND DEADLINE to reading the
# upstream response HEADERS. Measured on this exact sidecar, deterministically:
#
#   upstream takes 14s to send headers -> delivered at 14.02s
#   upstream takes 16s                 -> CLEAN EOF, ZERO BYTES, at exactly 15.00s
#   upstream takes 20s / 30s           -> same, always 15.00s
#
# The agent cannot tell that from a dead socket: no HTTP response ever arrives, so it logs
# `API Error: Unable to connect to API (ECONNRESET)` with `error_status: null`, and every
# retry dies identically for as long as the model stays slow. Streaming BODIES are fine —
# once headers are through, 30s gaps between SSE chunks relay indefinitely — and so is a
# 900KB request body. It is purely time-to-first-response-byte.
#
# TLS escapes it: gost sniffs TLS (SNI, or nothing at all when the target is a bare IP),
# matches the allowlist by ADDRESS, then forwards raw TCP. Measured on the same setup, 25s
# and 45s header latencies both come back intact. A non-HTTP payload behaves the same way,
# confirming the deadline belongs to gost's HTTP handler and not to the netns or the bridge.
# So the bridge terminates TLS and the agent gets NODE_EXTRA_CA_CERTS. This also happens to
# be what a real deployment looks like — a real API base URL is https, which is why nothing
# hit this until a plaintext loopback anonymizer was put behind the sidecar.
#
# NOTE ON SCOPE. This is harbor's enforcement, so it only bites when the task ASKS for it.
# A task whose agent phase is `public` (or unset) gets no egress control at all — harbor
# skips the sidecar entirely (_requires_egress_control) and warns that extra allowlist
# hosts are ignored. That is the correct semantics: task.toml is now honoured instead of
# silently overridden. build_agent_seal says so out loud rather than implying a seal that
# is not there.

# Which addresses might a container use to reach this VM? resolve_host_addr probes these one
# at a time; the TLS cert has to cover all of them because it is generated BEFORE the probe
# (the probe needs the bridge already listening). Keep the two lists in step.
candidate_host_addrs(){
  local cand
  [ -n "${PB_HOST_ADDR:-}" ] && printf '%s\n' "$PB_HOST_ADDR"
  cand="$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p' | head -1)"
  [ -n "$cand" ] && printf '%s\n' "$cand"
  cand="$(docker network inspect bridge -f '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null | grep -E '^[0-9]' | head -1)"
  [ -n "$cand" ] && printf '%s\n' "$cand"
  printf '%s\n' "127.0.0.1"
}

# Generate the bridge's TLS keypair. Self-signed and CA:TRUE so it works both as the leaf
# the agent connects to and as the trust anchor it is handed via NODE_EXTRA_CA_CERTS. Every
# candidate address goes in as an IP SAN, so whichever one resolve_host_addr settles on
# still verifies. Sets TLS_DIR/TLS_CERT/TLS_KEY.
gen_bridge_tls(){
  command -v openssl >/dev/null 2>&1 || { say "ERROR: openssl not found — cannot build the TLS bridge"; return 1; }
  TLS_DIR="$(mktemp -d -t mm_tls.XXXXXX)"
  TLS_CERT="$TLS_DIR/anonymizer-ca.crt"; TLS_KEY="$TLS_DIR/anonymizer-ca.key"
  local san="" a
  while read -r a; do [ -n "$a" ] && san="${san}${san:+,}IP:$a"; done < <(candidate_host_addrs)
  san="${san},DNS:host.docker.internal"
  if ! openssl req -x509 -newkey rsa:2048 -nodes -keyout "$TLS_KEY" -out "$TLS_CERT" \
        -days 2 -subj "/CN=mm-anonymizer-bridge" \
        -addext "subjectAltName=$san" \
        -addext "basicConstraints=critical,CA:TRUE" >/dev/null 2>&1; then
    say "ERROR: openssl could not generate the bridge certificate"; return 1
  fi
  # The container reads this through a bind mount as a non-root agent user.
  chmod 755 "$TLS_DIR"; chmod 644 "$TLS_CERT"; chmod 600 "$TLS_KEY"
  say "bridge TLS cert: $TLS_CERT (SAN $san)"
  return 0
}

# Start the host-side loopback->0.0.0.0 forwarder.
#
# What the bridge is REALLY for on the sealed path: TLS TERMINATION. With TLS_CERT set it
# speaks TLS to the container, which is what keeps gost from parsing the stream as HTTP and
# applying its 15s response-header deadline (see build_agent_seal).
#
# It is NOT necessarily needed for reachability, and an older comment here claiming
# "the anonymizer binds 127.0.0.1 only, so nothing in the sidecar's netns can reach it" was
# wrong on this host. Two separate facts, both measured:
#   * the container's OWN loopback is not the VM's, so an in-container http://localhost:8091
#     really does fail (ConnectionRefused) — that part holds;
#   * but under rootless docker, slirp4netns maps its gateway address (10.0.2.2) onto the
#     HOST's 127.0.0.1, so http://10.0.2.2:8091 reaches the loopback-bound anonymizer
#     directly, with no bridge at all. Verified both ways: real anonymizer bytes from inside
#     a container, ConnectionRefused for the same address from the host itself.
# That mapping is a slirp4netns default (`--disable-host-loopback` turns it off) and is absent
# under pasta or rootful docker, so it must not be assumed — which is exactly why
# resolve_host_addr PROBES for a working address instead of hardcoding one.
# Sets BRIDGE_PORT/BRIDGE_PID.
start_host_bridge(){  # $1 = upstream host, $2 = upstream port
  BRIDGE_PORT=""
  local -a targs=()
  [ -n "$TLS_CERT" ] && targs=(--tls-cert "$TLS_CERT" --tls-key "$TLS_KEY")
  python3 "$HERE/sandbox_proxy_bridge.py" --upstream-host "$1" --upstream-port "$2" \
    --listen-host 0.0.0.0 --listen-port 0 --gateway 0.0.0.0 "${targs[@]}" >"$BRIDGE_LOG" 2>&1 &
  BRIDGE_PID=$!
  local _i
  for _i in $(seq 1 12); do grep -q '^BRIDGE_' "$BRIDGE_LOG" 2>/dev/null && break; sleep 0.3; done
  if ! grep -q '^BRIDGE_READY ' "$BRIDGE_LOG"; then
    say "ERROR: host bridge failed ($(tr '\n' ' ' <"$BRIDGE_LOG"))"
    BRIDGE_PID=""; return 1
  fi
  BRIDGE_PORT="$(sed -n 's/^BRIDGE_READY //p' "$BRIDGE_LOG" | sed 's#.*:##')"
  say "host bridge: 0.0.0.0:$BRIDGE_PORT -> $1:$2 ($([ -n "$TLS_CERT" ] && printf 'TLS terminated at the bridge' || printf 'plaintext'))"
  return 0
}

# Read a phase's network_mode out of task.toml. $1 = agent|verifier|environment.
task_network_mode(){
  sed -n "/^\[$1\]/,/^\[/{s/^[[:space:]]*network_mode[[:space:]]*=[[:space:]]*[\"']\([^\"']*\)[\"'].*/\1/p}" \
    "$TASK_DIR/task.toml" 2>/dev/null | head -1
}

# Prepare the agent-phase seal. Writes a networking-FREE compose override (so `main` stays
# inside harbor's egress sidecar), points the container at the anonymizer via a host
# address, and sets ALLOW_AGENT_HOST for --allow-agent-host. Sets CBASE. Returns non-zero
# if the model route cannot be built, in which case the caller decides what to do.
build_agent_seal(){
  local host port upath mode
  mode="$(task_network_mode agent)"

  case "$mode" in
    no-network|no_network|none|allowlist)
      say "task.toml [agent] network_mode = '$mode' -> harbor WILL enforce the agent phase";;
    "")
      say "WARNING: task.toml declares no [agent] network_mode, so harbor applies no egress"
      say "         control during the agent phase. The trial is NOT sealed: the agent can"
      say "         curl or pip install the answer. Add [agent] network_mode = \"no-network\""
      say "         to the task to close this — it is the task's call, not the runner's.";;
    public)
      say "WARNING: task.toml sets [agent] network_mode = 'public', so the agent phase is"
      say "         deliberately unrestricted and NOT sealed. Any reward is unverified.";;
    *)
      say "NOTE: task.toml [agent] network_mode = '$mode' (unrecognised here; passing through)";;
  esac

  case "$BASE" in
    *://localhost*|*://127.0.0.1*) ;;
    *) say "base URL is not loopback — passing $BASE through unchanged"
       CBASE="$BASE"; ALLOW_AGENT_HOST="$(printf '%s' "$BASE" | sed -E 's#^[a-z]+://##; s#[:/].*##')"
       say "agent-phase allowlist host: $ALLOW_AGENT_HOST"
       return 0;;
  esac

  read host port upath < <(python3 - "$BASE" <<'PY'
import sys, urllib.parse as u
p = u.urlparse(sys.argv[1] if "://" in sys.argv[1] else "http://" + sys.argv[1])
print(p.hostname or "127.0.0.1", p.port or 80, p.path or "-")
PY
)
  [ "$upath" = "-" ] && upath=""

  # TLS is not decoration here — see the block above build_agent_seal. Inside the sidecar's
  # netns, plaintext HTTP is parsed by gost, which drops any response whose headers take
  # longer than 15s; TLS is tunnelled untouched.
  if [ "$TLS_BRIDGE" = 1 ]; then
    gen_bridge_tls || { say "ERROR: could not generate the bridge TLS cert"; return 1; }
  else
    say "WARNING: --no-tls-bridge — the agent will speak PLAINTEXT http to the bridge, so"
    say "         harbor's egress sidecar (gost) parses it as HTTP and kills any model turn"
    say "         that takes over 15s to return response headers. The agent reports that as"
    say "         'API Error: Unable to connect to API (ECONNRESET)' with no HTTP status."
  fi

  start_host_bridge "$host" "$port" || return 1
  if ! resolve_host_addr "$BRIDGE_PORT"; then
    say "ERROR: no address reaches the VM from a container — the agent cannot reach the"
    say "       model once it is inside the egress sidecar's network namespace."
    return 1
  fi
  if [ -n "$TLS_CERT" ]; then
    CBASE="https://$HOST_ADDR:$BRIDGE_PORT$upath"
  else
    CBASE="http://$HOST_ADDR:$BRIDGE_PORT$upath"
  fi
  ALLOW_AGENT_HOST="$HOST_ADDR"
  say "agent phase: allowlist collapses to $ALLOW_AGENT_HOST (the anonymizer relay) only"
  say "  in-container ANTHROPIC_BASE_URL=$CBASE"
  return 0
}

# A compose override that carries TAR_OPTIONS, the bridge CA, and NOTHING about networking.
# Declaring any network_mode/networks here would opt `main` out of harbor's egress sidecar
# and silently disable the very enforcement we are relying on — that is the original bug.
# A `volumes:` entry is safe: _egress_controlled_service_names only looks for
# network_mode/networks, so mounting a file does not take the service out of the sidecar.
build_seal_compose(){
  ISO_COMPOSE="$(mktemp -t mm_seal.XXXXXX.yaml)"
  {
    echo "# generated by mm_run.sh — TAR_OPTIONS${TLS_CERT:+ + the bridge CA} only."
    echo "# Deliberately declares NO networking: harbor's egress-control sidecar skips any"
    echo "# service that defines network_mode/networks, which would disable the seal."
    echo "services:"
    echo "  ${COMPOSE_SVC}:"
    [ "$USERNS_HOST" = 1 ] && echo '    userns_mode: "host"'
    if [ -n "$TLS_CERT" ]; then
      echo "    volumes:"
      echo "      - \"$TLS_CERT:$CA_IN_CONTAINER:ro\""
    fi
    echo "    environment:"
    echo "      TAR_OPTIONS: --no-same-owner"
  } > "$ISO_COMPOSE"
  HOSTNET_FILE="$ISO_COMPOSE"
  say "compose override: $ISO_COMPOSE (tar fix${TLS_CERT:+ + CA mount at $CA_IN_CONTAINER}, no networking — seal intact)"
}

# ------------------------------------------------- docker-compose override (all modes)
# This is the UNSEALED override, used by oracle/nop and by a trial that opted out of the
# seal (--no-isolate / --no-hostnet / --hostnet-file). A sealed trial does NOT come through
# here — it uses build_seal_compose, which deliberately declares no networking. Two purposes:
#   * TAR_OPTIONS=--no-same-owner — GNU tar honors this on every invocation, fixing
#     "Cannot change ownership to uid ..." extraction failures under the sandbox's
#     nested-docker user namespace (e.g. flutter's gradle-wrapper fetch). This breaks the
#     ENVIRONMENT BUILD, so it must apply to oracle and nop too, not just the trial.
#   * network_mode: host — lets the container reach the anonymizer on the VM's loopback.
#     This is also exactly what defeats task.toml's egress policy, which is why it is no
#     longer the trial's default: see the block above build_agent_seal.
# Precedence: --hostnet-file  >  tarfix.yaml shipped next to this script  >  generated.
resolve_compose(){
  [ "$HOSTNET" = 1 ] || { HOSTNET_FILE=""; return 0; }
  if [ -n "$HOSTNET_FILE" ]; then
    [ -f "$HOSTNET_FILE" ] || { say "ERROR: --hostnet-file $HOSTNET_FILE does not exist"; return 3; }
    say "compose override: $HOSTNET_FILE (provided)"
  elif [ "$USERNS_HOST" = 0 ] && [ -f "$HERE/tarfix.yaml" ]; then
    HOSTNET_FILE="$HERE/tarfix.yaml"
    say "compose override: $HOSTNET_FILE (shipped)"
  else
    GEN_COMPOSE="$(mktemp -t mm_compose.XXXXXX.yaml)"
    {
      echo "# generated by mm_run.sh"
      echo "services:"
      echo "  ${COMPOSE_SVC}:"
      echo "    network_mode: host"
      [ "$USERNS_HOST" = 1 ] && echo '    userns_mode: "host"'
      echo "    environment:"
      echo "      TAR_OPTIONS: --no-same-owner"
    } > "$GEN_COMPOSE"
    HOSTNET_FILE="$GEN_COMPOSE"
    say "compose override: $HOSTNET_FILE (generated, service '${COMPOSE_SVC}'$([ "$USERNS_HOST" = 1 ] && printf ', userns_mode=host'))"
  fi
  return 0
}

# ------------------------------------------------------------ post-trial verdict (hardening)
# A trial measures whether the AGENT can solve the task. reward 0 is the wanted outcome: the
# agent failed, so the task discriminates. A non-zero reward means the model solved it, and a
# task a model already solves says nothing about the model being measured — it must be hardened.
#
# THE QC MARKER IS NEVER DELETED HERE. An earlier version removed it on reward 0. That threw
# away the positive record that an audit passed THIS bundle, in response to a result that says
# nothing about whether the audit is still accurate — and the hygiene job it was doing (one
# global marker vouching for the next task) is already done properly by the task_dir check.
#
# INSTEAD, a trial the task SURVIVED writes a second record: $QC_TRIAL_MARKER. It carries the
# same digest block as the QC marker, so anything reading it can prove the trial it describes
# was run on the bundle in front of them. A record that merely said "a trial passed once" would
# survive every subsequent edit and vouch for files the trial never saw — which is the whole
# reason absence of a file is not a usable signal either.
#
# WHICH RESULTS COUNT. A trial is two runs (see trial_rule), and BOTH must hold:
#
#   Trials/without_images/  every text-only attempt failed (the image is really needed), and
#                     the run's digest matches the image-stripped copy of the bundle as it is now
#                     (check_text_only_run). Otherwise nothing is recorded, whatever with_images/ says.
#   Trials/with_images/  SOLVED within TRIAL_MIN_SOLVED..TRIAL_MAX_SOLVED (today exactly 1 of 4):
#     SOLVED = 0          not recorded, AND it blocks check-reviewers. The task is RL training
#                         data, so a task no attempt ever solves carries no positive reward
#                         signal and is unusable however cleanly its runs verify.
#     SOLVED below band   not recorded.
#     SOLVED within band  RECORDED.
#     SOLVED above band   not recorded — delivery blocked, harden it. all-solved is just the top
#                         of that band, reported in its own words.
#   unreadable   nothing recorded. "Cannot tell" is not "the task held".
#
# MM_FORCE_TRIAL_RECORD overrides the NORMAL half only, never the text-only one. It always writes
# the real result plus a `forced: true` line, never as though the task had held.
#
# The record is CLEARED WHEN A TRIAL LAUNCHES (see run_trial), not here, so it always
# describes the most recent trial and only ever exists because that trial wrote it. That is
# what makes an unrecorded result and a crashed run behave identically from a reader's point of
# view: in both cases no record survives, because neither produced one.
post_trial_verdict(){  # $1 = trials job dir, $2 = task dir
  local jobs="$1" dir="$2" r helper tally failed total solved verdict head why band
  local to_tally to_total to_digest
  resolve_record_paths
  band="$(trial_band)"

  # ---- the text-only half first: if it does not hold, with_images/ cannot rescue the trial.
  say ""
  if ! check_text_only_run "$dir"; then
    say "trial NOT RECORDED — the text-only half does not hold (above). Every text-only attempt"
    say "  must fail, on the image-stripped copy of THIS bundle. Re-run /run-trial."
    COST_TRIAL_RESULT="not recorded: the text-only half does not hold"
    return 0
  fi
  to_tally="$(trial_tally "$TEXT_ONLY_DIR")"; to_total="${to_tally##* }"
  to_digest="$(control_digest "$TEXT_ONLY_DIR")"

  r="$(control_reward "$jobs")"
  tally="$(trial_tally "$jobs")"

  # Either primitive coming back empty means the same thing: the rewards on disk cannot be read
  # as a set of attempts, so there is no result to judge and nothing may be recorded.
  if [ -z "$r" ] || [ -z "$tally" ]; then
    say ""
    say "trial reward could not be read from $jobs — no verdict, and nothing recorded."
    say "  Any previous trial record was cleared when this run launched, so nothing is left"
    say "  claiming a result. \"Cannot tell\" is not \"the task held\" — read the job dir."
    COST_TRIAL_RESULT="no verdict: trial reward unreadable"
    return 0
  fi

  failed="${tally%% *}"; total="${tally##* }"; solved=$((total - failed))

  # THE RECORD RULE lives in trial_rule(), so this path and the reviewer path decide alike.
  # Everything below only reports what it decided.
  verdict="$(trial_rule "$failed" "$total")"
  # The band is a COUNT of attempts, so it only means something over exactly N_ATTEMPTS of them. A
  # crashed attempt (no reward) drops out of the tally, and a pseudo-trial replays ONE submission:
  # either would otherwise read "1 of 3" or "1 of 1" as a pass. Too many solves stays decisive -- no
  # missing attempt could bring the count back down.
  if [ "$total" -ne "$N_ATTEMPTS" ] && [ "$verdict" != too-many-solved ] && [ "$verdict" != all-solved ]; then
    verdict=incomplete
  fi
  COST_TRIAL_RESULT="$verdict: $solved of $total solved, 0 of $to_total text-only solved"

  say ""
  case "$verdict" in
    incomplete)
      say "pass@$total: $solved of $total attempts solved the task — but only $total of $N_ATTEMPTS"
      say "  attempts produced a reward, and the band needs all $N_ATTEMPTS. NOT RECORDED."
      if [ "$(basename "$jobs")" = PseudoTrial ]; then
        say "  A pseudo-trial replays ONE submission, so it cannot stand in for the $N_ATTEMPTS-attempt"
        say "  trial. Run /run-trial."
      else
        say "  An attempt that crashed writes no reward. Read the attempt dirs under $jobs, then"
        say "  re-run the trial."
      fi
      why="$total of $N_ATTEMPTS attempts produced a reward";;
    record-split)
      say "pass@$total: $solved of $total attempts solved the task, $failed failed — inside the"
      say "  allowed band ($band of $total), and all $to_total text-only attempts failed."
      say "  TRIAL PASSED — the image is needed and the task discriminates. READY TO DELIVER."
      COST_TRIAL_PASSED=1
      head="# Trial recorded — $solved of $total solved, all $to_total text-only attempts failed";;
    too-few-solved)
      say "pass@$total: $solved of $total attempts solved the task, $failed failed."
      say "  NOT RECORDED — $band of $total attempts must solve it. Read a failing trajectory"
      say "  to see what blocks the attempts, then make the task more solvable."
      why="$solved of $total attempts solved it — below the allowed $band of $total";;
    too-many-solved)
      say "pass@$total: $solved of $total attempts solved the task, only $failed failed."
      say "  NOT RECORDED — DELIVERY IS BLOCKED. $band of $total attempts may solve it."
      why="$solved of $total attempts solved it — above the allowed $band of $total";;
    all-failed)
      say "pass@$total: ALL $total attempts failed (reward 0 every time)."
      say "  NOT RECORDED, and this BLOCKS the reviewer path (check-reviewers). The task is RL"
      say "  training data: one that no attempt ever solves carries no positive reward signal, so"
      say "  $band of the $total attempts must PASS for the task to be usable. Read a"
      say "  trajectory to see what blocks every attempt, then make the task solvable."
      say "  Re-running at --n_trial=1 is NOT a way round this — it is the same result with less"
      say "  evidence, and the reviewer path refuses the bundle either way."
      why="all $total attempts failed — no passing attempt, so the task has no RL signal";;
    all-solved)
      if [ "$BREAKER_TRIPPED" = 1 ] && [ "$total" -lt "$N_ATTEMPTS" ]; then
        say "THE MODEL PASSED THE TRIAL — all $total finished attempts solved the task (the circuit"
        say "  breaker cancelled the other $((N_ATTEMPTS - total)) once the result was decided)."
      elif [ "$total" -eq 1 ]; then say "THE MODEL PASSED THE TRIAL — reward $r."
      else say "THE MODEL PASSED THE TRIAL — all $total attempts solved the task."; fi
      why="the agent solved every attempt";;
  esac

  case "$verdict" in
    record-split)
      helper="$(qc_digest_helper)"
      if [ -z "$helper" ]; then
        say "  NOT RECORDED: qc_digest.py could not be found, so there is no way to tie this"
        say "  result to the bundle it ran on. Nothing was written."
        return 0
      fi
      # The attempt distribution is part of the record. Without it a pass@5 record and a
      # pass@1 record read identically, and they are not the same evidence.
      { printf '%s\n\n' "$head"
        printf -- '- task_dir: `%s`\n' "$dir"
        printf -- '- trial_reward: %s\n' "$r"
        printf -- '- attempts: %s\n' "$total"
        printf -- '- failed: %s   (reward 0 — the agent did not solve it)\n' "$failed"
        printf -- '- pass@%s: %s/%s attempt(s) solved the task\n' "$total" "$solved" "$total"
        printf -- '- allowed: %s of %s\n' "$band" "$total"
        printf -- '- text_only_attempts: %s   (all failed — images stripped)\n' "$to_total"
        printf -- '- text_only_digest: %s\n' "$to_digest"
        printf -- '- trials_dir: `%s`\n\n' "$jobs"
        printf 'The digest below is the bundle THIS trial ran on. A reader must compare it against\n'
        printf 'the task on disk before treating this as evidence about anything.\n\n'
        python3 "$helper" "$dir" --section
      # The PATH stays out of both lines. Naming it invites a CB to write one by hand, and a
      # hand-made record is indistinguishable from an earned one -- it would let the reviewer path
      # skip re-running a trial that never held. The state is what they can act on; the path is not.
      # $MM_QC_MARKER_DEBUG opts in, same switch fix.py and qc_digest.py use.
      } > "$QC_TRIAL_MARKER" 2>/dev/null || {
        say "  NOT RECORDED: the trial record could not be written (usually an unwritable /tmp)."
        [ -n "${MM_QC_MARKER_DEBUG:-}" ] && say "         (record path: $QC_TRIAL_MARKER)"
        return 0
      }
      say "  Recorded against this bundle's digest — this trial does NOT need re-running."
      [ -n "${MM_QC_MARKER_DEBUG:-}" ] && say "         (record path: $QC_TRIAL_MARKER)"
      return 0;;
  esac

  # Not recorded. Nothing to remove: the record was cleared when this trial launched, so the only
  # way one exists here is if THIS run wrote it, and this run is not writing one.
  #
  # Operator override. When set, the record is still written — with the REAL result and a
  # `forced: true` line, never as though the task had held, since the one fact this file
  # exists to attest is the one it must not get wrong.
  if [ -n "${MM_FORCE_TRIAL_RECORD:-}" ]; then
    helper="$(qc_digest_helper)"
    if [ -n "$helper" ]; then
      { printf '# Trial record — FORCED\n\n'
        printf -- '- task_dir: `%s`\n' "$dir"
        printf -- '- trial_reward: %s\n' "$r"
        printf -- '- forced: true\n'
        printf -- '- attempts: %s\n' "$total"
        printf -- '- failed: %s   (reward 0 — the agent did not solve it)\n' "$failed"
        printf -- '- pass@%s: %s/%s attempt(s) solved the task\n' "$total" "$solved" "$total"
        printf -- '- allowed: %s of %s\n' "$band" "$total"
        printf -- '- text_only_attempts: %s   (all failed — images stripped)\n' "$to_total"
        printf -- '- text_only_digest: %s\n' "$to_digest"
        printf -- '- trials_dir: `%s`\n\n' "$jobs"
        printf 'This record was written under an explicit override, NOT because the rule recorded\n'
        printf 'it: %s. The digest below is the bundle the trial ran on.\n\n' "$why"
        python3 "$helper" "$dir" --section
      } > "$QC_TRIAL_MARKER" 2>/dev/null \
        && say "trial record written under override (reward $r, $solved/$total solved)."
    fi
  fi

  if [ "$verdict" = all-solved ] || [ "$verdict" = too-many-solved ]; then
    say ""
    say "  THE TASK MUST BE HARDENED. A task the model solves this often does not discriminate,"
    say "  and its reward says little about the model being measured."
    say "  Aim for $band of $total attempts passing."
    say ""
    say "  After hardening, re-run  /run-check  in Claude chat, then the controls, then trial."
    say ""
  fi
  return 0
}

# ------------------------------------------------------- bundle digest gate (oracle / nop)
# qc_check.md records a content digest of the bundle the audit passed. oracle/nop run ONLY when
# the bundle now matches that record exactly. Anything else — no marker, a marker describing a
# different task, a marker with no digest, or a digest that disagrees — stops the run and sends
# the CB to /run-check.
#
# NO MARKER BLOCKS. A bundle nobody has audited is not a safer thing to measure than one whose
# audit has gone stale; in both cases the reward would describe files no audit has seen. That
# does mean the ordering is strict: integrity -> QC -> marker -> oracle/nop, and a task whose
# check found blockers cannot run the controls until the blockers are fixed and a clean check
# has recorded a digest.
#
# THE TWO EXCEPTIONS ARE BOTH "THE CHECK ITSELF IS UNAVAILABLE", never "the bundle looks fine":
# the QC skill or its helper missing, and harbor unreachable so only the evidence half can be
# compared. There is no bypass flag on this gate, so treating either as a failure would ground
# oracle and nop with no way back. Both warn loudly and proceed.
#
# The digest helper lives in the QC skill, alongside the fix.py that writes the marker, so the
# two can never disagree about the algorithm. resolve_qc() already locates that skill.
qc_digest_helper(){  # echoes the path to qc_digest.py, or nothing
  resolve_qc || return 0
  local h; h="$(dirname "$QC_FIX")/qc_digest.py"
  [ -f "$h" ] && printf '%s' "$h"
}

check_digest(){  # $1 = task dir, $2 = mode name for the message
  local dir="$1" mode="$2" helper out rc
  resolve_record_paths
  if ! resolve_qc; then
    say "WARNING: the MM SWE QC skill was not found, so the bundle could NOT be checked"
    say "         against an audit. Running $mode unverified."
    return 0
  fi
  helper="$(dirname "$QC_FIX")/qc_digest.py"
  if [ ! -f "$helper" ]; then
    say "WARNING: $helper is missing, so the bundle could NOT be checked against an"
    say "         audit. Running $mode unverified."
    return 0
  fi

  out="$(python3 "$helper" "$dir" --compare "$QC_MARKER" 2>&1)"; rc=$?
  case "$rc" in
    0) # Matched. Silent on a full match; a PARTIAL match is said out loud, because "we could
       # not check half of it" must not look identical to "we checked all of it and it was fine".
       printf '%s' "$out" | grep -q "NOT CHECKED" && {
         say "bundle digest only PARTIALLY verified against the last QC audit:"
         printf '%s\n' "$out" | sed 's/^/         /' >&2
       }
       return 0;;
    4) # Nothing on record FOR THIS TASK: never audited, audited then found to have blockers
       # (fix.py removes the marker), or the marker belongs to a different task.
       say "no QC audit is on record for this task:"
       printf '%s\n' "$out" | sed 's/^/         /' >&2
       say "$mode would describe a bundle no audit has seen."
       say ""
       say "Run  /run-check  in Claude chat first, then run $mode."
       return 1;;
  esac
  say "the task bundle has CHANGED since the QC audit that last passed it:"
  printf '%s\n' "$out" | sed 's/^/         /' >&2
  say "$mode would describe a bundle nobody has audited."
  say ""
  say "Run  /run-check  in Claude chat so the audit covers these edits, then run $mode again."
  return 1
}

# ------------------------------------------------- recorded-run gate (check-reviewers)
# THE PROBLEM THIS SOLVES. A reviewer receives the bundle AND its Oracle/, Nop/ and Trials/
# output, but never the two markers -- those are written to /tmp in the CB's sandbox and do not
# travel. With no qc_check.md, check_digest() above blocks oracle and nop, and that gate has no
# bypass flag; so the reviewer re-runs the controls, and re-runs the TRIAL as well just to satisfy
# themselves the task discriminates. That is a real model call spent to re-derive a number already
# sitting on disk.
#
# What is genuinely missing is one link: nothing proves the RECORDED runs describe the CURRENT
# bundle. qc_check.md does not -- it is written from the bundle at audit time, so it always matches
# itself. This establishes that link locally, for free, and only then mints the markers.
#
# ALL SIX CONDITIONS, NO PARTIAL CREDIT: three recorded digests equal to the bundle's digest now,
# oracle exactly 1, nop exactly 0, trial exactly 0 (we WANT the model to have failed). Any one of
# them missing means the reviewer re-runs the task, which is the status quo -- so a false negative
# costs a re-run, while a false positive ships a review based on numbers that describe other files.
#
# "COULD NOT VERIFY" IS A FAILURE HERE, and that is the one place this gate deliberately differs
# from the trial gate at the bottom of this script, which warns and proceeds when task_digest_now
# declines. That leniency is right when the thing being protected is a run the user explicitly
# asked for. It is wrong here: this marker exists to let somebody SKIP verifying, so minting one
# we could not verify is the only outcome worse than making them re-run.
#
# Deliberately NOT a refactor of that trial gate (see the `MODE = trial` block near the end), which
# does the Oracle/Nop half of this for a different purpose and phrases its failures for a different
# audience. Both call the same three primitives -- control_reward, control_digest, task_digest_now
# -- which is the reuse that matters; what is duplicated is three string comparisons, not logic.
verify_recorded_runs(){  # -> 0 = verified and markers minted, 1 = reviewer must re-run
  local dir="$TASK_DIR" now r d bad=0
  resolve_record_paths

  # A stale marker must never survive a verification it did not pass. Cleared FIRST, so every exit
  # path below leaves either a marker this run just earned or no marker at all.
  rm -f "$QC_TRIAL_MARKER"

  say "verifying the recorded runs against the bundle on disk (no run is spent)"

  now="$(task_digest_now "$dir")"
  if [ -z "$now" ]; then
    say ""
    say "CANNOT VERIFY: the current task digest could not be computed."
    say "  harbor could not be reached, or the task ships a .gitignore whose pathspec rules"
    say "  this script will not guess at. Without it there is nothing to compare the runs to."
    say ""
    say "  This is NOT a pass. Re-run the task (oracle, nop, trial) rather than reviewing"
    say "  against numbers nothing could check."
    return 1
  fi
  say "  bundle now: $now"

  # ---- digests: does each recorded run describe THIS bundle?
  local run rd
  for run in Oracle Nop Trials; do
    rd="$ROOT/$run"; [ "$run" = Trials ] && rd="$TRIALS_DIR"
    d="$(control_digest "$rd")"
    case "$d" in
      "")      say "  $run: no lock.json digest found        <- cannot verify"; bad=1;;
      mixed)   say "  $run: MIXED digests across its trials  <- cannot verify"; bad=1;;
      "$now")  say "  $run: digest matches (current)";;
      *)       say "  $run: $d  <- STALE"; bad=1;;
    esac
  done

  # ---- rewards: was the recorded gate actually green, and did the trial hold?
  # control_reward normalizes to "" / mixed / 0 / %g, so these are exact string tests. `mixed`
  # fails every one of them by construction, which is correct: attempts that disagree mean the
  # model solved it at least once.
  local orc nop trl nopc nfp nft npp npt
  orc="$(control_reward "$ROOT/Oracle")"
  nop="$(control_reward "$ROOT/Nop")"
  trl="$(control_reward "$TRIALS_DIR")"
  [ "$orc" = 1 ] || { say "  Oracle reward: ${orc:-unreadable}  <- expected 1"; bad=1; }
  # Nop is judged on the COUNTS, by the same rule the pre-trial gate applies via
  # control_counts() -- or the two halves of this script would contradict each other about one
  # bundle, which is exactly the drift the comment above warns of. The reward is still shown,
  # because it is worth reading, but it decides nothing: 0 is consistent with an inert f2p test.
  say "  Nop    reward: ${nop:-unreadable}  (informational; the counts below decide)"
  nopc="$(control_counts "$ROOT/Nop")"
  case "$nopc" in
    "")    say "  Nop    counts: none recorded  <- cannot tell whether the tests discriminate"
           bad=1;;
    mixed) say "  Nop    counts: MIXED across its attempts  <- not a usable control"; bad=1;;
    *)     read -r nfp nft npp npt <<<"$nopc"
           if   [ "$nft" -eq 0 ]; then
             say "  Nop    counts: f2p_total=0  <- no f2p test ran"; bad=1
           elif [ "$nfp" -ne 0 ]; then
             say "  Nop    counts: $nfp of $nft f2p PASS on an empty submission  <- inert test(s)"
             bad=1
           elif [ "$npp" -ne "$npt" ]; then
             say "  Nop    counts: $(( npt - npp )) of $npt p2p FAIL on nop  <- mislabeled, really f2p"
             bad=1
           else
             say "  Nop    counts: 0 of $nft f2p pass, $npp of $npt p2p pass  <- expected"
           fi;;
  esac
  # The trial is judged by the SAME rule that decides the record — trial_rule, which both this
  # and post_trial_verdict call — or the two halves of this script contradict each other about
  # one bundle: `mixed` used to fail here, so the split result the rule now records could never
  # be minted on the reviewer path at all.
  # Refused: an unreadable reward; solves outside TRIAL_MIN_SOLVED..TRIAL_MAX_SOLVED, all-solved
  # being the top of that band; every attempt failing, which is refused with its own header
  # further down because the runs themselves are real and verifiable there; and a text-only run
  # that is missing, stale, or solved even once (check_text_only_run).
  # Initialised, not just declared: `set -u` is on, and a bare `local x` is an unbound-variable
  # error the moment anything reads it. The VERIFIED line below is only reachable when both are
  # assigned, so "?" should never print -- it is here so a future edit that changes that
  # reachability prints a question mark instead of aborting the reviewer path.
  local ttally="" tfailed="?" ttotal="?" tsolved="?" tband no_pass=0 too_easy=0 text_bad=0
  tband="$(trial_band)"
  ttally="$(trial_tally "$TRIALS_DIR")"
  if [ -z "$ttally" ]; then
    say "  Trial  reward: ${trl:-unreadable}  <- no readable per-attempt reward"; bad=1
  else
    tfailed="${ttally%% *}"; ttotal="${ttally##* }"
    tsolved=$((ttotal - tfailed))
    local tverdict; tverdict="$(trial_rule "$tfailed" "$ttotal")"
    # Same completeness rule as post_trial_verdict: the band only means something over N_ATTEMPTS.
    if [ "$ttotal" -ne "$N_ATTEMPTS" ] && [ "$tverdict" != too-many-solved ] && [ "$tverdict" != all-solved ]; then
      tverdict=incomplete
    fi
    case "$tverdict" in
      incomplete)
        say "  Trial  reward: $trl  <- $ttotal of $N_ATTEMPTS attempts produced a reward; incomplete"
        bad=1;;
      all-solved)
        say "  Trial  reward: $trl  <- the model solved all $ttotal attempt(s); the task must FAIL it"
        bad=1; too_easy=1;;
      too-many-solved)
        # BLOCKS for the same reason all-solved does, one band lower: the model solves it more
        # often than the band allows, so the task does not discriminate.
        say "  Trial  reward: $trl  <- $tsolved of $ttotal attempts solved it; $tband may pass"
        bad=1; too_easy=1;;
      all-failed)
        # BLOCKS. The task is RL training data: a task no attempt ever solves carries no positive
        # signal, so a run with every attempt failing is not a usable task, however cleanly the
        # runs verify.
        say "  Trial  reward: $trl  <- ALL $ttotal attempts failed; $tband must PASS"
        bad=1; no_pass=1;;
      too-few-solved)
        say "  Trial  reward: $trl  <- only $tsolved of $ttotal attempts solved it; $tband must pass"
        bad=1;;
      *)
        say "  Trial  reward: $trl  ($tfailed of $ttotal attempt(s) failed)";;
    esac
  fi
  # The text-only half: every image-stripped attempt failed, on a copy of THIS bundle.
  check_text_only_run "$dir" || { bad=1; text_bad=1; }

  if [ "$bad" != 0 ]; then
    say ""
    # The no-passing-attempt refusal gets its own header and NO re-run instructions. The generic
    # ones are actively wrong for it: the runs here DO describe the bundle and the digests match,
    # so "re-run oracle, nop, then the trial" points at the one thing that is not the problem.
    if [ "$no_pass" = 1 ]; then
      say "NOT VERIFIED — the task has NO PASSING ATTEMPT."
    elif [ "$too_easy" = 1 ]; then
      say "NOT VERIFIED — the model solved TOO MANY attempts."
    elif [ "$text_bad" = 1 ]; then
      say "NOT VERIFIED — the text-only half of the trial does not hold (see the Text-only line)."
      say "  If a text-only attempt SOLVED the task, the image is not really needed: put what the"
      say "  fix depends on into the image, then re-run /run-check, the controls and the trial."
      say "  If the text-only run is missing or STALE, re-run /run-trial — it runs both halves."
    else
      say "NOT VERIFIED — the recorded runs do not describe this bundle, or the gate was not green."
      say "  No trial record was written and no run was spent. The task must be re-run:"
      say "    mm_run.sh \"$dir\" oracle   &&  mm_run.sh \"$dir\" nop"
      say "    then /run-trial in Claude chat"
    fi
    # NOT "nothing was written": the QC audit ran BEFORE this and, if the bundle was clean, has
    # already recorded its own pass. That marker is honestly earned -- it says the bundle has no
    # blocking defects, which stays true however stale the runs are -- and it is precisely what
    # check_digest needs to let the re-runs above start. Saying "nothing was written" would send a
    # reviewer looking for a blocker that is not there.
    if [ "$no_pass" = 1 ]; then
      say "  All $ttotal attempts failed, so the task yields no positive reward signal and is"
      say "  unusable as RL training data. At least one attempt must PASS. The digests matched"
      say "  and the controls were green — the bundle is not stale, the task is not solvable."
      say ""
      say "  Read a trajectory to see what blocks every attempt, make the task solvable, then"
      say "  re-run the trial. Re-running at --n_trial=1 is NOT a way round this: one failure is"
      say "  the same result with less evidence, and it would record a task this gate refused."
    elif [ "$too_easy" = 1 ]; then
      # Same shape as the no-passing-attempt refusal, and for the same reason: the runs DO
      # describe this bundle and the digests match, so "re-run the controls" points at the one
      # thing that is not the problem. The task is what has to change.
      if [ "$ttotal" -eq 1 ]; then
        say "  The single attempt SOLVED the task, and the task must FAIL it."
      else
        say "  $tsolved of $ttotal attempts solved the task. $tband of $ttotal may pass."
      fi
      say "  A task the model solves this often does not discriminate, so its reward says little"
      say "  about the model being measured. The digests matched and the controls were green:"
      say "  the bundle is not stale, the task is too easy."
      say ""
      say "  Harden it, then re-run /run-check, the controls, and the trial."
    elif [ "$text_bad" = 1 ]; then
      :   # its header above already says what to do
    else
      say ""
      say "  (The QC pass, if the audit was clean, is already recorded — so those re-runs can"
      say "   start immediately; the controls gate will not ask you to audit again.)"
    fi
    return 1
  fi

  say ""
  say "VERIFIED — oracle 1, nop 0, trial $tfailed/$ttotal attempt(s) failed, all three recorded against $now."
  say "  Text-only: every image-stripped attempt failed, on a copy of this bundle."
  # WHAT THIS DOES NOT COVER, said out loud rather than left for someone to discover.
  #
  # The only digest the runs left behind is harbor's, in lock.json, and harbor hashes exactly
  # task.toml, instruction.md, README.md, environment/, tests/, solution/ and steps/. Root-level
  # files outside that set -- evidence_bundle.json above all -- are in NO run record, so there is
  # nothing to compare them against. This is not a gap that better code here could close: the
  # comparison needs a value recorded AT RUN TIME, and none was.
  #
  # Verified by test: editing instruction.md or tests/config.json trips the STALE branch above;
  # appending to evidence_bundle.json does not move harbor's digest at all.
  #
  # Tolerable because the uncovered files cannot change a reward -- the tests, environment and
  # solution that produce the numbers are all inside harbor's set. What they can change is the
  # evidence a reviewer reads, which is why this says so instead of implying full coverage.
  say "  Covers task.toml, instruction.md, README.md, environment/, tests/, solution/, steps/"
  say "  — everything that can move a reward. NOT evidence_bundle.json or other root files:"
  say "  no run recorded them, so nothing can vouch for them. Read those yourself."
  # post_trial_verdict re-reads Trials/with_images/ with control_reward and writes $QC_TRIAL_MARKER only on an
  # exact 0. It does not care that no trial just ran, so pointing it at shipped artifacts is
  # precisely what it was built to do -- and it keeps ONE writer for that file.
  post_trial_verdict "$TRIALS_DIR" "$dir"
  if [ -f "$QC_TRIAL_MARKER" ]; then
    say "  trial record written — the trial does NOT need re-running."
  else
    # Reachable only if the digest helper is missing (post_trial_verdict says so itself). Do not
    # claim a record that is not there.
    say "  NOTE: no trial record could be written, so the trial is NOT covered by this run."
  fi
  return 0
}

# ---------------------------------------------------------------- oracle / nop
run_plain(){  # $1 = oracle|nop  -> keyless, no proxy, no bridge
  # Output goes STRAIGHT into <ROOT>/Oracle or <ROOT>/Nop — no per-task subfolder.
  # harbor puts the job under <-o>/<--job-name>, so we pass -o <ROOT> and name the
  # job "Oracle"/"Nop" to land exactly there.
  local mode="$1" jobname
  case "$mode" in oracle) jobname="Oracle";; nop) jobname="Nop";; esac
  check_digest "$TASK_DIR" "$mode" || return 2
  mkdir -p "$ROOT"
  [ "$KEEP" = 1 ] || rm -rf "${ROOT:?}/$jobname"
  say "task $TASK_ID"
  local CBASE="" SEALED=0
  [ "$HAS_RUBRICS" = 1 ] && { resolve_creds; CBASE="$BASE"; }

  # --isolate-all extends the trial's seal to oracle/nop. Off by default: neither runs an
  # agent, so neither can cheat, and sealing them can break a solve.sh that legitimately
  # installs something. Turn it on to prove the task does not need network at RUN time —
  # otherwise a sealed trial can fail for an environment reason and look like a model
  # failure. With no rubric there is nothing to relay to, so the seal is total.
  if [ "$ISOLATE_ALL" = 1 ]; then
    if [ "$HAS_RUBRICS" = 1 ] && ! build_agent_seal; then
      say "WARNING: could not build the model route for $mode — continuing UNSEALED."
    else
      SEALED=1
      build_seal_compose
      say "$mode: '${COMPOSE_SVC}' stays inside harbor's egress sidecar, so task.toml's"
      say "  [verifier] network_mode is enforced. If it is no-network and the task has a"
      say "  rubric, the in-container judge will fail and the host-side fallback"
      say "  (mm_grade_rubrics.py) grades instead — that is expected, not a bug."
    fi
  fi
  [ "$SEALED" = 1 ] || { resolve_compose || return $?; }

  if [ "$HAS_RUBRICS" = 1 ]; then
    # [verifier.env] expands from OUR environment — so export, on BOTH judge channels.
    resolve_eval_base "$SEALED"
    export_judge_env "$CBASE" "$CEVAL_BASE"
    # Only now is it true that the creds are forwarded, so only now is it said. Anything
    # still missing is a name we cannot supply, and harbor would abort on it regardless.
    preflight_verifier_env || return 2
    say "$mode -> $ROOT/$jobname   (rubric present: judge creds forwarded)"
    say "  claude-format ANTHROPIC_BASE_URL=$CBASE model=$JUDGE_MODEL key=$(mask "$KEY")"
    say "  openai-format EVAL_BASE_URL=$CEVAL_BASE model=$EVAL_MODEL_NAME key=$(mask "$EVAL_KEY")"
  else
    say "$mode -> $ROOT/$jobname   (no credentials needed: verifier is unit-tests only)"
  fi
  local -a hargs=(run -p "$TASK_DIR" -a "$mode" -e "$HENV" -o "$ROOT" --job-name "$jobname" --yes)
  [ -n "$HOSTNET_FILE" ] && hargs+=(--extra-docker-compose "$HOSTNET_FILE")
  say "harbor ${hargs[*]}"
  harbor "${hargs[@]}"
  local rc=$?; report "$ROOT/$jobname" "$mode"; return $rc
}

# ---------------------------------------------------------------- pseudo-trial
# REPLAY A RECORDED SUBMISSION AGAINST THE CURRENT TESTS. A trial costs a model call; editing the
# tests afterwards invalidates its reward but NOT its submission, because the agent never saw the
# tests. So the tests are re-run against the saved submission and the reward is measured again --
# a real number, freshly computed, not a stale one taken on trust.
#
# THE GATE IS THE WHOLE ARGUMENT, and it runs BEFORE anything is spent, like every other gate
# here. Only files the agent CANNOT see may have changed: tests/, solution/ and task.toml are
# free, while instruction.md, environment/ and README.md are pinned. Edit what the agent reads and
# the recorded submission is no longer what an agent would produce, so replaying it answers a
# question nobody asked. qc_digest.py --gate-trusted decides that from the baseline run_trial
# recorded, and names the offending file when it refuses.
#
# task.toml IS FREE BECAUSE IT IS COUPLED TO tests/. Its f2p/p2p arrays must mirror
# tests/config.json or mm_check_integrity.py fails the bundle, so adding or removing a test
# forces an edit to task.toml in the same breath -- and pinning it made the single edit this
# whole mode exists to permit impossible to perform. The agent never reads that file. The cost is
# that [agent]/[environment] policy edits now pass unchecked; the gate says when task.toml has
# changed rather than refusing, and AGENT_BLIND in qc_digest.py argues the trade in full.
#
# ON WRITING THE TRIAL RECORD. This hands off to post_trial_verdict unchanged, so the record is
# written by the same single writer as a real trial, under the same condition (reward exactly 0)
# and stamped with the same digest block. That block describes the bundle NOW -- which for a
# pseudo-trial is simply true: these tests did just run against this bundle. The only thing the
# gate vouches for is that the submission is still the submission; the reward is measured.
run_pseudo_trial(){
  local jobname="PseudoTrial" src rc
  mkdir -p "$ROOT"

  local helper; helper="$(qc_digest_helper)"
  if [ -z "$helper" ]; then
    say "the QC digest helper was not found, so the bundle cannot be checked against the"
    say "trial that produced the submission. A pseudo-trial is refused: without that check"
    say "there is nothing distinguishing a valid replay from a stale one."
    return 2
  fi

  # ---- is there anything to replay? ----
  src="$(find "$TRIALS_DIR" -type f -name submission.patch -size +0 2>/dev/null | head -1)"
  if [ -z "$src" ]; then
    say "no submission was captured by the recorded trial, so there is nothing to replay."
    say "  Trials run before tests/test.sh saved the agent's work cannot be pseudo-trialled;"
    say "  the container is gone and its file state with it."
    say ""
    say "  Wire the capture (/run-check reports it, fix.py applies it), then run a trial."
    return 2
  fi

  # ---- may it be replayed against the bundle as it stands? ----
  local out; out="$(python3 "$helper" "$TASK_DIR" --gate-trusted "$TRIALS_DIR" 2>&1)"; rc=$?
  if [ "$rc" != 0 ]; then
    say "this submission cannot be replayed against the current bundle:"
    printf '%s\n' "$out" | sed 's/^/         /' >&2
    say ""
    say "  Files the AGENT can see have changed since the trial that produced it, so the"
    say "  submission is not what an agent would write for the task as it stands now. Its"
    say "  score would describe a different task. Run a real trial instead: /run-trial."
    say ""
    say "  (Changes under tests/ and solution/, and to task.toml, are ignored by this check -"
    say "   they cannot change what the agent produced. Only the files above blocked it.)"
    return 2
  fi
  # The helper's first line is the verdict; anything after it is a note it wants read -- today,
  # that task.toml moved and was deliberately not checked. say() would fold the lot behind one
  # prefix, so the tail is indented under the verdict instead of vanishing into it.
  say "replay permitted: $(printf '%s\n' "$out" | head -1)"
  printf '%s\n' "$out" | tail -n +2 | sed 's/^/[mm_run]          /' >&2
  say "  submission: $src ($(wc -c < "$src") bytes)"

  [ "$KEEP" = 1 ] || rm -rf "${ROOT:?}/$jobname"

  # CLEAR THE TRIAL RECORD BEFORE LAUNCHING, exactly as run_trial does. Past this line a result
  # is going to be produced, and whatever it is must replace the old claim rather than sit beside
  # it: a replay that errors, or scores above 0, would otherwise leave an earlier trial's record
  # standing -- still asserting the agent did not solve a task whose tests have since changed.
  # Deliberately AFTER the gate: a refusal spends nothing and decides nothing, so it must not
  # destroy a record that is still true.
  resolve_record_paths
  rm -f "$QC_TRIAL_MARKER"
  say "task $TASK_ID"

  # Same verifier credentials a real trial's verifier needs: the agent phase runs no model, but
  # the JUDGE still does when the task ships a rubric.
  local CBASE=""
  if [ "$HAS_RUBRICS" = 1 ]; then
    resolve_creds; CBASE="$BASE"
    resolve_compose || return $?
    resolve_eval_base 0
    export_judge_env "$CBASE" "$CEVAL_BASE"
    preflight_verifier_env || return 2
    say "pseudo-trial -> $ROOT/$jobname   (rubric present: judge creds forwarded)"
  else
    resolve_compose || return $?
    say "pseudo-trial -> $ROOT/$jobname   (no credentials needed: verifier is unit-tests only)"
  fi

  # The agent class lives beside this script; harbor imports it by path, so its directory has to
  # be importable by HARBOR's interpreter, not ours.
  export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
  export MM_SUBMISSION_PATCH="$src"

  local -a hargs=(run -p "$TASK_DIR" -a "mm_pseudo_agent:PseudoTrialAgent" -e "$HENV"
                  -o "$ROOT" --job-name "$jobname" --yes)
  [ -n "$HOSTNET_FILE" ] && hargs+=(--extra-docker-compose "$HOSTNET_FILE")
  say "harbor ${hargs[*]}"
  harbor "${hargs[@]}"
  rc=$?
  report "$ROOT/$jobname" "pseudo-trial"
  say ""
  say "This reward was measured against the tests as they are NOW, using the submission the"
  say "agent produced. No model call was made."
  post_trial_verdict "$ROOT/$jobname" "$TASK_DIR"
  return $rc
}

report_attempts(){  # $1 = job dir, $2 = "text-only" for the image-stripped run. EVERY attempt, plus the tally.
  # `report` takes the first reward it finds, which at k>1 would describe one attempt as if it
  # were the whole run. pass@k is a distribution, so all of them are printed.
  local d="$1" n=0 solved=0 f r
  say "attempts under $d:"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    r="$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));r=d.get('rewards') or (d.get('verifier_result') or {}).get('rewards') or d;print(r.get('reward') if isinstance(r,dict) and r.get('reward') is not None else '')" "$f" 2>/dev/null)"
    # A result.json with NO reward is not an attempt. The JOB-level result.json is exactly that
    # (it holds stats/evals), so counting it made a 5-attempt run report itself as pass@6 with a
    # phantom reward=<none> attempt. Reported, never counted.
    # An attempt CANCELLED after its verifier finished (the circuit breaker's SIGTERM can land in
    # that window) has its reward in verifier/ but not in result.json. trial_tally reads verifier/
    # too, so read it here as well, or the listing and the verdict disagree about the same run.
    local note="" vd; vd="$(dirname "$f")/verifier"
    if [ -z "$r" ] && [ -d "$vd" ]; then
      r="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('reward',''))" "$vd/reward.json" 2>/dev/null)"
      [ -z "$r" ] && [ -f "$vd/reward.txt" ] && r="$(tr -d '[:space:]' < "$vd/reward.txt")"
      [ -n "$r" ] && note="  [verifier reward; harbor cancelled the attempt before recording it]"
    fi
    if [ -z "$r" ]; then
      # The JOB-level result.json also names CancelledError (in its exception stats), so only an
      # attempt dir gets the "cancelled" label.
      if [ "$(dirname "$f")" != "$d" ] && grep -q '"CancelledError"' "$f" 2>/dev/null; then
        say "  (cancelled before it produced a reward: $(dirname "$f" | sed "s|^$d/||"))"
      else
        say "  (not an attempt: no reward in $(dirname "$f" | sed "s|^$d/||")/result.json)"
      fi
      continue
    fi
    n=$((n+1))
    say "  attempt $n: reward=${r}   ($(dirname "$f" | sed "s|^$d/||"))$note"
    case "$r" in 0|0.0|0.00|-0|-0.0) ;; *) solved=$((solved+1));; esac
  done < <(find "$d" -name result.json 2>/dev/null | sort)
  if [ "$n" -eq 0 ]; then say "  no attempt with a readable reward found under $d"; return 0; fi
  # "solved" is any NON-ZERO reward, not just an exact 1.0: a rubric task can score 0.5, and
  # counting only 1.0 as solved would report a partly-solved attempt as a failure.
  say "pass@$n: $solved/$n attempt(s) solved the task ($((n - solved)) failed)"
  # One line on what the distribution means, from the SAME rule that decides the record, so the
  # tally and the verdict below it cannot say different things. The detail (what to do about a
  # blocked result) belongs to post_trial_verdict; this only names the band.
  if [ "${2:-}" = text-only ]; then
    case "$(text_only_rule "$((n - solved))" "$n")" in
      text-only-clean)  say "  text-only: no attempt solved it without the image - as required.";;
      text-only-solved) say "  text-only: $solved of $n solved it WITHOUT the image - the image is not really needed.";;
    esac
    return 0
  fi
  case "$(trial_rule "$((n - solved))" "$n")" in
    record-split)
      say "  $solved of $n solved - inside the allowed band ($(trial_band) of $n). PASS.";;
    too-few-solved)
      say "  $solved of $n solved - BELOW the allowed band ($(trial_band) of $n).";;
    too-many-solved)
      say "  $solved of $n solved - ABOVE the allowed band ($(trial_band) of $n). The task must be hardened.";;
    all-solved)
      say "  NOTE: every attempt solved it - the task does not discriminate.";;
    all-failed)
      say "  NOTE: no attempt solved it - a usable task needs at least one PASSING attempt.";;
  esac
  return 0
}

# ---------------------------------------------------------------------- trial
run_trial(){
  # Output goes STRAIGHT into <ROOT>/Trials/without_images and <ROOT>/Trials/with_images — no
  # per-task subfolder and no timestamped job dir. harbor writes a job at <-o>/<--job-name>, so
  # pass -o <ROOT>/Trials and name each phase's job after its folder. Trials_TextOnly/ is where
  # the text-only phase used to go; it is cleared too, so a stale one cannot sit beside a new run.
  mkdir -p "$ROOT"
  [ "$KEEP" = 1 ] || rm -rf "${ROOT:?}/Trials" "${ROOT:?}/Trials_TextOnly"

  # BOTH PHASES RUN FROM NAMED COPIES (see trial_stage_dir), built before anything is spent: a
  # task with no image to strip is refused here, since its text-only run would just be the normal
  # run and prove nothing.
  local STAGE TO_DIR N_DIR rc
  STAGE="$(trial_stage_dir)"
  rm -rf "$STAGE" && mkdir -p "$STAGE" || { say "REFUSED: cannot prepare $STAGE"; return 2; }
  TO_DIR="$STAGE/$TEXT_ONLY_TASK_NAME"
  N_DIR="$STAGE/$NORMAL_TASK_NAME"
  cp -a "$TASK_DIR" "$N_DIR" || { say "REFUSED: cannot copy the task to $N_DIR"; return 2; }
  say "building the text-only copy (every image stripped):"
  build_text_only_copy "$TASK_DIR" "$TO_DIR" >&2; rc=$?
  if [ "$rc" = 3 ]; then
    say "REFUSED: the task has no image to strip (no image in instruction.md, no image copied by"
    say "  the Dockerfile). The text-only attempts would be identical to the normal ones."
    return 2
  elif [ "$rc" = 4 ]; then
    say "REFUSED: the image is downloaded by a RUN line (above), which cannot be stripped without"
    say "  guessing what else that line does. Ship the image under environment/assets/ and COPY it."
    return 2
  elif [ "$rc" != 0 ]; then
    say "REFUSED: the text-only copy could not be built (rc $rc)."
    return 2
  fi

  resolve_creds
  # Before the rm below and before post_trial_verdict: both must act on the SAME path fix.py used,
  # or a record in a fallback location survives a trial that should have cleared it.
  resolve_record_paths
  say "task $TASK_ID"
  say "trial agent=$AGENT model=$MODEL"
  say "creds base=$BASE key=$(mask "$KEY")"

  # Default stall window = this task's own [agent].timeout_sec (task.toml), so a stalled
  # subagent is not killed sooner than the whole trial would time out anyway. Falls back
  # to 5400000ms (90min) if task.toml has no [agent].timeout_sec for some reason.
  if [ "$IDLE_TIMEOUT_FIX" = 1 ] && [ -z "$STALL_TIMEOUT_MS" ]; then
    local agent_timeout_sec
    agent_timeout_sec="$(sed -n '/^\[agent\]/,/^\[/{s/^[[:space:]]*timeout_sec[[:space:]]*=[[:space:]]*\([0-9.]*\).*/\1/p}' "$TASK_DIR/task.toml" 2>/dev/null | head -1)"
    if [ -n "$agent_timeout_sec" ]; then
      STALL_TIMEOUT_MS="$(python3 -c "print(int(float(\"$agent_timeout_sec\") * 1000))" 2>/dev/null)"
      say "stall timeout derived from task.toml [agent].timeout_sec=${agent_timeout_sec}s -> ${STALL_TIMEOUT_MS}ms"
    fi
    : "${STALL_TIMEOUT_MS:=5400000}"
  fi

  # How does the CONTAINER reach the anonymizer on the VM's loopback? Two routes:
  #  (a) HOST NETWORKING (default) — an extra docker-compose override puts harbor's
  #      environment service on the host network stack, so the container's localhost IS
  #      the VM's localhost and http://localhost:8091 just works. No bridge, no gateway
  #      guessing, nothing to tear down mid-run.
  #  (b) BRIDGE (--no-hostnet) — start a TCP forwarder on a host-reachable gateway and
  #      rewrite the in-container URL to it. Kept as a fallback.
  local CBASE="$BASE" IS_LOOPBACK=0 SEALED=0
  printf '%s' "$BASE" | grep -qE '://(localhost|127\.0\.0\.1)' && IS_LOOPBACK=1

  # (c) AGENT-PHASE SEAL (default) — leave `main` inside harbor's egress sidecar and
  #     collapse the agent-phase allowlist to the anonymizer via --allow-agent-host, so
  #     setup/agent-install still have network but the agent itself has only the model
  #     API. See build_agent_seal for why a compose-level seal is the wrong window.
  if [ "$ISOLATE" = 1 ]; then
    if build_agent_seal; then
      SEALED=1
      build_seal_compose
    else
      say "WARNING: could not build the model route — falling back to HOST NETWORKING."
      say "         The agent will have the VM's full network stack and can curl or pip"
      say "         install the answer. Fix the cause above, or pass --no-isolate to"
      say "         accept an unsealed run deliberately."
      ISOLATE=0
    fi
  fi

  if [ "$SEALED" = 1 ]; then
    :
  elif [ "$HOSTNET" = 1 ]; then
    resolve_compose || return $?
    say "container reaches the proxy directly at $CBASE (no bridge needed)"
  elif [ "$IS_LOOPBACK" = 1 ]; then
    local UP_HOST UP_PORT GATEWAY
    read UP_HOST UP_PORT < <(python3 - "$BASE" <<'PY'
import sys,urllib.parse as u
p=u.urlparse(sys.argv[1] if "://" in sys.argv[1] else "http://"+sys.argv[1])
h=p.hostname or "127.0.0.1"
print("127.0.0.1" if h=="localhost" else h, p.port or 8091)
PY
)
    GATEWAY="${PB_HOST_ADDR:-}"
    if [ -z "$GATEWAY" ] && docker info -f '{{range .SecurityOptions}}{{println .}}{{end}}' 2>/dev/null | grep -q rootless; then
      GATEWAY="$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p' | head -1)"
    fi
    [ -n "$GATEWAY" ] || GATEWAY="$(docker network inspect bridge -f '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null | grep -E '^[0-9]' | head -1)"
    : "${GATEWAY:=172.17.0.1}"
    python3 "$HERE/sandbox_proxy_bridge.py" --upstream-host "$UP_HOST" --upstream-port "$UP_PORT" \
      --gateway "$GATEWAY" --listen-port 0 >"$BRIDGE_LOG" 2>&1 &
    BRIDGE_PID=$!
    for _ in $(seq 1 12); do grep -q '^BRIDGE_' "$BRIDGE_LOG" 2>/dev/null && break; sleep 0.3; done
    if grep -q '^BRIDGE_READY ' "$BRIDGE_LOG"; then
      CBASE="$(sed -n 's/^BRIDGE_READY //p' "$BRIDGE_LOG")$(printf '%s' "$BASE" | sed -E 's#^[a-z]+://[^/]+##')"
      say "loopback proxy bridged -> container uses $CBASE"
    else
      BRIDGE_PID=""
      say "WARNING: bridge failed ($(tr '\n' ' ' <"$BRIDGE_LOG")) — the agent may not reach the proxy."
    fi
  fi

  if [ "$PREFLIGHT" = 1 ] && [ "$SEALED" = 1 ]; then
    # build_agent_seal already proved this address reachable from a real container via
    # resolve_host_addr, which is the hop that actually varies. Nothing more to probe:
    # the agent-phase restriction is applied by harbor inside the run, not by us.
    say "preflight ok: container reaches the model at $CBASE (probed by resolve_host_addr)"
  elif [ "$PREFLIGHT" = 1 ]; then
    say "preflight: checking $CBASE is reachable before spending the trial…"
    if printf '%s' "$CBASE" | grep -qE '^https://'; then
      if curl -s -m 10 -o /dev/null "$CBASE"; then say "preflight ok (host reached $CBASE)"
      else say "WARNING: host could not reach $CBASE (continuing; harbor may still succeed)"; fi
    else
      # Probe from INSIDE a container — that is the reachability that actually matters.
      # `docker run` needs -i or the heredoc is never forwarded: python3 - reads EOF,
      # does nothing, exits 0, and the probe silently "passes" without opening a socket.
      # Prefer an image that is already local so a fresh sandbox does not pull one.
      local probe_img
      probe_img="$(docker image ls --format '{{.Repository}}:{{.Tag}}' 2>/dev/null \
                   | grep -E '^(python|alpine/python|docker\.io/library/python):' | head -1)"
      : "${probe_img:=python:3-slim}"
      local probe_net=""
      [ "$HOSTNET" = 1 ] && probe_net="--network host"   # probe the same stack the agent gets
      if docker run --rm -i $probe_net "$probe_img" python3 - "$CBASE" <<'PY'
import sys, socket, urllib.parse as u
p = u.urlparse(sys.argv[1])
s = socket.socket(); s.settimeout(6)
try:
    s.connect((p.hostname, p.port or 80)); s.close()
    print("reached")
except Exception as e:
    sys.stderr.write("%s\n" % e); raise SystemExit(1)
PY
      then say "preflight ok (container reached $CBASE via $probe_img${probe_net:+ }$probe_net)"
      else
        say "WARNING: container CANNOT reach $CBASE — the agent will not reach the model."
        say "         Check the bridge line above, and that the proxy is up on the VM"
        say "         (curl -s \$ANTHROPIC_BASE_URL). Re-run with --no-preflight to skip this."
      fi
    fi
  fi

  # Export so task.toml's [verifier.env] entries expand — the agent gets the Claude-format
  # pair via --ae below, but the VERIFIER's judge (when the task has a rubric) reads these,
  # and it may be on either channel. Note the agent is NOT given the OpenAI-format pair:
  # it has no reason to call the judge's endpoint, and --ae is agent-phase only.
  if [ "$HAS_RUBRICS" = 1 ]; then
    resolve_eval_base "$SEALED"
    export_judge_env "$CBASE" "$CEVAL_BASE"
    preflight_verifier_env || return 2
    say "rubric present -> judge creds also exported for the verifier"
    say "  claude-format ANTHROPIC_BASE_URL=$CBASE model=$JUDGE_MODEL"
    say "  openai-format EVAL_BASE_URL=$CEVAL_BASE model=$EVAL_MODEL_NAME"
  else
    export ANTHROPIC_BASE_URL="$CBASE" ANTHROPIC_API_KEY="$KEY" JUDGE_MODEL="$JUDGE_MODEL"
  fi
  say "trial -> $TEXT_ONLY_DIR ($N_TEXT_ONLY text-only attempts), then"
  say "         $TRIALS_DIR ($N_ATTEMPTS normal attempts, only if every text-only attempt fails)"
  # Keep the bridge log with the run. Without this the only record of a mid-trial connection
  # teardown is a temp file that cleanup() deletes on the way out. Re-pointed at with_images/
  # when the normal phase starts; the one log covers both phases.
  BRIDGE_LOG_KEEP="$TEXT_ONLY_DIR/bridge.log"
  # Shared by both phases; -p, --job-name and -k are added per phase.
  local -a hargs=(run -a "$AGENT" -m "$MODEL"
                  -e "$HENV" -o "$ROOT/Trials" --yes
                  --ae ANTHROPIC_BASE_URL="$CBASE"
                  --ae ANTHROPIC_API_KEY="$KEY"
                  --agent-timeout-multiplier 1)
  # The bridge's cert is self-signed, so node has to be told to trust it. NODE_EXTRA_CA_CERTS
  # ADDS a trust anchor rather than replacing the bundle, so public TLS still works normally.
  if [ "$SEALED" = 1 ] && [ -n "$TLS_CERT" ]; then
    hargs+=(--ae NODE_EXTRA_CA_CERTS="$CA_IN_CONTAINER")
    say "agent trusts the bridge cert via NODE_EXTRA_CA_CERTS=$CA_IN_CONTAINER"
  fi
  if [ "$IDLE_TIMEOUT_FIX" = 1 ]; then
    # Three INDEPENDENT idle-abort mechanisms, confirmed against code.claude.com/docs/en/env-vars:
    #   - API_FORCE_IDLE_TIMEOUT   the "body idle timeout" — default-on for gateway/proxy
    #     connections (which is what ANTHROPIC_BASE_URL=http://localhost:8091 is), 5min.
    #   - CLAUDE_ENABLE_STREAM_WATCHDOG   the "event-level" watchdog — on by default for
    #     ALL providers as of v2.1.169, explicitly documented as independent of the above.
    #     This is the one that actually fired in practice (measured ~302s idle gap) even
    #     with API_FORCE_IDLE_TIMEOUT=0 set alone — do not drop this one.
    #   - CLAUDE_ENABLE_BYTE_WATCHDOG   off by default for gateway connections already, but
    #     forced off explicitly for belt-and-suspenders.
    # CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS is a SEPARATE, fourth mechanism (background
    # subagents only, not the main agent stream) — see its own derivation above.
    say "idle-timeout fix: API_FORCE_IDLE_TIMEOUT=0, CLAUDE_ENABLE_STREAM_WATCHDOG=0, CLAUDE_ENABLE_BYTE_WATCHDOG=0, CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS=$STALL_TIMEOUT_MS"
    hargs+=(--ae API_FORCE_IDLE_TIMEOUT=0
            --ae CLAUDE_ENABLE_STREAM_WATCHDOG=0
            --ae CLAUDE_ENABLE_BYTE_WATCHDOG=0
            --ae CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS="$STALL_TIMEOUT_MS")
  fi
  [ -n "$DISALLOW_TOOLS" ] && hargs+=(--ak "disallowed_tools=$DISALLOW_TOOLS")
  # The seal itself: harbor merges this into the agent-phase allowlist during agent.run()
  # only, so setup/agent-install keep the environment baseline and the agent does not.
  [ "$SEALED" = 1 ] && [ -n "$ALLOW_AGENT_HOST" ] && hargs+=(--allow-agent-host "$ALLOW_AGENT_HOST")
  [ -n "$HOSTNET_FILE" ]   && hargs+=(--extra-docker-compose "$HOSTNET_FILE")
  # The trial record describes THE MOST RECENT TRIAL, so it is cleared the moment a new one
  # launches — not after it finishes. Anything that stops this run from producing a readable
  # reward (a crash, a timeout, a harbor error) would otherwise leave the previous run's
  # record standing as though it described this one. Placed after every gate has passed, so a
  # trial that never starts cannot wipe a record that is still accurate.
  rm -f "$QC_TRIAL_MARKER"

  # ---- phase 1: text-only. Every attempt must FAIL, or the image is not really needed. ----
  # Run first because a single solve already decides the trial: the normal attempts are then
  # skipped rather than paid for.
  local -a to_args=("${hargs[@]}" -p "$TO_DIR" --job-name "$(basename "$TEXT_ONLY_DIR")")
  [ "$N_TEXT_ONLY" -gt 1 ] && to_args+=(-k "$N_TEXT_ONLY")
  say ""
  say "phase 1/2: $N_TEXT_ONLY text-only attempt(s) — images stripped, ALL must fail."
  say_harbor "${to_args[@]}"   # masked: this array carries ANTHROPIC_API_KEY
  # Breaker limit 1: text_only_rule fails the trial on ANY solve, so the first one decides it.
  harbor_breaker "$TEXT_ONLY_DIR" 1 "text-only phase" "${to_args[@]}"
  rc=$?
  local to_tripped="$BREAKER_TRIPPED"
  report_attempts "$TEXT_ONLY_DIR" text-only
  local to_tally to_failed to_total
  to_tally="$(trial_tally "$TEXT_ONLY_DIR")"
  if [ -z "$to_tally" ]; then
    say ""
    say "text-only rewards could not be read — no verdict, nothing recorded, and the normal"
    say "  attempts were NOT run. Read $TEXT_ONLY_DIR."
    COST_TRIAL_RESULT="no verdict: text-only rewards unreadable"
    return $rc
  fi
  to_failed="${to_tally%% *}"; to_total="${to_tally##* }"
  if [ "$(text_only_rule "$to_failed" "$to_total")" != text-only-clean ]; then
    say ""
    say "TRIAL FAILED — $((to_total - to_failed)) of $to_total text-only attempt(s) solved the task WITHOUT the image."
    say "  The words alone are enough, so the image is not really needed. NOT RECORDED, and the"
    say "  $N_ATTEMPTS normal attempts were NOT run (no point paying for them)."
    [ "$to_tripped" = 1 ] && [ "$to_total" -lt "$N_TEXT_ONLY" ] && \
      say "  The circuit breaker stopped the other $((N_TEXT_ONLY - to_total)) text-only attempt(s) at the first solve."
    say "  Move the information the fix depends on out of instruction.md and into the image"
    say "  (read a solving trajectory under Trials/without_images to see what it used), then re-run"
    say "  /run-check, the controls and the trial."
    COST_TRIAL_RESULT="text-only-solved: $((to_total - to_failed)) of $to_total text-only solved"
    return $rc
  fi
  # A crashed attempt writes no reward and drops out of the tally. "0 of 2 solved" is not the
  # evidence "0 of 3" is, so a short phase is incomplete rather than clean.
  if [ "$to_total" -lt "$N_TEXT_ONLY" ]; then
    say ""
    say "text-only INCOMPLETE — only $to_total of $N_TEXT_ONLY text-only attempts produced a reward (none"
    say "  solved it). NOT RECORDED, and the normal attempts were NOT run. Read the attempt dirs"
    say "  without a reward under $TEXT_ONLY_DIR, then re-run the trial."
    COST_TRIAL_RESULT="text-only incomplete: $to_total of $N_TEXT_ONLY produced a reward"
    return $rc
  fi
  say "text-only: all $to_total attempt(s) failed without the image — as required."

  # ---- phase 2: the normal attempts, on the real bundle. ----
  BRIDGE_LOG_KEEP="$TRIALS_DIR/bridge.log"
  local -a n_args=("${hargs[@]}" -p "$N_DIR" --job-name "$(basename "$TRIALS_DIR")")
  [ "$N_ATTEMPTS" -gt 1 ] && n_args+=(-k "$N_ATTEMPTS")
  say ""
  say "phase 2/2: $N_ATTEMPTS normal attempt(s) — $(trial_band) must solve it."
  say_harbor "${n_args[@]}"   # masked: this array carries ANTHROPIC_API_KEY
  # Breaker limit TRIAL_MAX_SOLVED+1: one solve past the band is too-many-solved whatever the
  # remaining attempts do. (If that exceeds N_ATTEMPTS it simply never trips.)
  harbor_breaker "$TRIALS_DIR" "$((TRIAL_MAX_SOLVED + 1))" "normal phase" "${n_args[@]}"
  rc=$?
  report_attempts "$TRIALS_DIR"
  if [ "$BREAKER_TRIPPED" = 1 ]; then
    say "  The circuit breaker stopped this phase at $((TRIAL_MAX_SOLVED + 1)) solves — above the allowed"
    say "  band ($(trial_band) of $N_ATTEMPTS) — so the attempts still running were cancelled unpaid."
  fi
  # THE BASELINE FOR A LATER PSEUDO-TRIAL, recorded here because here is the only place it can
  # be: harbor's lock.json holds ONE hash over the whole bundle, and you cannot subtract tests/
  # from a hash. Written from the bundle on disk seconds after the run and refused unless it
  # recombines to the digest harbor recorded, so it either describes the bundle this trial
  # measured or it does not exist. Costs nothing and never blocks -- a trial that cannot record
  # one is still a valid trial; it just cannot be replayed later.
  if [ -d "$TRIALS_DIR" ]; then
    local _h; _h="$(qc_digest_helper)"
    if [ -n "$_h" ]; then
      say "recording the replay baseline: $(python3 "$_h" "$TASK_DIR" --write-manifest "$TRIALS_DIR" 2>&1 | tail -1)"
    fi
  fi
  post_trial_verdict "$TRIALS_DIR" "$TASK_DIR"
  return $rc
}

# ---------------------------------------------------------- task file structure
# An MM SWE task must carry exactly this set of files. harbor check's rubric
# criteria assume they exist, so a missing one comes back as a puzzling judge
# verdict (or a bare error) rather than "that file isn't there" — and costs a
# check run to learn. Names are free to verify locally, so check them first and
# refuse the run when one is absent. --no-file-check skips this.
# NOTE: instruction.md is SINGULAR — that is harbor's canonical name
# (models/task/paths.py: instruction_path). A plural instructions.md is invisible
# to harbor, so requiring the plural here would fail every valid task.
REQUIRED_FILES=(
  "task.toml"
  "instruction.md"
  "evidence_bundle.json"
  "environment/Dockerfile"
  "environment/assets/ASSET_MANIFEST.json"
  "solution/fix.patch"
  "solution/solve.sh"
  "tests/config.json"
  "tests/test.patch"
  "tests/test.sh"
  "tests/verifier.py"
)
# tests/rubrics.json and tests/judge.py are deliberately NOT here. The rubric layer has two legal
# shapes and "absent" is one of them: a Mode B task ships neither file, on purpose. Requiring
# rubrics.json aborted `check` on correctly-shaped Mode B tasks before the metadata gate or the QC
# audit ever ran, and --no-file-check was the only way past it -- which also disables the checks
# that DO apply. (judge.py was never listed, so the old set required one half of a pair that must
# travel together, matching neither mode.)
#
# No coverage is lost. This gate has no mode opinion by design -- it answers "do the universally
# required files exist". Whether a rubric SHOULD be there is qc_gate()'s call further down, via
# qc_rubric_format.py, which is mode-aware: a Mode A task missing its rubric is still blocking
# (rubfmt_judge_present), and a Mode B task without one reads as correct.
# The QC skill's own qc_structure.py:REQUIRED_TASK_FILES was fixed for this same reason; this
# list simply never got the same update.

check_files(){  # $1 = task dir. Reports EVERY missing file, not just the first.
  local dir="$1" f missing=0
  for f in "${REQUIRED_FILES[@]}"; do
    [ -f "$dir/$f" ] || { say "  MISSING: $f"; missing=1; }
  done
  if [ "$missing" -ne 0 ]; then
    say "file check FAILED in $dir"
    return 1
  fi
  say "file check ok — all ${#REQUIRED_FILES[@]} required files present"
  return 0
}

# check_files() above only confirms the required files EXIST; it says nothing about
# whether they agree with each other. mm_check_integrity.py cross-checks task metadata
# (base_commit vs the Dockerfile's checkout, files_edited vs solution/fix.patch,
# f2p/p2p vs tests/config.json, asset paths, and the evidence posters read from disk
# outward: documented in BOTH files, cited in instruction.md, and delivered by COPY to
# the container_path the documents promise) — pure stdlib, no docker, no network,
# sub-second. See that script's docstring for the full list and for why
# patch-applies-cleanly / JSON-TOML-syntax / repo-existence checks are deliberately NOT
# included (they surface for free once oracle runs, or need a checkout).
#
# Every check is offline, so MM_INTEGRITY_OFFLINE / --offline are no-ops, still accepted.
check_integrity(){  # $1 = task dir
  local dir="$1"
  python3 "$HERE/mm_check_integrity.py" "$dir" >&2
}

# ------------------------------------------------------------- check / analyze
# Both are rubric-judge jobs, not unit-test jobs: they produce no reward.txt, so
# they report through report_rubric() instead of report().
# ---------------------------------------------------------------- QC gate (check mode)
# THIRD pre-flight, after the file-name and metadata gates and for the same reason they exist: a
# check run costs credentials and wall clock, so anything decidable locally is decided first.
# This one runs the MM SWE QC skill's full audit.
#
# --gate-tier bundle separates DISPLAY from BLOCKING, and both halves matter:
#   * the CB sees EVERY finding, at the phase actually on disk - a stale Oracle or a broken
#     1.0/0.0 gate is printed in full, not compressed into a one-line OPEN list. Showing a CB
#     only what you are willing to block on hides real defects from them.
#   * only bundle-tier FAILs count toward the exit code, because `harbor check` grades the TASK,
#     not the runs. A stale Oracle must be SHOWN and must not cost the run.
# (An earlier version passed --phase bundle, which did both jobs at once and could therefore only
#  show what it would block on.)
#
# `qc` only - never `auto` or `verify`. qc reads files and calls no runner, so there is no path
# back into this script and no recursion.
QC_FIX=""
# ------------------------------------------------------------------ QC pass marker (INTERNAL)
# NOT CB-FACING. This is an internal artifact: no message from this script may name it or say
# whether it exists. `say "QC clean"` below used to read "pass recorded in $QC_MARKER". The marker
# gates nothing -- qc_gate() decides from fix.py's exit code and nothing tests for the file -- so
# the CB loses no actionable information by never hearing about it.
#
# The marker (or $MM_QC_MARKER) is written and removed by fix.py, NOT here.
#
# It has to be, because the marker must be earnable by FIXING the blockers -- and the supported
# way to fix them is the QC skill, which never calls this script. If mm_run.sh owned the file, a
# CB who repaired their task would have to spend a whole credentialed `check` run just to record
# that the repair worked, which is backwards.
#
# fix.py updates it on EVERY audit: written when there are no bundle-tier blocking FAILs, removed
# when there are. So it always describes the last audit, from whichever entry point ran it, and
# stale markers cannot survive -- there is no path that leaves an old verdict in place.
#
# The override case needs no special handling here: reaching the [y/N] prompt at all means fix.py
# just found blockers, and therefore just removed the marker. Proceeding writes nothing back.
QC_MARKER="${MM_QC_MARKER:-/tmp/qc_check.md}"
# Written by post_trial_verdict when a trial scores 0, i.e. the agent could NOT solve the task.
# Same shape as QC_MARKER (task_dir + the qc_digest block), so the same --compare reads either:
# a record is only worth anything if whoever reads it can prove it describes the bundle in
# front of them, and a bare "a trial passed once" file cannot survive an edit being made to
# the task afterwards.
QC_TRIAL_MARKER="${MM_QC_TRIAL_MARKER:-/tmp/qc_trial.md}"
# Where fix.py records adjudicated verdicts so they survive the next audit. NOT a pass record and
# it gates nothing on its own: a stored ruling can only re-resolve a finding the audit recomputes
# as PENDING, so it can never stand in for the QC pass the way qc_check.md does.
QC_ADJUDICATIONS="${MM_QC_ADJUDICATIONS:-/tmp/qc_adjudications.json}"

# Both defaults above are only a starting point: qc_digest.py owns the real resolution, so this
# script and fix.py cannot disagree about where a record lives. Resolved LAZILY -- resolve_qc is
# defined below this line and the assignments above run at source time -- and once, then EXPORTED,
# so the fix.py this script invokes inherits the identical value instead of resolving it again.
#
# Why it matters: /tmp being unwritable used to mean a clean audit could not record its pass, which
# blocked oracle and nop behind a gate with no bypass flag and left the CB to go and fix a directory
# they should never have to think about. qc_digest.record_path falls back to another location
# outside the bundle instead. Failure is closed, not open: the worst a fallback costs is a re-run of
# a free audit, because compare() still checks task_dir and digest before believing any record.
QC_PATHS_RESOLVED=0
resolve_record_paths(){
  [ "$QC_PATHS_RESOLVED" = 1 ] && return 0
  QC_PATHS_RESOLVED=1
  local helper p
  helper="$(qc_digest_helper)" || return 0
  [ -n "$helper" ] || return 0
  if [ -z "${MM_QC_MARKER:-}" ]; then
    p="$(python3 "$helper" --record-path check 2>/dev/null)" || p=""
    [ -n "$p" ] && QC_MARKER="$p"
  fi
  if [ -z "${MM_QC_TRIAL_MARKER:-}" ]; then
    p="$(python3 "$helper" --record-path trial 2>/dev/null)" || p=""
    [ -n "$p" ] && QC_TRIAL_MARKER="$p"
  fi
  if [ -z "${MM_QC_ADJUDICATIONS:-}" ]; then
    p="$(python3 "$helper" --record-path adjudications 2>/dev/null)" || p=""
    [ -n "$p" ] && QC_ADJUDICATIONS="$p"
  fi
  export MM_QC_MARKER="$QC_MARKER" MM_QC_TRIAL_MARKER="$QC_TRIAL_MARKER"
  export MM_QC_ADJUDICATIONS="$QC_ADJUDICATIONS"
  return 0
}

resolve_qc(){
  local c
  for c in "${MM_QC_FIX:-}" \
           "$HOME/.claude/skills/mm-swe-qc-fix-sandbox/fix.py" \
           "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)/fix.py"; do
    [ -n "$c" ] && [ -f "$c" ] && { QC_FIX="$c"; return 0; }
  done
  return 1
}

qc_gate(){
  local task="$1"
  # Before fix.py runs: it inherits $MM_QC_MARKER from here, so the pass is written where
  # check_digest will look for it, whichever candidate directory that turned out to be.
  resolve_record_paths
  if ! resolve_qc; then
    say "WARNING: MM SWE QC skill not found - the QC gate was SKIPPED, not passed."
    say "         Install mm-swe-qc-fix-sandbox or set \$MM_QC_FIX to its fix.py."
    # No marker: "we could not check" must never leave the same trace as "it passed".
    return 0
  fi
  say "QC audit via $QC_FIX (read-only; no fixes, no docker)"
  local qrc
  local -a qargs=(qc "$task" --gate-tier bundle --no-report)
  local v
  for v in ${ADJUDICATED+"${ADJUDICATED[@]}"}; do qargs+=(--adjudicated "$v"); done
  python3 "$QC_FIX" "${qargs[@]}"
  qrc=$?
  if [ "$qrc" = 0 ]; then
    # No mention of the marker: it is an internal artifact and fix.py owns it silently.
    say "QC clean"
    return 0
  fi

  # 3 = no blocking FAILs, but bundle-tier finding(s) are PENDING an agent's ruling, so fix.py
  # recorded no QC pass. THIS IS NOT "CLEAN" AND MUST NOT SPEND A RUN. Reading only the truthiness
  # of the exit status collapsed this into the 0 branch: the gate said "QC clean", the check run was
  # spent, and because the audit had written no marker, check_digest() then refused to run
  # oracle/nop and sent the CB back to /run-check -- which said "QC clean" again. The loop had no
  # exit, and the one action that ends it (adjudicating) was never named to anybody.
  #
  # NO [y/N] OVERRIDE HERE, unlike the blocker branch below. An override is the right offer when
  # the alternative is expensive (fixing real defects); here the correct action is cheap, and
  # overriding would spend the run AND still leave no marker -- i.e. re-enter the livelock one step
  # further along. fix.py has already printed the ids and the exact flag, so this only has to say
  # that the run was not spent and why.
  if [ "$qrc" = 3 ]; then
    say "QC found no blockers, but the finding(s) above await adjudication — NOT spending a run."
    say "         These are proposals, not failures: the script gathered the evidence but cannot"
    say "         perform the READ that decides them."
    say ""
    say "         OVERFIT findings (tests_overfit_*) - THREE STEPS, IN THIS ORDER."
    say ""
    say "         1. REPORT. Tell the CB in plain words what each test pins and which other"
    say "            correct implementation it would reject. Never an id on its own."
    say "         2. ASK WHETHER TO INSPECT, AND WAIT. Do not investigate unasked and do not"
    say "            rule unasked. These are read off test source alone, so each is a QUESTION -"
    say "            the CB decides whether chasing it is worth the time. Do not ask them to"
    say "            adjudicate it either; that is the analysis they have you for."
    say "         3. IF THEY SAY YES, inspect with TEST_FITNESS.md: read the test BODY rather"
    say "            than the diff (the diff hides the helpers) to see whether the symbol is"
    say "            asserted BY NAME or discovered by behaviour; grep the BASE tree to check"
    say "            the 'the golden fix introduces this' claim, the most common false finding;"
    say "            open the posters; and MEASURE where the read runs out (~2s per test)."
    say ""
    say "         What the evidence shows to be a FALSE POSITIVE, you clear yourself with that"
    say "         evidence as the reason - it is recorded and replays on later audits, so the"
    say "         gate stays green for every run. What it shows to be REAL is a defect to fix."
    say "         Inconclusive: say so and go back to the CB."
    say ""
    say "         NEVER clear one you have not inspected. THE CB NEVER TYPES A FLAG."
    say ""
    say "         Matcher/collision findings are yours to decide - read the cited line in"
    say "         tests/verifier.py first. Either way, YOU apply the ruling by re-running:"
    say "           MM_VIA=run-check bash <runner>/mm_run.sh <task> check \\"
    say "               --adjudicated <id>=cleared:\"why\"      (or =confirmed:\"why\")"
    say ""
    say "         A ruling is recorded, so it is applied once: later audits replay it without the"
    say "         flag. It expires by itself if tests/ or solution/ changes, because then it is a"
    say "         judgment about code that no longer exists."
    say ""
    # NO BACKTICKS IN say STRINGS. say's argument is double-quoted, so `cleared` runs a command and
    # substitutes its (empty) output -- the word vanishes from the message and bash prints
    # "cleared: command not found" into the middle of the gate's advice.
    say "         A ruling is a judgment, not a formality: 'cleared' is what records the QC pass,"
    say "         so clear only what you have actually read and can justify. When the verifier's"
    say "         matching is not clearly collision-proof, 'confirmed' is the safe ruling."
    say "         (--no-qc skips this gate, but records no pass either, so oracle/nop stay blocked.)"
    return 9
  fi

  # 4 = the audit found nothing blocking, but could NOT record the pass -- the marker write failed,
  # or the judging raised. PROCEED: no decidable finding was a FAIL, so the check run is still worth
  # spending, and grounding the gate on a /tmp problem would strand the CB (the oracle/nop digest
  # gate has no bypass flag at all). But NEVER say "QC clean" here -- that word claims a recorded
  # pass, and the absence of one is exactly what will bite them at the next step. Said loudly and
  # unconditionally: fix.py keeps the marker internal and stays silent, so if this branch does not
  # speak, nobody learns why oracle and nop refuse to run afterwards.
  #
  # This branch should now be unreachable for the reason it used to fire. Records resolve through
  # qc_digest.record_path, which falls back to another directory when the primary cannot hold one,
  # so a clean audit no longer loses its pass to a directory the CB never chose. What is left is a
  # genuine internal fault -- the judging block raising -- which is ours to fix, not theirs.
  #
  # So this says NOTHING the CB must act on: no path, no directory, no cleanup, no environment to
  # repair. Naming the file would be worse here than anywhere else, because the record is missing
  # exactly when this prints, putting them one `touch` from a record no audit earned. And naming a
  # directory would be asking them to go fix infrastructure to make their own controls run. The
  # only supported action is re-running a free audit, so that is the only thing offered.
  # $MM_QC_MARKER_DEBUG surfaces the underlying write error, for us.
  if [ "$qrc" = 4 ]; then
    say "QC found nothing blocking, but NO QC pass could be recorded."
    say "         Nothing is wrong with the task, and there is nothing for you to fix — this is the"
    say "         audit's own bookkeeping, and it should not happen. Please report it."
    say "         Re-run /run-check: the audit is free and a clean pass records itself."
    say ""
    say "         The check run proceeds. oracle and nop will REFUSE until a pass is on record,"
    say "         so re-run the audit before the controls."
    [ -n "${MM_QC_MARKER_DEBUG:-}" ] && say "         (record path: $QC_MARKER — write error above.)"
    return 0
  fi

  # QC found bundle-level FAILs. The decision to spend the run anyway is the USER'S, so ask -
  # but only when there is a human on the other end of stdin.
  if [ -t 0 ]; then
    printf '\n'
    say "QC found bundle-level FAIL(s) above."
    printf '[mm_run] spend a check run on this task anyway? [y/N] '
    local ans=""; read -r ans </dev/tty || ans=""
    case "$ans" in
      # Deliberately NO write_qc_marker here. The run proceeds, but the blockers were not fixed,
      # so nothing may record this task as having passed QC.
      y|Y|yes|YES) say "proceeding at your request - the findings above still stand."
                   say "NOT recording a QC pass: the blockers above were overridden, not fixed."
                   return 0;;
      *) say "stopped. Fix the FAILs above, then re-run - a clean audit records the QC pass."
         say "         (--no-qc skips this gate, and never records a pass either.)"
         return 1;;
    esac
  fi

  # Non-interactive (an agent, a script, CI): there is nobody to ask here, so DO NOT guess.
  # Exit 7 - distinct from the other gates' 2 - means "QC found issues, ask the user and re-run".
  say "QC found bundle-level FAIL(s) above, and stdin is not a terminal so you cannot be asked."
  say "Ask the CB whether to spend the run, then re-run with --no-qc to proceed."
  return 7
}


run_check(){
  if [ "$FILE_CHECK" = 1 ]; then
    say "task $TASK_ID — checking required files under $TASK_DIR"
    check_files "$TASK_DIR" || {
      say "not spending a check run on an incomplete task — add the files above,"
      say "or pass --no-file-check to run harbor check anyway."
      return 2
    }
  fi
  if [ "$INTEGRITY_CHECK" = 1 ]; then
    say "task $TASK_ID — checking metadata consistency under $TASK_DIR"
    check_integrity "$TASK_DIR" || {
      say "not spending a check run on a task with inconsistent metadata — fix the"
      say "FAILs above, or pass --no-integrity-check to run harbor check anyway."
      return 2
    }
  fi
  # --no-qc skips the gate, so fix.py never runs and never updates the marker. Clear it here so a
  # verdict from an earlier task cannot vouch for this one. (When the gate DOES run, fix.py owns
  # the file end to end - it writes on clean and removes on blockers.)
  # Resolve first: clearing the default path while the record sits in a fallback one would leave
  # exactly the stale verdict this line exists to remove.
  [ "$QC_CHECK" = 1 ] || { resolve_record_paths; rm -f "$QC_MARKER"; }
  if [ "$QC_CHECK" = 1 ]; then
    say "task $TASK_ID — QC audit before spending a check run"
    qc_gate "$TASK_DIR"; qcrc=$?
    [ "$qcrc" = 0 ] || return "$qcrc"
  fi
  # check-reviewers rides the SAME function rather than a parallel copy of it, so the file check,
  # the integrity check, the QC gate and the whole harbor invocation below cannot drift between the
  # two modes. The only difference is this block.
  #
  # Placed after the QC gate and before anything is spent, deliberately: a bundle whose recorded
  # runs are stale has to be re-run whatever the check rubric says, so buying a check verdict first
  # would be spend the reviewer cannot use. Exit 9 is the trial gate's existing "the controls are
  # not green and current" code, reused rather than invented.
  if [ "$REVIEWERS" = 1 ]; then
    verify_recorded_runs || return 9
  fi
  mkdir -p "$ROOT"
  [ "$KEEP" = 1 ] || rm -rf "${ROOT:?}/Check"
  resolve_creds
  say "task $TASK_ID"
  say "check agent=$AGENT model=$CHECK_MODEL"
  say "creds base=$BASE key=$(mask "$KEY")"
  setup_anon_route
  local -a hargs=(check "$TASK_DIR" -e "$HENV" -o "$ROOT" --job-name "Check"
                  -a "$AGENT" -m "$CHECK_MODEL"
                  --ae ANTHROPIC_BASE_URL="$CBASE"
                  --ae ANTHROPIC_API_KEY="$KEY")
  [ -n "$RUBRIC" ]       && hargs+=(-r "$RUBRIC")
  [ -n "$CHECK_PROMPT" ] && hargs+=(-p "$CHECK_PROMPT")
  say "check -> $ROOT/Check"
  say_harbor "${hargs[@]}"
  harbor "${hargs[@]}"
  local rc=$?; report_rubric "$ROOT/Check/check_report.json" check; return $rc
}

run_analyze(){
  if [ ! -d "$ANALYZE_PATH" ]; then
    say "ERROR: nothing to analyze at $ANALYZE_PATH"
    say "       run a trial first, or pass a job/trial dir instead of a task dir."
    return 2
  fi
  mkdir -p "$ROOT"
  [ "$KEEP" = 1 ] || rm -rf "${ROOT:?}/Analyze"
  resolve_creds
  say "analyze $ANALYZE_PATH ($ANALYZE_SRC dir)"
  say "analyze agent=$AGENT model=$ANALYZE_MODEL"
  say "creds base=$BASE key=$(mask "$KEY")"
  setup_anon_route
  local -a hargs=(analyze "$ANALYZE_PATH" -e "$HENV" -o "$ROOT" --job-name "Analyze"
                  -a "$AGENT" -m "$ANALYZE_MODEL"
                  --ae ANTHROPIC_BASE_URL="$CBASE"
                  --ae ANTHROPIC_API_KEY="$KEY")
  [ -n "$RUBRIC" ]         && hargs+=(-r "$RUBRIC")
  [ -n "$CHECK_PROMPT" ]   && hargs+=(-p "$CHECK_PROMPT")
  [ -n "$ANALYZE_FILTER" ] && hargs+=("$ANALYZE_FILTER")
  [ -n "$N_TRIALS" ]       && hargs+=(-l "$N_TRIALS")
  say "analyze -> $ROOT/Analyze"
  say_harbor "${hargs[@]}"
  harbor "${hargs[@]}"
  local rc=$?
  report_rubric "$ROOT/Analyze/analysis.json" analyze
  # harbor also writes an analysis.json INTO each analyzed trial dir. A later
  # `trial` run without --keep deletes <ROOT>/Trials wholesale and takes those
  # with it — say so rather than let them vanish quietly.
  case "$ANALYZE_PATH" in
    "$ROOT/Trials"*) say "note: analysis.json was also written into $ANALYZE_PATH —"
                     say "      a later 'trial' run without --keep deletes that dir.";;
  esac
  return $rc
}

# --------------------------------------------------------------------- report
report_rubric(){  # $1 = check_report.json | analysis.json, $2 = label
  local f="$1" lbl="$2"
  [ -f "$f" ] || { say "$lbl: no report written at $f"; return 0; }
  python3 - "$f" "$lbl" <<'PY' >&2
import json, sys
d = json.load(open(sys.argv[1])); lbl = sys.argv[2]
for r in d.get("results", []):
    name = r.get("task_name") or r.get("trial_name") or "?"
    if r.get("error"):
        print(f"[mm_run] {lbl} {name}: ERROR {r['error'].splitlines()[0]}")
        continue
    tally = {}
    for cname, c in (r.get("checks") or {}).items():
        outcome = (c or {}).get("outcome", "?")
        tally[outcome] = tally.get(outcome, 0) + 1
        print(f"[mm_run] {lbl} {name}: {cname} = {outcome}")
    cost = r.get("cost_usd")
    line = ", ".join(f"{k}={v}" for k, v in sorted(tally.items())) or "no checks returned"
    if isinstance(cost, (int, float)):
        line += f"  (${cost:.4f})"
    print(f"[mm_run] {lbl} {name}: {line}")
PY
}

report(){  # $1 = job dir, $2 = label
  local d="$1" lbl="$2" f q
  # Prefer multi-key rewards (reward.json / result.json rewards dict) so the rubric verdict
  # is visible SEPARATELY from tests_passed. A single blended float hides the difference
  # between "the code is bad" and "the judge never ran".
  f="$(find "$d" -name reward.json 2>/dev/null | head -1)"
  [ -n "$f" ] || f="$(find "$d" -name result.json 2>/dev/null | head -1)"
  if [ -n "$f" ]; then
    q="$(python3 - "$f" "$lbl" <<'PY'
import json, sys
lbl = sys.argv[2] if len(sys.argv) > 2 else ""
try: d = json.load(open(sys.argv[1]))
except Exception: raise SystemExit(0)
r = d.get("rewards") or (d.get("verifier_result") or {}).get("rewards") or d
if not isinstance(r, dict): raise SystemExit(0)
bits = []
for k in ("reward", "tests_passed"):
    if k in r: bits.append("%s=%s" % (k, r[k]))
if r.get("f2p_total") is not None:
    bits.append("f2p=%s/%s" % (r.get("f2p_passed"), r.get("f2p_total")))
# p2p alongside f2p: the nop verdict below turns on BOTH halves, and a p2p regression shown
# only as a lower `reward` reads as "the fix is incomplete" rather than "this test is f2p".
if r.get("p2p_total") is not None:
    bits.append("p2p=%s/%s" % (r.get("p2p_passed"), r.get("p2p_total")))
# rubric: harbor's rewards dict must hold scalars, so the verifier now writes a numeric
# "rubric" plus "rubric_graded" (0 = the judge never ran). Older runs wrote the string
# "pass"/"fail"/None directly — still parsed so past job dirs stay readable.
# `rubric_passed` is the CANONICAL key (1 pass / 0 fail / -1 not graded) and is the ONLY
# spelling accepted: the QC skill enforces it as a blocking key-set check, so a reader that
# also took the old `rubric_pass` would let an unmigrated task look correct here while
# failing the audit. A task that reads "unavailable" below has not been migrated yet.
if "rubric_passed" in r:
    bits.append("rubric=%s" % {1: "pass", 0: "fail"}.get(r["rubric_passed"], "unavailable"))
elif "rubric_graded" in r:
    bits.append("rubric=%s" % ("pass" if r.get("rubric") else "fail")
                if r["rubric_graded"] else "rubric=unavailable")
elif "rubric" in r:
    bits.append("rubric=%s" % ("unavailable" if r["rubric"] is None else r["rubric"]))
if bits: print("  ".join(bits))
# Per-test detail: each test is graded individually; an aggregate cannot show which.
# New form is flattened "f2p::<name>" keys; old form was a nested {name: bool} dict.
flat = {}
for k, val in r.items():
    if isinstance(k, str) and "::" in k:
        grp, _, name = k.partition("::")
        if grp in ("f2p", "p2p"): flat.setdefault(grp, []).append((name, bool(val)))
for grp in ("f2p", "p2p"):
    rows = flat.get(grp)
    if rows is None:
        res = r.get(grp)
        rows = list(res.items()) if isinstance(res, dict) and res else []
    for name, ok in rows:
        sys.stderr.write("[mm_run]     %s %s  %s\n" % (grp, "PASS" if ok else "FAIL", name))
# THE NOP CRITERION, printed where it is first knowable. The pre-trial gate applies the same
# rule from control_counts() and refuses to spend a trial when it does not hold; this is the
# same verdict at the moment nop finishes, so an inert test is not first learned about later,
# after a `/run-check` that structurally could not see it (that audit runs at bundle tier,
# before Nop/ exists). Display only -- control_counts() does the blocking.
if lbl == "nop":
    _c = [r.get(k) for k in ("f2p_passed", "f2p_total", "p2p_passed", "p2p_total")]
    if any(v is None or isinstance(v, bool) for v in _c):
        sys.stderr.write("[mm_run]     nop: NO VERDICT - reward.json carries no f2p/p2p counts\n")
    else:
        _fp, _ft, _pp, _pt = (int(v) for v in _c)
        if _ft == 0:
            sys.stderr.write("[mm_run]     nop: BAD - f2p_total=0, no f2p test ran\n")
        elif _fp:
            sys.stderr.write("[mm_run]     nop: BAD - %d of %d f2p test(s) PASS on an empty "
                             "submission; they cannot detect the bug\n" % (_fp, _ft))
        elif _pp != _pt:
            sys.stderr.write("[mm_run]     nop: BAD - %d of %d p2p test(s) FAIL; they are "
                             "really f2p\n" % (_pt - _pp, _pt))
        else:
            sys.stderr.write("[mm_run]     nop: OK - all %d f2p fail, all %d p2p pass\n"
                             % (_ft, _pt))
failed = r.get("rubric_failed") or []
if failed:
    sys.stderr.write("[mm_run]     rubric failed criteria: %s\n" % ", ".join(map(str, failed)))
elif r.get("rubric_failed_count"):
    sys.stderr.write("[mm_run]     rubric failed criteria: %s (see verifier/detail.json)\n"
                     % r["rubric_failed_count"])
PY
)"
    [ -n "$q" ] && say "$lbl rewards: $q"
    if [ -z "$q" ]; then
      local rw; rw="$(find "$d" -name reward.txt 2>/dev/null | head -1)"
      [ -n "$rw" ] && say "$lbl reward = $(cat "$rw")"
    fi
  else
    local rw; rw="$(find "$d" -name reward.txt 2>/dev/null | head -1)"
    [ -n "$rw" ] && say "$lbl reward = $(cat "$rw")"
  fi

  # Rubric configured but no verdict came back while tests passed -> the in-container judge
  # probably never ran. Grade the same rubric HOST-side so QC still gets an answer.
  local already_graded=0
  if [ "$HAS_RUBRICS" = 1 ] && [ "$lbl" != "nop" ]; then
    if ! printf '%s' "${q:-}" | grep -qE "rubric=(pass|fail)"; then
      # BEFORE declaring anything: did the in-container judge already grade this run? It
      # writes summary.json beside verdict.json, and both survive into the collected logs.
      # `q` is built from the REWARD keys, so a run whose verifier records a non-canonical
      # key (`rubric_pass` for `rubric_passed`) shows no rubric= bit even though grading
      # succeeded — and the old code read that as "the judge never ran" and spent a second
      # model call re-grading a diff that had already been graded.
      local sum sv
      sum="$(find "$d" -type f -name summary.json -path '*judge*' 2>/dev/null | head -1)"
      if [ -n "$sum" ]; then
        sv="$(python3 -c "import json,sys
try: print((json.load(open(sys.argv[1])) or {}).get('rubric') or '')
except Exception: pass" "$sum" 2>/dev/null)"
        case "$sv" in
          pass|fail)
            say "$lbl: the in-container judge DID grade this run — rubric=$sv"
            say "  $sum"
            say "  It is absent from the rewards above because they carry no canonical"
            say "  'rubric_passed' key. That is a TASK defect, not a judge failure: check the"
            say "  write site in tests/verifier.py (QC reports it as <run>_reward_keys_noncanonical)."
            say "  Not re-grading — the verdict already exists."
            already_graded=1;;
        esac
      fi
    fi
  fi
  if [ "$HAS_RUBRICS" = 1 ] && [ "$lbl" != "nop" ] && [ "$already_graded" = 0 ]; then
    if ! printf '%s' "${q:-}" | grep -qE "rubric=(pass|fail)"; then
      say "$lbl: no rubric verdict from the verifier — grading host-side as a fallback"
      local ws hq jdir vout req src
      # WHERE THE CANDIDATE DIFF COMES FROM, in order of fidelity.
      #
      # This used to look only for a collected `workspace` directory — and harbor does not
      # collect one. Measured on a real run: agent/ artifacts/ verifier/ and four files, no
      # workspace at any depth. So the fallback could never fire, and the one time it was
      # asked to it said "no collected workspace found" and gave up.
      #
      # judge/source.txt is the RIGHT source anyway: judge.py writes it precisely when its own
      # API backend failed, which is the only situation where this fallback matters, and it is
      # the same already-filtered diff the in-container judge would have graded. Grading the
      # identical bytes is what makes the two backends comparable.
      src=""
      req="$(find "$d" -type f -name PROMPT.md 2>/dev/null | head -1)"
      [ -n "$req" ] && [ -s "$(dirname "$req")/source.txt" ] && src="$(dirname "$req")/source.txt"
      ws="$(find "$d" -type d -name workspace 2>/dev/null | tail -1)"
      # Last resort, oracle only: the oracle's candidate diff IS the golden patch, by
      # construction. Never for a trial — there the agent's diff is the whole question, and
      # substituting the golden fix would grade the wrong artifact and always pass.
      if [ -z "$src" ] && [ -z "$ws" ] && [ "$lbl" = oracle ] && [ -f "$TASK_DIR/solution/fix.patch" ]; then
        src="$TASK_DIR/solution/fix.patch"
        say "  no judge request and no workspace — grading solution/fix.patch (the oracle's own diff)"
      fi
      if [ -n "$src" ] || [ -n "$ws" ]; then
        # Write the grade where the task's own judge.py looks. Prefer the judge dir the
        # in-container run already laid down (it sits beside PROMPT.md); otherwise put it
        # next to the collected verifier logs, which is where rescore searches.
        req="$(find "$d" -type f -name PROMPT.md 2>/dev/null | head -1)"
        if [ -n "$req" ]; then jdir="$(dirname "$req")"
        else
          jdir="$(find "$d" -type d -name verifier 2>/dev/null | head -1)"
          [ -n "$jdir" ] && jdir="$jdir/judge" || jdir="$d/verifier/judge"
        fi
        vout="$jdir/verdict.json"
        local -a gargs=(--rubrics "$RUBRICS_FILE" --verdict-out "$vout")
        if [ -n "$src" ]; then gargs+=(--diff-file "$src"); say "  grading $src"
        else                   gargs+=(--workspace "$ws");  say "  grading the diff in $ws"; fi
        # Same channel and model as the in-container judge (resolve_creds set these), so the
        # two backends cannot disagree on the same diff for want of a different model.
        # ONE call. stdout is the verdict, stderr is the grader's diagnostics — kept in a log
        # beside the run so a failure says why, without spending a second model call to find out.
        local glog="$d/host_judge.log"
        hq="$(EVAL_BASE_URL="${EVAL_BASE:-}" EVAL_API_KEY="${EVAL_KEY:-}" \
              EVAL_MODEL="${EVAL_MODEL_NAME:-}" \
              ANTHROPIC_BASE_URL="${BASE:-http://localhost:8091}" \
              ANTHROPIC_API_KEY="${KEY:-anonymizer-placeholder}" \
              JUDGE_MODEL="${JUDGE_MODEL:-claude-sonnet-5}" \
              python3 "$HERE/mm_grade_rubrics.py" "${gargs[@]}" 2>"$glog" || true)"
        if [ -n "$hq" ]; then
          say "$lbl HOST-SIDE rubric verdict = $hq"
          grep -E '^\[grade\] (graded via|[0-9]+/[0-9]+ criteria)' "$glog" 2>/dev/null \
            | while IFS= read -r l; do say "  $l"; done
          if [ -f "$vout" ]; then
            say "  verdict written to $vout — fold it into the reward with:"
            say "    mm_run.sh \"$TASK_DIR\" rescore --run \"$d\""
            say "  until you do, this run's reward is scored on tests alone."
          fi
        else
          say "$lbl host-side grade unavailable too — see $glog"
          tail -3 "$glog" 2>/dev/null | while IFS= read -r l; do say "    $l"; done
        fi
      else
        say "$lbl: no collected workspace found, cannot host-side grade"
      fi
    fi
  fi

  case "$lbl" in
    oracle) say "expected: 1.0  (lower = the golden patch does not satisfy the tests)";;
    nop)    say "expected: every f2p FAILS, every p2p PASSES  (see the nop: line above; the"
            say "          reward is NOT the criterion - it is 0.0 whenever any f2p fails, so it"
            say "          cannot show an f2p test that passes without the fix)";;
  esac
}

# Fold a judge verdict into an EXISTING run's reward. Ported from runner 1.3.0, which was the
# only copy that had it — without this the sub-agent judge path cannot complete: judge.py writes
# a request during the run, something grades it, and nothing existed to recompute the reward.
#
# Keyless and dockerless: it re-runs the task's OWN judge.py and verifier.py over artifacts that
# are already on disk, so the reward is computed by exactly the code the container would have
# used. No model call happens here — the grading already happened when verdict.json was written.
run_rescore(){
  local d="${RUN_DIR:-$TRIALS_DIR}"
  [ -d "$d" ] || { say "ERROR: no run dir at $d (pass --run DIR)"; return 2; }
  [ "$HAS_RUBRICS" = 1 ] || { say "ERROR: $RUBRICS_FILE not found — nothing to rescore"; return 2; }

  local vdir vfile xml
  vfile="$(find "$d" -type f -name verdict.json 2>/dev/null | head -1)"
  if [ -z "$vfile" ]; then
    local req; req="$(find "$d" -type f -name PROMPT.md 2>/dev/null | head -1)"
    if [ -n "$req" ]; then
      say "no verdict.json yet. The judge request is at:"
      say "  $(dirname "$req")"
      say "Have the judge sub-agent read PROMPT.md and write verdict.json beside it, then"
      say "re-run: mm_run.sh \"$TASK_DIR\" rescore --run \"$d\""
    else
      say "no verdict.json and no judge request under $d — run oracle/trial first."
    fi
    return 2
  fi
  vdir="$(dirname "$vfile")"
  xml="$(find "$d" -type f -name 'report*.xml' 2>/dev/null | head -1)"
  [ -n "$xml" ] || { say "ERROR: no JUnit report under $d; cannot recompute the reward"; return 2; }
  say "rescoring $d"
  say "  verdict: $vfile"
  say "  report:  $xml"

  # Score the verdict, then re-run the task's own verifier over the existing XML so the
  # reward is computed by exactly the same code the container would have used.
  local verdict
  verdict="$(PB_JUDGE_DIR="$vdir" python3 "$TASK_DIR/tests/judge.py" \
               --rubrics "$RUBRICS_FILE" --repo "$TASK_DIR" --judge-dir "$vdir" 2>&1 | tail -1)"
  case "$verdict" in
    pass|fail) say "  rubric verdict: $verdict";;
    *) say "ERROR: judge could not score the verdict (got: ${verdict:-<empty>})"; return 2;;
  esac

  # verifier.py writes reward.txt/reward.json NEXT TO the JUnit report, so running it from the
  # report's directory keeps the host-side rewrite inside this run dir.
  local outdir; outdir="$(dirname "$xml")"
  ( cd "$outdir" && python3 "$TASK_DIR/tests/verifier.py" "$xml" --rubric "$verdict" ) >/dev/null 2>&1 \
    || say "  note: verifier.py returned non-zero; check its output paths"
  say "NOTE: this rewrites the run dir's reward.json/reward.txt. harbor's own result.json is"
  say "      NOT updated — it was recorded when the run finished and is immutable."
  report "$d" rescore
  return 0
}

# ------------------------------------------------------ `check` goes through Claude Code chat
# WHY ONLY check. It is the mode whose output a CB cannot act on alone: it spends credentials, and
# it returns a task-quality rubric plus a QC audit that has to be READ to them -- worst finding
# first, with a decision about whether to spend another run. /run-check carries those instructions;
# a bare shell invocation has nobody to give them. oracle/nop stay directly invocable on purpose:
# they are keyless and are the loop a CB runs while repairing a task, which is where friction costs
# the most.
#
# WHY A TOKEN AND NOT A COMMAND-LINE OR ENVIRONMENT TEST. /run-check's own step is this same
# command, and a command pasted into chat reaches this script through the same Bash tool with the
# same environment (CLAUDECODE=1 either way). The two paths were genuinely indistinguishable, so
# the sanctioned one now announces itself: MM_VIA=run-check. Nothing about the shell can be
# sniffed to recover that -- it has to be passed.
#
# NOT A SECURITY BOUNDARY, and not meant as one. Anyone reading this file can set the variable.
# It exists to make the supported path the easy one and the bypass deliberate, not to prevent it.
#
# MM_ALLOW_DIRECT=1 is the escape hatch, and it is load-bearing: CI, and the team's own scripted
# runs, invoke this without a chat session and must not be broken by a workflow preference.
# Both check modes, for the same reason: each spends a credentialed run, and each is only useful
# when an agent reads the findings back to the CB or reviewer. check-reviewers additionally MINTS
# markers other gates trust, so a bare shell invocation of it is even less something to leave
# reachable by accident.
# pseudo-trial joins them on the check-reviewers argument specifically: it spends no model call,
# but it WRITES the trial record other gates trust, off a gate whose refusals need reading back to
# a human in words. A bare shell invocation of a record-minting mode is the thing this prevents.
if { [ "$MODE" = check ] || [ "$MODE" = check-reviewers ] || [ "$MODE" = pseudo-trial ]; } \
   && [ -z "${MM_VIA:-}" ] && [ "${MM_ALLOW_DIRECT:-0}" != 1 ]; then
  # The message deliberately does NOT mention MM_ALLOW_DIRECT. The hatch still works and is still
  # documented in the usage block and SKILL.md, where CI and the team look for it -- but printing it
  # HERE would teach the terminal invocation to the one audience being redirected away from it, one
  # line after telling them not to. TASK_DIR is guaranteed non-empty: the -d check above exits 2
  # before this point.
  say "\`$MODE\` is run through Claude Code chat, not directly through the terminal."
  say ""
  if [ "$MODE" = check-reviewers ]; then
    say "  In the chat, run:  /run-check-reviewers $TASK_DIR"
    say "                     or just     /run-check-reviewers"
  elif [ "$MODE" = pseudo-trial ]; then
    say "  In the chat, run:  /run-pseudo-trial $TASK_DIR"
    say "                     or just     /run-pseudo-trial"
  else
    say "  In the chat, run:  /run-check $TASK_DIR"
    say "                     or just     /run-check"
  fi
  say ""
  say "Nothing was run and no credentials were used."
  exit 8
fi

# ------------------------------------------- `trial` needs both controls on disk first
# WHY. The trial is the one mode that spends a real model on real wall clock, and its
# reward is uninterpretable until the task's two controls have already agreed:
#   oracle = 1  the tests CAN be passed — the golden patch passes them
#   nop    = 0  the tests are not passed for free — an empty submission fails them
# Without those, a trial that scores 0 cannot be told apart from a broken task, and a
# trial that scores 1 might just be a task that scores 1 for doing nothing. So the
# controls are a precondition, not advice.
#
# WHAT IS READ. <ROOT>/Oracle and <ROOT>/Nop — exactly where run_plain writes them, so
# the gate is satisfied by having run the two commands it prints and nothing else. Both
# dirs are per-ROOT and rm -rf'd on each run, so whatever is in them is the most recent
# oracle/nop for this ROOT. It follows that a CB juggling several tasks under one ROOT
# should point --root at each task's own output tree, as they already must for the runs
# themselves not to overwrite each other.
#
# IT IS ALSO A STALENESS CHECK, via control_digest() below. A green reward alone answers
# "were the controls ever green", not "are they still green for THIS bundle" — and a control
# that ran before the last edit to tests/ or solution/ is measuring code that no longer
# exists, which is the more expensive failure of the two: the trial it green-lights costs a
# real model call and its reward describes a task nobody is submitting.
#
# MM_ALLOW_UNVERIFIED=1 is the escape hatch, and it is load-bearing for the same reason
# MM_ALLOW_DIRECT is: CI and scripted sweeps run the trial with no CB present, sometimes
# against controls collected elsewhere. Like that hatch, it is documented in the header
# and SKILL.md but deliberately NOT printed below — the audience being redirected to the
# controls is not the audience that needs it.
# ---- staleness: is a control's recorded task digest the digest of the bundle right now? ----
#
# WHAT THE DIGEST IS, MEASURED against harbor 0.18 rather than assumed. Every harbor run writes
# <job>/lock.json with trials[].task.digest, and that value is
# `Packager.compute_content_hash(task_dir)`:
#
#     files = [task.toml, instruction.md, README.md] + rglob(environment/, tests/, solution/, steps/)
#     files sorted by relative posix path, filtered by .gitignore or a default ignore list
#     sha256 over  f"{relative_path}\0{sha256(file_bytes)}\n"  for each file, in that order
#
# CONTENT ONLY — no mtimes, no absolute paths, no run id, no timestamp. So it is stable across
# runs of an unchanged bundle (verified: an oracle and a nop two minutes apart recorded the same
# digest, and recomputing it 11 days later still matched), and it changes if and only if one of
# those files changes. That is exactly the property a staleness gate needs.
#
# WHAT IT DOES NOT COVER: evidence_bundle.json, and anything else outside the directories above.
# harbor hashes what it ships to the container, so an edit to the evidence documents alone leaves
# the digest untouched — correctly, since it cannot change a reward. Use `qc` for those.
#
# WHY NOT result.json: harbor 0.18's job-level result.json carries no task_checksum at all (it
# holds stats/evals), so anything reading one there is reading None. lock.json is where the value
# actually lives.
harbor_python(){  # echoes an interpreter that can import harbor, or nothing
  local h shebang first
  h="$(command -v harbor 2>/dev/null)" || return 0
  h="$(readlink -f "$h" 2>/dev/null || printf '%s' "$h")"
  shebang="$(head -1 "$h" 2>/dev/null)"
  case "$shebang" in "#!"*) : ;; *) return 0 ;; esac
  first="$(printf '%s' "${shebang#\#!}" | awk '{print $1}')"
  # `#!/usr/bin/env python3` -> take the interpreter env would resolve, not env itself.
  case "$first" in */env) first="$(printf '%s' "${shebang#\#!}" | awk '{print $2}')" ;; esac
  [ -x "$first" ] || return 0
  "$first" -c "import harbor.publisher.packager" 2>/dev/null && printf '%s' "$first"
}

task_digest_now(){  # $1 = task dir -> echoes "sha256:..." or nothing if it cannot be computed
  local py
  py="$(harbor_python)"
  # PREFER HARBOR'S OWN CODE. The digest recorded in lock.json is whatever harbor computed, so
  # recomputing it with harbor's function is the only way the comparison cannot drift when
  # harbor changes the algorithm. The fallback below exists for a harbor that cannot be
  # imported, and it declines rather than guesses wherever it would not be byte-exact.
  if [ -n "$py" ]; then
    "$py" - "$1" <<'PY' 2>/dev/null
import sys
from pathlib import Path
from harbor.publisher.packager import Packager
print("sha256:" + Packager.compute_content_hash(Path(sys.argv[1]))[0])
PY
    return 0
  fi
  python3 - "$1" <<'PY' 2>/dev/null
# Stdlib reimplementation of Packager.compute_content_hash, used only when harbor is not
# importable. It DECLINES (prints nothing) when the task ships a .gitignore, because harbor
# then filters with pathspec's gitignore semantics and a hand-rolled imitation could differ —
# printing a wrong digest would fail a current control, which is worse than not checking.
import hashlib, sys
from pathlib import Path
task = Path(sys.argv[1]).resolve()
if (task / ".gitignore").exists():
    raise SystemExit(0)
IGNORE_SUFFIX = (".pyc", ".swp", ".swo", "~")
def ignored(rel):
    parts = rel.split("/")
    return "__pycache__" in parts[:-1] or parts[-1] == ".DS_Store" \
        or rel.endswith(IGNORE_SUFFIX)
files = [task / n for n in ("task.toml", "instruction.md", "README.md")]
files = [f for f in files if f.exists()]
for d in ("environment", "tests", "solution", "steps"):
    p = task / d
    if p.exists():
        files += [f for f in p.rglob("*") if f.is_file()]
rels = sorted(f.relative_to(task).as_posix() for f in files)
outer = hashlib.sha256()
for rel in rels:
    if ignored(rel):
        continue
    inner = hashlib.sha256()
    with (task / rel).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            inner.update(chunk)
    outer.update(f"{rel}\0{inner.hexdigest()}\n".encode())
print("sha256:" + outer.hexdigest())
PY
}

control_digest(){  # $1 = job dir -> echoes the digest its lock.json recorded, "mixed", or nothing
  [ -d "$1" ] || return 0
  python3 - "$1" <<'PY'
import json, os, sys

# Every trial in the lock file must name the same task digest; a job that somehow mixed two
# bundles is not a control, so it reports "mixed" rather than having one value picked for it -
# the same rule control_reward() applies to a dir holding disagreeing rewards.
seen = set()
for dirpath, _, filenames in os.walk(sys.argv[1]):
    if "lock.json" not in filenames:
        continue
    try:
        lock = json.load(open(os.path.join(dirpath, "lock.json")))
    except Exception:
        continue
    for trial in lock.get("trials") or []:
        digest = ((trial or {}).get("task") or {}).get("digest")
        if digest:
            seen.add(digest)
    # BOTH LOCK SHAPES, because harbor writes two. The job-level lock.json carries a trials[]
    # array; the per-trial lock.json inside Tasks__*/ has no array at all and hangs `task` off the
    # root. Reading only the array meant a stale per-trial lock sat unexamined next to a current
    # job-level one -- and this function reported the bundle as current. On a job dir kept with
    # --keep, where an old trial dir can survive a newer job lock, that is a live way to be told a
    # stale run is fresh. Collecting both shapes makes the divergence surface as "mixed", which is
    # what it is. Real harbor writes the same digest at both levels, so this changes nothing on
    # honest output -- it only ever makes the answer stricter, never looser.
    digest = ((lock.get("task") or {}).get("digest"))
    if digest:
        seen.add(digest)
if not seen:
    raise SystemExit(0)
print(next(iter(seen)) if len(seen) == 1 else "mixed")
PY
}

control_reward(){  # $1 = job dir -> echoes the reward, "mixed", or nothing if unreadable
  [ -d "$1" ] || return 0
  python3 - "$1" <<'PY'
import json, os, sys

# Same precedence as report(): a verifier-written reward.json/reward.txt is the truth, and
# a result.json is read through harbor's own nesting. The JOB-level result.json carries no
# reward at all (it holds stats/evals), so it drops out here instead of reading as 0.
vals = []
def add(v):
    try: vals.append(float(v))
    except (TypeError, ValueError): pass

for dirpath, _, filenames in os.walk(sys.argv[1]):
    for name in filenames:
        path = os.path.join(dirpath, name)
        if name in ("reward.json", "result.json"):
            try: d = json.load(open(path))
            except Exception: continue
            r = d.get("rewards") or (d.get("verifier_result") or {}).get("rewards") or d
            if isinstance(r, dict) and r.get("reward") is not None:
                add(r["reward"])
        elif name == "reward.txt":
            try: add(open(path).read().strip())
            except Exception: pass

if not vals: raise SystemExit(0)
# Attempts inside one control dir must agree. A mixed dir is not a clean control, and
# picking one of the values would hide that — so it is reported as mixed and fails.
if len(set(vals)) != 1:
    print("mixed"); raise SystemExit(0)
# The caller compares the printed text against "1"/"0", so -0.0 (which %g renders as
# "-0") has to land on the same spelling as 0.0 or a zero nop would read as non-zero.
v = vals[0]
print("%g" % (0.0 if v == 0 else v))
PY
}

# ---- nop inertness: do the COUNTS show every f2p failing and every p2p passing? ----
#
# WHY THE COUNTS AND NOT THE REWARD. `reward` is 0.0 whenever ANY f2p test fails, so it says
# nothing about the others: a nop scoring 0 is equally consistent with "all four f2p failed" and
# with "three failed and the fourth passed without the fix". That fourth test is INERT -- it
# cannot detect the bug, so the task grades nothing real while every reward looks healthy -- and
# it is the defect class that got through review before. The four count keys answer it directly;
# the reward cannot, at any value.
#
# THE KEYS ARE THERE BY CONSTRUCTION. qc_rubric_format fails `verifier.reward_json.keys` as a
# BLOCKING bundle-tier finding when verifier.py's write site is missing any of the canonical
# seven, and check_digest() refuses to run nop without that audit on record. So a Nop/ produced
# through this runner came from a bundle audited to emit them. Absence is still handled below
# rather than assumed away: an audit can be SKIPPED (no QC skill installed -> qc_gate() warns and
# returns 0), and a run killed before the verifier's atexit flush leaves the file short. Both
# land here as "no counts", and both are refused -- re-running nop is keyless and cheap, and
# falling back to the reward would reinstate exactly the blind spot this function exists to close.
#
# The rubric side is deliberately not read: a judge verdict on an empty diff says nothing about
# whether the TESTS discriminate, which is the only question here.
control_counts(){  # $1 = job dir -> "f2p_passed f2p_total p2p_passed p2p_total", "mixed", or nothing
  [ -d "$1" ] || return 0
  python3 - "$1" <<'PY'
import json, os, sys

KEYS = ("f2p_passed", "f2p_total", "p2p_passed", "p2p_total")
# Same precedence as control_reward(): a verifier-written reward.json is the truth, and a
# result.json is read through harbor's own nesting. reward.txt is a lone float carrying no
# counts, so it drops out here instead of reading as zeros.
seen = set()
for dirpath, _, filenames in os.walk(sys.argv[1]):
    for name in filenames:
        if name not in ("reward.json", "result.json"):
            continue
        try: d = json.load(open(os.path.join(dirpath, name)))
        except Exception: continue
        r = d.get("rewards") or (d.get("verifier_result") or {}).get("rewards") or d
        if not isinstance(r, dict):
            continue
        vals = []
        for k in KEYS:
            v = r.get(k)
            # bool is an int subclass, and `f2p_passed: false` must not read as a healthy 0.
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                vals = None
                break
            vals.append(int(v))
        if vals is not None:
            seen.add(tuple(vals))

if not seen: raise SystemExit(0)
# Attempts inside one control dir must agree, exactly as control_reward() requires of the
# reward. Picking one of two disagreeing tallies would hide that they disagree at all.
if len(seen) != 1:
    print("mixed"); raise SystemExit(0)
print("%d %d %d %d" % tuple(next(iter(seen))))
PY
}

# ---- pass@k tally ------------------------------------------------------------------------
# control_reward() answers "do the attempts AGREE", which is right for a control and wrong for
# a trial: it collapses 1-of-5-solved and 4-of-5-solved into the same `mixed`. The record rule
# needs the distribution, so this counts ATTEMPTS, not reward files.
#
# One attempt writes its reward three times (result.json, verifier/reward.json,
# verifier/reward.txt), so files are grouped by attempt dir -- the directory holding them, with
# a trailing /verifier stripped -- and each attempt contributes exactly one value. The JOB-level
# result.json carries no reward at all, so it drops out instead of counting as an extra attempt
# (which is precisely the miscount report_attempts used to make: pass@6 for a 5-attempt run).
# An attempt whose own files disagree is not a readable attempt: the tally reports nothing
# rather than guess, and every caller has a "cannot tell" branch for that.
trial_tally(){  # $1 = job dir -> echoes "<failed> <total>" (failed = reward 0), or nothing
  [ -d "$1" ] || return 0
  python3 - "$1" <<'PY'
import json, os, sys

attempts = {}   # attempt dir -> set of rewards seen for it

def add(key, v):
    try: attempts.setdefault(key, set()).add(float(v))
    except (TypeError, ValueError): pass

for dirpath, _, filenames in os.walk(sys.argv[1]):
    key = dirpath[:-len("/verifier")] if dirpath.endswith("/verifier") else dirpath
    for name in filenames:
        path = os.path.join(dirpath, name)
        if name in ("reward.json", "result.json"):
            try: d = json.load(open(path))
            except Exception: continue
            r = d.get("rewards") or (d.get("verifier_result") or {}).get("rewards") or d
            if isinstance(r, dict) and r.get("reward") is not None:
                add(key, r["reward"])
        elif name == "reward.txt":
            try: add(key, open(path).read().strip())
            except Exception: pass

if not attempts: raise SystemExit(0)
# An attempt that cannot state its own reward consistently is not counted as an attempt at all.
if any(len(v) != 1 for v in attempts.values()): raise SystemExit(0)
vals = [next(iter(v)) for v in attempts.values()]
print("%d %d" % (sum(1 for v in vals if v == 0), len(vals)))
PY
}

# ---- the record rule, in ONE place ---------------------------------------------------------
# Both readers of a trial's distribution -- post_trial_verdict (which writes the record) and
# verify_recorded_runs (which lets a reviewer skip re-running it) -- decide from these, so the two
# halves of the script cannot disagree about one bundle.
#
# A trial is TWO runs, and both must hold:
#   Trials/without_images/  N_TEXT_ONLY attempts on a copy with every image stripped
#                     (build_text_only_copy). ALL must fail: if the words alone solve it, the
#                     image is not really needed.
#   Trials/with_images/  N_ATTEMPTS attempts on the real bundle. The solves must fall inside
#                     TRIAL_MIN_SOLVED..TRIAL_MAX_SOLVED -- today 1..1, exactly 1 of 4.
#
# trial_rule (the normal run):
#   solved = 0                  -> all-failed       (not recorded, blocks check-reviewers: no RL signal)
#   solved < TRIAL_MIN_SOLVED   -> too-few-solved   (not recorded)
#   solved within the band      -> record-split     (recorded)
#   solved = total, above band  -> all-solved       (not recorded, harden it)
#   solved > TRIAL_MAX_SOLVED   -> too-many-solved  (not recorded, harden it)
trial_rule(){  # $1 = failed, $2 = total -> echoes the verdict
  local failed="$1" total="$2" solved=$(( $2 - $1 ))
  if   [ "$solved" -eq 0 ];                   then printf 'all-failed\n'
  elif [ "$solved" -lt "$TRIAL_MIN_SOLVED" ]; then printf 'too-few-solved\n'
  elif [ "$solved" -le "$TRIAL_MAX_SOLVED" ]; then printf 'record-split\n'
  elif [ "$solved" -eq "$total" ];            then printf 'all-solved\n'
  else printf 'too-many-solved\n'
  fi
  return 0
}

# The allowed band, in words, for every message that quotes it.
trial_band(){
  if [ "$TRIAL_MIN_SOLVED" -eq "$TRIAL_MAX_SOLVED" ]; then printf 'exactly %s' "$TRIAL_MIN_SOLVED"
  else printf '%s to %s' "$TRIAL_MIN_SOLVED" "$TRIAL_MAX_SOLVED"; fi
}

# text_only_rule (the image-stripped run): every attempt must fail.
text_only_rule(){  # $1 = failed, $2 = total -> text-only-clean | text-only-solved
  if [ "$1" -eq "$2" ]; then printf 'text-only-clean\n'; else printf 'text-only-solved\n'; fi
  return 0
}

# ---- the trial's task copies ---------------------------------------------------------------------
# harbor names each attempt dir after the task FOLDER (`<name[:32]>__<rand>`), so both phases run
# from a copy whose folder carries the delivery template's name: `task_with_images__<rand>` for
# the normal attempts and `task_without_images__<rand>` for the text-only ones. The name changes no digest --
# harbor hashes relative paths and contents only -- and no image cache entry, which is keyed on a
# hash of the build context.
NORMAL_TASK_NAME="task_with_images"
TEXT_ONLY_TASK_NAME="task_without_images"

# Where the copies live. NOT a temp dir: every attempt's result.json records its task path, and
# `harbor analyze` reads the task (instruction, tests, solution) from there -- a deleted copy
# leaves the analysis without it. Outside <ROOT> so it never ships with the deliverable; rebuilt
# by each trial, so it always holds the bundle the latest trial ran on.
trial_stage_dir(){
  printf '%s/mm_run/trial_tasks/%s' "${XDG_CACHE_HOME:-$HOME/.cache}" \
    "$(printf '%s' "$TASK_ID" | tr -c 'A-Za-z0-9._-' '_')"
}

# ---- the text-only copy -------------------------------------------------------------------------
# A copy of the task the agent sees WITHOUT any image. Images reach the agent two ways, and both are
# removed:
#   instruction.md   inline ![alt](path), reference-style ![alt][ref] (and its [ref]: definition)
#                    and HTML <img ...> are deleted
#   environment/     every image file under environment/ is deleted -- otherwise the agent could
#                    `ls` its way to /app/.harbor_assets and open the picture anyway -- and every
#                    COPY/ADD source naming an image (path, glob or URL) is dropped. An instruction
#                    with sources left keeps them (rewritten on one line); one with none left goes.
#                    Directory sources stay: the directory still exists, minus its images.
# Everything that is not an image stays, prose and non-image evidence (logs, text dumps) alike:
# the question is whether the WORDS suffice.
#
# DETERMINISTIC on purpose. Nothing here depends on time or location, so the reviewer path can
# rebuild the copy and get the same harbor digest the text-only run recorded (harbor hashes
# relative paths and contents only).
#
# Refuses (rc 3) when there was nothing to strip: on a task with no image the text-only run is the
# normal run, and proves nothing. Refuses (rc 4) when a RUN line downloads an image at build time:
# that cannot be removed without guessing what else the line does.
build_text_only_copy(){  # $1 = task dir, $2 = dest dir (must not exist) -> rc 0 ok, 3/4 refused
  cp -a "$1" "$2" || return 2
  python3 - "$2" <<'PY'
import json, os, re, shlex, sys
task = sys.argv[1]
EXT = r"png|jpe?g|gif|webp|bmp|svg|tiff?|avif|heic|mp4|webm|mov"
IMG_PATH = re.compile(r"\.(%s)$" % EXT, re.I)
removed = []

# ---- instruction.md
p = os.path.join(task, "instruction.md")
if os.path.exists(p):
    text = open(p, encoding="utf-8").read()
    defs = {}
    def_re = re.compile(r"^ {0,3}\[([^\]]+)\]:[ \t]*<?(\S+?)>?(?:[ \t]+.*)?$", re.M)
    for m in def_re.finditer(text):
        defs.setdefault(m.group(1).strip().lower(), m.group(2))
    used = set()
    def ref(m):
        label = (m.group(2) or m.group(1)).strip().lower()
        if label not in defs:
            return m.group(0)
        used.add(label); removed.append("instruction.md: " + m.group(0)); return ""
    def drop(m):
        removed.append("instruction.md: " + m.group(0)); return ""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", drop, text)              # ![alt](url)
    text = re.sub(r"<img\b[^>]*>", drop, text, flags=re.I)           # <img ...>
    text = re.sub(r"!\[([^\]]*)\]\[([^\]]*)\]", ref, text)           # ![alt][ref], ![alt][]
    text = re.sub(r"!\[([^\]]+)\]()(?![\[(])", ref, text)            # ![ref] shortcut
    def drop_def(m):
        if m.group(1).strip().lower() in used:
            removed.append("instruction.md: " + m.group(0).strip()); return ""
        return m.group(0)
    text = def_re.sub(drop_def, text)
    if removed:
        text = "\n".join(l.rstrip() for l in text.split("\n"))
        text = re.sub(r"\n{3,}", "\n\n", text)
        open(p, "w", encoding="utf-8").write(text)

# ---- Dockerfile: whole instructions, so a COPY continued over several lines is handled as one
env = os.path.join(task, "environment")
df = os.path.join(env, "Dockerfile")
if os.path.exists(df):
    phys = open(df, encoding="utf-8").read().split("\n")
    out, i, fetches = [], 0, []
    while i < len(phys):
        j = i
        while phys[j].rstrip().endswith("\\") and j + 1 < len(phys):
            j += 1
        block = phys[i:j + 1]; i = j + 1
        joined = " ".join(l.rstrip()[:-1] if l.rstrip().endswith("\\") else l for l in block)
        if re.match(r"\s*RUN\b", joined, re.I) and \
           re.search(r"https?://\S+\.(%s)\b" % EXT, joined, re.I):
            fetches.append(joined.strip())
        m = re.match(r"\s*(COPY|ADD)\s+(.*)$", joined, re.I | re.S)
        if not m:
            out += block; continue
        kw, rest = m.group(1), m.group(2).strip()
        try:
            toks = shlex.split(rest)
            flags = [t for t in toks if t.startswith("--")]
            args = [t for t in toks if not t.startswith("--")]
            exec_form = False
            if args and args[0].startswith("["):
                flag_part = rest[:rest.index("[")]
                flags = shlex.split(flag_part)
                args = json.loads(rest[rest.index("["):]); exec_form = True
        except Exception:
            out += block; continue
        if any(f.startswith("--from") for f in flags) or len(args) < 2:
            out += block; continue          # another stage's files, or nothing to parse
        srcs, dest = args[:-1], args[-1]
        imgs = [s for s in srcs if IMG_PATH.search(s.rstrip("/"))]
        if not imgs:
            out += block; continue
        keep = [s for s in srcs if s not in imgs]
        removed.append("Dockerfile: " + joined.strip())
        if keep:
            if exec_form:
                out.append("%s %s" % (kw, " ".join(flags + [json.dumps(keep + [dest])])))
            else:
                out.append(" ".join([kw] + flags + [shlex.quote(a) for a in keep + [dest]]))
    if fetches:
        for f in fetches:
            print("  REFUSED: the Dockerfile downloads an image at build time: " + f)
        raise SystemExit(4)
    open(df, "w", encoding="utf-8").write("\n".join(out))

# ---- image files under environment/
for dp, dns, fns in os.walk(env):
    dns.sort()
    for fn in sorted(fns):
        if IMG_PATH.search(fn):
            os.remove(os.path.join(dp, fn))
            removed.append("deleted: " + os.path.relpath(os.path.join(dp, fn), task))

for r in removed:
    print("  stripped " + r)
raise SystemExit(0 if removed else 3)
PY
}

# The digest a text-only run on the CURRENT bundle would record: rebuild the copy, hash it, drop it.
text_only_digest_now(){  # $1 = task dir -> "sha256:..." or nothing
  local tmp d=""
  tmp="$(mktemp -d -t mm_textonly.XXXXXX)" || return 0
  if build_text_only_copy "$1" "$tmp/$TEXT_ONLY_TASK_NAME" >/dev/null 2>&1; then
    d="$(task_digest_now "$tmp/$TEXT_ONLY_TASK_NAME")"
  fi
  rm -rf "$tmp"
  printf '%s' "$d"
}

# Is the text-only half of the trial good for THIS bundle? Says why not; rc 0 only when every
# text-only attempt failed AND the run describes the bundle as it is now. Shared by
# post_trial_verdict and verify_recorded_runs.
check_text_only_run(){  # $1 = task dir
  local jobs="$TEXT_ONLY_DIR" tally failed total d now
  tally="$(trial_tally "$jobs")"
  if [ -z "$tally" ]; then
    say "  Text-only: no readable run in $jobs  <- the text-only attempts are required"
    return 1
  fi
  failed="${tally%% *}"; total="${tally##* }"
  if [ "$(text_only_rule "$failed" "$total")" != text-only-clean ]; then
    say "  Text-only: $((total - failed)) of $total attempt(s) SOLVED it without the image  <- all must fail"
    return 1
  fi
  if [ "$total" -lt "$N_TEXT_ONLY" ]; then
    say "  Text-only: only $total of $N_TEXT_ONLY attempts produced a reward  <- incomplete"
    return 1
  fi
  d="$(control_digest "$jobs")"; now="$(text_only_digest_now "$1")"
  if [ -z "$d" ] || [ -z "$now" ] || [ "$d" = mixed ] || [ "$d" != "$now" ]; then
    say "  Text-only: digest ${d:-unrecorded} vs stripped bundle now ${now:-uncomputable}  <- STALE or unverifiable"
    return 1
  fi
  say "  Text-only: all $total attempt(s) failed without the image, digest current ($d)"
  return 0
}

if [ "$MODE" = trial ] && [ "${MM_ALLOW_UNVERIFIED:-0}" != 1 ]; then
  ORACLE_R="$(control_reward "$ROOT/Oracle")"
  NOP_R="$(control_reward "$ROOT/Nop")"
  NOP_C="$(control_counts "$ROOT/Nop")"
  # 1 exactly. control_reward normalises through float, so 1.0/1.00 arrive as "1".
  [ "$ORACLE_R" = 1 ] && ORACLE_OK=1 || ORACLE_OK=0
  # NOP IS JUDGED ON THE COUNTS, NOT THE REWARD. A 0 reward only means SOME f2p test failed --
  # see control_counts() for why that is consistent with an inert test the empty submission
  # passes. NOP_WHY carries the reason into the message below, so the CB is told which half
  # failed rather than being handed a number and the old "want 0".
  NOP_OK=0; NOP_WHY=""; NOP_FP=0; NOP_FT=0; NOP_PP=0; NOP_PT=0
  case "$NOP_C" in
    "")
      if [ -z "$NOP_R" ]; then
        NOP_WHY="no reward found - nop has not been run"
      else
        # The keys are a BLOCKING bundle-tier QC finding, so this state means the audit was
        # skipped or the run died before the verifier's atexit flush. Re-running nop is keyless.
        NOP_WHY="reward=$NOP_R but reward.json carries no f2p/p2p counts - re-run nop (QC reports this as verifier.reward_json.keys)"
      fi;;
    mixed)
      NOP_WHY="attempts under Nop/ record disagreeing f2p/p2p counts";;
    *)
      read -r NOP_FP NOP_FT NOP_PP NOP_PT <<<"$NOP_C"
      if   [ "$NOP_FT" -eq 0 ]; then
        NOP_WHY="f2p_total=0 - no f2p test ran, so nothing was measured"
      elif [ "$NOP_FP" -ne 0 ]; then
        NOP_WHY="$NOP_FP of $NOP_FT f2p test(s) PASS on an empty submission - they cannot detect the bug"
      elif [ "$NOP_PP" -ne "$NOP_PT" ]; then
        NOP_WHY="$(( NOP_PT - NOP_PP )) of $NOP_PT p2p test(s) FAIL on nop - they are really f2p"
      else
        NOP_OK=1
      fi;;
  esac
  if [ "$ORACLE_OK" = 0 ] || [ "$NOP_OK" = 0 ]; then
    say "You cannot start a harbor trial without first running oracle and getting a 1,"
    say "and running nop and having every f2p test FAIL while every p2p test PASSES."
    say ""
    # Each line says which control it is, what it scored, and what was wanted — the three
    # things that decide whether the fix is "run it" or "the task is broken".
    say "  oracle  $([ "$ORACLE_OK" = 1 ] && echo "OK: reward=1" \
                     || echo "NOT SATISFIED: ${ORACLE_R:-no reward found} (want 1)")"
    say "          $ROOT/Oracle"
    say "  nop     $([ "$NOP_OK" = 1 ] \
                     && echo "OK: 0 of $NOP_FT f2p pass, $NOP_PP of $NOP_PT p2p pass" \
                     || echo "NOT SATISFIED: $NOP_WHY")"
    say "          $ROOT/Nop"
    say ""
    if [ "$HAS_RUBRICS" = 1 ]; then
      say "Run the outstanding control(s) first (this task ships a rubric, so its verifier's"
      say "judge needs credentials — the runner forwards them):"
    else
      say "Run the outstanding control(s) first (keyless — the verifier is unit-tests only):"
    fi
    [ "$ORACLE_OK" = 0 ] && say "  bash $0 $TASK_DIR oracle"
    [ "$NOP_OK" = 0 ]    && say "  bash $0 $TASK_DIR nop"
    say ""
    say "If a control has run and still scores wrong, that is the task to fix, not the"
    say "trial to force: an oracle below 1 means the golden patch does not pass its own"
    say "tests; an f2p test passing on nop means that test cannot detect the bug, so the"
    say "task grades nothing real; and a p2p test failing on nop is mislabeled - it is f2p."
    say ""
    say "Nothing was run and no credentials were used."
    exit 9
  fi

  # ---- and are those two controls describing the bundle as it is NOW? ----
  #
  # A green oracle from before the last edit to tests/, solution/ or environment/ measured code
  # that no longer exists. The reward check above cannot see that: 1.0 is 1.0 whenever it was
  # earned. So the digest harbor recorded for each control is compared against the digest of
  # $TASK_DIR right now, and a mismatch is refused for the same reason a wrong reward is - the
  # trial about to be paid for would be reported against a bundle nobody is submitting.
  NOW_DIGEST="$(task_digest_now "$TASK_DIR")"
  ORACLE_D="$(control_digest "$ROOT/Oracle")"
  NOP_D="$(control_digest "$ROOT/Nop")"
  if [ -z "$NOW_DIGEST" ]; then
    # UNVERIFIABLE IS NOT VERIFIED, and it is not a failure either: the controls are green, and
    # the one thing missing is a digest this runner could not compute (no importable harbor, or a
    # .gitignore the stdlib fallback declines to imitate). Saying so and continuing is right -
    # blocking here would ground every trial on a harbor whose internals moved, over a check that
    # is an improvement on the reward gate rather than a replacement for it.
    say "controls verified: oracle=1 (Oracle/), nop all-f2p-fail 0/$NOP_FT + all-p2p-pass $NOP_PP/$NOP_PT (Nop/)"
    say "staleness NOT checked: could not compute the current task digest"
  elif [ "$ORACLE_D" != "$NOW_DIGEST" ] || [ "$NOP_D" != "$NOW_DIGEST" ]; then
    say "The controls are green, but they were not produced from THIS bundle."
    say ""
    say "  Tasks/ now   ${NOW_DIGEST}"
    for _c in Oracle Nop; do
      [ "$_c" = Oracle ] && _d="$ORACLE_D" || _d="$NOP_D"
      if [ "$_d" = "$NOW_DIGEST" ]; then
        say "$(printf '  %-11s' "$_c")${_d}  (current)"
      elif [ -z "$_d" ]; then
        say "$(printf '  %-11s' "$_c")no lock.json digest found - cannot tell which bundle it ran"
      elif [ "$_d" = mixed ]; then
        say "$(printf '  %-11s' "$_c")MIXED digests in one job - not a usable control"
      else
        say "$(printf '  %-11s' "$_c")${_d}  <- STALE"
      fi
      say "             $ROOT/$_c"
    done
    say ""
    say "harbor hashes task.toml, instruction.md and everything under environment/, tests/,"
    say "solution/ and steps/. So one of those changed after that control ran, and its reward"
    say "describes code the trial will not be running. Re-run the stale control(s):"
    [ "$ORACLE_D" != "$NOW_DIGEST" ] && say "  bash $0 $TASK_DIR oracle"
    [ "$NOP_D" != "$NOW_DIGEST" ]    && say "  bash $0 $TASK_DIR nop"
    say ""
    say "(evidence_bundle.json is deliberately outside the digest - editing it alone cannot"
    say "make a control stale, because it cannot change a reward.)"
    say ""
    say "Nothing was run and no credentials were used."
    exit 9
  else
    say "controls verified: oracle=1 (Oracle/), nop all-f2p-fail 0/$NOP_FT + all-p2p-pass $NOP_PP/$NOP_PT (Nop/),"
    say "                   both from the current bundle"
    say "                   ${NOW_DIGEST}"
  fi
fi

# COST LEDGER -- silent by design: no output, no prompt, no effect on the exit code. Records what
# the job dir(s) this mode writes cost (harbor's figure, cross-checked with ccusage) into
# ~/.mm_swe_cost/ledger.json. Rows are keyed on harbor's job id, so a mode refused before harbor
# ran re-reads the previous job and changes nothing. After EVERY trial that ran (pass or fail) it
# also re-reads the CB's own Claude Code sessions with ccusage, replacing the previous reading --
# ccusage re-reads every session file, so the newest reading already contains the older ones and
# replacing is what keeps work done after a pass from being double counted or lost. A trial
# refused before harbor ran leaves no job dir, so it takes no reading. See mm_cost.py.
# Called twice: before the mode runs ("pre": rescues a previous job that was killed before it could
# record itself, since this mode is about to delete its dir -- adds missing rows only), and after.
cost_record(){  # $1 = mode, $2 = "pre" for the before-run pass
  local -a jobs=() args
  local j found=0
  case "$1" in
    # oracle and nop are NOT recorded: neither runs an agent, so harbor has no model cost for
    # them and a row would only ever read $0. A task with tests/rubrics.json can still pay for
    # a judge during them, but the host-side grader (mm_grade_rubrics.py) logs that itself as
    # an api_calls row, independently of this function.
    trial)  jobs=("$TEXT_ONLY_DIR" "$TRIALS_DIR");;
    pseudo-trial) jobs=("$ROOT/PseudoTrial");;
    check|check-reviewers) jobs=("$ROOT/Check");;
    analyze) jobs=("$ROOT/Analyze");;
    *) return 0;;
  esac
  args=(record-run --mode "$1" --task-id "$TASK_ID" --task-dir "$TASK_DIR")
  for j in "${jobs[@]}"; do
    [ -f "$j/result.json" ] && { args+=(--job "$j"); found=$((found + 1)); }
  done
  if [ "${2:-}" = pre ]; then
    [ "$found" -gt 0 ] || return 0      # no previous job on disk
    args+=(--only-new)
  elif [ "$1" = trial ] && [ "$found" -gt 0 ]; then
    args+=(--snapshot-sessions --trials-dir "$TRIALS_DIR"
           --trial-result "${COST_TRIAL_RESULT:-ended before a verdict}")
    [ "${COST_TRIAL_PASSED:-0}" = 1 ] && args+=(--trial-passed)
  fi
  timeout 600 python3 "$HERE/mm_cost.py" "${args[@]}" </dev/null >/dev/null 2>&1 || true
}

cost_record "$MODE" pre
case "$MODE" in
  oracle)  run_plain oracle;;
  nop)     run_plain nop;;
  trial)   run_trial;;
  pseudo-trial) run_pseudo_trial;;
  check)   run_check;;
  # Sets the flag and reuses run_check -- see the REVIEWERS block inside it.
  check-reviewers) REVIEWERS=1; run_check;;
  analyze) run_analyze;;
  rescore) run_rescore;;
  *) echo "unknown mode: $MODE (want oracle|nop|trial|pseudo-trial|check|check-reviewers|analyze|rescore)" >&2; exit 2;;
esac
MM_RC=$?
cost_record "$MODE"
exit "$MM_RC"
