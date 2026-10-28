FROM node:22-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates curl python3 build-essential \
 && rm -rf /var/lib/apt/lists/*

# Enable corepack for Yarn 4 Berry (tldraw uses yarn4 + workspaces)
RUN corepack enable

WORKDIR /app

# Clone, pin to base commit, strip .git (anti-cheat: agent cannot see fix PR history).
# Re-init a single-commit repo tagged harbor_base so the verifier can reset test files.
RUN git clone https://github.com/tldraw/tldraw /app \
 && git -C /app checkout 56c3bc3fbec3bdf48e314732a51dd22fcfdd53a5 \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install workspace dependencies (pinned lockfile)
RUN yarn install --immutable 2>&1 | tail -10 || yarn install 2>&1 | tail -10

# Visual evidence readable by the agent at /app/.harbor_assets/
# tests/ and solution/ are NOT baked in — supplied by the harness at verify time
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
