# SuperTux task environment (issue #1398 / PR #1449)
# Base commit: d2c892e2d94308da759a3fb8451101e3add55754
FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

# This sandbox only reaches the internet over HTTPS (port 80 is closed), so a
# plain apt-get against the default http mirrors hangs. Point apt at an https
# Ubuntu mirror first.
RUN sed -i \
      -e 's#http://archive.ubuntu.com/ubuntu#https://mirrors.edge.kernel.org/ubuntu#g' \
      -e 's#http://security.ubuntu.com/ubuntu#https://mirrors.edge.kernel.org/ubuntu#g' \
      /etc/apt/sources.list 2>/dev/null; true

# apt over https needs a CA bundle, which this base image doesn't have yet.
# Bootstrap ca-certificates with peer verification off just for this one
# install, then use fully verified https for everything after.
RUN apt-get -o Acquire::https::Verify-Peer=false -o Acquire::https::Verify-Host=false update \
 && apt-get -o Acquire::https::Verify-Peer=false -o Acquire::https::Verify-Host=false install -y --no-install-recommends ca-certificates \
 && update-ca-certificates

# Everything the build and the tests need. ffmpeg is for the agent to pull
# frames out of the evidence video; xvfb/mesa are kept in case a test ever
# needs a headless GL context (there is no GPU here or where this is graded).
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      cmake \
      git \
      ca-certificates \
      pkg-config \
      libsdl2-dev \
      libsdl2-image-dev \
      libopenal-dev \
      libogg-dev \
      libvorbis-dev \
      libboost-filesystem-dev \
      libboost-system-dev \
      libboost-date-time-dev \
      libboost-locale-dev \
      libcurl4-openssl-dev \
      libpng-dev \
      libfreetype6-dev \
      libglew-dev \
      libgl1-mesa-dev \
      libgl1-mesa-dri \
      zlib1g-dev \
      xvfb \
      ffmpeg \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Check out the project at exactly base_commit (full sha), plus the git
# submodules the build needs: vendored googletest (the JUnit/XML-capable test
# runner the tests link against), tinygettext, squirrel, sexp-cpp, physfs,
# SDL_ttf. Same project, same commit the task is based on -- no second clone
# or another version of the project.
RUN git -C /app init -q \
 && git -C /app remote add origin https://github.com/SuperTux/supertux.git \
 && git -C /app fetch --depth 1 origin d2c892e2d94308da759a3fb8451101e3add55754 \
 && git -C /app -c advice.detachedHead=false checkout d2c892e2d94308da759a3fb8451101e3add55754 \
 && git -C /app submodule update --init --recursive --depth 1 \
 && find /app -mindepth 2 -name .git -exec rm -rf {} +

# [IMPORTANT] Injected bugs: copied to a temp path, applied BEFORE the timestamp
# step, the prebuilt binaries and the harbor_base snapshot, and deleted in the
# same RUN so no patch reaches the final image.
COPY bugs/ /tmp/bugs/
RUN set -e; for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done; \
    rm -rf /tmp/bugs

# One timestamp for every tracked file: which file changed last must not hint
# at the bug.
RUN find /app -mindepth 1 -not -path '/app/.git*' -exec touch -h -t 202301010000 {} +

# Configure with tests enabled and build once, into a directory outside /app,
# so the build output never becomes part of the task's recorded git history.
# Later, network-less rebuilds (after test.patch / fix.patch are applied)
# only need to recompile the handful of files that changed.
RUN cmake -S /app -B /build \
      -DCMAKE_BUILD_TYPE=Debug \
      -DBUILD_TESTS=ON \
      -DGLBINDING_ENABLED=OFF \
      -DENABLE_OPENGL=ON \
      -DCMAKE_VERBOSE_MAKEFILE=OFF \
 && cmake --build /build -j"$(nproc)" --target test_supertux2

# Drop the upstream history and record the task base (the fix commit must be
# unreachable; test.sh restores test files from this tag).
RUN rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Visual evidence for the agent only -- never the whole assets/ folder (which
# also holds ASSET_MANIFEST.json) and never tests/ or solution/.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/recording.mp4 /app/.harbor_assets/

CMD ["bash"]
