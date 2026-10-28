# MM_SWE_QC_FIX_SANDBOX

QC and repair for CBs working **in the sandbox**. Same checks and fixes as the local
`MM_SWE_QC_FIX`, wired to the run commands CBs already use.

```bash
bash install.sh                                   # -> /qc-fix-sandbox

FIX=~/.claude/skills/mm-swe-qc-fix-sandbox/fix.py
python3 $FIX qc     /home/sandbox/Tasks           # report only
python3 $FIX auto   /home/sandbox/Tasks           # fix safely + ALWAYS verify oracle/nop
python3 $FIX verify /home/sandbox/Tasks           # reproduce the gate on its own
```

`/home/sandbox/Tasks` works for both layouts. From TASK101 (V2) the bundle is
`Tasks/<task_id>/` and the skill descends into it — or pass that folder directly. Either way
`FIX_REPORT.md` lands in `/home/sandbox`, beside `Tasks/`, never inside it.

## No API key — anywhere in this flow

- the rubric judge is a **sub-agent**: it makes no model call, so **oracle and nop are keyless**
- the four checks are **stdlib-only, no network**
- `--emit-graders` writes prompts for the CB's **own agent**, it does not call an API
- **the trial is never run by this skill** — the only step that would need credentials, and
  re-running it is a human decision because it costs a real model call

## Harbor is never called directly

Runs go through the MM SWE runner (`mm_run.sh <task> oracle|nop`), resolved in order:

1. `$MM_RUNNER`
2. `~/.claude/skills/mmswe-runner/mm_run.sh`
3. **the copy bundled in `runner/`**

The bundled copy is deliberately the one **with `rescore`**. Two runners are in circulation both
labelled `v1.3.0`, and the older one has no `rescore` — a CB with that copy can never fold a
rubric verdict into the reward. If that is what is installed, point `$MM_RUNNER` at the bundled
path.

`auto` verifies the gate on **every** run, including when it fixed nothing — a clean task can
still have a broken gate. `--no-verify` opts out and says so. Exit **0** verified · **4** gate
broken · **5** not verified.

Runs are bounded by `$MM_RUN_TIMEOUT` (default 5400s) and the reward is read from the
`reward.txt` harbor wrote rather than scraped from the log. If it cannot verify, it exits
**2 / NOT VERIFIED** instead of reporting a pass.

## Fix policy

| | |
|---|---|
| **Automatic** | build junk and editor debris, legacy `[verifier.env]`, missing `rubric_file`, drifted/missing `judge.py`, the `test.sh` judge block, `rubrics.json` shape, mismatched rubric task id |
| **Escalated** (2 only) | an unrecognised non-canonical file · an unreferenced asset — both invalidate the trial |
| **Reported, never fixed** | rubric criterion wording — rewriting a criterion is authoring |

An unreferenced image may still be the task's visual source, so "unused" is never inferred safely.

## Trial classes

**A** verifier-side cosmetic → keep the trial · **B** rubric/judge only → keep it and `rescore` ·
**C** agent-visible → must be re-run. `plan` shows the verdict for approving only the automatic
fixes versus also approving an escalated one, so the cost is visible before deciding.

## Guarantees

Snapshot before any edit, restored on regression. Canonical-layout whitelist: a fix may add a
file the layout allows (`judge.py`) but never anything outside it, or it aborts and rolls back.
