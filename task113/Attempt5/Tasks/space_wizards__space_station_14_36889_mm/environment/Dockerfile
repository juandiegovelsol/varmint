# Space Station 14 (space-wizards/space-station-14) at the base commit
# 58dae1ce4a0806fa3b928834789b2b508b47b0f3, fetched directly (shallow) along with
# RobustToolbox checked out as a submodule at the pin recorded in that commit.
FROM mcr.microsoft.com/dotnet/sdk:10.0

ENV DEBIAN_FRONTEND=noninteractive \
    DOTNET_NOLOGO=1 \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1 \
    NUGET_XMLDOC_MODE=skip

# Use an https Ubuntu mirror (plain HTTP/port 80 is blocked in this environment, and
# archive.ubuntu.com itself has no https endpoint).
RUN sed -i -E 's#https?://(archive|security)\.ubuntu\.com/ubuntu/?#https://mirrors.edge.kernel.org/ubuntu/#' \
        /etc/apt/sources.list.d/*.sources 2>/dev/null; true

# Runtime deps for: headless/software-rendered Clyde (SDL3 + OpenGL via llvmpipe),
# OpenAL audio (kept muted via SDL_AUDIODRIVER=dummy at run time), fonts for text
# rendering/screenshots, video capture tooling, input-injection for scripted
# gameplay recording, and git to fetch the source at the exact base commit.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git \
        libx11-6 libxcursor1 libxi6 libxinerama1 libxrandr2 libxss1 libxext6 \
        libxkbcommon0 libxfixes3 \
        libgl1 libglx-mesa0 libegl1 libgbm1 libgl1-mesa-dri \
        libopenal1 libasound2t64 \
        fontconfig fonts-dejavu-core fonts-noto-core \
        ffmpeg \
        procps \
        python3 \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Source at the base commit: a direct shallow fetch of that exact commit (GitHub allows
# fetching any reachable commit hash for public repos), plus RobustToolbox checked out as
# a submodule at the pin recorded in that commit (and any submodules it itself has).
# [IMPORTANT] Injected bugs are applied in the same RUN, right after the checkout, and the
# patches are deleted there too, so no patch reaches the image. Every checked-out file then gets
# one fixed timestamp inside this same layer: resetting timestamps in a later layer would copy
# the whole tree into that layer (a second multi-GB copy of /app).
COPY bugs/ /tmp/bugs/
RUN set -e; \
    git init -q /app; \
    git -C /app remote add origin https://github.com/space-wizards/space-station-14.git; \
    git -C /app fetch --depth 1 origin 58dae1ce4a0806fa3b928834789b2b508b47b0f3; \
    git -C /app -c advice.detachedHead=false checkout 58dae1ce4a0806fa3b928834789b2b508b47b0f3; \
    git -C /app submodule update --init --recursive --depth 1; \
    for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done; \
    rm -rf /tmp/bugs; \
    find /app -mindepth 1 -name .git -prune -o -exec touch -h -t 202301010000 {} +

# Restore all NuGet packages (network needed here only; later builds and test runs work
# offline) and build once, so the prebuilt binaries match the source tree and any later
# incremental rebuild after a source patch is fast. Whatever the restore and the build create
# or change gets the same fixed timestamp inside this layer.
RUN set -e; \
    dotnet restore Content.IntegrationTests/Content.IntegrationTests.csproj; \
    dotnet build Content.IntegrationTests/Content.IntegrationTests.csproj --configuration DebugOpt --no-restore /m; \
    find /app -mindepth 1 -name .git -prune -o -newermt 2023-01-02 -exec touch -h -t 202301010000 {} +

ENV SDL_VIDEODRIVER=x11 \
    SDL_AUDIODRIVER=dummy \
    LIBGL_ALWAYS_SOFTWARE=1 \
    DOTNET_gcServer=1

# Drop the upstream history (including the submodules') and record the task base: the fix
# commit becomes unreachable, and test.sh restores test files from this tag. git is told to
# compare only mtime and size, so the index recorded here stays valid in every container
# started from the image (overlay filesystems change inode numbers and ctimes) and git status /
# git add stay fast. The few directories touched by removing the submodule .git files get the
# fixed timestamp too.
RUN set -e; \
    find /app -mindepth 2 -name .git -exec rm -rf {} +; \
    rm -rf /app/.git; \
    git -C /app init -q; \
    git -C /app config core.checkStat minimal; \
    git -C /app config core.trustctime false; \
    git -C /app -c user.email=h@l -c user.name=h add -A; \
    git -C /app -c user.email=h@l -c user.name=h commit -q -m base; \
    git -C /app tag harbor_base; \
    find /app -mindepth 1 -name .git -prune -o -newermt 2023-01-02 -exec touch -h -t 202301010000 {} +

# Visual evidence for the agent (only the evidence file itself, never the whole assets/
# folder -- ASSET_MANIFEST.json describes it in words and must stay out of the image).
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/recording.mp4 /app/.harbor_assets/
RUN find /app/.harbor_assets -exec touch -h -t 202301010000 {} +

CMD ["bash"]
