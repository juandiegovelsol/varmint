FROM node:22-bookworm

# System deps: git for the anti-cheat re-init below, python3/build-essential for any native npm
# deps, and Chromium + the shared libs it needs to run headless (this task's spec drives the
# real VoxelInspectorViewModel class through Cesium's own Karma/Jasmine harness -- it needs a
# real browser runtime, even though (unlike this repo's other karma tasks) it never opens a
# WebGL context: the class under test only ever calls `scene.requestRender()` on its `scene`
# argument, so a lightweight mock scene suffices and no createScene()/canvas is involved).
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    python3 \
    build-essential \
    ca-certificates \
    chromium \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxshmfence1 \
    xdg-utils \
 && rm -rf /var/lib/apt/lists/*

# karma-chrome-launcher (used by this repo's `gulp test` / `npm test`) resolves the browser via
# CHROME_BIN first, falling back to google-chrome/google-chrome-stable on PATH -- neither exists
# on Debian, so point it at the Chromium package installed above. --no-sandbox is required to
# run Chrome as root inside a container.
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMIUM_BIN=/usr/bin/chromium
ENV CHROME_FLAGS="--no-sandbox --disable-dev-shm-usage"
# Skip the repo's own `npm install` step re-downloading Playwright's browser fleet (Chrome for
# Testing/Firefox/WebKit/ffmpeg) via its `prepare` lifecycle script -- none of Playwright's
# browsers are used by the Karma/Jasmine spec suite this task verifies against; only Chromium
# (installed above) is needed. The repo's "prepare" script is `gulp prepare && husky &&
# playwright install --with-deps`; CI=true/HUSKY=0 make husky's own install succeed, but that
# alone is NOT sufficient -- see the zip.js override below for the real trigger of `gulp
# prepare` itself failing outright (which, per this repo's own banked history, is what actually
# matters here: an earlier failure in the `&&` chain aborts before playwright install is even
# reached, so PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD is kept only as defense-in-depth).
ENV CI=true
ENV HUSKY=0
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

WORKDIR /app

# [IMPORTANT] Copy bug patches to a TEMP path (not into /app) so they can be applied into the
# base snapshot below and never reach the agent-visible tree.
COPY assets/bugs/ /tmp/bugs/

# Clone and pin to the base commit (still with real .git/history here, so `npm pkg set` below
# just edits a tracked file in a normal working tree). base_commit is the exact merge-base of
# PR #12522 (confirmed via `gh api repos/CesiumGS/cesium/compare/<base>...<pr-head-sha>`
# returning ahead_by=7, behind_by=0, merge_base_commit=<base> -- matching the PR's own 7 commits
# exactly).
RUN git clone https://github.com/CesiumGS/cesium /app \
 && git -C /app checkout 88bfd9547927bbdcb2cbdfd1950ba8b0d275ff32

# Pin @zip.js/zip.js to the last release whose dist/ output still ships z-worker-pako.js, BEFORE
# the one-and-only `npm install` below. packages/engine declares "^2.7.34" at this base commit
# and no lockfile is committed upstream, so a plain `npm install` resolves the newest matching
# version -- @zip.js/zip.js 2.8.x (confirmed empirically while authoring this task: 2.8.36, the
# version this repo's other tasks pin for THEIR later base commits, does NOT ship
# dist/z-worker-pako.js at all under this "^2.7.34" range's vintage) breaks gulp's `prepare` copy
# step with ENOENT. 2.7.73 (the newest 2.7.x release) still ships the expected dist layout.
# Pinning correctly BEFORE the install that runs life-cycle scripts avoids the ENOENT outright.
RUN npm pkg set "overrides[@zip.js/zip.js]=2.7.73"

# [IMPORTANT] Apply every additional injected bug patch BEFORE the harbor_base snapshot below,
# so each defect becomes part of harbor_base (the exact state the model starts from). These are
# hand-authored regressions layered on top of the real, historical #12521 regression that is
# already present in the base_commit source itself (the cylinder height/angle mislabeling this
# task's issue report describes) -- unlike that one, these four have no upstream commit to pin
# to, so they ship as patches here instead.
RUN for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done

# NOW strip .git so the agent cannot inspect the fix PR / future history (anti-cheat), and
# re-init a single base commit + immutable tag so the verifier can reset test files (git apply
# still works without upstream history). This commit is made AFTER the zip.js override edit and
# the bug-patch apply loop above, so both become part of harbor_base itself, not a stray
# post-tag diff.
RUN rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Bake ALL deps at BUILD time -- build has internet, and the agent (solve) phase is OFFLINE
# (task.toml [agent] network_mode="no-network"), so anything the agent's own work depends on
# must already be here. This repo's own npm workspaces install (engine + widgets); no
# package-lock.json is committed upstream (it is .gitignore'd there), so `npm install` -- not
# `npm ci` -- is the correct, repo-native install command (matches this project's own CI in
# .github/workflows/dev.yml).
RUN npm install --no-audit --no-fund

# karma-junit-reporter (the JUnit reporter tests/test.sh needs -- the repo's own karma.conf.cjs
# only wires up "spec"/"longest") is intentionally NOT installed here: it is a test-only
# dependency, isolated to the verify step in tests/test.sh instead of being baked into the
# agent-visible image build.

# Visual evidence, readable by the agent at /app/.harbor_assets/. tests/ and solution/ are
# intentionally NOT copied into the image -- the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/
# [IMPORTANT] Delete the bug diffs from the agent-visible dir so the model can't read the answer
# (the reverse of a bug patch is the fix).
RUN rm -rf /app/.harbor_assets/bugs

CMD ["bash"]
