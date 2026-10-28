FROM node:22-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    python3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Build-only helper (not left in /app). Renames sheet-rule helper + drops
# telltale specs so classic filename greps miss; solve.sh reverses the rename
# before applying upstream fix.patch (git apply --check on base_commit holds).
COPY obfuscate_harbor.py /tmp/obfuscate_harbor.py

RUN git clone https://github.com/fabricjs/fabric.js /app \
 && git -C /app checkout d8c58db563c73f3887e70bdc59431acb6c87ba90 \
 && rm -f /app/src/parser/getCSSRules.spec.ts /app/src/parser/parser.spec.ts \
 && python3 /tmp/obfuscate_harbor.py \
 && rm -f /tmp/obfuscate_harbor.py \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Install dependencies
RUN npm ci

# Visual evidence, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied — the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
