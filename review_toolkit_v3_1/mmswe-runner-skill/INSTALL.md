# Install — mmswe-runner

    unzip mmswe-runner-skill.zip
    cd mmswe-runner-skill
    bash install.sh

Installs to your personal Claude scope:

- skill    -> `~/.claude/skills/mmswe-runner/`
- commands -> `~/.claude/commands/` (`/run-oracle`, `/run-nop`, `/run-trial`, `/run-all`)

Re-running overwrites the previous copy. Requires the Harbor CLI and a running Docker.
Only the agent trial needs `ANTHROPIC_API_KEY` (env or `~/.claude/settings.json`);
oracle and nop run without one.
