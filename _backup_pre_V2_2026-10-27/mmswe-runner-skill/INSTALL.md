# Install — mmswe-runner

    unzip mmswe-runner-skill.zip
    cd mmswe-runner-skill
    bash install.sh

Installs to your personal Claude scope:

- skill    -> `~/.claude/skills/mmswe-runner/`
- commands -> `~/.claude/commands/` (`/run-oracle`, `/run-nop`, `/run-trial`,
  `/run-check`, `/run-analyze`)

Re-running overwrites the previous copy. Requires the Harbor CLI and a running Docker.
The trial, check, and analyze need `ANTHROPIC_API_KEY` (env or
`~/.claude/settings.json`, else the anonymizer placeholder); oracle and nop run
without one.

## 1.1 — check and analyze

`bash mm_run.sh <task-dir> check` and `bash mm_run.sh <task-dir> analyze` wrap
`harbor check` and `harbor analyze`. Run those subcommands bare and the container
inherits `ANTHROPIC_BASE_URL=http://localhost:8091`, dials its own loopback, and dies
with `API Error: Unable to connect to API (ConnectionRefused)` — reported as
`UnknownApiError` with a mean of 0.000. Neither subcommand accepts
`--extra-docker-compose`, and both discard a `-c` JobConfig's `[environment]`, so the
host-network override the trial uses cannot reach them; the runner probes for a
container-reachable host address and passes it via `--ae` instead. See SKILL.md.
