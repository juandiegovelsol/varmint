FROM node:22-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    curl \
    chromium \
    chromium-driver \
    xvfb \
    fonts-liberation \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    lsb-release \
    wget \
    xdg-utils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone, pin to the base commit, then STRIP .git so the agent cannot inspect the fix PR /
# future history (anti-cheat). Re-init a single base commit + immutable tag so the verifier
# can reset test files; git apply still works without upstream history.
RUN git clone https://github.com/IvarK/AntimatterDimensionsSourceCode /app \
 && git -C /app checkout cc08c9f84f3ea8ffb2f56d8afa7a909d0a78b108 \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install the repo's own dependencies so verify time doesn't wait on the network.
# This repo's package-lock.json was generated with an older npm; npm ci in npm 10+ is
# stricter about lock-file/package.json drift (webpack-sources version mismatch).
# We use `npm install --legacy-peer-deps` to tolerate the drift while still pinning
# all direct deps.  The --prefer-offline cache shim is kept for faster rebuilds.
RUN npm install --legacy-peer-deps 2>/dev/null || npm install --legacy-peer-deps --prefer-offline

# Install Playwright and its Chromium browser for the synthetic visual tests.
# We pin to a known stable release that ships with Chromium support.
# PLAYWRIGHT_BROWSERS_PATH=0 installs browser alongside the package.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
RUN npm install --save-dev playwright@1.44.1 \
 && (npx playwright install chromium --with-deps || npx playwright install chromium) \
 && node -e "const{chromium}=require('playwright');const p=chromium.executablePath();require('fs').accessSync(p);console.log('playwright chromium ok:',p)"

# Test-only runtime deps, baked in at BUILD time (this stage has network;
# [verifier] in task.toml runs with network_mode="no-network").
#
# pngjs@6 decodes the clipped PNG screenshot in tests/scrollbar-corner-test.js.
# It is installed into an isolated prefix rather than /app/node_modules so that
# it survives anything the agent does to the repo tree (rm -rf node_modules,
# npm install, npm prune).  test.sh puts this on NODE_PATH.
ENV TEST_DEPS_DIR=/opt/test-deps
RUN mkdir -p "$TEST_DEPS_DIR" \
 && npm install --prefix "$TEST_DEPS_DIR" --no-audit --no-fund pngjs@6.0.0 \
 && NODE_PATH="$TEST_DEPS_DIR/node_modules" node -e "require('pngjs');console.log('pngjs ok')"

# Visual evidence, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied into the image —
# the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
