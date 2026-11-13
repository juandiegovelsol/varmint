#!/usr/bin/env bash
# qc_env_probe.sh - build environment/Dockerfile and prove the HARNESS can run inside it.
#
# WHY THIS EXISTS ALONGSIDE THE STATIC CHECK. qc_structure's group E reads the Dockerfile and can
# only judge what the text says: a fragment that deletes curl, a registry pointed at a black hole, a
# minimal base with no fetcher installed. What it cannot know is what the base image actually
# CONTAINS - a private base, a multi-stage COPY, an ENTRYPOINT that mangles PATH, a USER with no
# writable HOME. This probe answers the question by asking the built image directly, and it is the
# only form of the check that cannot be fooled.
#
# WHY IT IS CHEAP. No API key, no model call, no agent, no network beyond the build harbor already
# performs: it runs `command -v` and one `npm ping`-free registry read inside the container. That is
# the entire cost, against a trial that is the single most expensive step in the pipeline.
#
#   usage: qc_env_probe.sh /home/sandbox/Tasks [--no-build]
#
# exit 0  the image can host the agent CLI, the verifier's git diff, and a bash phase
# exit 1  something the harness needs is missing - the trial WILL die at startup
# exit 2  could not build or could not reach docker (nothing proven either way)
set -uo pipefail

TASKS="${1:-}"
[ -d "$TASKS" ] || { echo "usage: $0 <path-to-Tasks> [--no-build]" >&2; exit 2; }
# Flat Tasks/task.toml or nested Tasks/<any-task-name>/task.toml - resolved by qc_layout, the
# same rule every other check uses.
_resolved="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1])
from qc_layout import find_task_dir, AmbiguousLayout
try: print(find_task_dir(sys.argv[2]) or "")
except AmbiguousLayout as e: sys.exit(f"error: {e}")' "$(dirname "${BASH_SOURCE[0]}")" "$TASKS")" || exit 2
[ -n "$_resolved" ] && TASKS="$_resolved"
DF="$TASKS/environment/Dockerfile"
[ -f "$DF" ] || { echo "no $DF" >&2; exit 2; }

# Named after the task folder; docker tags must be lowercase [a-z0-9._-].
TAG="qc-env-probe:$(basename "$TASKS" | tr 'A-Z' 'a-z' | tr -c 'a-z0-9._\n-' '-' | cut -c1-120)"
# Which uids this image drops to, read from the Dockerfile by the SAME function group P uses, so the
# probe and the static check can never disagree about what the file says. Empty is the normal case.
CHECKDIR="$(cd "$(dirname "$0")" && pwd)"
PRIV_USERS=$(python3 -c '
import sys
sys.path.insert(0, sys.argv[1])
from qc_structure import _privilege_sites
print(" ".join(sorted({s["user"] for s in _privilege_sites(open(sys.argv[2], errors="replace").read())})))
' "$CHECKDIR" "$DF" 2>/dev/null)
# Is there a RUN-TIME drop that does NOT repair `/` first? This is the half the probe cannot infer on
# its own. A bare drop failing inside the container is a fact about the DAEMON, true of every image
# here including a perfectly repaired one - so on its own it is not a defect and must not be reported
# as one. It becomes a defect only in combination with an unguarded runtime drop, which is exactly
# what group P decides. Same function, one answer.
UNGUARDED_RT=$(python3 -c '
import sys
sys.path.insert(0, sys.argv[1])
from qc_structure import _privilege_sites
print("1" if any(s["phase"] == "verify" and not s["guarded"]
                 for s in _privilege_sites(open(sys.argv[2], errors="replace").read())) else "")
' "$CHECKDIR" "$DF" 2>/dev/null)
if [ "${2:-}" != "--no-build" ]; then
  echo "== building $TAG from $DF (this is the same build harbor performs)"
  docker build -t "$TAG" "$TASKS/environment" >/tmp/qc_env_probe_build.log 2>&1 || {
    echo "BUILD FAILED - see /tmp/qc_env_probe_build.log (tail below)"; tail -25 /tmp/qc_env_probe_build.log
    exit 2; }
fi

# The probe body runs INSIDE the container. It mirrors what harbor actually does, in order:
#   1. every phase is spawned as `bash -c 'set -euo pipefail; ...'`      -> bash must exist
#   2. the agent CLI install picks a path on `command -v apk`            -> curl OR npm+registry
#   3. the verifier diffs the candidate against the harbor_base tag      -> git + the tag
#   4. the install appends to ~/.bashrc and writes ~/.local/bin          -> HOME must be writable
PROBE='
PRIV_USERS="'"$PRIV_USERS"'"
UNGUARDED_RT="'"$UNGUARDED_RT"'"
fail=0
say() { printf "%-6s %s\n" "$1" "$2"; }
need() { if command -v "$1" >/dev/null 2>&1; then say "ok" "$1 -> $(command -v "$1")";
         else say "FAIL" "$1 MISSING - $2"; fail=1; fi; }

need bash "harbor spawns every phase as bash -c \"set -euo pipefail; ...\""
need git  "the verifier diffs the candidate against harbor_base with git"

if command -v apk >/dev/null 2>&1; then
  say "info" "apk base -> harbor installs the agent with: npm install -g @anthropic-ai/claude-code"
  need npm "the apk install path for the agent CLI"
  reg=$(npm config get registry 2>/dev/null)
  case "$reg" in
    *127.0.0.1*|*localhost*|*0.0.0.0*|*::1*)
      say "FAIL" "npm registry is a black hole ($reg) - the agent CLI cannot be installed"; fail=1 ;;
    *) say "ok" "npm registry = $reg" ;;
  esac
else
  say "info" "non-apk base -> harbor installs the agent with: curl -fsSL https://downloads.claude.ai/... | bash"
  need curl "THE agent CLI install path on this base - its absence is the exit-127 failure"
fi

# /etc/hosts must not blackhole what the install and the trial reach for.
for h in downloads.claude.ai claude.ai api.anthropic.com; do
  line=$(grep -E "[[:space:]]$h([[:space:]]|$)" /etc/hosts 2>/dev/null | tail -1)
  case "$line" in
    127.*|0.0.0.0*|::1*) say "FAIL" "/etc/hosts blackholes $h ($line)"; fail=1 ;;
    ?*) say "info" "/etc/hosts pins $h -> $line" ;;
  esac
done

# The install writes ~/.local/bin and appends to ~/.bashrc, so HOME must be writable by this USER.
if touch "$HOME/.qc_probe" 2>/dev/null; then rm -f "$HOME/.qc_probe"; say "ok" "HOME=$HOME writable as $(id -un)"
else say "FAIL" "HOME=$HOME NOT writable as $(id -un) - the CLI install cannot place ~/.local/bin"; fail=1; fi

# CAN A NON-ROOT PROCESS RUN HERE AT ALL? (group P, and the half no text can settle)
#
# The build already proved the build-time drops work - it completed. What it cannot prove is that
# they still work in the SHIPPED image, because the mode change on `/` that made them work is not
# captured in a layer diff. MEASURED on docker 29.6: a build whose RUN does `chmod a+rx /` succeeds,
# and `docker run` on the resulting image still shows `drwxr-x---  /` and still fails `su`. So a
# starter script or entrypoint that drops privileges needs its own chmod, at run time, as root -
# and this is the only check that can see whether it has one.
#
# THE PROBE MUST PERFORM THE SAME DROP THE DOCKERFILE DOES, and `--regid` is what makes it the same.
# MEASURED in this image: `/` is `drwxr-x---`, so GROUP root still has r-x, and
# `setpriv --reuid=pg --clear-groups` KEEPS gid 0 - it traverses `/` happily and prints OK, while
# `su pg`, which switches gid as well, dies. A fallback missing `--regid` therefore reported a green
# PASS on an image where every `su` in the Dockerfile fails: the probe was testing a weaker drop than
# the one that breaks. With `--regid` it reproduces the exact libc symptom instead:
#   /bin/sh: error while loading shared libraries: libc.so.6: cannot open shared object file
say "info" "rootfs at run time: $(ls -ld / 2>/dev/null | awk "{print \$1}")"
for u in $PRIV_USERS; do
  if command -v su >/dev/null 2>&1; then
    drop_ok=$(su "$u" -c "echo ok" 2>/dev/null)
  elif command -v setpriv >/dev/null 2>&1; then
    drop_ok=$(setpriv --reuid="$u" --regid="$(id -g "$u" 2>/dev/null || echo "$u")" \
                      --clear-groups /bin/sh -c "echo ok" 2>/dev/null)
  else
    say "info" "neither su nor setpriv in the image - cannot probe the drop to $u"
    continue
  fi
  if [ "$drop_ok" = "ok" ]; then
    say "ok" "dropping to $u works unaided - this daemon does not impose the 0750 rootfs"
  elif [ -z "$UNGUARDED_RT" ]; then
    # NOT A DEFECT, AND SAYING SO IS THE POINT. A bare drop fails in every image on this daemon,
    # a repaired one included, so reporting it as a failure would FAIL the correct shape - the
    # opposite mistake to the one above, and just as wrong.
    say "ok" "a bare drop to $u fails here ($(ls -ld / | cut -c1-10) /), and every generated script repairs / itself first - which is the correct shape"
  else
    # WHICH OF THE TWO CAUSES IS IT? A 0750 `/` is repairable in the Dockerfile; a restriction the
    # daemon or an LSM imposes is not, and telling a CB to add a chmod that cannot help is worse than
    # saying "escalate". The mode is right there, so the probe decides instead of guessing.
    case "$(ls -ld / | cut -c1-10)" in
      drwxr-xr-x|drwxrwxr-x|drwxrwxrwx)
        say "FAIL" "dropping to $u fails although / is ALREADY world-traversable - the restriction is imposed by the daemon or an LSM, NOT by file modes. Not fixable in the Dockerfile; escalate." ;;
      *)
        say "FAIL" "dropping to $u FAILS in the shipped image ($(ls -ld / | cut -c1-10) /), and a runtime script drops privileges WITHOUT repairing / first. That script dies with a libc Permission denied at verify time. It must chmod a+rx / as root before its first drop - the build-time chmod does not ship." ;;
    esac
    echo "NONROOT_BROKEN"
    fail=1
  fi
done

# The anti-cheat tag the verifier diffs against.
if command -v git >/dev/null 2>&1; then
  if git -C /app rev-parse harbor_base >/dev/null 2>&1; then say "ok" "git tag harbor_base present in /app"
  else say "FAIL" "no harbor_base tag in /app - the verifier cannot produce a candidate diff"; fail=1; fi
  if [ -d /app/.git ]; then
    n=$(git -C /app log --oneline 2>/dev/null | wc -l)
    [ "$n" -le 1 ] && say "ok" "/app history is a single squashed commit (upstream fix not reachable)" \
                   || { say "FAIL" "/app has $n commits - the upstream fix may be reachable by the agent"; fail=1; }
  fi
fi
exit $fail
'
echo "== probing the built image"
OUT=$(mktemp)
docker run --rm --entrypoint bash "$TAG" -c "$PROBE" 2>&1 | tee "$OUT"
rc=${PIPESTATUS[0]}

# A GREEN PROBE IS NOT A CLEARANCE FOR THIS ONE PATTERN, and saying so is the whole point of the
# warning. Measured on docker 29.6/BuildKit: /etc/hosts is read-only during a build, so
# `printf >> /etc/hosts && npm config set ... && rm -f /usr/bin/curl` aborts at its FIRST link -
# curl survives, the probe passes, and the image looks sound. On a builder that permits the write,
# the same chain runs to completion, curl is deleted, and the trial dies with exit 127. The probe
# can only ever describe the builder it just ran on, so the static check (qc_structure group E,
# env_hosts_build_write) stays authoritative here.
if grep -qE '>>?[[:space:]]*/etc/hosts|tee[[:space:]]+(-a[[:space:]]+)?/etc/hosts' "$DF"; then
  echo
  echo "!! CAUTION: this Dockerfile writes /etc/hosts from a RUN, so THIS PROBE'S RESULT IS NOT"
  echo "   PORTABLE. /etc/hosts is read-only under BuildKit: the write fails, an && chain aborts"
  echo "   there, and whatever followed it (an npm registry redirect, an rm of curl) never ran -"
  echo "   which is why the probe may be green here and the trial still die with exit 127 on a"
  echo "   builder that permits the write. Fix the Dockerfile per group E rather than trusting this."
fi

if [ $rc -eq 0 ]; then
  echo "== PASS: the harness can install the agent CLI and run the verifier in this image"
elif grep -q NONROOT_BROKEN "$OUT"; then
  # A DIFFERENT FAILURE NEEDS A DIFFERENT SENTENCE. The agent-startup wording below would send the
  # reader to network_mode and the agent CLI, neither of which is involved: the harness installs and
  # runs fine here, and what dies is the privilege drop inside test.sh - at verify time, scoring the
  # run 0.0 with a message about libc.
  echo "== FAIL: a privilege drop fails in this image (see the NONROOT lines above)."
  echo "   The harness itself is fine; what breaks is any test.sh helper, entrypoint or starter"
  echo "   script that switches uid - it dies with a libc \"Permission denied\" that reads as a"
  echo "   corrupt base image. The generated script must \`chmod a+rx /\` as root before its first"
  echo "   drop; the build-time chmod does NOT ship, because a mode change on \`/\` is not captured"
  echo "   in a layer diff. See qc_structure group P (env_nonroot_verify)."
else
  echo "== FAIL: the trial would die at startup in this image (see the FAIL lines above)."
  echo "   Anti-cheat belongs in task.toml [agent] network_mode = \"no-network\", which seals the"
  echo "   agent phase at the harness level and covers far more than deleting clients in the image."
fi
rm -f "$OUT"
exit $rc
