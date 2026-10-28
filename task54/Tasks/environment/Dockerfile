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

# curl is REQUIRED and is not optional tooling: harbor installs the agent CLI *into this image*
# over `curl -fsSL https://downloads.claude.ai/... | bash` on a glibc base, so without it every
# agent trial dies at startup with `curl: command not found` (exit 127). node:24-bookworm-slim
# ships neither curl nor wget (verified: `command -v curl wget` is empty in the bare base), and
# the oracle/nop controls install no agent -- so they both score normally on an image no agent
# can actually run in, and the defect would first surface on a paid trial.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    python3 \
 && rm -rf /var/lib/apt/lists/*

# The repo pins yarn via `yarnPath: .yarn/releases/yarn-4.14.1.cjs` + `packageManager: yarn@4.14.1`.
# corepack is what turns the `yarn` shim into that pinned release. Node 24 still ships corepack;
# the fallback keeps the recipe alive on images where it was dropped.
RUN (corepack enable || (npm install -g corepack@latest && corepack enable)) \
 && corepack --version

WORKDIR /app

# Injected-defect diffs go to a TEMP path, never into /app. They are applied into the base snapshot
# below and the copy under /app/.harbor_assets is deleted further down, because the REVERSE of a bug
# patch is a fix -- leaving one readable in the agent-visible tree would hand over the answer.
COPY assets/bugs/ /tmp/bugs/

# Shallow-fetch just the base commit (a full clone of this monorepo is >1 GB of history), pin to
# it, then STRIP .git so the agent cannot read the fix PR / future history (anti-cheat). Re-init a
# single base commit + an immutable `harbor_base` tag so the verifier can restore the test files
# it owns; `git apply` still works without upstream history.
RUN git init -q /app \
 && cd /app \
 && git remote add origin https://github.com/trezor/trezor-suite.git \
 && git fetch --depth 1 origin a79489da9278f6b4b1a76c380945f1c34a7a18e3 \
 && git checkout a79489da9278f6b4b1a76c380945f1c34a7a18e3 \
 && rm -rf /app/.git \
 && git -C /app init -q \
 # Apply every injected defect BEFORE the commit + tag below, so the defects are part of
 # harbor_base -- the exact state the agent starts from and the verifier resets test files to.
 && for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Bake ALL deps at BUILD time — the build has internet, the RUN (solve + verify) does NOT
# (task.toml [agent]/[verifier] network_mode = "no-network").
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

# The signed message-system config is a GENERATED artefact: `sign-config` signs
# suite-common/message-system/config with the repo's DEVELOPMENT key (no network, no secret, ~4 s)
# and writes suite-common/message-system/files/config.v1.ts. That file is gitignored, is produced
# by no install step, and `suite-common/message-system/src/messageSystemThunks.ts` imports it
# unconditionally — so WITHOUT this layer every jest suite in packages/suite dies at import time
# with "Cannot find module '../files/config.v1'", including the repo's own tests. It is
# force-added to the base commit (a second commit, `harbor_base` moved onto it) so that
# tests/test.sh can restore it if the agent deletes it; no future history is exposed.
RUN cd /app \
 && yarn workspace @suite-common/message-system sign-config \
 && git -C /app -c user.email=h@l -c user.name=h add -f suite-common/message-system/files \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m "generated message-system config" \
 && git -C /app tag -f harbor_base

# Test-only tooling that the repo does NOT declare: jest 29 has no JUnit reporter of its own and
# the verifier is offline, so jest-junit is baked into an ISOLATED prefix. Keeping it out of
# /app/node_modules is deliberate — it leaves `yarn.lock` / `--immutable` intact and keeps the
# harness invisible to the agent. tests/test.sh loads it by absolute path:
#   --reporters=/opt/test-deps/node_modules/jest-junit
RUN mkdir -p /opt/test-deps \
 && cd /opt/test-deps \
 && npm init -y >/dev/null \
 && npm install --no-audit --no-fund --loglevel=error jest-junit@16.0.0 \
 && npm cache clean --force >/dev/null 2>&1 || true

# Visual evidence, readable by the agent at /app/.harbor_assets/. tests/ and solution/ are
# intentionally NOT copied into the image — the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/
# Anti-cheat: drop the injected-defect diffs from the agent-visible tree. `rm` is sufficient -- the
# agent sees only the final merged filesystem, never the earlier layer that still holds them.
#
# BOTH copies must go. /tmp/bugs is the staging path the COPY near the top of this file writes to,
# and the apply loop does not consume it -- verified by `docker run` on the shipped image, which
# still listed /tmp/bugs/bug_01.patch, root-readable (there is no USER directive, so the agent is
# root). The REVERSE of a bug patch is the fix, so leaving that file behind hands over the injected
# defect verbatim -- the one gate this task's difficulty rests on -- to any agent that runs `ls /tmp`
# or `find / -name '*.patch'`. Deleting here rather than in the apply RUN is intentional: editing
# that early layer would invalidate the yarn install below it and force a full rebuild, and it would
# buy nothing, since layer history is not reachable from inside a running container.
RUN rm -rf /app/.harbor_assets/bugs /tmp/bugs

CMD ["bash"]
