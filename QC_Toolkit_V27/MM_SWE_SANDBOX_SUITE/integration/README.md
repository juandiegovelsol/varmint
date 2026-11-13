# Integrating the QC gate into mmswe-runner

`harbor check` costs credentials and wall clock. `mm_run.sh` already refuses to spend a check run
on a task whose required files are missing, or whose metadata is inconsistent. This patch adds a
**third** pre-flight in the same place, for the same reason: the MM SWE QC audit.

## What it changes

Three files, **purely additive** — no existing line is modified or removed:

| File | Change |
|---|---|
| `skills/mmswe-runner/mm_run.sh` | `QC_CHECK` flag, `--no-qc`, `resolve_qc()`, `qc_gate()`, and the gate call in `run_check()` |
| `skills/mmswe-runner/SKILL.md` | documents the third gate |
| `commands/run-check.md` | tells the agent what exit 7 means and to ask the CB |

## Behaviour

Runs `fix.py qc <task> --phase bundle --no-report` before `harbor check`.

- **Passes** → straight through to harbor, nothing printed beyond the audit.
- **Bundle FAILs, terminal attached** → prints the audit and asks
  `spend a check run on this task anyway? [y/N]`.
- **Bundle FAILs, no terminal** (an agent, CI) → exits **7** rather than guessing. 7 means
  "findings above, ask the user, then re-run with `--no-qc`".
- **QC skill not installed** → says the gate was SKIPPED, **not** passed, and continues.
- `--no-qc` skips the gate entirely.

`--phase bundle` is deliberate: `harbor check` grades the TASK, not the runs, so gate-tier and
trial-tier findings become OPEN and cannot block. A stale Oracle never stops a check run.

Only `check` is gated by *this patch*. `oracle`, `nop`, `analyze` and `rescore` are untouched by it.

`trial` has its own gate, which is **not** part of this patch: it requires oracle = 1, a nop whose
f2p tests all fail and whose p2p tests all pass, and
that both controls' recorded task digest match the bundle's digest now. That lives in the runner
bundled here, so applying this patch to a separately installed `mmswe-runner` gives you the `check`
pre-flight without the trial staleness check. See the suite README, "The trial needs its controls
first".

No recursion: it calls `qc` only, which reads files and invokes no runner.

## Resolution order

`$MM_QC_FIX` → `~/.claude/skills/mm-swe-qc-fix-sandbox/fix.py` → `$(dirname $0)/../fix.py`.

The third candidate is what makes a runner copy sitting beside a `fix.py` self-contained: it finds
its own sibling with nothing installed and no env var set.

## Applying it

The copy bundled in `skills/mmswe-runner/mm_run.sh` **already has the gate** — you
only need this patch for a *separately installed* `mmswe-runner`, and again after any update to it
overwrites the change.

    cd <mmswe-runner-skill root>          # the dir holding skills/ and commands/
    patch -p0 --dry-run < mmswe-runner-qc-gate.patch    # check first
    patch -p0 < mmswe-runner-qc-gate.patch

Verified to apply cleanly to mmswe-runner v1.4.0 (`mm_run.sh` 1130 lines, `SKILL.md` 408 lines).
If a future version has moved those anchors, re-generate rather than force it.
