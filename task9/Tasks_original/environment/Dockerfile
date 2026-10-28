FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV FLUTTER_HOME=/opt/flutter
ENV PATH="${FLUTTER_HOME}/bin:${FLUTTER_HOME}/bin/cache/dart-sdk/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git unzip xz-utils zip libglu1-mesa wget ca-certificates \
    clang cmake ninja-build pkg-config libgtk-3-dev liblzma-dev \
    python3 python3-pip \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone flutter/flutter, pin to base commit, strip .git for anti-cheat,
# then re-init with a single base commit + immutable tag.
RUN git clone https://github.com/flutter/flutter /opt/flutter \
 && git -C /opt/flutter checkout 96d292fa0acd9d11e85fd04f7355a47cf3fb2723 \
 && /opt/flutter/bin/flutter --version

RUN git clone https://github.com/flutter/flutter /app \
 && git -C /app checkout 96d292fa0acd9d11e85fd04f7355a47cf3fb2723 \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install Flutter dependencies
RUN cd /app && /opt/flutter/bin/flutter pub get --directory packages/flutter 2>/dev/null || true

# Visual evidence, readable by agent at /app/.harbor_assets/
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
