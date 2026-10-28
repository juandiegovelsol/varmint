# ---------------------------------------------------------------------------------------------
# trezor/trezor-suite — reusable build recipe (DONOR).
#
# Retargeting to another base commit is a pure string substitution of the 40-hex SHA below
# (tools/harvest_m2.py::retarget_dockerfile does exactly that); NOTHING else in this file is
# task-specific. It installs the WHOLE yarn workspace set, so it works no matter which of the
# ~100 workspaces (packages/*, suite/*, suite-common/*, suite-native/*, networks/*/*) the fix
# under test lives in.
# ---------------------------------------------------------------------------------------------

# Node 24: the repo pins `"engines": {"node": "24"}` in the root package.json and `.nvmrc` says
# 24.17.0 at this base commit. Do NOT downgrade — several transitive deps (and yarn 4.14's own
# `npmMinimalAgeGate` machinery) require >= 20, and a too-old Node makes `yarn install` hard-fail
# with no reward at all. bookworm-slim keeps the layer small; python3 is needed by the verifier
# (verifier.py / judge.py), git by the harness reset step.
FROM node:24-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    python3 \
 && rm -rf /var/lib/apt/lists/*

# The repo pins yarn via `yarnPath: .yarn/releases/yarn-4.14.1.cjs` + `packageManager: yarn@4.14.1`.
# corepack is what turns the `yarn` shim into that pinned release. Node 24 still ships corepack;
# the fallback keeps the recipe alive on images where it was dropped.
RUN (corepack enable || (npm install -g corepack@latest && corepack enable)) \
 && corepack --version

WORKDIR /app

# Shallow-fetch just the base commit (a full clone of this monorepo is >1 GB of history), pin to
# it, then STRIP .git so the agent cannot read the fix PR / future history (anti-cheat). Re-init a
# single base commit + an immutable `harbor_base` tag so the verifier can restore the test files
# it owns; `git apply` still works without upstream history.
RUN git init -q /app \
 && cd /app \
 && git remote add origin https://github.com/trezor/trezor-suite.git \
 && git fetch --depth 1 origin 7156f2b3ebb3f7752ee21a831e94b3451a1c5584 \
 && git checkout 7156f2b3ebb3f7752ee21a831e94b3451a1c5584 -q \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Bake ALL deps at BUILD time — the build has internet, the agent's solve RUN does NOT
# (task.toml [agent] network_mode = "no-network"). The verifier RUN is granted public network
# (task.toml [verifier] network_mode = "public"), but deps are pre-baked here anyway so grading
# doesn't depend on the npm registry being reachable, and stays fast.
#
#   * `--immutable`      : install exactly what yarn.lock says; fails loudly on drift.
#   * `--mode=skip-build`: the root package.json marks ~19 packages `dependenciesMeta.built=true`
#                          (playwright browser bundles, detox, react-native-skia, better-sqlite3,
#                          usb, sharp, …). Those build steps download hundreds of MB of browser
#                          binaries and compile native toolkits that NO jest unit suite in this
#                          repo needs; skipping them cuts the build from ~30 min to a few minutes
#                          and avoids a class of flaky network fetches. @swc/core and esbuild —
#                          the two that jest actually touches — ship prebuilt per-platform
#                          optional dependencies (@swc/core-linux-*), so they still work.
#   * every workspace links via `workspace:*` and every @suite-common / @trezor package resolves
#     its `main` to `src/index`, so jest runs straight off TypeScript sources: there is NO
#     per-workspace build step to run here.
# A scratch cache folder is removed inside the same layer so the download cache never ships.
ENV YARN_ENABLE_GLOBAL_CACHE=false \
    YARN_CACHE_FOLDER=/tmp/yarn-cache \
    YARN_NPM_MINIMAL_AGE_GATE=0
RUN cd /app \
 && yarn install --immutable --mode=skip-build \
 && rm -rf /tmp/yarn-cache /root/.cache/node/corepack

# jest-junit (the JUnit reporter jest itself doesn't ship) is intentionally NOT installed here.
# It is test-only tooling needed solely for grading, so it is installed by tests/test.sh at
# verify time instead — nothing test-only is baked into the agent-visible image.

# Visual evidence, readable by the agent at /app/.harbor_assets/. tests/ and solution/ are
# intentionally NOT copied into the image — the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
