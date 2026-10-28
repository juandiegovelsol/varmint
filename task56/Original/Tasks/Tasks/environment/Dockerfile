FROM node:24-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ENV CI=true

WORKDIR /app

# Clone, pin to the base commit, then STRIP .git so the agent cannot inspect the fix PR
# or future history (anti-cheat). Re-init a single base commit + immutable tag so the
# verifier can reset test files; git apply still works without upstream history.
RUN git clone --depth 500 https://github.com/carbon-design-system/carbon /app \
 && git -C /app checkout 1a9ccca45f0671c874a9cf83d244ab81f7adc7ab \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

RUN corepack enable && yarn install --immutable

# Bake the FULL build (web-components + its workspace deps) at base-commit state. Verify
# time only needs to rebuild @carbon/web-components itself (fast) since the fix/test
# patches never touch other workspace packages.
RUN yarn lerna run build --scope='@carbon/web-components' --include-dependencies

RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
