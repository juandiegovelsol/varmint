FROM node:24-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ENV CI=true

WORKDIR /app

# [IMPORTANT] Bug patches live outside environment/assets/ (build-only input, never
# agent-visible evidence) and are staged in a TEMP path so they can be baked into the
# base snapshot without ever reaching /app.
COPY bugs/ /tmp/bugs/

# Clone, pin to the base commit, then STRIP .git so the agent cannot inspect the fix PR
# or future history (anti-cheat).
#
# [IMPORTANT] Every bug patch is applied BEFORE the snapshot below, so the defects are
# part of harbor_base -- the exact state the agent starts from. A patch that fails to
# apply fails the build instead of silently producing a task with no bug in it.
#
# [IMPORTANT] harbor_base = base commit + all bug patches, re-inited as a single commit
# so the verifier can reset test files; git apply still works without upstream history.
RUN git init -q \
 && git remote add origin https://github.com/carbon-design-system/carbon \
 && git fetch --depth 1 origin 1a9ccca45f0671c874a9cf83d244ab81f7adc7ab \
 && git checkout 1a9ccca45f0671c874a9cf83d244ab81f7adc7ab \
 && rm -rf .git \
 && for p in /tmp/bugs/*.patch; do git apply "$p" || exit 1; done \
 && rm -rf /tmp/bugs \
 && git init -q \
 && git -c user.email=h@l -c user.name=h add -A \
 && git -c user.email=h@l -c user.name=h commit -q -m base \
 && git tag harbor_base

RUN corepack enable && yarn install --immutable

# Bake the FULL build (web-components + its workspace deps) at base-commit state. Verify
# time only needs to rebuild @carbon/web-components itself (fast) since the fix/test
# patches never touch other workspace packages.
RUN yarn lerna run build --scope='@carbon/web-components' --include-dependencies

RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
