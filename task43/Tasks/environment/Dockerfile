FROM node:22-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates chromium chromium-driver fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone, pin to base commit, strip .git (anti-cheat: agent cannot inspect fix PR / future history).
# Re-init a single-commit repo so git apply works and verifier can reset test files.
RUN git clone https://github.com/recharts/recharts /app \
 && git -C /app checkout bf0460641dd33939e5b4b22feecdc629cc1407b6 \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install dependencies so verify time does not wait on the network.
# npm ci, not pnpm: this repo is an npm workspaces project and ships package-lock.json at the base
# commit. pnpm cannot read that lockfile, so `pnpm install --no-frozen-lockfile` re-resolved every
# dependency from its semver range on each build - vitest, jsdom and @testing-library/react included -
# leaving the environment unpinned and the runs only accidentally reproducible. `npm ci` installs the
# exact tree the lockfile records and fails loudly if the lockfile and package.json ever disagree.
RUN npm ci

# Visual evidence — readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are supplied by the harness at verify time — NOT baked in.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
