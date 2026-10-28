FROM node:18-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    python3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone the repository, pin to the base commit, then strip .git so the agent
# cannot inspect the fix PR or future history (anti-cheat). Re-init a single
# base commit with an immutable tag so the verifier can reset test files and
# git apply still works without upstream history.
RUN git clone https://github.com/IvarK/AntimatterDimensionsSourceCode /app \
 && git -C /app checkout b07bff4ec0ded834890fce6cff4af8555b9f68a9 \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install repo dependencies so verify time doesn't wait on the network.
# Use npm ci for reproducible install from the lockfile.
RUN npm ci --prefer-offline 2>/dev/null || npm install --legacy-peer-deps

# Visual evidence, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied into the image —
# the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
