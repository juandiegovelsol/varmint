FROM buildpack-deps:bookworm
USER root

ENV DEBIAN_FRONTEND=noninteractive

# This sandbox allows outbound HTTPS only; switch apt to https mirrors first.
RUN sed -i 's#http://#https://#g' /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null; true

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git ffmpeg \
    build-essential cmake ninja-build pkg-config gettext \
    libpng-dev libjpeg-dev libgl1-mesa-dev libsdl2-dev libfreetype6-dev \
    libsqlite3-dev libgmp-dev libjsoncpp-dev zlib1g-dev libzstd-dev \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

ARG LUANTI_BASE_SHA=c07499ccfc5622f7cdb08e69e63b61327d9242c1
ARG LUANTI_REPO_URL=https://github.com/luanti-org/luanti

# Clone the project and check out exactly the task's base commit (full sha).
RUN git clone --no-checkout "${LUANTI_REPO_URL}" /app \
 && git -C /app -c advice.detachedHead=false checkout c07499ccfc5622f7cdb08e69e63b61327d9242c1
# one timestamp for every file: which file changed last must not point at the bug
RUN keep=$(find /app \( -name .ninja_log -o -name CMakeCache.txt -o -name CACHEDIR.TAG -o -name meson-private \) -not -path '*/.git/*' -printf '%h\n' 2>/dev/null | sort -u | grep -vx /app || true); prune=''; for d in $keep; do prune="$prune -path $d -prune -o"; done; eval "find /app -mindepth 1 $prune -exec touch -h -t 202301010000 {} +"

WORKDIR /app

# Drop the upstream history (the fix commit, and everything else after
# base_commit, must be unreachable) and record the task base: test.sh resets
# any test file a candidate could tamper with from this tag.
RUN rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Build the project (including the unittest binary) once here so grading,
# which installs nothing, only needs a fast incremental rebuild after the
# hidden tests / a fix are applied.
RUN cmake -B build -GNinja \
    -DCMAKE_BUILD_TYPE=Release \
    -DRUN_IN_PLACE=TRUE \
    -DENABLE_GETTEXT=TRUE \
    -DBUILD_SERVER=TRUE \
    -DBUILD_CLIENT=TRUE \
    -DBUILD_UNITTESTS=TRUE \
    -DBUILD_BENCHMARKS=FALSE \
    -DENABLE_LUAJIT=FALSE \
    -DENABLE_SOUND=FALSE \
    -DENABLE_CURL=TRUE \
    && cmake --build build --parallel "$(nproc)"

# Visual evidence for the agent (named files only, never the whole assets/
# folder: that also holds ASSET_MANIFEST.json, which describes the bug in
# words).
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/bug.mp4 assets/expected.mp4 /app/.harbor_assets/

CMD ["bash"]
