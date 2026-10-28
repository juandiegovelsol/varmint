FROM node:22-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN corepack enable && corepack prepare yarn@4.1.0 --activate

WORKDIR /app

# Clone, pin to base commit, then strip .git so the agent cannot inspect fix PR /
# future history (anti-cheat). Re-init a single base commit + immutable tag so the
# verifier can reset test files; git apply still works without upstream history.
RUN git clone https://github.com/radix-ui/primitives /app \
 && git -C /app checkout 53287e0d9df330657297a0d15ec333663cf7ca09 \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install dependencies so verify time doesn't wait on the network.
# This commit uses yarn@4.1.0 (not pnpm) — use the correct package manager.
RUN yarn install --immutable --mode=skip-build

# Visual evidence, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied — the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
