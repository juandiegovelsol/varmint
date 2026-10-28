FROM node:22-bookworm

# Build tools needed by the 'canvas' npm package (node-gyp / Cairo bindings)
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      python3 \
      libcairo2-dev \
      libpango1.0-dev \
      libjpeg-dev \
      libgif-dev \
      librsvg2-dev \
      pkg-config \
      git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone, pin to the base commit, then STRIP .git so the agent cannot inspect
# the fix PR or future history (anti-cheat). Re-init a single base commit with
# an immutable tag so the verifier can reset test files; git apply still works.
RUN git clone https://github.com/vega/vega /app \
 && git -C /app checkout 15c5b1f0492e928d5b799de17c187323fed652de \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install all workspace dependencies (monorepo root install) so verify
# time does not wait on the network. This also compiles the canvas native addon.
RUN DISABLE_POSTINSTALL_SCRIPT=1 npm ci --prefer-offline || DISABLE_POSTINSTALL_SCRIPT=1 npm install

# Build all workspace packages so test-time ESM imports resolve correctly.
RUN npm run build --workspaces --if-present 2>&1 | tail -10 || true

# Visual evidence, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied — the harness supplies them.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
