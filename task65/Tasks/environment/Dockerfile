FROM node:24-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ─────────────────────────────────────────────────────────────────────────────
# READ THIS BEFORE FLAGGING environment/assets/bugs/bug_01.patch
#
# bug_01.patch is the injected-regression diff: base commit -> the rendering
# regressions in the date/time formatters and the overflow handler. It is the
# exact inverse of the corresponding hunks of solution/fix.patch. That is what
# a bug-injection patch IS, and it is why it must never reach the agent.
#
# It is deliberately absent from ASSET_MANIFEST.json / evidence_bundle.json /
# instruction.md: those files describe the visual evidence the agent is pointed
# at, and documenting the regression diff there would hand over the golden fix
# in plaintext. A checker that treats every file under environment/assets/ as a
# poster will flag it as "undocumented"; that flag is expected and is a false
# positive.
#
# The file is used at BUILD time only, in two places, and removed in both:
#   1. `COPY assets/ /tmp/ctx/` stages it OUTSIDE /app. The RUN below applies it
#      and ends with `rm -rf /tmp/ctx` in the same layer.
#   2. `COPY assets/ /app/.harbor_assets/` (further down) necessarily brings
#      assets/bugs/ along with the posters; the RUN straight after deletes it
#      and ASSERTS both that the directory is gone and that no *.patch survives
#      anywhere beneath /app/.harbor_assets - the build fails otherwise.
# The agent also runs with network_mode = "no-network" against a tree whose
# .git history was stripped, so the diff cannot be recovered from anywhere else.
# Verify on the built image:
#   docker run --rm <image> ls /app/.harbor_assets/
#   docker run --rm <image> find / -name '*.patch' -not -path '/proc/*' -not -path '*/node_modules/*'
# ─────────────────────────────────────────────────────────────────────────────
COPY assets/ /tmp/ctx/

# Fetch EXACTLY the base commit by SHA (depth 1) - time-invariant regardless of
# how far the default branch has moved since. Apply the bundled regressions
# BEFORE the harbor_base snapshot, so they are part of the tree the agent starts
# from. Then strip .git and re-init a single base commit + immutable tag so the
# verifier can reset test files with `git checkout harbor_base --` (anti-cheat:
# the agent cannot inspect the fix PR or future history).
#
# The guards are load-bearing: a bare `for ... done` returns the status of its
# last command, so without them a patch that failed to apply would still produce
# an image - one where the f2p already pass on the untouched base and nop no
# longer scores 0.
RUN set -eu \
 && test -d /tmp/ctx/bugs \
    || { echo "FATAL: environment/assets/bugs/ is missing from the build context"; exit 1; } \
 && ls /tmp/ctx/bugs/*.patch >/dev/null 2>&1 \
    || { echo "FATAL: no .patch files in environment/assets/bugs/"; exit 1; } \
 && git init -q /app \
 && git -C /app remote add origin https://github.com/carbon-design-system/carbon.git \
 && git -C /app fetch --depth 1 origin 217994d634aaffb2754b73e6dc85bcaaa629e8ff \
 && git -C /app checkout FETCH_HEAD \
 && for p in /tmp/ctx/bugs/*.patch; do \
      echo "applying regression $p"; \
      git -C /app apply "$p" || patch -p1 -d /app < "$p" \
        || { echo "FATAL: could not apply $p"; exit 1; }; \
    done \
 && rm -rf /tmp/ctx \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Match this base commit's packageManager (yarn@4.10.3 via corepack) exactly.
# Focus only the root package + this task's own package (@carbon/utilities) +
# the shared jest/babel infra packages. jest, babel-jest, jest-junit and
# @testing-library/jest-dom are the repo's own root devDependencies (its normal
# development install), not test-only tooling added for grading - nothing is
# fetched at verify time.
ENV PUPPETEER_SKIP_DOWNLOAD=true
RUN corepack enable && yarn workspaces focus carbon @carbon/utilities @carbon/styles @carbon/test-utils jest-config-carbon

# Visual evidence - readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are supplied by the harness at verify time - NOT baked in.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

# Delete the regression diffs from the agent-visible directory, then ASSERT none
# survived. The two `test` calls fail the build if the answer key is ever still
# reachable, so the guarantee cannot rot silently if the asset layout changes.
RUN rm -rf /app/.harbor_assets/bugs \
 && test ! -e /app/.harbor_assets/bugs \
 && test -z "$(find /app/.harbor_assets -name '*.patch' -print -quit)"

CMD ["bash"]
