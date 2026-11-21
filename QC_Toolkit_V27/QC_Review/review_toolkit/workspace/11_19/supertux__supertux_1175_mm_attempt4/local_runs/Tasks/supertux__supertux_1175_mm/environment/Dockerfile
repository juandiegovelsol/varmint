FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    SDL_AUDIODRIVER=dummy \
    SDL_VIDEODRIVER=dummy \
    ALSOFT_DRIVERS=null \
    LIBGL_ALWAYS_SOFTWARE=1

# Use https mirrors (plain HTTP is blocked in this sandbox), works for both
# classic sources.list and deb822 .sources layouts.
RUN sed -i 's#http://#https://#g' /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null; true
RUN sed -i 's#archive.ubuntu.com#mirrors.edge.kernel.org#g; s#security.ubuntu.com#mirrors.edge.kernel.org#g' /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null; true

# This base image ships with no ca-certificates at all, so apt's https
# transport cannot verify anything yet (chicken-and-egg: can't fetch
# ca-certificates over verified https without ca-certificates). Bootstrap by
# disabling TLS verification just long enough to install ca-certificates,
# then turn verification back on for every apt-get after that.
RUN echo 'Acquire::https::Verify-Peer "false";' > /etc/apt/apt.conf.d/99insecure-bootstrap \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -f /etc/apt/apt.conf.d/99insecure-bootstrap \
    && apt-get update

RUN apt-get install -y --no-install-recommends \
      cmake build-essential automake pkg-config git \
      libogg-dev libvorbis-dev libopenal-dev libboost-all-dev \
      libsdl2-dev libsdl2-image-dev libfreetype6-dev libharfbuzz-dev \
      libfribidi-dev libglib2.0-dev libraqm-dev libglew-dev \
      libcurl4-openssl-dev libglm-dev zlib1g-dev \
      xvfb x11-utils mesa-utils libgl1-mesa-dri libglx-mesa0 libosmesa6 \
      ffmpeg \
      fonts-dejavu-core fonts-noto-cjk fonts-noto-color-emoji \
      python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Check out the base commit (network allowed at build time only). A full
# clone (not shallow) so the historical SHA is reachable, then the
# submodules (squirrel, tinygettext, sexp-cpp, physfs, SDL_ttf) the build
# needs. discord-sdk is never needed (ENABLE_DISCORD stays OFF) and
# sexp-cpp's own benchmark/googletest submodules are never needed either
# (sexp-cpp's sources are globbed directly, not built via its own
# CMakeLists), so both are skipped to save time and space.
RUN git clone https://github.com/SuperTux/supertux.git /app \
    && git -C /app -c advice.detachedHead=false checkout 8f0c06e3a0cf20294f960cc48a6bfbaf85bd0ca6 \
    && git -C /app -c submodule."discord-sdk".update=none \
         -c submodule."external/sexp-cpp".update=none \
         submodule update --init --recursive --depth 1 \
         external/tinygettext external/squirrel external/physfs external/SDL_ttf \
    && git -C /app submodule update --init --depth 1 external/sexp-cpp \
    && find /app -mindepth 2 -name .git -prune -exec rm -rf {} +

# Applied before the timestamp step, the build and the harbor_base snapshot; the patches are
# deleted in the same RUN so none of them reaches the final image.
COPY bugs/ /tmp/bugs/
RUN set -e; for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done; \
    rm -rf /tmp/bugs

# one timestamp for every file: which file changed last must not point at the bug
RUN keep=$(find /app \( -name .ninja_log -o -name CMakeCache.txt -o -name CACHEDIR.TAG -o -name meson-private \) -not -path '*/.git/*' -printf '%h\n' 2>/dev/null | sort -u | grep -vx /app || true); prune=''; for d in $keep; do prune="$prune -path $d -prune -o"; done; eval "find /app -mindepth 1 $prune -exec touch -h -t 202301010000 {} +"

# Configure once with tests enabled; build at image-build time so dependency
# objects (physfs/squirrel/SDL_ttf external projects, all .cpp files) are
# cached in the image. tests/test.sh re-applies the fix inside the
# (network-less) container and only needs a small incremental rebuild.
RUN cmake -S /app -B /app/build \
      -DCMAKE_BUILD_TYPE=RelWithDebInfo \
      -DENABLE_DISCORD=OFF \
      -DBUILD_TESTS=OFF \
      -DWARNINGS=OFF -DWERROR=OFF \
    && cmake --build /app/build -j"$(nproc)" --target supertux2

# Drop the upstream history (the fix commit must be unreachable) and record
# the task base: test.sh restores any test file a candidate tampers with
# from this tag. build/ is covered by the repo's own .gitignore, so the
# compiled binary and object files are not committed here.
RUN rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Visual evidence for the agent only (never the whole assets/ folder: that
# also holds ASSET_MANIFEST.json, a description in words).
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/recording.mp4 /app/.harbor_assets/

CMD ["bash"]
