#!/usr/bin/env bash
###############################################################################
# mm_run.sh — run an MM SWE Harbor task as oracle, nop, a single agent trial, a
# rubric quality check, or a post-hoc analysis of a finished trial.
#
# Layout (mirrors the QH folder):
#   <ROOT>/Tasks/               the task (task.toml, environment/, solution/, tests/)
#   <ROOT>/Oracle/              oracle run output (no per-task subfolder)
#   <ROOT>/Nop/                 nop run output    (no per-task subfolder)
#   <ROOT>/Trials/              agent trial output (no per-task subfolder)
#   <ROOT>/Check/               harbor check output (rubric quality checks)
#   <ROOT>/Analyze/             harbor analyze output (post-hoc trial analysis)
#
# Credentials: ONLY the trial needs them. The verifier here is unit-tests ->
# JUnit -> reward.txt with no model call, so oracle and nop run keyless.
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
#   mm_run.sh <task-dir> <oracle|nop|trial|check> [options]
#   mm_run.sh <task-dir|job-dir|trial-dir> analyze [options]
# Options:
#   --model M       model for the trial      (default anthropic/claude-opus-4-8)
#   --check-model M    model for check       (default claude-sonnet-4-6)
#   --analyze-model M  model for analyze     (default claude-haiku-4-5)
#   --agent A       agent for the trial      (default claude-code)
#   --root DIR      where Trials/Oracle/Nop go   (default: dir containing tasks/)
#   --env E         harbor environment       (default docker)
#   --no-preflight  skip the connectivity probe before spending a trial
#   --no-hostnet    do not use the host-network compose override; bridge the proxy instead
#   --hostnet-file F  use this compose override instead of the generated one
#   --no-disallow-tools  do not pass --ak disallowed_tools (web/plan tools stay enabled)
#   --userns-host   add userns_mode: host to the override (retry if tar chown still fails)
#   --keep          do not delete a previous run dir for this task+mode
#   --rubric F      rubric file for check/analyze     (default: harbor's built-in)
#   --check-prompt F  evaluator prompt file for check/analyze
#   --passing       analyze only passing trials (reward 1.0)
#   --failing       analyze only failing trials
#   -l N            analyze at most N trials
###############################################################################
set -uo pipefail

TASK_DIR=""; MODE=""
MODEL="anthropic/claude-opus-4-8"; AGENT="claude-code"
# check/analyze keep harbor's own defaults; both were verified to answer through
# the anonymizer. Bump --analyze-model to claude-sonnet-4-6 if haiku cannot emit
# valid JSON (harbor's own failure hint says the same).
CHECK_MODEL="claude-sonnet-4-6"; ANALYZE_MODEL="claude-haiku-4-5"
RUBRIC=""; CHECK_PROMPT=""; ANALYZE_FILTER=""; N_TRIALS=""
ROOT=""; ROOT_GIVEN=0; HENV="docker"; PREFLIGHT=1; KEEP=0
HOSTNET=1; HOSTNET_FILE=""            # host-networking compose override (replaces the bridge)
DISALLOW_TOOLS="WebSearch,WebFetch,EnterPlanMode"
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
    --keep) KEEP=1; shift;;
    --no-hostnet) HOSTNET=0; shift;;
    --hostnet-file) HOSTNET_FILE="$2"; HOSTNET=1; shift 2;;
    --no-disallow-tools) DISALLOW_TOOLS=""; shift;;
    --userns-host) USERNS_HOST=1; shift;;
    -h|--help) sed -n '3,59p' "$0"; exit 0;;   # keep in sync with the header block
    *) if [ -z "$TASK_DIR" ]; then TASK_DIR="$1"; elif [ -z "$MODE" ]; then MODE="$1"; fi; shift;;
  esac
done
[ -n "$TASK_DIR" ] && [ -n "$MODE" ] || { echo "usage: mm_run.sh <task-dir> <oracle|nop|trial|check|analyze> [opts]" >&2; exit 2; }
[ -d "$TASK_DIR" ] || { echo "error: no such directory: $TASK_DIR" >&2; exit 2; }

# ---- helpers (defined before first use: bash resolves functions at call time) ----
say(){ printf '[mm_run] %s\n' "$*" >&2; }
mask(){ [ -n "${1:-}" ] && printf '%s…%s' "${1:0:6}" "${1: -4}" || printf '(none)'; }
TASK_DIR="$(cd "$TASK_DIR" && pwd)"

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
  say "$mode -> $ROOT/$jobname   (no credentials needed: verifier is unit-tests only)"
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

  local KEY BASE
  KEY="${ANTHROPIC_API_KEY:-$(read_settings_env ANTHROPIC_API_KEY)}"
  BASE="${ANTHROPIC_BASE_URL:-$(read_settings_env ANTHROPIC_BASE_URL)}"
  # anonymizer defaults (same as ProjectBench) — NOT the public Scale endpoint
  : "${BASE:=http://localhost:8091}"
  : "${KEY:=anonymizer-placeholder}"
  case "$BASE" in
    https://litellm-proxy.ml.scale.com*)
      say "NOTE: using the PUBLIC Scale endpoint ($BASE) because it was explicitly set."
      say "      Unset ANTHROPIC_BASE_URL (and the settings.json entry) to use the anonymizer.";;
  esac
  say "task $TASK_ID"
  say "trial agent=$AGENT model=$MODEL"
  say "creds base=$BASE key=$(mask "$KEY")"

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

  say "trial -> $ROOT/Trials   (single attempt)"
  local -a hargs=(run -p "$TASK_DIR" -a "$AGENT" -m "$MODEL"
                  -e "$HENV" -o "$ROOT" --job-name "Trials" --yes
                  --ae ANTHROPIC_BASE_URL="$CBASE"
                  --ae ANTHROPIC_API_KEY="$KEY"
                  --agent-timeout-multiplier 6)
  [ -n "$DISALLOW_TOOLS" ] && hargs+=(--ak "disallowed_tools=$DISALLOW_TOOLS")
  [ -n "$HOSTNET_FILE" ]   && hargs+=(--extra-docker-compose "$HOSTNET_FILE")
  say_harbor "${hargs[@]}"   # masked: this array carries ANTHROPIC_API_KEY
  harbor "${hargs[@]}"
  local rc=$?; report "$ROOT/Trials" trial; return $rc
}

# ------------------------------------------------------------- check / analyze
# Both are rubric-judge jobs, not unit-test jobs: they produce no reward.txt, so
# they report through report_rubric() instead of report().
run_check(){
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
  local d="$1" lbl="$2" rw
  rw="$(find "$d" -name reward.txt 2>/dev/null | head -1)"
  if [ -n "$rw" ]; then
    say "$lbl reward = $(cat "$rw")"
  else
    rw="$(find "$d" -name result.json 2>/dev/null | head -1)"
    [ -n "$rw" ] && say "$lbl result: $(python3 -c "
import json,sys
d=json.load(open(sys.argv[1])); print(json.dumps((d.get('verifier_result') or {}).get('rewards', {})))" "$rw" 2>/dev/null)"
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
  *) echo "unknown mode: $MODE (want oracle|nop|trial|check|analyze)" >&2; exit 2;;
esac
