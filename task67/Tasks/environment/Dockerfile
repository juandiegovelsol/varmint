FROM debian:bookworm-slim

# Build tools and SDL2 / fheroes2 dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        ca-certificates \
        cmake \
        make \
        g++ \
        libsdl2-dev \
        libsdl2-mixer-dev \
        libsdl2-image-dev \
        libpng-dev \
        zlib1g-dev \
        gettext \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# [IMPORTANT] Copy bug patches to a TEMP path (not into /app) so they can be applied
# into the base snapshot below and never reach the agent-visible tree. These live
# outside assets/ (which is exclusively the documented, agent-visible evidence
# directory) so the patches are never mistaken for shipped evidence.
COPY bugs/ /tmp/bugs/

# Clone fheroes2, pin to the base commit, then strip .git (anti-cheat: the agent
# cannot inspect the fix PR or future history).  Apply the additional injected-bug
# patches (on top of the real historical pre-fix commit) before re-initializing a
# single-commit repo tagged harbor_base, so the defects are part of the exact state
# the model starts from and the verifier can reset test files via `git checkout harbor_base`.
RUN git clone https://github.com/ihhub/fheroes2 /app \
    && git -C /app checkout 8ece9d7007c714b749953ab5cd765a271912b06f \
    && rm -rf /app/.git \
    # [IMPORTANT] Apply every bug patch BEFORE the snapshot below, so the defect
    # becomes part of harbor_base (the exact state the model starts from).
    && for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done \
    && git -C /app init -q \
    && git -C /app -c user.email=h@l -c user.name=h add -A \
    && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
    # [IMPORTANT] harbor_base = base commit + all bug patches. Must come AFTER the
    # apply loop; the verifier resets to this tag.
    && git -C /app tag harbor_base \
    # [IMPORTANT] Delete the temp copy now that the patches are applied. The COPY
    # above still exists in an earlier layer, but the agent only ever sees the
    # final merged filesystem (CMD is bash), so a live shell can no longer find
    # /tmp/bugs -- and with it, the exact before/after values the bugs corrupted.
    && rm -rf /tmp/bugs

WORKDIR /app

# Prepare log directory and the harbor_assets mount point
RUN mkdir -p /logs /app/.harbor_assets

# Visual evidence — readable by the agent at /app/.harbor_assets/. The bug patches
# above live outside this directory (environment/bugs/, not environment/assets/),
# so nothing here needs to be scrubbed before it reaches the agent.
# tests/ and solution/ are intentionally NOT copied into the image;
# the harness supplies them at verify time.
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
