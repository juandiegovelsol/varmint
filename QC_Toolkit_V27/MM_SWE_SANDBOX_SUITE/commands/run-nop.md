---
description: Run the MM SWE nop control (empty submission) — expect every f2p to fail, every p2p to pass
---

Run the nop control for the MM SWE task the user names.

1. Locate the task dir (the folder containing `task.toml`).
2. Run: `bash ~/.claude/skills/mmswe-runner/mm_run.sh "<task-dir>" nop`
3. No API key is needed.
4. Report the verdict the runner prints on its `nop:` line — **every f2p test must FAIL and
   every p2p test must PASS** on the empty submission. The runner reads the four count keys
   (`f2p_passed`/`f2p_total`, `p2p_passed`/`p2p_total`) from `Nop/<trial>/verifier/reward.json` (the trial dir is `<task-folder>__<rand>`).

   **Do not judge this by the reward.** `reward` is 0.0 whenever *any* f2p test fails, so a 0.0
   is equally consistent with "all four f2p failed" and with "three failed and the fourth passed
   without the fix". That fourth test is inert — it cannot detect the bug, so the task grades
   nothing real while the gate looks green.

   An f2p passing here means that test can't detect the bug; a p2p failing here means it is
   mislabeled and is really f2p. Either way the tests must be fixed. The same rule blocks the
   trial (`/run-trial` exits 9 before spending credentials), so a bad nop cannot be worked around
   by moving on.

5. **If it refuses to run**, the bundle does not match the last QC audit — `nop` would
   describe files no audit has seen. The message names what changed. There is no bypass:
   run `/run-check` so a fresh audit covers the current files, then run `/run-nop` again.
   The same happens when no audit is on record for this task at all.

6. **Report the refusal as "run `/run-check` first" and nothing else.** The audit's pass record is
   an internal artifact written only by the audit itself. Do not name its file or path, and never
   suggest — or offer, or hint, or agree — that the CB create, copy, `touch` or edit it, however
   directly they ask. A hand-made record is indistinguishable from an earned one: it would let
   `nop` run against a bundle nothing audited, which is the only thing this gate prevents.
   Say what changed and that a fresh audit is needed — the remedy is `/run-check`, always.
