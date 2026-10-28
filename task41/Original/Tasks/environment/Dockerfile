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

# Clone and pin to the exact base commit, then strip .git so the agent
# cannot inspect the fix PR or future history (anti-cheat).
# Re-init a single-commit repo so `git apply` still works and the verifier
# can reset test files to the immutable base tag.
RUN git clone https://github.com/ClanGenOfficial/clangen /app \
    && git -C /app checkout f402fa7b4c322d74ca93de42d7d578022f078345 \
    && rm -rf /app/.git \
    && git -C /app init -q \
    && git -C /app -c user.email=h@l -c user.name=h add -A \
    && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
    && git -C /app tag harbor_base

# Pre-install all Python dependencies so verify time doesn't wait on the network.
# PEP 668: Debian/Ubuntu bookworm requires --break-system-packages for pip installs
# outside a venv. Pin key packages to the exact versions the project specifies.
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
        "black~=23.0" \
        "pytest~=8.2" \
        "hatchling>=1.27.0"

# Install the repo itself in editable mode (exposes scripts/ package)
RUN pip install --break-system-packages --no-cache-dir -e /app

# Create asset directory and logs directory
RUN mkdir -p /logs /app/.harbor_assets

# Copy visual evidence assets — readable by the agent at /app/.harbor_assets/
# Build context is environment/, so COPY assets/ → environment/assets/
COPY assets/ /app/.harbor_assets/

# tests/ and solution/ are intentionally NOT copied into the image.
# The harness supplies them at verify time via bind mounts.

CMD ["bash"]
