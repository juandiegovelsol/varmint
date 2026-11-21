FROM eclipse-temurin:17-jdk-jammy

# apt over https (plain http/port 80 is blocked in the grading sandbox)
RUN sed -i 's#http://#https://#g' /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null; true

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    xvfb \
    libgl1-mesa-dri \
    libglu1-mesa \
    mesa-utils \
    fonts-dejavu-core \
    ffmpeg \
    unzip \
    python3 \
    && rm -rf /var/lib/apt/lists/*

ENV GRADLE_USER_HOME=/opt/gradle-home
ENV DISPLAY=:99
ENV LIBGL_ALWAYS_SOFTWARE=1
ENV SDL_AUDIODRIVER=dummy

WORKDIR /app

# Check out exactly base_commit, full sha.
RUN git clone --quiet https://github.com/agateau/pixelwheels.git /app \
 && git -C /app -c advice.detachedHead=false checkout 8baa87705929292ea4f33f77cc34e6c06c15cb0b

# Warm Gradle's dependency and wrapper-distribution caches (network is allowed during docker
# build), so the grading run can happen fully offline. The test suite needs a real, off-screen
# desktop GL context, so it resolves one extra jar (the desktop/lwjgl3 backend); add that
# dependency line here to pull it down now, then run the module's existing test suite once so
# every jar the offline test run will need (junit, mockito, the gdx/box2d natives, the lwjgl3
# backend, the gradle wrapper distribution) is already cached. The repo tree is reverted to the
# clean base checkout afterwards, and build output removed, so nothing of this ships in the image.
RUN cd /app \
 && chmod +x gradlew \
 && sed -i '/mockito-core:3.12.4/a\    implementation "com.badlogicgames.gdx:gdx-backend-lwjgl3:$gdxVersion"' core-tests/build.gradle \
 && (xvfb-run -a -s "-screen 0 1280x800x24" \
        ./gradlew --no-daemon :core-tests:test \
        > /tmp/warmup.log 2>&1 || true) \
 && tail -c 20000 /tmp/warmup.log \
 && git checkout --quiet -- . \
 && git clean --quiet -fdx \
 && rm -rf "$GRADLE_USER_HOME"/caches/[0-9]* \
 && rm -f /tmp/warmup.log

# Injected bugs: copied to a temp path, applied BEFORE the timestamp step and the harbor_base
# snapshot, and deleted in the same RUN so no patch reaches the final image.
COPY bugs/ /tmp/bugs/
RUN set -e; for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done; \
    rm -rf /tmp/bugs

# one timestamp for every file: which file changed last must not point at the bug
RUN keep=$(find /app \( -name .ninja_log -o -name CMakeCache.txt -o -name CACHEDIR.TAG -o -name meson-private \) -not -path '*/.git/*' -printf '%h\n' 2>/dev/null | sort -u | grep -vx /app || true); prune=''; for d in $keep; do prune="$prune -path $d -prune -o"; done; eval "find /app -mindepth 1 $prune -exec touch -h -t 202301010000 {} +"

# Drop the upstream history and record the task base.
RUN rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

RUN mkdir -p /logs /app/.harbor_assets
COPY assets/recording.mp4 /app/.harbor_assets/

CMD ["bash"]
