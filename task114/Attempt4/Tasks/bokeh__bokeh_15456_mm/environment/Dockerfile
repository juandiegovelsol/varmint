FROM node:22-bookworm

# This sandbox allows outbound HTTPS only; switch apt to https mirrors first.
RUN sed -i 's#http://#https://#g' /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null; true

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates fonts-liberation fonts-dejavu-core fontconfig ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/bokeh/bokeh.git /app \
 && git -C /app -c advice.detachedHead=false checkout eaaaeb043ab10371a4f3a6dc0a945ffa6a784ae4

# Injected bugs: copied to a temp path and applied BEFORE the timestamp step, the BokehJS build and
# the harbor_base snapshot, then deleted in the same RUN so no patch reaches the final image.
COPY bugs/ /tmp/bugs/
RUN set -e; for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done; \
    rm -rf /tmp/bugs

# one timestamp for every file: which file changed last must not point at the bug
RUN keep=$(find /app \( -name .ninja_log -o -name CMakeCache.txt -o -name CACHEDIR.TAG -o -name meson-private \) -not -path '*/.git/*' -printf '%h\n' 2>/dev/null | sort -u | grep -vx /app || true); prune=''; for d in $keep; do prune="$prune -path $d -prune -o"; done; eval "find /app -mindepth 1 $prune -exec touch -h -t 202301010000 {} +"

WORKDIR /app/bokehjs

RUN npm ci --no-progress
RUN npx --no-install playwright-core install --with-deps --no-shell chromium
RUN node make build

ENV BOKEH_IN_DOCKER=1
ENV CI=true
ENV FORCE_COLOR=0

# The stored layout/image snapshots of the integration suite encode the expected geometry of every
# layout; they are not used by the verifier (behavioral unit tests only), so they are not shipped.
RUN find /app/bokehjs/test/baselines -type f \( -name '*.blf' -o -name '*.png' \) -delete

RUN rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

RUN mkdir -p /logs /app/.harbor_assets
COPY assets/recording.mp4 /app/.harbor_assets/

CMD ["bash"]
