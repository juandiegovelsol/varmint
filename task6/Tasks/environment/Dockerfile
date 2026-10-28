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
RUN git clone https://github.com/fabricjs/fabric.js /app \
 && git -C /app checkout 2721047af4506c5daa56177e95dd5ba65ad446f5 \
 && rm -rf /app/.git

# Scrub repo breadcrumbs from package metadata BEFORE the baseline commit, so that
# `git diff harbor_base` stays empty on an untouched checkout and cannot replay the scrub.
RUN node -e "const fs=require('fs'); const p=JSON.parse(fs.readFileSync('package.json','utf8')); delete p.repository; delete p.homepage; delete p.bugs; fs.writeFileSync('package.json', JSON.stringify(p,null,2)+'\n');"

RUN git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Install dependencies using npm ci (reproducible from package-lock.json)
RUN npm ci

# Pre-install the Claude Code CLI while the real npm registry is still
# reachable. Harbor's agent-setup step checks `command -v claude` first and
# skips its own (curl-based) bootstrap when it's already present, so this
# keeps the runtime network lockdown below fully intact.
RUN npm install -g @anthropic-ai/claude-code

# Anti-cheat: block GitHub/npm reads if the agent's network is still open.
#
# Each measure is its own RUN on purpose. The previous version was a single `&&`
# chain ending in `|| true`, so when its first step failed every later step was
# skipped and the whole block silently did nothing.
#
# /etc/hosts is deliberately NOT used: Docker replaces that file at container
# start, so any build-time edit is discarded and blocks nothing at run time.

# 1. git must not reach a remote. Everything the harness does with git
#    (checkout harbor_base, apply, diff) is local, so dropping the HTTP remote
#    helpers and forbidding the protocols costs the task nothing.
RUN rm -f /usr/lib/git-core/git-remote-http /usr/lib/git-core/git-remote-https \
          /usr/lib/git-core/git-remote-ftp /usr/lib/git-core/git-remote-ftps
RUN git config --system protocol.https.allow never \
 && git config --system protocol.http.allow never \
 && git config --system protocol.git.allow never

# 2. no ad-hoc HTTP clients
RUN rm -f /usr/bin/curl /usr/bin/wget

# 3. npm points at a dead port (node_modules is already installed above).
#    Written to the prefix-level npmrc so it applies to every user at run time -
#    `npm config set` alone lands in a per-user file that the agent may not use.
RUN printf 'registry=http://127.0.0.1:9/\n' > "$(npm prefix -g)/etc/npmrc" \
 && npm config set registry http://127.0.0.1:9/

# 4. catch anything that honours proxy variables.
#    npm_config_registry is set here rather than in a config file because the
#    repo ships its own /app/.npmrc, and project config outranks user/global -
#    editing that file instead would dirty the harbor_base baseline.
ENV HTTP_PROXY=http://127.0.0.1:9 \
    HTTPS_PROXY=http://127.0.0.1:9 \
    http_proxy=http://127.0.0.1:9 \
    https_proxy=http://127.0.0.1:9 \
    NO_PROXY=localhost,127.0.0.1 \
    npm_config_registry=http://127.0.0.1:9/

# Visual evidence, readable by the agent at /app/.harbor_assets/.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]