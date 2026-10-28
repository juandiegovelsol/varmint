FROM node:18-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      git \
      ca-certificates \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone, pin to the base commit, then strip .git so the agent cannot inspect
# the fix PR or future history (anti-cheat). Re-init a single base commit +
# immutable tag so the verifier can reset test files; git apply still works
# without upstream history.
RUN git clone https://github.com/IvarK/AntimatterDimensionsSourceCode /app \
 && git -C /app checkout 0bcc55d2c8cdbf4decfc59e99f889694b52fcb52 \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install the repo's own dependencies so verify time does not wait on the
# network. npm ci honours the package-lock.json exactly.
RUN npm ci --prefer-offline 2>&1 || npm install

# Create workspace directories.
# tests/ and solution/ are intentionally NOT copied into the image — the
# harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets

# Visual evidence, readable by the agent at /app/.harbor_assets/.
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
