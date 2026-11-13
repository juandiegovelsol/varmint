# Fix template — the canonical shape a task is repaired toward

`fix.py` restores from these files rather than improvising, so every task ends up wired the
same way. Derived from a known-good golden bundle (`mui__material-ui-47967-mm`).

| File | Used by | How |
|---|---|---|
| `CANONICAL_LAYOUT.txt` | whitelist guard | the path SET allowed inside `Tasks/`. Anything else after a fix = abort + rollback. |
| `tests/judge.py` | `judge_drift`, `judge_missing` | installed only when a rubric ships and none is present. Drift is now **ask**, not byte-restore: there are two valid judge backends (keyless sub-agent, API-capable) and this template is one of them, so a hash mismatch usually means "the other backend", not "edited". |
| `tests/test_sh_judge_block.sh` | `test_sh_judge` | **inserted verbatim**, replacing the plain verifier invocation. Verified to reproduce the golden byte-for-byte. |
| `tests/verifier_reward_block.py` | `verifier_rubric` | **printed as a proposal, never applied.** `verifier.py` holds task-specific scoring; a blind insert could silently change what the task grades. |
| `tests/config_required_keys.json` | `rubric_file` | the keys every `config.json` carries. `rubric_file` is required **only when a rubric ships**. |

`tests/rubrics.stub.json` was **deleted**. It existed to create an always-pass stub rubric, which
is no longer a legal shape: a stub cannot fail any submission yet reports `rubric_passed = 1` as
though a real rubric had been satisfied. A task that needs no rubric ships **no rubric layer at
all** — see `checks/qc_rubric_format.py`, which reports a stub as a blocking Fail.

## Why some things are restored and others only proposed

Byte-restoration is safe exactly when a file is supposed to be identical everywhere —
`judge.py` and the `test.sh` judge block qualify. `verifier.py` does not: it resolves this
task's f2p/p2p identifiers and computes its own tests score. So the fixer shows the canonical
block and stops.

## Keeping this current

The golden is the source of truth. If the canonical wiring changes, re-derive these files from
an updated golden bundle rather than hand-editing them here, or the fixer will start restoring
tasks toward a shape nothing else uses.
