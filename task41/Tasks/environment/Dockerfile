FROM python:3.11-bookworm

# Install system dependencies needed by pygame-ce (SDL2, audio, image libs)
# and general build toolchain
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        libsdl2-dev \
        libsdl2-image-dev \
        libsdl2-mixer-dev \
        libsdl2-ttf-dev \
        libfreetype6-dev \
        libjpeg-dev \
        libpng-dev \
        libportmidi-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# [IMPORTANT] Copy bug patches to a TEMP path (not into /app) so they can be
# applied into the base snapshot and never reach the agent-visible tree.
COPY assets/bugs/ /tmp/bugs/

# Clone and pin to the exact base commit, then strip .git so the agent
# cannot inspect the fix PR or future history (anti-cheat).
# Re-init a single-commit repo so `git apply` still works and the verifier
# can reset test files to the immutable base tag.
RUN git clone https://github.com/ClanGenOfficial/clangen /app \
    && git -C /app checkout f402fa7b4c322d74ca93de42d7d578022f078345 \
    && rm -rf /app/.git \
    # [IMPORTANT] Apply every bug patch BEFORE the snapshot below, so the defect
    # becomes part of harbor_base (the exact state the agent starts from).
    && for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done \
    # [IMPORTANT] Delete the bug patches from /tmp once applied - each patch's
    # '-' lines are literally the correct code, so leaving the file readable
    # anywhere in the image hands the agent the exact fix.
    && rm -rf /tmp/bugs \
    && git -C /app init -q \
    && git -C /app -c user.email=h@l -c user.name=h add -A \
    && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
    && git -C /app tag harbor_base

# Pre-install runtime Python dependencies so verify time doesn't wait on the network.
# PEP 668: Debian/Ubuntu bookworm requires --break-system-packages for pip installs
# outside a venv. Pin key packages to the exact versions the project specifies.
# pytest is TEST-ONLY and is intentionally not installed here - it goes into
# tests/test.sh at verify time so the agent-facing image never carries it.
# black~=23.0 is a genuine [project.dependencies] entry of clangen itself (not a
# test tool here), so it is left for the editable install below to resolve.
RUN pip install --break-system-packages --no-cache-dir \
        "pygame-ce==2.5.3" \
        "pygame-gui==0.6.13" \
        "ujson~=5.7" \
        "pydantic>=2.12.0" \
        "cryptography~=42.0" \
        "pgpy~=0.6" \
        "platformdirs~=3.3" \
        "requests~=2.28" \
        "strenum~=0.4" \
        "tomli>=2.2.1" \
        "hatchling>=1.27.0"

# Install the repo itself in editable mode (exposes scripts/ package; also
# resolves clangen's own [project.dependencies], e.g. black~=23.0)
RUN pip install --break-system-packages --no-cache-dir -e /app

# Create asset directory and logs directory
RUN mkdir -p /logs /app/.harbor_assets

# Copy visual evidence assets — readable by the agent at /app/.harbor_assets/
# Build context is environment/, so COPY assets/ → environment/assets/
COPY assets/ /app/.harbor_assets/
# [IMPORTANT] Delete the bug diffs from the agent-visible dir so the agent
# can't read the answer (the reverse of a bug patch is the fix).
RUN rm -rf /app/.harbor_assets/bugs

# tests/ and solution/ are intentionally NOT copied into the image.
# The harness supplies them at verify time via bind mounts.

CMD ["bash"]
