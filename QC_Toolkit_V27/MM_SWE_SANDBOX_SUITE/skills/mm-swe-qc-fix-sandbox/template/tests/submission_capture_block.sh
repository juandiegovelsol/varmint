# MM SWE submission capture -- canonical block, installed by fix.py's `submission_capture`
# fix and detected by qc_structure's check_T. Must run immediately after `cd /app` and
# BEFORE the restore loop: that is the only moment /app is base + agent work.
#
# Depends on the environment providing: a git repo at /app with a `harbor_base` ref (see
# the canonical Dockerfile), $STDOUT_LOG / $STDERR_LOG, and /logs/verifier existing.

# Capture the agent's submission BEFORE anything below mutates /app -- this is the last
# moment the tree is base + agent work; the restore loop and test.patch come next.
#
# A THROWAWAY INDEX, never /app/.git/index: `git add` against the real one would leave paths
# staged and change how the `git checkout harbor_base --` and `git clean` below behave.
#
# TRACKED EDITS + A SOURCE WHITELIST, not `add -A` with a blacklist. This image builds wx
# in-tree AFTER the harbor_base commit (environment/Dockerfile), so everything the build
# emits is untracked and NOT in wx's .gitignore. A bare `add -A` captured 380MB of .o/.d/.so;
# excluding those by extension still left ~120 configure-generated files (samples/*/Makefile,
# bk-deps, version-script, lib/wx/config/*, the utils/wxrc/wxrc binary) because most have no
# extension to blacklist. Inverting it -- stage tracked modifications, then add only untracked
# files that LOOK like source -- keeps the agent's work and drops generated output by default.
_SUB=/logs/verifier/submission.patch
_SUBIDX=/tmp/.submission_index
_SUBSRC=('*.c' '*.cc' '*.cpp' '*.cxx' '*.h' '*.hh' '*.hpp' '*.hxx' '*.inl' '*.m' '*.mm'
         '*.py' '*.rb' '*.go' '*.rs' '*.java' '*.js' '*.ts' '*.tsx' '*.cs' '*.kt' '*.swift')
rm -f "$_SUBIDX"
GIT_INDEX_FILE="$_SUBIDX" git -C /app read-tree harbor_base 2>>"$STDERR_LOG" || true
GIT_INDEX_FILE="$_SUBIDX" git -C /app add -u 2>>"$STDERR_LOG" || true
# Enumerate before adding: `git add` aborts and stages NOTHING if any one pathspec matches
# no file, which silently drops the agent's new files on most tasks.
# Generated-output dirs are dropped from the UNTRACKED scan only. A project that keeps real
# source under lib/ is unaffected: those files are tracked at harbor_base, so `add -u` above
# already has them. This drops only files CREATED under a build dir during the run -- which,
# left in, break replay: they are recorded as new-file hunks and a fresh container from the
# same image already has them, so `git apply` fails with "already exists in working directory".
mapfile -t _SUBNEW < <(git -C /app ls-files --others --exclude-standard \
  -- "${_SUBSRC[@]}" ':(exclude)lib/' ':(exclude)build/' ':(exclude).deps/' 2>/dev/null)
if [ "${#_SUBNEW[@]}" -gt 0 ]; then
  GIT_INDEX_FILE="$_SUBIDX" git -C /app add -- "${_SUBNEW[@]}" 2>>"$STDERR_LOG" || true
fi
GIT_INDEX_FILE="$_SUBIDX" git -C /app diff --binary --cached harbor_base \
  > "$_SUB" 2>>"$STDERR_LOG" || true
rm -f "$_SUBIDX"

# WHAT THE WHITELIST DROPPED, listed rather than silently discarded. The split above captures
# every change to a TRACKED file (any extension, deletions included) but only NEW files that
# look like source -- so an agent adding config.yml, a .cmake module or an extensionless script
# loses it, and the patch still looks clean. That is the failure this manifest exists to expose.
#
# NEWEST FIRST, which is the useful ordering and not a cosmetic one: build output and image
# assets are created before the agent phase starts, so anything the agent made sorts to the top.
# Build artifacts are excluded by the same rules as the capture, to keep the list readable.
#
# If something here belongs in the submission, widen _SUBSRC. Do not reach for `add -A`.
_SUBSKIP=/logs/verifier/submission-skipped.txt
_SUBCAP=/tmp/.submission_captured
if [ "${#_SUBNEW[@]}" -gt 0 ]; then printf '%s\n' "${_SUBNEW[@]}" > "$_SUBCAP"; else : > "$_SUBCAP"; fi
_SUBSKIPN=$(git -C /app ls-files --others --exclude-standard -- . \
    ':(exclude)lib/' ':(exclude)build/' ':(exclude).deps/' \
    ':(exclude)*.o' ':(exclude)*.d' ':(exclude)*.a' ':(exclude)*.lo' ':(exclude)*.la' \
    ':(exclude)*.so' ':(exclude)*.so.*' ':(exclude)*.gch' ':(exclude)*.pyc' 2>/dev/null \
  | grep -vxF -f "$_SUBCAP" 2>/dev/null | wc -l)
{ echo "# Untracked files NOT captured into submission.patch, newest first."
  echo "# Anything the agent created sorts above build output, which predates the agent phase."
  echo "# total: ${_SUBSKIPN}  (showing at most 40)"
  git -C /app ls-files --others --exclude-standard -- . \
      ':(exclude)lib/' ':(exclude)build/' ':(exclude).deps/' \
      ':(exclude)*.o' ':(exclude)*.d' ':(exclude)*.a' ':(exclude)*.lo' ':(exclude)*.la' \
      ':(exclude)*.so' ':(exclude)*.so.*' ':(exclude)*.gch' ':(exclude)*.pyc' 2>/dev/null \
    | grep -vxF -f "$_SUBCAP" 2>/dev/null | head -200 \
    | while IFS= read -r _f; do
        printf '%s\t%s\t%s\n' "$(stat -c %Y "/app/$_f" 2>/dev/null || echo 0)" \
                              "$(stat -c %s "/app/$_f" 2>/dev/null || echo 0)" "$_f"
      done \
    | sort -rn | head -40 | awk -F'\t' '{printf "%s\t%s\t%s\n",$1,$2,$3}'
} > "$_SUBSKIP" 2>/dev/null || true
rm -f "$_SUBCAP"

# Size guard. The whitelist is a heuristic, so a task laying out source unusually could still
# produce something enormous. Cap it and leave a diagnosable stub: a truncated capture is
# recoverable, a full disk is not.
_SUBSZ=$(wc -c < "$_SUB" 2>/dev/null || echo 0)
if [ "$_SUBSZ" -gt 5242880 ]; then
  { echo "SUBMISSION CAPTURE SUPPRESSED: ${_SUBSZ} bytes exceeds the 5MB cap."
    echo "Directories contributing to the discarded patch:"
    grep -a "^diff --git" "$_SUB" | sed 's#^diff --git a/##; s# b/.*##; s#/[^/]*$##' \
      | sort | uniq -c | sort -rn | head -20
  } > "$_SUB.suppressed" 2>/dev/null
  : > "$_SUB"
  echo "== submission.patch SUPPRESSED (${_SUBSZ} bytes > 5MB cap) ==" | tee -a "$STDOUT_LOG"
else
  echo "== captured submission.patch (${_SUBSZ} bytes, $(grep -ac '^diff --git' "$_SUB" 2>/dev/null || echo 0) files) ==" \
    | tee -a "$STDOUT_LOG"
fi
