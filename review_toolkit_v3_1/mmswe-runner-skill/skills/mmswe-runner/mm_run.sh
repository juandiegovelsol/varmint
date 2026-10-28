#!/usr/bin/env bash
###############################################################################
# mm_run.sh — run an MM SWE Harbor task as oracle, nop, or a single agent trial.
#
# Layout (mirrors the QH folder):
#   <ROOT>/Tasks/<task_id>/     the task (task.toml, environment/, ...) - V2; V1: <ROOT>/Tasks/
#   <ROOT>/Oracle/              oracle run output (no per-task subfolder)
#   <ROOT>/Nop/                 nop run output    (no per-task subfolder)
#   <ROOT>/Trials/              agent trial output (no per-task subfolder)
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
# Usage:
#   mm_run.sh <task-dir> <oracle|nop|trial|check|analyze> [options]
# Options:
#   --model M       model for the trial      (default anthropic/claude-opus-4-8)
#   --agent A       agent for the trial      (default claude-code)
#   --root DIR      where Trials/Oracle/Nop go   (default: dir containing tasks/)
#   --env E         harbor environment       (default docker)
#   --no-preflight  skip the connectivity probe before spending a trial
#   --no-hostnet    do not use the host-network compose override; bridge the proxy instead
#   --hostnet-file F  use this compose override instead of the generated one
#   --no-disallow-tools  do not pass --ak disallowed_tools (web/plan tools stay enabled)
#   --keep          do not delete a previous run dir for this task+mode
###############################################################################
set -uo pipefail

TASK_DIR=""; MODE=""
MODEL="anthropic/claude-opus-4-8"; AGENT="claude-code"
ROOT=""; HENV="docker"; PREFLIGHT=1; KEEP=0
HOSTNET=1; HOSTNET_FILE=""            # host-networking compose override (replaces the bridge)
DISALLOW_TOOLS="WebSearch,WebFetch,EnterPlanMode"
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
    --agent) AGENT="$2"; shift 2;;
    --root) ROOT="$2"; shift 2;;
    --env) HENV="$2"; shift 2;;
    --no-preflight) PREFLIGHT=0; shift;;
    --keep) KEEP=1; shift;;
    --no-hostnet) HOSTNET=0; shift;;
    --hostnet-file) HOSTNET_FILE="$2"; HOSTNET=1; shift 2;;
    --no-disallow-tools) DISALLOW_TOOLS=""; shift;;
    -h|--help) sed -n '3,36p' "$0"; exit 0;;
    *) if [ -z "$TASK_DIR" ]; then TASK_DIR="$1"; elif [ -z "$MODE" ]; then MODE="$1"; fi; shift;;
  esac
done
[ -n "$TASK_DIR" ] && [ -n "$MODE" ] || { echo "usage: mm_run.sh <task-dir> <oracle|nop|trial> [opts]" >&2; exit 2; }
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
if   [ -f "$TASK_DIR/task.toml" ];          then :
elif [ -f "$TASK_DIR/project/task.toml" ];  then TASK_DIR="$TASK_DIR/project"
else echo "error: no task.toml in $TASK_DIR (nor in $TASK_DIR/project, nor one Tasks/<task_id>/ below it)" >&2; exit 2; fi

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


read_settings_env(){ [ -f "$SETTINGS_JSON" ] || return 0
  python3 - "$SETTINGS_JSON" "$1" <<'PY'
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: sys.exit(0)
v=(d.get("env") or {}).get(sys.argv[2])
if v: print(v)
PY
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
  harbor run -p "$TASK_DIR" -a "$mode" -e "$HENV" -o "$ROOT" --job-name "$jobname" --yes
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
    if [ -z "$HOSTNET_FILE" ]; then
      GEN_COMPOSE="$(mktemp -t mm_hostnet.XXXXXX.yaml)"
      cat > "$GEN_COMPOSE" <<YAML
# generated by mm_run.sh — puts harbor's environment service on the host network so the
# agent container can reach the anonymizer proxy on the VM's loopback (127.0.0.1:8091).
services:
  ${COMPOSE_SVC}:
    network_mode: host
YAML
      HOSTNET_FILE="$GEN_COMPOSE"
      say "host networking: generated $HOSTNET_FILE (service '${COMPOSE_SVC}')"
    else
      [ -f "$HOSTNET_FILE" ] || { say "ERROR: --hostnet-file $HOSTNET_FILE does not exist"; return 3; }
      say "host networking: using $HOSTNET_FILE"
    fi
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
  say "harbor ${hargs[*]}"
  harbor "${hargs[@]}"
  local rc=$?; report "$ROOT/Trials" trial; return $rc
}

# ------------------------------------------------------------------- check
# Resolve credentials the same way as the trial (anonymizer by default) and
# run `harbor check` with them injected as environment variables.
# harbor check reads ANTHROPIC_API_KEY/BASE_URL from the shell environment
# rather than from --ae flags, so we prepend them directly.
run_check(){
  local KEY BASE
  KEY="${ANTHROPIC_API_KEY:-$(read_settings_env ANTHROPIC_API_KEY)}"
  BASE="${ANTHROPIC_BASE_URL:-$(read_settings_env ANTHROPIC_BASE_URL)}"
  : "${BASE:=http://localhost:8091}"
  : "${KEY:=anonymizer-placeholder}"
  case "$BASE" in
    https://litellm-proxy.ml.scale.com*)
      say "NOTE: using the PUBLIC Scale endpoint ($BASE) because it was explicitly set."
      say "      Unset ANTHROPIC_BASE_URL (and the settings.json entry) to use the anonymizer.";;
  esac
  say "task $TASK_ID"
  say "check creds base=$BASE key=$(mask "$KEY")"
  say "harbor check $TASK_DIR"
  ANTHROPIC_API_KEY="$KEY" ANTHROPIC_BASE_URL="$BASE" harbor check "$TASK_DIR"
}

# ------------------------------------------------------------------ analyze
# Resolve credentials the same way as the trial and run `harbor analyze` on
# the Trials output directory (or a custom path via --root).
run_analyze(){
  local KEY BASE
  KEY="${ANTHROPIC_API_KEY:-$(read_settings_env ANTHROPIC_API_KEY)}"
  BASE="${ANTHROPIC_BASE_URL:-$(read_settings_env ANTHROPIC_BASE_URL)}"
  : "${BASE:=http://localhost:8091}"
  : "${KEY:=anonymizer-placeholder}"
  case "$BASE" in
    https://litellm-proxy.ml.scale.com*)
      say "NOTE: using the PUBLIC Scale endpoint ($BASE) because it was explicitly set."
      say "      Unset ANTHROPIC_BASE_URL (and the settings.json entry) to use the anonymizer.";;
  esac
  local out_dir="$ROOT/Trials"
  say "task $TASK_ID"
  say "analyze creds base=$BASE key=$(mask "$KEY")"
  say "harbor analyze $out_dir"
  ANTHROPIC_API_KEY="$KEY" ANTHROPIC_BASE_URL="$BASE" harbor analyze "$out_dir"
}

# --------------------------------------------------------------------- report
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
  oracle)   run_plain oracle;;
  nop)      run_plain nop;;
  trial)    run_trial;;
  check)    run_check;;
  analyze)  run_analyze;;
  *) echo "unknown mode: $MODE (want oracle|nop|trial|check|analyze)" >&2; exit 2;;
esac
