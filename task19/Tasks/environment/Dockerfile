FROM node:22-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates chromium chromium-driver fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone, pin to base commit, strip .git (anti-cheat: agent cannot inspect fix PR / future history).
# Re-init a single-commit repo so git apply works and verifier can reset test files.
RUN git clone https://github.com/recharts/recharts /app \
 && git -C /app checkout 92064250666c820551c3e3a52a5b852aca662066 \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install dependencies so verify time does not wait on the network.
# No pnpm-lock.yaml exists at this base commit, so --frozen-lockfile has nothing to
# freeze against; --no-frozen-lockfile is required here, not just permissive.
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate \
 && pnpm install --no-frozen-lockfile

# Anti-cheat: a dev dependency transitively installs a PUBLISHED build of this same
# library, from a release that is newer than the base commit and therefore already
# contains the corrected geometry code. Left in place, the answer is sitting in
# node_modules and can simply be copied out, so remove every such copy plus the pnpm
# content-addressed store that also holds it (node_modules hardlinks keep whatever
# remains alive). Nothing at test time resolves through these: vitest.config.mts
# aliases the package name to /app/src.
RUN set -eu; \
    rm -rf /app/node_modules/.pnpm/recharts@*; \
    rm -rf /app/node_modules/recharts; \
    rm -rf /app/www/node_modules/.pnpm/recharts@* /app/www/node_modules/recharts; \
    find /app -path '*/node_modules/*' -name 'recharts' \( -type d -o -type l \) -prune -exec rm -rf {} + || true; \
    rm -rf /app/dist /app/build; \
    rm -rf /root/.cache/pnpm /root/.local/share/pnpm/store; \
    if grep -rlsq -e 'effectiveMinAngle' -e 'needsMinAngleAdjustment' /app; then \
      echo "ANTI-CHEAT FAILURE: a build containing the fix is still reachable under /app" >&2; \
      grep -rls -e 'effectiveMinAngle' -e 'needsMinAngleAdjustment' /app >&2; \
      exit 1; \
    fi

# Visual evidence - readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are supplied by the harness at verify time - NOT baked in.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
