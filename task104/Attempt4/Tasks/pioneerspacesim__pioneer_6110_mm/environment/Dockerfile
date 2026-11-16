FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
# This sandbox only allows outbound HTTPS; switch apt to https mirrors first.
RUN sed -i 's#http://#https://#g' /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null || true

# Bootstrap: this base image ships with no CA bundle at all, so the first
# https fetch can't verify its TLS cert yet. Fetch just ca-certificates with
# verification disabled, then do everything else over verified https.
RUN apt-get -o Acquire::https::Verify-Peer=false -o Acquire::https::Verify-Host=false update \
    && apt-get -o Acquire::https::Verify-Peer=false -o Acquire::https::Verify-Host=false install -y --no-install-recommends ca-certificates \
    && update-ca-certificates

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        g++ \
        git \
        cmake \
        ninja-build \
        pkg-config \
        mesa-common-dev \
        libfreeimage-dev \
        libglew-dev \
        libfreetype6-dev \
        libsigc++-2.0-dev \
        libvorbis-dev \
        libassimp-dev \
        libsdl2-dev \
        libsdl2-image-dev \
        libopenal-dev \
        libgl1-mesa-dri \
        libglu1-mesa \
        mesa-utils \
        xvfb \
        x11-utils \
        ffmpeg \
        gdb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Check out the repository at the exact base commit (shallow fetch of just that one commit -- no
# need for the other 18000+ commits of history).
RUN git init -q /app \
 && git -C /app remote add origin https://github.com/pioneerspacesim/pioneer.git \
 && git -C /app fetch --depth 1 origin baf8112d806a6288f2025401eff033a5b8adb1c3 \
 && git -C /app -c advice.detachedHead=false checkout baf8112d806a6288f2025401eff033a5b8adb1c3

ENV PIONEER_LOCAL_DATA_ONLY=1
ENV HOME=/root
ENV LIBGL_ALWAYS_SOFTWARE=1
ENV SDL_AUDIODRIVER=dummy
ENV SDL_VIDEODRIVER=x11

# Pioneer's FileSourceFS::MakeDirectory has a pre-existing off-by-one bug recursing to create
# missing parent directories (path.substr(0, pos - 1) instead of pos), which mis-creates a
# truncated directory name when more than one level of $HOME/.local/share/pioneer is missing.
# Pre-create the single level needed so every later MakeDirectory("subdir") call only ever needs
# to make one directory whose parent already exists, avoiding that code path entirely.
RUN mkdir -p /root/.local/share/pioneer

# Configure and build the unit-test target at image build time, so grading (which runs with
# --network none and applies test.patch/fix.patch on top) only ever has to recompile the handful
# of files a patch actually touches, using this baked ninja build cache -- not all ~360 files.
RUN cmake -S /app -B /app/build -G Ninja \
        -DCMAKE_BUILD_TYPE=RelWithDebInfo \
 && cmake --build /app/build --target unittest -- -j"$(nproc)"

# [IMPORTANT] Injected bugs: copied to a temp path, applied BEFORE the timestamp step and the
# harbor_base snapshot, and deleted in the same RUN so no patch reaches the final image.
COPY bugs/ /tmp/bugs/
RUN set -e; for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done; \
    rm -rf /tmp/bugs

# One timestamp for every source file (except the build cache's own bookkeeping files, which must
# keep their real relative timestamps so ninja's incremental build stays correct): which file
# changed last must not point at the bug once a patch is applied at grading time.
RUN keep=$(find /app \( -name .ninja_log -o -name CMakeCache.txt -o -name CACHEDIR.TAG -o -name meson-private \) -not -path '*/.git/*' -printf '%h\n' 2>/dev/null | sort -u | grep -vx /app || true); prune=''; for d in $keep; do prune="$prune -path $d -prune -o"; done; eval "find /app -mindepth 1 $prune -exec touch -h -t 202301010000 {} +"

# Drop the upstream history and record the task base; the fix commit must be unreachable, and
# test.sh restores test files from this tag. The build cache is left out of the snapshot (it is
# regenerated/extended in place at grading time, never replayed from git).
RUN rm -rf /app/.git \
 && git -C /app init -q \
 && echo 'build/' >> /app/.git/info/exclude \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Only the visual evidence for the agent -- never the whole assets/ folder (that holds
# ASSET_MANIFEST.json, which describes the evidence in words) and never tests/ or solution/.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/recording.mp4 /app/.harbor_assets/

CMD ["bash"]
