# Snapshot file
# Unset all aliases to avoid conflicts with functions
unalias -a 2>/dev/null || true
# Shopt
shopt -u autocd
shopt -u assoc_expand_once
shopt -u cdable_vars
shopt -u cdspell
shopt -u checkhash
shopt -u checkjobs
shopt -s checkwinsize
shopt -s cmdhist
shopt -u compat31
shopt -u compat32
shopt -u compat40
shopt -u compat41
shopt -u compat42
shopt -u compat43
shopt -u compat44
shopt -s complete_fullquote
shopt -u direxpand
shopt -u dirspell
shopt -u dotglob
shopt -u execfail
shopt -u expand_aliases
shopt -u extdebug
shopt -u extglob
shopt -s extquote
shopt -u failglob
shopt -s force_fignore
shopt -s globasciiranges
shopt -s globskipdots
shopt -u globstar
shopt -u gnu_errfmt
shopt -u histappend
shopt -u histreedit
shopt -u histverify
shopt -s hostcomplete
shopt -u huponexit
shopt -u inherit_errexit
shopt -s interactive_comments
shopt -u lastpipe
shopt -u lithist
shopt -u localvar_inherit
shopt -u localvar_unset
shopt -s login_shell
shopt -u mailwarn
shopt -u no_empty_cmd_completion
shopt -u nocaseglob
shopt -u nocasematch
shopt -u noexpand_translation
shopt -u nullglob
shopt -s patsub_replacement
shopt -s progcomp
shopt -u progcomp_alias
shopt -s promptvars
shopt -u restricted_shell
shopt -u shift_verbose
shopt -s sourcepath
shopt -u varredir_close
shopt -u xpg_echo
# Functions
# Shell Options
set -o braceexpand
set -o hashall
set -o interactive-comments
set -o monitor
shopt -s expand_aliases
# Aliases
# Check for rg availability
if ! hash rg 2>/dev/null && ! typeset -f rg >/dev/null 2>&1; then
  function rg {
  if [[ -x /root/.local/share/claude/versions/2.1.325 ]]; then
  if [[ -n ${ZSH_VERSION:-} ]]; then
    ARGV0=rg /root/.local/share/claude/versions/2.1.325 ${1+"$@"}
  elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    ARGV0=rg /root/.local/share/claude/versions/2.1.325 ${1+"$@"}
  else
    (exec -a rg /root/.local/share/claude/versions/2.1.325 ${1+"$@"})
  fi
  elif [[ -x /root/.local/bin/claude ]]; then
  if [[ -n ${ZSH_VERSION:-} ]]; then
    ARGV0=rg /root/.local/bin/claude ${1+"$@"}
  elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    ARGV0=rg /root/.local/bin/claude ${1+"$@"}
  else
    (exec -a rg /root/.local/bin/claude ${1+"$@"})
  fi
  else command rg ${1+"$@"}; fi
}
fi
# Shadow find/grep with embedded bfs/ugrep
unalias find 2>/dev/null || true
unalias grep 2>/dev/null || true
function find {
  if [[ -x /root/.local/share/claude/versions/2.1.325 ]]; then
  if [[ -n ${ZSH_VERSION:-} ]]; then
    ARGV0=bfs /root/.local/share/claude/versions/2.1.325 -S dfs -regextype findutils-default ${1+"$@"}
  elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    ARGV0=bfs /root/.local/share/claude/versions/2.1.325 -S dfs -regextype findutils-default ${1+"$@"}
  else
    (exec -a bfs /root/.local/share/claude/versions/2.1.325 -S dfs -regextype findutils-default ${1+"$@"})
  fi
  elif [[ -x /root/.local/bin/claude ]]; then
  if [[ -n ${ZSH_VERSION:-} ]]; then
    ARGV0=bfs /root/.local/bin/claude -S dfs -regextype findutils-default ${1+"$@"}
  elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    ARGV0=bfs /root/.local/bin/claude -S dfs -regextype findutils-default ${1+"$@"}
  else
    (exec -a bfs /root/.local/bin/claude -S dfs -regextype findutils-default ${1+"$@"})
  fi
  else command find ${1+"$@"}; fi
}
function grep {
  local _cc_a
  for _cc_a in ${1+"$@"}; do
    case "$_cc_a" in -*-filter*|-*-pager*|-*-view*|-*-format-open*|-*-config*|---*|-@*|-*-save-config*|-[Zz]*|-[!-]*[Zz]*|--null|--null-data) command grep ${1+"$@"}; return ;; esac
  done
  if [[ -x /root/.local/share/claude/versions/2.1.325 ]]; then
  if [[ -n ${ZSH_VERSION:-} ]]; then
    ARGV0=ugrep /root/.local/share/claude/versions/2.1.325 -G --ignore-files --hidden -I --exclude-dir=.git --exclude-dir=.svn --exclude-dir=.hg --exclude-dir=.bzr --exclude-dir=.jj --exclude-dir=.sl ${1+"$@"}
  elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    ARGV0=ugrep /root/.local/share/claude/versions/2.1.325 -G --ignore-files --hidden -I --exclude-dir=.git --exclude-dir=.svn --exclude-dir=.hg --exclude-dir=.bzr --exclude-dir=.jj --exclude-dir=.sl ${1+"$@"}
  else
    (exec -a ugrep /root/.local/share/claude/versions/2.1.325 -G --ignore-files --hidden -I --exclude-dir=.git --exclude-dir=.svn --exclude-dir=.hg --exclude-dir=.bzr --exclude-dir=.jj --exclude-dir=.sl ${1+"$@"})
  fi
  elif [[ -x /root/.local/bin/claude ]]; then
  if [[ -n ${ZSH_VERSION:-} ]]; then
    ARGV0=ugrep /root/.local/bin/claude -G --ignore-files --hidden -I --exclude-dir=.git --exclude-dir=.svn --exclude-dir=.hg --exclude-dir=.bzr --exclude-dir=.jj --exclude-dir=.sl ${1+"$@"}
  elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    ARGV0=ugrep /root/.local/bin/claude -G --ignore-files --hidden -I --exclude-dir=.git --exclude-dir=.svn --exclude-dir=.hg --exclude-dir=.bzr --exclude-dir=.jj --exclude-dir=.sl ${1+"$@"}
  else
    (exec -a ugrep /root/.local/bin/claude -G --ignore-files --hidden -I --exclude-dir=.git --exclude-dir=.svn --exclude-dir=.hg --exclude-dir=.bzr --exclude-dir=.jj --exclude-dir=.sl ${1+"$@"})
  fi
  else command grep ${1+"$@"}; fi
}
# Shadow pkill to refuse patterns matching the CLI process
unalias pkill 2>/dev/null || true
function pkill {
  if [ -n "${CLAUDE_PID:-}" ] && [ -r "/proc/${CLAUDE_PID}/comm" ]; then
    local _cc_skip="" _cc_a
    local -a _cc_probe=()
    for _cc_a in ${1+"$@"}; do
      if [ -n "$_cc_skip" ]; then _cc_skip=""; continue; fi
      case "$_cc_a" in
        --signal) _cc_skip=1 ;;
        --signal=*|-e|--echo) ;;
        -[0-9]*) ;;
        -[PUGOF]?*) _cc_probe+=("$_cc_a") ;;
        -[ABCDEFGHIJKLMNOPQRSTUVWXYZ][ABCDEFGHIJKLMNOPQRSTUVWXYZ0-9]*) ;;
        *) _cc_probe+=("$_cc_a") ;;
      esac
    done
    if command pgrep ${_cc_probe[@]+"${_cc_probe[@]}"} 2>/dev/null | command grep -qx "${CLAUDE_PID}"; then
      printf 'pkill: refusing to run — this pattern matches the Claude CLI process (PID %s). Narrow the pattern, or target your own children with `pkill -P $$ ...`.\n' "${CLAUDE_PID}" >&2
      return 1
    fi
  fi
  command pkill ${1+"$@"}
}
export PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
