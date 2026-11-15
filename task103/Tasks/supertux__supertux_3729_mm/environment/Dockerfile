FROM ubuntu:24.04

# --- bootstrap CA trust (this sandbox's ubuntu:24.04 has no ca-certificates
# preinstalled, and apt cannot fetch ca-certificates over https without it;
# seed /etc/ssl/certs from a known-good bundle shipped alongside this file) ---
COPY ca-certificates.crt /etc/ssl/certs/ca-certificates.crt

# Plain HTTP(80) is blocked in this sandbox; archive.ubuntu.com is not
# reliably reachable over https either, so point apt at the kernel.org mirror.
RUN sed -i \
      -e 's#http://archive.ubuntu.com/ubuntu#https://mirrors.edge.kernel.org/ubuntu#g' \
      -e 's#http://security.ubuntu.com/ubuntu#https://mirrors.edge.kernel.org/ubuntu#g' \
      -e 's#http://#https://#g' \
      /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null; true

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    apt-get update

RUN DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      build-essential cmake ninja-build git pkg-config python3 \
      libsdl2-dev libsdl2-image-dev \
      libphysfs-dev libfmt-dev libglm-dev libcurl4-openssl-dev \
      libharfbuzz-dev libfribidi-dev libraqm-dev libfreetype-dev \
      libopenal-dev libogg-dev libvorbis-dev zlib1g-dev libpng-dev libjpeg-dev \
      libasound2-dev \
      xvfb ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Note: this base commit (pre SDL3-migration) builds SDL_ttf from the
# vendored external/SDL_ttf submodule (with RAQM support) rather than a
# system package, so no separate SDL2_ttf install is needed here.

# --- Checkout SuperTux at the base commit, directly into /app ---
# Only the base commit is fetched (depth 1): the history is dropped further down anyway, and a full
# clone is several times larger and fails often on slow links. Retried, then checked to be the pin.
WORKDIR /app
RUN git init -q /app && git -C /app remote add origin https://github.com/SuperTux/supertux.git && \
    for i in 1 2 3 4 5; do git -C /app fetch -q --depth 1 origin 4b5663fc0c3ba08a8f8bd2ec8b75b5c02f82f7c7 && break; sleep 10; done && \
    git -C /app -c advice.detachedHead=false checkout 4b5663fc0c3ba08a8f8bd2ec8b75b5c02f82f7c7 && \
    test "$(git -C /app rev-parse HEAD)" = 4b5663fc0c3ba08a8f8bd2ec8b75b5c02f82f7c7 && \
    for i in 1 2 3 4 5; do git -C /app submodule update --init --recursive --depth 1 && break; sleep 10; done

# [IMPORTANT] Injected bugs: applied to the checkout BEFORE the image's build (so the prebuilt
# binary matches the sources the agent sees), BEFORE the timestamp step and the harbor_base
# snapshot, and deleted in the same RUN so no patch reaches the final image.
COPY bugs/ /tmp/bugs/
RUN set -e; for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done; \
    rm -rf /tmp/bugs

# --- Configure & build once at image-build time, so that applying a small
# patch later (fix.patch / test.patch) only triggers an incremental rebuild
# of the handful of changed files instead of a full rebuild from scratch. Same -O2 optimisation as
# RelWithDebInfo but without -g: identical code, much smaller build/ tree and faster links. ---
RUN cmake -S /app -B /app/build -GNinja \
      -DCMAKE_BUILD_TYPE=RelWithDebInfo \
      "-DCMAKE_C_FLAGS_RELWITHDEBINFO=-O2 -DNDEBUG" \
      "-DCMAKE_CXX_FLAGS_RELWITHDEBINFO=-O2 -DNDEBUG" \
      -DENABLE_OPENGL=OFF \
      -DENABLE_NETWORKING=OFF \
      -DENABLE_DISCORD=OFF \
      -DBUILD_DOCUMENTATION=OFF \
      -DBUILD_TESTING=OFF \
      -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    && cmake --build /app/build -j"$(nproc)"

# --- Drop the upstream history and record the task base: only base_commit's
# tree survives, with no history, so the fix commit is unreachable. test.sh
# restores test-plumbing paths from this tag before applying the hidden tests. ---
RUN rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# --- Visual evidence for the agent only (never tests/ or solution/, never the
# whole assets/ folder: ASSET_MANIFEST.json describes it in words). ---
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/recording.mp4 /app/.harbor_assets/

ENV SDL_AUDIODRIVER=dummy
ENV SDL_VIDEODRIVER=dummy

# one timestamp for every file: which file changed last must not point at the bug
RUN find /app -mindepth 1 -exec touch -h -t 202301010000 {} +

CMD ["bash"]
