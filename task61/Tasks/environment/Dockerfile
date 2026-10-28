FROM node:22-bookworm

# System build deps: git (for repo init/apply), ca-certificates/curl for the clone.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# [IMPORTANT] Copy the hardening bug patches to a TEMP path (not under /app or
# /app/.harbor_assets) so they can be applied into the base snapshot below and
# never reach the agent-visible tree -- this Dockerfile only ever COPYs the
# single screenshot file into /app/.harbor_assets (see below), never this
# directory, so the diffs are unreadable even from the final image's layers.
# Kept under environment/bugs/ (not environment/assets/), which is layout for
# defect patches, not visual evidence -- it is not subject to the
# ASSET_MANIFEST.json/evidence_bundle.json documentation that poster images need.
COPY bugs/ /tmp/bugs/

# Clone the SR5-FoundryVTT system at the base commit, then STRIP .git so the
# agent cannot inspect the fix PR or future history (anti-cheat). Re-init a
# single base commit with an immutable tag so `git apply` still works and the
# verifier can reset test files.
RUN git clone https://github.com/SR5-FoundryVTT/SR5-FoundryVTT /app \
 && git -C /app checkout 7d19e38d49e38d9851c4b0b25d8240c448a1c24b \
 && rm -rf /app/.git \
 # [IMPORTANT] Apply every hardening bug patch BEFORE the snapshot below, so
 # each defect becomes part of harbor_base -- the exact state the agent starts
 # from, alongside the original AP-field bug already present in this commit.
 && for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 # [IMPORTANT] harbor_base = base commit + all bug patches. Must come AFTER
 # the apply loop above; the verifier resets test-patch paths to this tag.
 && git -C /app tag harbor_base

# Install npm dependencies (includes the pinned TypeScript compiler used by the
# verifier's standalone test harness). --ignore-scripts skips postinstall hooks
# that may need a display or native build tooling neither the agent nor the
# verifier need here.
RUN npm install --ignore-scripts

# Visual evidence, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied into the image --
# the harness supplies them at verify time. Only the poster image itself is
# copied (not the whole assets/ directory) so ASSET_MANIFEST.json -- which
# names the real task_id / repo / issue number -- never lands in the
# agent-visible container filesystem (anti-cheat, same intent as the .git
# strip above).
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/bug_screenshot_1.png /app/.harbor_assets/bug_screenshot_1.png

CMD ["bash"]
