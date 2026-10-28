FROM node:20-bookworm

# Use https apt mirrors (plain HTTP is blocked in this sandbox)
RUN sed -i 's#http://#https://#g' /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null; true

WORKDIR /app

# Check out the exact base commit (git and python3 already ship with node:20-bookworm).
RUN git init -q /app \
 && git -C /app remote add origin https://github.com/ariakit/ariakit.git \
 && git -C /app fetch --depth 1 origin ac992aed50e709b34b064aa005b7b7deb226db48 \
 && git -C /app -c advice.detachedHead=false checkout ac992aed50e709b34b064aa005b7b7deb226db48

# Install every dependency the tests need (vitest ships its own JUnit reporter) at build time.
RUN npm ci --no-audit

# Injected bugs: copied to a temp path, applied BEFORE harbor_base is recorded, then deleted in the
# same layer so the patches (whose reverse is the fix) never reach the agent-visible filesystem.
COPY assets/bugs/ /tmp/bugs/
RUN set -e; for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done; rm -rf /tmp/bugs

# Drop the upstream history and record the task base; the fix commit must be unreachable.
RUN rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Visual evidence for the agent only; never the tests or solution.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/*.png /app/.harbor_assets/
RUN rm -rf /app/.harbor_assets/bugs

CMD ["bash"]
