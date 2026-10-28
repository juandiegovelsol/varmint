# Fix template — the canonical shape a task is repaired toward

`fix.py` restores from these files rather than improvising, so every task ends up wired the
same way. Derived from a known-good golden bundle (`mui__material-ui-47967-mm`).

| File | Used by | How |
|---|---|---|
| `CANONICAL_LAYOUT.txt` | whitelist guard | the path SET allowed inside `Tasks/`. Anything else after a fix = abort + rollback. |
| `tests/judge.py` | `judge_drift`, `judge_missing` | **byte-restored**. Identical in every task, so a hash mismatch means someone edited the judge. |
| `tests/test_sh_judge_block.sh` | `test_sh_judge` | **inserted verbatim**, replacing the plain verifier invocation. Verified to reproduce the golden byte-for-byte. |
| `tests/verifier_reward_block.py` | `verifier_rubric` | **printed as a proposal, never applied.** `verifier.py` holds task-specific scoring; a blind insert could silently change what the task grades. |
| `tests/rubrics.stub.json` | `rubrics_shape` | the sanctioned always-pass stub, and the source of the standard stub `description`. |
| `tests/config_required_keys.json` | `rubric_file` | the keys every `config.json` carries; only `rubric_file` has a fixed value. |

## Why some things are restored and others only proposed

Byte-restoration is safe exactly when a file is supposed to be identical everywhere —
`judge.py` and the `test.sh` judge block qualify. `verifier.py` does not: it resolves this
task's f2p/p2p identifiers and computes its own tests score. So the fixer shows the canonical
block and stops.

## Keeping this current

The golden is the source of truth. If the canonical wiring changes, re-derive these files from
an updated golden bundle rather than hand-editing them here, or the fixer will start restoring
tasks toward a shape nothing else uses.
