FROM buildpack-deps:jammy

ENV DEBIAN_FRONTEND=noninteractive

# This sandbox blocks plain HTTP; switch apt to the https mirrors first.
RUN sed -i 's#http://#https://#g' /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null; true

RUN apt-get update && apt-get install -y --no-install-recommends \
		g++ make cmake git ca-certificates pkg-config \
		libpng-dev libjpeg-dev libgl1-mesa-dev libsqlite3-dev \
		libogg-dev libvorbis-dev libopenal-dev libcurl4-openssl-dev \
		libfreetype6-dev zlib1g-dev libgmp-dev libjsoncpp-dev libzstd-dev \
		gettext libsdl2-dev \
		xvfb mesa-utils libgl1-mesa-dri \
		ffmpeg \
		fonts-dejavu-core fonts-noto-cjk fonts-noto-core fonts-noto-color-emoji \
		python3 python3-pil \
	&& rm -rf /var/lib/apt/lists/*

# Check out the repository at the base commit (before the fix), directly at /app so the
# task harness (which restores paths from the `harbor_base` tag under /app) matches the
# checked-out tree.
# Shallow-fetch just the base commit instead of cloning the whole history (the history is
# deleted below anyway).
RUN git init -q /app \
	&& git -C /app remote add origin https://github.com/luanti-org/luanti.git \
	&& git -C /app fetch --quiet --depth 1 origin 041d67cecad21b8cea26b74d8d0faaf0f58b138b \
	&& git -C /app -c advice.detachedHead=false checkout 041d67cecad21b8cea26b74d8d0faaf0f58b138b

# [IMPORTANT] Injected bugs: copied to a temp path, applied BEFORE the timestamp step, the
# harbor_base snapshot and the build below, and deleted in the same RUN, so no patch is left in
# the container's filesystem. (The COPY layer itself still holds them, but a running container
# only sees the final merged filesystem and cannot read earlier layers.)
COPY bugs/ /tmp/bugs/
RUN set -e; for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done; \
	rm -rf /tmp/bugs

# one timestamp for every file: which file changed last must not point at the bug
RUN keep=$(find /app \( -name .ninja_log -o -name CMakeCache.txt -o -name CACHEDIR.TAG -o -name meson-private \) -not -path '*/.git/*' -printf '%h\n' 2>/dev/null | sort -u | grep -vx /app || true); prune=''; for d in $keep; do prune="$prune -path $d -prune -o"; done; eval "find /app -mindepth 1 $prune -exec touch -h -t 202301010000 {} +"

# Drop the upstream history and record the task base (source tree only, before the build
# below adds compiled artifacts): the fix commit becomes unreachable, and test.sh restores
# hidden test plumbing from this tag before grading.
RUN rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

WORKDIR /app

RUN cmake -B build \
		-DCMAKE_BUILD_TYPE=Release \
		-DRUN_IN_PLACE=TRUE \
		-DENABLE_GETTEXT=FALSE \
		-DBUILD_CLIENT=TRUE \
		-DBUILD_SERVER=FALSE \
		-DBUILD_UNITTESTS=FALSE \
		-DBUILD_BENCHMARKS=FALSE \
	&& cmake --build build --parallel "$(nproc)"

ENV SDL_AUDIODRIVER=dummy
ENV ALSOFT_DRIVERS=null
ENV LIBGL_ALWAYS_SOFTWARE=1
ENV MINETEST_BIN=/app/bin/minetest

RUN mkdir -p /logs /app/.harbor_assets
COPY assets/recording.mp4 /app/.harbor_assets/

CMD ["bash"]
