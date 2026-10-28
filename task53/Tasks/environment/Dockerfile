FROM node:22-bookworm

# System build deps: git (for repo init/apply), patch (fallback for the bug-patch apply
# loop below), ca-certificates/curl for the clone.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    patch \
    ca-certificates \
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# [IMPORTANT] Copy the injected bug diffs to a TEMP path (never into /app, and never under
# environment/assets/ -- that directory is shipped verbatim to the agent as visual evidence,
# and these patches are the reverse of the answer) so they can be folded into the base
# snapshot below without ever reaching the agent-visible tree.
COPY bugs/ /tmp/bugs/

# Clone the SR5-FoundryVTT system at the base commit, then STRIP .git so the
# agent cannot inspect the fix PR or future history (anti-cheat). Apply every bug
# patch, then re-init a single base commit with an immutable tag so `git apply`
# still works and the verifier can reset test files.
RUN git clone https://github.com/SR5-FoundryVTT/SR5-FoundryVTT /app \
 && git -C /app checkout 86fc0f8f31ad9b406d0947faa3f0d9e0c6b90f07 \
 && rm -rf /app/.git \
 # [IMPORTANT] Apply every bug patch BEFORE the snapshot below, so the defects
 # become part of harbor_base (the exact state the model starts from).
 && for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done \
 && rm -rf /tmp/bugs \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 # [IMPORTANT] harbor_base = base commit + all bug patches. Must come AFTER the
 # apply loop; the verifier resets to this tag.
 && git -C /app tag harbor_base

# Install npm dependencies (includes the pinned TypeScript compiler used by the
# verifier's standalone test harness). --ignore-scripts skips postinstall hooks
# that may need a display or native build tooling neither the agent nor the
# verifier need here.
RUN npm install --ignore-scripts

# Handlebars is a verifier-only dependency (renders the candidate's own templates at
# verify time) — it is installed by tests/test.sh, not baked in here, so it stays
# scoped to the verify step like every other test-only dependency.

# Visual evidence, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied into the image —
# the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
