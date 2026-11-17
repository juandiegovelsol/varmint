FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN sed -i 's#http://#https://#g' /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null; true

# Bootstrap: ca-certificates isn't present yet, so apt can't verify the https
# mirrors. Fetch just that package with peer verification off, then proceed
# normally once certificates are available.
RUN apt-get -o Acquire::https::Verify-Peer=false -o Acquire::https::Verify-Host=false update -y && \
    apt-get -o Acquire::https::Verify-Peer=false -o Acquire::https::Verify-Host=false install -y --no-install-recommends ca-certificates && \
    update-ca-certificates

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    ninja-build \
    pkg-config \
    git \
    curl \
    python3 \
    python3-pip \
    python3-pytest \
    python3-pil \
    rustc \
    cargo \
    gdb \
    zlib1g-dev \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswresample-dev \
    libswscale-dev \
    libx264-dev \
    libfreetype6-dev \
    libglew-dev \
    libnotify-dev \
    libpng-dev \
    libsdl2-dev \
    libsqlite3-dev \
    libcurl4-openssl-dev \
    libssl-dev \
    libogg-dev \
    libopus-dev \
    libopusfile-dev \
    libwavpack-dev \
    libgtest-dev \
    xvfb \
    x11-utils \
    xdotool \
    mesa-utils \
    libgl1-mesa-dri \
    libglx-mesa0 \
    ffmpeg \
    fonts-dejavu-core \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Check out exactly base_commit (full sha), including the ddnet-libs submodule the build needs,
# then drop the submodule's own .git (only /app/.git, pinned to base_commit, may remain).
RUN git clone https://github.com/ddnet/ddnet.git /app \
 && git -C /app -c advice.detachedHead=false checkout 174340a8c49c91a68dbd8b9a5efd6ea98c0df748 \
 && git -C /app submodule update --init --depth 1 \
 && rm -rf /app/ddnet-libs/.git
# one timestamp for every file: which file changed last must not point at the bug
RUN keep=$(find /app \( -name .ninja_log -o -name CMakeCache.txt -o -name CACHEDIR.TAG -o -name meson-private \) -not -path '*/.git/*' -printf '%h\n' 2>/dev/null | sort -u | grep -vx /app || true); prune=''; for d in $keep; do prune="$prune -path $d -prune -o"; done; eval "find /app -mindepth 1 $prune -exec touch -h -t 202301010000 {} +"

RUN mkdir -p /app/build && cd /app/build && \
    cmake -GNinja \
      -DCMAKE_BUILD_TYPE=Release \
      -DDOWNLOAD_GTEST=OFF \
      -DCMAKE_RUNTIME_OUTPUT_DIRECTORY=/app/build \
      -DTOOLS=OFF \
      -DVULKAN=OFF \
      -DANTIBOT=OFF \
      -DWEBSOCKETS=OFF \
      -DMYSQL=OFF \
      -DAUTOUPDATE=OFF \
      .. && \
    cmake --build . --target DDNet DDNet-Server -- -j$(nproc)

ENV SDL_AUDIODRIVER=dummy
ENV LIBGL_ALWAYS_SOFTWARE=1
ENV DDNET_BUILD_DIR=/app/build

WORKDIR /app

# Drop the upstream history and record the task base: only /app/.git, holding exactly this one
# commit, may remain in the image (the fix commit must be unreachable from it).
RUN rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

RUN mkdir -p /logs /app/.harbor_assets
COPY assets/recording.mp4 /app/.harbor_assets/

CMD ["bash"]
