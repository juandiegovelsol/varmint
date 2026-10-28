FROM python:3.11-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends git curl build-essential libffi-dev libssl-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone, pin to base commit, strip .git (anti-cheat: agent cannot inspect fix PR/future history).
# Re-init a single base commit + immutable tag so the verifier can reset test files;
# git apply still works without upstream history.
RUN git clone https://github.com/Textualize/textual /app \
 && git -C /app checkout a4432febe7f92bb8752b19760c66d77e9fd1d5da \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Install the package itself, editable, so whatever ends up in src/ is what the suite imports.
RUN pip install --upgrade pip setuptools wheel -q \
 && pip install -e .

# Pin the package's own runtime dependencies to exactly what this commit's poetry.lock resolves.
# Each satisfies the constraint pyproject declares, so this is the environment the repository
# itself was tested in rather than a guess. Installed AFTER the editable install so these pins win
# over the open ranges in pyproject.
#
# No `2>/dev/null || true` here, unlike the harvested version: a dependency that fails to install
# has to break the build loudly at image-build time. Swallowed, it resurfaces much later as a
# suite that cannot even be collected, which the verifier can only report as a reward of 0.0.
RUN pip install -q \
      "markdown-it-py[plugins,linkify]==3.0.0" \
      rich==13.9.4 \
      platformdirs==4.3.6 \
      typing-extensions==4.12.2

# Test tooling is DOWNLOADED here but deliberately NOT installed: the image the agent works in
# carries nothing it would not need to write the fix, and test.sh installs pytest from this cache
# at verify time. Downloading at build time rather than installing at verify time keeps the
# verifier off the network, so a registry outage cannot turn a correct fix into a reward of 0.0,
# and freezes the resolved wheel set into the image layer instead of re-resolving it per run.
# Only pytest is cached: the suite is run with --noconftest and no addopts, so no plugin is
# loaded, and pytest pulls no wheel that could shadow the editable install of the package itself.
RUN pip download -q -d /opt/test-wheels pytest==8.3.4 \
 && if pip show pytest >/dev/null 2>&1; then \
      echo "ERROR: pytest must not be installed in the image"; exit 1; \
    fi

# Visual evidence, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied into the image:
# the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
