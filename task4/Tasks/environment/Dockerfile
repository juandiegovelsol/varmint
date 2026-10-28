FROM node:22.23.2-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone, pin to base commit, strip .git (anti-cheat: agent cannot inspect fix PR / future history).
# Re-init a single-commit repo so git apply works and verifier can reset test files.
RUN git clone https://github.com/recharts/recharts /app \
 && git -C /app checkout 1552fe08a39632ebff75882b0f765c239809fbba \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install dependencies so verify time does not wait on the network.
# Pinned: the committed package-lock.json, so the dependency tree is
# byte-identical on every build and the reward cannot drift with upstream releases.
# pnpm is kept available (via corepack) because tests/test.sh invokes `pnpm vitest run`
# to execute the locally installed vitest binary; it is not used to install deps.
RUN npm ci \
 && corepack enable && corepack prepare pnpm@9.15.9 --activate

# Visual evidence — readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are supplied by the harness at verify time — NOT baked in.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
