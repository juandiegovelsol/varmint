FROM node:18-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# [IMPORTANT] Bug patches are staged in a TEMP path, never under /app, so they
# can be baked into the base snapshot without ever reaching the agent-visible
# tree. They are deleted again inside the same RUN layer that applies them.
COPY assets/bugs/ /tmp/bugs/

# Clone the repository and pin to the base commit. Every patch in /tmp/bugs is
# applied BEFORE the snapshot below, so each defect is part of harbor_base - the
# exact state the model starts from. `|| exit 1` is load-bearing: without it the
# for loop's status is only that of its last iteration, so a patch that stops
# applying would be skipped silently and ship a task missing one of its bugs.
# Then strip .git so the agent cannot inspect the fix PR or future history
# (anti-cheat), and re-init a single base commit tagged harbor_base so the
# verifier can reset test files and git apply still works without upstream history.
RUN git clone https://github.com/IvarK/AntimatterDimensionsSourceCode /app \
 && git -C /app checkout 5b8d4296e697f3ea83a9fea5aa84eb5e4f8d4385 \
 && for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || exit 1; done \
 && rm -rf /tmp/bugs \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install the repo's dependencies so verify time does not wait on the network.
RUN npm install --prefix /app

# Visual evidence readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied into the image —
# the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

# [IMPORTANT] Delete the bug diffs from the agent-visible dir: the reverse of a
# bug patch is the fix, so the model must never be able to read them.
RUN rm -rf /app/.harbor_assets/bugs

CMD ["bash"]
