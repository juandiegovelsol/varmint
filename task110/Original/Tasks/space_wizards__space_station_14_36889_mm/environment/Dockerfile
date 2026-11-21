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
        libgl1 libglx-mesa0 libegl1 libgbm1 libgl1-mesa-dri mesa-utils \
        libopenal1 libasound2t64 \
        fontconfig fonts-dejavu-core fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji \
        xvfb x11-xserver-utils xdotool x11-utils \
        ffmpeg \
        procps \
        python3 \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Source at the base commit: a direct shallow fetch of that exact commit (GitHub allows
# fetching any reachable commit hash for public repos), plus RobustToolbox checked out as
# a submodule at the pin recorded in that commit (and any submodules it itself has).
RUN git init -q /app \
    && git -C /app remote add origin https://github.com/space-wizards/space-station-14.git \
    && git -C /app fetch --depth 1 origin 58dae1ce4a0806fa3b928834789b2b508b47b0f3 \
    && git -C /app -c advice.detachedHead=false checkout 58dae1ce4a0806fa3b928834789b2b508b47b0f3 \
    && git -C /app submodule update --init --recursive --depth 1

# Restore all NuGet packages (network needed here only). This warms the global packages
# cache so that later `dotnet build`/`dotnet test` runs -- including ones against a
# patched source tree -- work fully offline.
RUN dotnet restore

# Build once at image time so the environment, and any later incremental rebuild after a
# source patch, is fast and known-good.
RUN dotnet build --configuration DebugOpt --no-restore /m

ENV SDL_VIDEODRIVER=x11 \
    SDL_AUDIODRIVER=dummy \
    LIBGL_ALWAYS_SOFTWARE=1 \
    DOTNET_gcServer=1

# Drop the upstream history (including the submodules') and record the task base: the fix
# commit becomes unreachable, and test.sh restores test files from this tag.
RUN find /app -mindepth 2 -name .git -exec rm -rf {} + \
    && rm -rf /app/.git \
    && git -C /app init -q \
    && git -C /app -c user.email=h@l -c user.name=h add -A \
    && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
    && git -C /app tag harbor_base

# Visual evidence for the agent (only the evidence file itself, never the whole assets/
# folder -- ASSET_MANIFEST.json describes it in words and must stay out of the image).
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/recording.mp4 /app/.harbor_assets/

# one timestamp for every file: which file changed last must not point at the bug
RUN keep=$(find /app \( -name .ninja_log -o -name CMakeCache.txt -o -name CACHEDIR.TAG -o -name meson-private \) -not -path '*/.git/*' -printf '%h\n' 2>/dev/null | sort -u | grep -vx /app || true); prune=''; for d in $keep; do prune="$prune -path $d -prune -o"; done; eval "find /app -mindepth 1 $prune -exec touch -h -t 202301010000 {} +"

CMD ["bash"]
