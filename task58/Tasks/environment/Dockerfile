FROM node:22-bookworm

# System build deps: git (for repo init/apply), ca-certificates/curl for the clone.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone the SR5-FoundryVTT system at the base commit, then STRIP .git so the
# agent cannot inspect the fix PR or future history (anti-cheat). Re-init a
# single base commit with an immutable tag so `git apply` still works and the
# verifier can reset test files.
RUN git clone https://github.com/SR5-FoundryVTT/SR5-FoundryVTT /app \
 && git -C /app checkout 074121360c08d8ee9288d1c3ac9ce61bdad8545b \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Install npm dependencies (includes the pinned TypeScript compiler used by the
# verifier's standalone test harness). --ignore-scripts skips postinstall hooks
# that may need a display or native build tooling neither the agent nor the
# verifier need here.
RUN npm install --ignore-scripts

# Visual evidence, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied into the image —
# the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
