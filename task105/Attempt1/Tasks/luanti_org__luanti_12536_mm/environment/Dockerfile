FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

# This sandbox only allows outbound HTTPS; switch apt to the https mirrors first.
RUN sed -i 's#http://#https://#g' /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null; true

# ubuntu:20.04 ships without ca-certificates, so the first https fetch (of
# ca-certificates itself) has nothing to verify with yet. Bootstrap it with
# peer verification off just for that one install, then verify normally.
RUN printf 'Acquire::https::Verify-Peer "false";\nAcquire::https::Verify-Host "false";\n' \
        > /etc/apt/apt.conf.d/99insecure-bootstrap \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -f /etc/apt/apt.conf.d/99insecure-bootstrap \
    && update-ca-certificates \
    && apt-get update

RUN apt-get install -y --no-install-recommends \
        ca-certificates wget git cmake ninja-build pkg-config build-essential \
        libpng-dev libjpeg-dev libxxf86vm-dev libgl1-mesa-dev libx11-dev libxi-dev \
        libsqlite3-dev libgmp-dev zlib1g-dev libzstd-dev libfreetype6-dev \
        python3 \
        xvfb libgl1-mesa-dri mesa-utils mesa-vulkan-drivers ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Engine source, checked out at this task's base commit.
RUN git clone --quiet https://github.com/luanti-org/luanti.git /app && \
    git -C /app -c advice.detachedHead=false checkout d400a98ef0408ccbd2cc4c72f8b48c3813dfce41

# ---- IrrlichtMt (the Minetest/Luanti fork of Irrlicht), pinned to a commit
# from just before the base commit's date (2022-07-17). The root CMakeLists.txt
# looks for it at lib/irrlichtmt and builds it as a static library.
RUN git clone --quiet https://github.com/minetest/irrlicht.git /app/lib/irrlichtmt && \
    git -C /app/lib/irrlichtmt checkout --detach abebac8bd4c60c8a25a8e4fa76c1e260f741daeb && \
    rm -rf /app/lib/irrlichtmt/.git

# [IMPORTANT] Injected bugs: copied to a temp path, applied BEFORE the timestamp step, the
# build below and the harbor_base snapshot, and deleted in the same RUN so no patch reaches
# the final image.
COPY bugs/ /tmp/bugs/
RUN set -e; for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done; \
    rm -rf /tmp/bugs

# one timestamp for every file: which file changed last must not point at the bug
RUN keep=$(find /app \( -name .ninja_log -o -name CMakeCache.txt -o -name CACHEDIR.TAG -o -name meson-private \) -not -path '*/.git/*' -printf '%h\n' 2>/dev/null | sort -u | grep -vx /app || true); prune=''; for d in $keep; do prune="$prune -path $d -prune -o"; done; eval "find /app -mindepth 1 $prune -exec touch -h -t 202301010000 {} +"

RUN cmake -B /app/build -GNinja \
        -DCMAKE_BUILD_TYPE=Release \
        -DRUN_IN_PLACE=TRUE \
        -DBUILD_CLIENT=TRUE \
        -DBUILD_SERVER=FALSE \
        -DBUILD_UNITTESTS=TRUE \
        -DBUILD_BENCHMARKS=FALSE \
        -DENABLE_CURL=FALSE \
        -DENABLE_GETTEXT=FALSE \
        -DENABLE_SOUND=FALSE \
        -DENABLE_CURSES=FALSE \
        -DENABLE_LEVELDB=FALSE \
        -DENABLE_REDIS=FALSE \
        -DENABLE_POSTGRESQL=FALSE \
        -DENABLE_SPATIAL=FALSE \
        -DENABLE_PROMETHEUS=FALSE \
    && cmake --build /app/build --parallel "$(nproc)"

ENV LIBGL_ALWAYS_SOFTWARE=1
ENV SDL_AUDIODRIVER=dummy

# ---- Drop the upstream history and record the task base: the fix commit must
# be unreachable, and tests/test.sh restores test files from this tag.
RUN rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# ---- Visual evidence for the agent only (never the whole assets/ folder:
# ASSET_MANIFEST.json describes it in words).
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/recording.mp4 /app/.harbor_assets/

CMD ["bash"]
