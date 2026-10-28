FROM node:22-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates curl python3 build-essential \
 && rm -rf /var/lib/apt/lists/*

# Enable corepack for Yarn 4 Berry (tldraw uses yarn4 + workspaces)
RUN corepack enable

WORKDIR /app

# [IMPORTANT] Copy bug patches to a TEMP path (not into /app) so they can be applied
# into the base snapshot below and never reach the agent-visible tree.
COPY assets/bugs/ /tmp/bugs/

# Clone, pin to base commit, strip .git (anti-cheat: agent cannot see fix PR history).
# Re-init a single-commit repo tagged harbor_base so the verifier can reset test files.
RUN git clone https://github.com/tldraw/tldraw /app \
 && git -C /app checkout 56c3bc3fbec3bdf48e314732a51dd22fcfdd53a5 \
 && rm -rf /app/.git \
 # [IMPORTANT] Apply every bug patch BEFORE the snapshot below, so each defect
 # becomes part of harbor_base (the exact state the agent starts from).
 && for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 # [IMPORTANT] harbor_base = base commit + all bug patches. Must come AFTER the
 # apply loop; the verifier resets to this tag.
 && git -C /app tag harbor_base

# Pre-install workspace dependencies (pinned lockfile)
RUN yarn install --immutable 2>&1 | tail -10 || yarn install 2>&1 | tail -10

# Visual evidence readable by the agent at /app/.harbor_assets/
# tests/ and solution/ are NOT baked in — supplied by the harness at verify time
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/
# [IMPORTANT] Delete the bug diffs from the agent-visible dir so the agent can't read
# the answer (the reverse of a bug patch is the fix), and drop the authoring-only
# asset manifest, which describes the screenshot's defect in prose the task must not
# leak to the agent (the image itself stays — it's the one thing meant to be read).
RUN rm -rf /app/.harbor_assets/bugs /app/.harbor_assets/ASSET_MANIFEST.json

CMD ["bash"]
