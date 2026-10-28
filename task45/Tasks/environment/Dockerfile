FROM node:22-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    python3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone, pin to the base commit, then strip .git (anti-cheat).
# Re-init a single base commit + immutable tag so the verifier
# can reset test files; git apply still works without upstream history.
RUN git clone https://github.com/fabricjs/fabric.js /app \
 && git -C /app checkout 356c25c27dd30d03f6f8ac2c9df60e654824eda8 \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Install dependencies using npm ci (reproducible from package-lock.json)
RUN npm ci

# Visual evidence, readable by the agent at /app/.harbor_assets/.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/*.png /app/.harbor_assets/

CMD ["bash"]
