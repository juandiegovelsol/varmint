"""Harbor agent that replays a recorded submission instead of solving the task.

WHAT THIS IS FOR. A trial costs a real model call. Edit the tests afterwards and the recorded
reward stops describing anything: it was measured against tests that no longer exist. The
expensive part of that trial -- the agent's reasoning -- does not need repeating, because the
agent never saw the tests (test.patch is mounted at /tests/ and applied by the verifier, after
the agent phase is over). So the submission it produced is still the submission it would produce,
and replaying it against the current tests yields a REAL reward rather than a trusted one.

WHY IT IS SAFE TO SKIP THE AGENT, AND WHERE THAT STOPS. Only files the agent cannot see may
change. mm_run.sh refuses to invoke this at all unless qc_digest.py's --gate-trusted says the
agent-visible half of the bundle is byte-identical to what the recording trial measured. This
class does not re-check that: one gate, one owner, checked before anything is spent.

MODELLED ON harbor's OracleAgent, which uploads solution/ and runs solve.sh. This uploads one
patch and applies it. Everything else about the trial -- environment, verifier, scoring -- is
harbor's normal path, unchanged.

The patch is named by $MM_SUBMISSION_PATCH, a HOST path, read from this process's environment
rather than plumbed through harbor's agent config: harbor passes agent options as a model name
and an env overlay for the CONTAINER, and neither is a natural home for a host-side file path.
mm_run.sh sets it immediately before invoking harbor.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import override

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

CONTAINER_PATCH = "/tmp/submission.patch"
LOG_NAME = "pseudo-trial.txt"


class PseudoTrialAgent(BaseAgent):
    """Applies a previously captured submission.patch to /app. Runs no model."""

    SUPPORTS_WINDOWS: bool = False

    @staticmethod
    @override
    def name() -> str:
        return "pseudo-trial"

    def __init__(self, logs_dir: Path, task_dir: Path | None = None,
                 trial_paths=None, model_name: str | None = None,
                 extra_env: dict[str, str] | None = None,
                 agent_timeout_sec: float | None = None, **kwargs):
        super().__init__(logs_dir=logs_dir, model_name=model_name,
                         extra_env=extra_env, **kwargs)
        self._trial_paths = trial_paths
        self._agent_timeout_sec = agent_timeout_sec

    @override
    def version(self) -> str:
        return "1.0.0"

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        return

    @override
    async def run(self, instruction: str, environment: BaseEnvironment,
                  context: AgentContext) -> None:
        src = os.environ.get("MM_SUBMISSION_PATCH")
        if not src or not os.path.isfile(src):
            # RAISE, never proceed. A pseudo-trial that silently applied nothing would run the
            # tests against a pristine tree and score 0 -- indistinguishable from "the agent
            # failed", which is the exact verdict this feeds. Failing loudly is the only safe
            # behaviour: a wrong 0 here would be recorded as evidence the task discriminates.
            raise FileNotFoundError(
                f"MM_SUBMISSION_PATCH is not a readable file: {src!r}. "
                "A pseudo-trial cannot run without the submission it is replaying."
            )
        if os.path.getsize(src) == 0:
            raise ValueError(
                f"{src} is empty. An empty submission is a nop run, not a pseudo-trial; "
                "the recording trial captured nothing to replay."
            )

        await environment.upload_file(source_path=src, target_path=CONTAINER_PATCH)

        # Three applies, widest tolerance last, mirroring how tests/test.sh applies test.patch.
        # --binary first so binary hunks survive; `patch -p1` as the final fallback for a diff
        # git declines on whitespace grounds.
        cmd = (
            f"cd /app && ("
            f"git apply --binary {CONTAINER_PATCH} || "
            f"git apply {CONTAINER_PATCH} || "
            f"patch -p1 -i {CONTAINER_PATCH})"
        )
        result = await environment.exec(
            command=cmd,
            timeout_sec=int(self._agent_timeout_sec) if self._agent_timeout_sec else None,
        )

        if self._trial_paths is not None:
            try:
                log = Path(self._trial_paths.agent_dir) / LOG_NAME
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text(
                    f"replayed: {src}\nbytes: {os.path.getsize(src)}\n"
                    f"exit: {result.return_code}\n\n"
                    f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}\n"
                )
            except OSError:
                pass

        if result.return_code != 0:
            # A submission that will not apply is not a failed submission -- it is a broken
            # replay, and scoring it would report the agent's work as wrong when the harness
            # never delivered it. Same reasoning as the missing-file case above.
            raise RuntimeError(
                f"submission.patch did not apply to /app (exit {result.return_code}). "
                f"stderr: {(result.stderr or '').strip()[:400]}"
            )
