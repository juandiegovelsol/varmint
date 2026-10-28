#!/usr/bin/env bash
###############################################################################
# mm_run.sh — run an MM SWE Harbor task as oracle, nop, a single agent trial, a
# rubric quality check, or a post-hoc analysis of a finished trial.
#
# Layout (mirrors the QH folder):
#   <ROOT>/Tasks/<task_id>/     the task (task.toml, environment/, ...) - V2; V1: <ROOT>/Tasks/
#   <ROOT>/Oracle/              oracle run output (no per-task subfolder)
#   <ROOT>/Nop/                 nop run output    (no per-task subfolder)
#   <ROOT>/Trials/              agent trial output (no per-task subfolder)
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
#   mm_run.sh <task-dir> <oracle|nop|trial|check|rescore> [options]
#   mm_run.sh <task-dir|job-dir|trial-dir> analyze [options]
# Options:
#   --model M       model for the trial      (default anthropic/claude-opus-4-8)
#   --check-model M    model for check       (default claude-sonnet-5)
#   --analyze-model M  model for analyze     (default claude-sonnet-5)
#   --agent A       agent for the trial      (default claude-code)
#   --root DIR      where Trials/Oracle/Nop go   (default: dir containing tasks/)
#   --env E         harbor environment       (default docker)
#   --no-preflight  skip the connectivity probe before spending a trial
#   --no-hostnet    do not use the host-network compose override; bridge the proxy instead
#   --hostnet-file F  use this compose override instead of the generated one
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
#   --run DIR       which run dir to rescore (default: <ROOT>/Trials)
#
#   (rubrics: the judge is a SUB-AGENT — no API key, no network from the verifier. If
#    tests/rubrics.json exists the verifier writes a judge request and scores on tests
#    alone; a judge sub-agent writes verdict.json, then `rescore` folds that verdict into
#    reward.txt/reward.json from the existing JUnit XML — no container, no rebuild.)
#   --no-file-check run harbor check even if required task files are missing
#   --no-integrity-check  run harbor check even if task metadata is internally inconsistent
#    (base_commit vs Dockerfile, files_edited vs fix.patch, f2p/p2p vs config.json, etc. —
#     see mm_check_integrity.py's own docstring for the full list)
#   --rubric F      rubric file for check/analyze     (default: harbor's built-in)
#   --check-prompt F  evaluator prompt file for check/analyze
#   --passing       analyze only passing trials (reward 1.0)
#   --failing       analyze only failing trials
#   -l N            analyze at most N trials
###############################################################################
set -uo pipefail

TASK_DIR=""; MODE=""
MODEL="anthropic/claude-opus-4-8"; AGENT="claude-code"
# check and analyze both default to claude-sonnet-5 — that is what the anonymizer
# serves for these two. Harbor's own defaults (claude-sonnet-4-6, claude-haiku-4-5) are
# NOT served, and an unserved name does not come back as a clean 404: the agent retries,
# dies, and the run reports "agent did not produce a valid result / missing result file"
# after burning the full wall clock. (The trial is a separate path — see MODEL above.)
CHECK_MODEL="claude-sonnet-5"; ANALYZE_MODEL="claude-sonnet-5"
RUBRIC=""; CHECK_PROMPT=""; ANALYZE_FILTER=""; N_TRIALS=""
ROOT=""; ROOT_GIVEN=0; HENV="docker"; PREFLIGHT=1; KEEP=0
FILE_CHECK=1                          # check mode verifies the task file names first
INTEGRITY_CHECK=1                     # check mode cross-checks task metadata for internal consistency
HOSTNET=1; HOSTNET_FILE=""            # host-networking compose override (replaces the bridge)
DISALLOW_TOOLS="WebSearch,WebFetch,EnterPlanMode"
IDLE_TIMEOUT_FIX=1                    # trial only: API_FORCE_IDLE_TIMEOUT=0 + a matching subagent stall window
STALL_TIMEOUT_MS=""                   # default: derived from the task's own [agent].timeout_sec; override with --stall-timeout-ms
RUN_DIR=""                            # rescore: which run dir to fold a verdict into
USERNS_HOST=0                         # add userns_mode: host to the override (retry aid)
COMPOSE_SVC="${COMPOSE_SVC:-main}"    # harbor's environment service name
SETTINGS_JSON="${SETTINGS_JSON:-$HOME/.claude/settings.json}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_PID=""; BRIDGE_LOG="$(mktemp -t mm_bridge.XXXXXX.log)"
GEN_COMPOSE=""
cleanup(){ [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null
           rm -f "$BRIDGE_LOG"; [ -n "$GEN_COMPOSE" ] && rm -f "$GEN_COMPOSE"; return 0; }
trap cleanup EXIT INT TERM

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
    --keep) KEEP=1; shift;;
    --no-hostnet) HOSTNET=0; shift;;
    --hostnet-file) HOSTNET_FILE="$2"; HOSTNET=1; shift 2;;
    --no-disallow-tools) DISALLOW_TOOLS=""; shift;;
    --no-idle-timeout-fix) IDLE_TIMEOUT_FIX=0; shift;;
    --stall-timeout-ms) STALL_TIMEOUT_MS="$2"; shift 2;;
    --run) RUN_DIR="$2"; shift 2;;
    --userns-host) USERNS_HOST=1; shift;;
    -h|--help) sed -n '3,69p' "$0"; exit 0;;   # keep in sync with the header block
    *) if [ -z "$TASK_DIR" ]; then TASK_DIR="$1"; elif [ -z "$MODE" ]; then MODE="$1"; fi; shift;;
  esac
done
[ -n "$TASK_DIR" ] && [ -n "$MODE" ] || { echo "usage: mm_run.sh <task-dir> <oracle|nop|trial|check|analyze|rescore> [opts]" >&2; exit 2; }
[ -d "$TASK_DIR" ] || { echo "error: no such directory: $TASK_DIR" >&2; exit 2; }

# ---- helpers (defined before first use: bash resolves functions at call time) ----
say(){ printf '[mm_run] %s\n' "$*" >&2; }
mask(){ [ -n "${1:-}" ] && printf '%s…%s' "${1:0:6}" "${1: -4}" || printf '(none)'; }
TASK_DIR="$(cd "$TASK_DIR" && pwd)"

# V2 layout (TASK101+): the bundle sits one level down, at Tasks/<task_id>/task.toml (V1 kept
# task.toml directly in Tasks/). Pointing at the Tasks/ folder, or at the root holding it,
# descends to the single bundle inside, so `mm_run.sh /home/sandbox/Tasks <mode>` works for
# both layouts. Two or more bundles there is ambiguous: name the one you mean.
if [ ! -f "$TASK_DIR/task.toml" ] && [ ! -f "$TASK_DIR/project/task.toml" ]; then
  _found=()
  case "$(basename "$TASK_DIR")" in
    [Tt]asks) _globs=("$TASK_DIR"/*/task.toml);;
    *)        _globs=("$TASK_DIR"/[Tt]asks/task.toml "$TASK_DIR"/[Tt]asks/*/task.toml);;
  esac
  for _t in "${_globs[@]}"; do [ -f "$_t" ] && _found+=("$(dirname "$_t")"); done
  if [ "${#_found[@]}" -gt 1 ]; then
    echo "error: ${#_found[@]} task bundles under $TASK_DIR — pass the one you mean:" >&2
    printf '  %s\n' "${_found[@]}" >&2; exit 2
  elif [ "${#_found[@]}" -eq 1 ]; then
    say "task dir: ${_found[0]}"; TASK_DIR="${_found[0]}"
  fi
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
else echo "error: no task.toml in $TASK_DIR (nor in $TASK_DIR/project, nor one Tasks/<task_id>/ below it)" >&2; exit 2; fi

# Task label — used ONLY for log output; every run dir is flat, so this affects no
# path. Prefer task_id from task.toml's [metadata] (the real identity), else the
# folder name. ID_DIR is what ROOT inference keys off, and skips a project/ wrapper.
ID_DIR="$TASK_DIR"
[ "$(basename "$TASK_DIR")" = "project" ] && ID_DIR="$(dirname "$TASK_DIR")"
TASK_ID="$(sed -n 's/^[[:space:]]*task_id[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$TASK_DIR/task.toml" 2>/dev/null | head -1)"
[ -n "$TASK_ID" ] || TASK_ID="$(basename "$ID_DIR")"

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

# analyze: decide WHAT gets analyzed, and keep ROOT above the job dir. Pointing at
# a single trial dir would otherwise infer ROOT=<the job dir> and harbor would
# write Analyze/ INSIDE Trials/. A task dir means "the trial I just ran".
ANALYZE_PATH=""
if [ "$MODE" = analyze ]; then
  case "$ANALYZE_SRC" in
    trial) [ "$ROOT_GIVEN" = 1 ] || ROOT="$(cd "$(dirname "$ID_DIR")/.." && pwd)"
           ANALYZE_PATH="$ID_DIR";;
    job)   ANALYZE_PATH="$ID_DIR";;
    task)  ANALYZE_PATH="$ROOT/Trials";;
  esac
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
  case "$BASE" in
    https://litellm-proxy.ml.scale.com*)
      say "NOTE: using the PUBLIC Scale endpoint ($BASE) because it was explicitly set."
      say "      Unset ANTHROPIC_BASE_URL (and the settings.json entry) to use the anonymizer.";;
  esac
}

# Echo a harbor command with any API-key value masked. The key has to be passed
# to harbor via --ae, but it must never be echoed into a log.
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

# ------------------------------------------------- docker-compose override (all modes)
# One override file serves two purposes, so every mode gets it:
#   * TAR_OPTIONS=--no-same-owner — GNU tar honors this on every invocation, fixing
#     "Cannot change ownership to uid ..." extraction failures under the sandbox's
#     nested-docker user namespace (e.g. flutter's gradle-wrapper fetch). This breaks the
#     ENVIRONMENT BUILD, so it must apply to oracle and nop too, not just the trial.
#   * network_mode: host — lets the agent container reach the anonymizer on the VM's
#     loopback (only needed by the trial, harmless elsewhere).
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

# ---------------------------------------------------------------- oracle / nop
run_plain(){  # $1 = oracle|nop  -> keyless, no proxy, no bridge
  # Output goes STRAIGHT into <ROOT>/Oracle or <ROOT>/Nop — no per-task subfolder.
  # harbor puts the job under <-o>/<--job-name>, so we pass -o <ROOT> and name the
  # job "Oracle"/"Nop" to land exactly there.
  local mode="$1" jobname
  case "$mode" in oracle) jobname="Oracle";; nop) jobname="Nop";; esac
  mkdir -p "$ROOT"
  [ "$KEEP" = 1 ] || rm -rf "${ROOT:?}/$jobname"
  say "task $TASK_ID"
  # The rubric judge is a SUB-AGENT: it writes a request and reads a verdict, and never
  # calls out. So oracle and nop stay keyless whether or not the task carries a rubric.
  say "$mode -> $ROOT/$jobname   (no credentials needed: verifier makes no model call)"
  [ "$HAS_RUBRICS" = 1 ] && say "  rubric present: the verifier will write a judge request; rescore after grading it"
  resolve_compose || return $?
  local -a hargs=(run -p "$TASK_DIR" -a "$mode" -e "$HENV" -o "$ROOT" --job-name "$jobname" --yes)
  [ -n "$HOSTNET_FILE" ] && hargs+=(--extra-docker-compose "$HOSTNET_FILE")
  say "harbor ${hargs[*]}"
  harbor "${hargs[@]}"
  local rc=$?; report "$ROOT/$jobname" "$mode"; return $rc
}

# ---------------------------------------------------------------------- trial
run_trial(){
  # Output goes STRAIGHT into <ROOT>/Trials — no per-task subfolder. harbor writes a
  # job at <-o>/<--job-name>, so pass -o <ROOT> and name the job "Trials".
  mkdir -p "$ROOT"
  [ "$KEEP" = 1 ] || rm -rf "${ROOT:?}/Trials"

  resolve_creds
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
  local CBASE="$BASE" IS_LOOPBACK=0
  printf '%s' "$BASE" | grep -qE '://(localhost|127\.0\.0\.1)' && IS_LOOPBACK=1

  if [ "$HOSTNET" = 1 ]; then
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

  if [ "$PREFLIGHT" = 1 ]; then
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

  # No creds are exported for the verifier: its rubric judge is a sub-agent and makes no
  # model call. Only the AGENT gets credentials, via --ae below.
  say "trial -> $ROOT/Trials   (single attempt)"
  local -a hargs=(run -p "$TASK_DIR" -a "$AGENT" -m "$MODEL"
                  -e "$HENV" -o "$ROOT" --job-name "Trials" --yes
                  --ae ANTHROPIC_BASE_URL="$CBASE"
                  --ae ANTHROPIC_API_KEY="$KEY"
                  --agent-timeout-multiplier 1)
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
  [ -n "$HOSTNET_FILE" ]   && hargs+=(--extra-docker-compose "$HOSTNET_FILE")
  say_harbor "${hargs[@]}"   # masked: this array carries ANTHROPIC_API_KEY
  harbor "${hargs[@]}"
  local rc=$?; report "$ROOT/Trials" trial; return $rc
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
  "tests/rubrics.json"
)

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
# f2p/p2p vs tests/config.json, asset paths, etc.) — pure string/set comparisons, no
# docker, no network, sub-second. See that script's docstring for the full list and for
# why patch-applies-cleanly / JSON-TOML-syntax / upstream-GitHub checks are deliberately
# NOT included (they either surface for free once oracle runs, or need a real checkout).
check_integrity(){  # $1 = task dir
  local dir="$1"
  python3 "$HERE/mm_check_integrity.py" "$dir" >&2
}

# ------------------------------------------------------------- check / analyze
# Both are rubric-judge jobs, not unit-test jobs: they produce no reward.txt, so
# they report through report_rubric() instead of report().
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

# -------------------------------------------------------------------- rescore
# Phase 2 of the sub-agent judge. The verifier already produced report.xml and a judge
# request; once a sub-agent has written verdict.json, this recomputes the reward WITHOUT
# re-running the container (an MUI/flutter rebuild costs minutes; this costs nothing).
run_rescore(){
  local d="${RUN_DIR:-$ROOT/Trials}"
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

  local outdir; outdir="$(dirname "$xml")"
  ( cd "$outdir" && python3 "$TASK_DIR/tests/verifier.py" "$xml" --rubric "$verdict" ) >/dev/null 2>&1 \
    || say "  note: verifier.py returned non-zero; check its output paths"
  report "$d" rescore
  return 0
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
    q="$(python3 - "$f" <<'PY'
import json, sys
try: d = json.load(open(sys.argv[1]))
except Exception: raise SystemExit(0)
r = d.get("rewards") or (d.get("verifier_result") or {}).get("rewards") or d
if not isinstance(r, dict): raise SystemExit(0)
bits = []
for k in ("reward", "tests_passed"):
    if k in r: bits.append("%s=%s" % (k, r[k]))
if r.get("f2p_total") is not None:
    bits.append("f2p=%s/%s" % (r.get("f2p_passed"), r.get("f2p_total")))
if "rubric" in r:
    bits.append("rubric=%s" % ("unavailable" if r["rubric"] is None else r["rubric"]))
if bits: print("  ".join(bits))
# Per-test detail: each test is graded individually; an aggregate cannot show which.
for grp in ("f2p", "p2p"):
    res = r.get(grp)
    if isinstance(res, dict) and res:
        for name, ok in res.items():
            sys.stderr.write("[mm_run]     %s %s  %s\n" % (grp, "PASS" if ok else "FAIL", name))
failed = r.get("rubric_failed") or []
if failed:
    sys.stderr.write("[mm_run]     rubric failed criteria: %s\n" % ", ".join(map(str, failed)))
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

  # Rubric configured but no verdict folded in yet: the NORMAL first-pass state for the
  # sub-agent judge, not an error. Point at the request so it can be graded and rescored.
  if [ "$HAS_RUBRICS" = 1 ] && [ "$lbl" != "rescore" ]; then
    if ! printf '%s' "${q:-}" | grep -qE "rubric=(pass|fail)"; then
      local req; req="$(find "$d" -type f -name PROMPT.md 2>/dev/null | head -1)"
      if [ -n "$req" ]; then
        say "$lbl: scored on tests alone — the rubric judge request is at $(dirname "$req")"
        say "       have the judge sub-agent write verdict.json there, then:"
        say "       mm_run.sh \"$TASK_DIR\" rescore --run \"$d\""
      else
        say "$lbl: rubric configured but no judge request was written — check the verifier log"
      fi
    fi
  fi

  case "$lbl" in
    oracle) say "expected: 1.0  (lower = the golden patch does not satisfy the tests)";;
    nop)    say "expected: 0.0  (higher = the verifier accepts an empty submission)";;
  esac
}

case "$MODE" in
  oracle)  run_plain oracle;;
  nop)     run_plain nop;;
  trial)   run_trial;;
  check)   run_check;;
  analyze) run_analyze;;
  rescore) run_rescore;;
  *) echo "unknown mode: $MODE (want oracle|nop|trial|check|analyze|rescore)" >&2; exit 2;;
esac
