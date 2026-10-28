FROM node:22-slim

# Minimal system deps: git (for harbor_base checkout in test.sh),
# python3 (for verifier.py), ca-certificates (HTTPS clones),
# build-essential (native modules if needed).
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    python3 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Enable corepack so yarn 4 (from packageManager field) is available to agents.
RUN corepack enable && corepack prepare yarn@4.16.0 --activate

WORKDIR /app

# Shallow fetch: only the files at base_commit, no git history.
# GitHub's uploadpack.allowReachableSHA1InWant allows fetching arbitrary SHAs.
# After fetching, strip .git and create a fresh one-commit harbor_base repo so:
#   (a) agents cannot follow git history to find the fix, and
#   (b) test.sh can reset touched files via `git checkout harbor_base -- <path>`.
RUN git init -q \
 && git remote add origin https://github.com/OpenCTI-Platform/opencti \
 && git fetch --depth=1 --no-tags origin 23bec28c6c3d1c5a2c165a76c504746f2b6fc503 \
 && git -c advice.detachedHead=false checkout 23bec28c6c3d1c5a2c165a76c504746f2b6fc503 \
 && rm -rf /app/.git \
 && git init -q \
 && git -c user.email=h@l -c user.name=h add -A \
 && git -c user.email=h@l -c user.name=h commit -q -m base \
 && git tag harbor_base

# Test-only deps (vitest, @testing-library/*, jsdom, a pinned React/MUI stack, ...) are
# installed at VERIFY time by tests/test.sh, not here -- see the note there. Full yarn
# install (1611 packages, >3 GB node_modules) exceeds sandbox disk limits, so no
# node_modules is baked into this image at all; the image only carries the app source at
# base_commit plus git/node/corepack.

# Visual evidence readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied — the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
