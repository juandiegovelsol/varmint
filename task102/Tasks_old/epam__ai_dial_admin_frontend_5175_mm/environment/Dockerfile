FROM node:24.22.2-alpine3.24

# bash/git/python3 are needed to apply patches and run test.sh at container-run time (no network then).
# ca-certificates lets apk/git/npm talk https (this sandbox only has https egress).
RUN apk add --no-cache bash git python3 ca-certificates

WORKDIR /app

# Clone the repo and check out the exact base commit (network needed only at build time).
RUN git clone https://github.com/epam/ai-dial-admin-frontend.git /app \
 && git -C /app -c advice.detachedHead=false checkout 5e1a82bfdf99bde855f4931d795d6e01cdb127d2

# Install every dependency the tests need (grading installs nothing). vitest's built-in junit
# reporter is used at test time (--reporter=junit), no extra reporter package required.
RUN npm ci

ENV CI=true

# Injected bugs: copied to a temp path, applied BEFORE the timestamp step and the harbor_base snapshot,
# and deleted in the same RUN so no patch reaches the final image.
COPY bugs/ /tmp/bugs/
RUN set -e; for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done; \
    rm -rf /tmp/bugs

# One timestamp for every file: which file changed last must not point at the bug.
RUN find /app -mindepth 1 -exec touch -h -t 202301010000 {} +

# Drop upstream history and record the task base; the fix commit must stay unreachable from here.
RUN rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Visual evidence for the agent only (never the whole assets/ folder, never tests/ or solution/).
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/current.png assets/mockup.png /app/.harbor_assets/

CMD ["bash"]
