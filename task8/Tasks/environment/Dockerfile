FROM python:3.11-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends git curl build-essential libffi-dev libssl-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone, pin to base commit, strip .git (anti-cheat: agent cannot inspect fix PR/future history).
# Re-init a single base commit + immutable tag so the verifier can reset test files;
# git apply still works without upstream history.
RUN git clone https://github.com/Textualize/textual /app \
 && git -C /app checkout 4ec7d38b612ab672ee45c6de5b3b9372f0b09254 \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# The repo's own RUNTIME dependencies, so verify time does not wait on the network.
# rich is pinned because it renders the SVG the snapshot baseline was captured from —
# an unpinned upgrade would change that rendering and silently invalidate the baseline.
# It is a runtime dependency of textual itself, not test tooling.
RUN pip install --upgrade pip setuptools wheel -q \
 && pip install -e . -q \
 && pip install -q rich==15.0.0

# TEST-ONLY tooling is deliberately NOT installed into this image. Leaving pytest and
# pytest-textual-snapshot importable would tell the agent the fix is graded by an SVG
# snapshot comparison before it has diagnosed anything, and it would put the harness in
# the environment instead of in the test stage. Only the pinned wheels are staged here;
# tests/test.sh installs them at verify time, which has no network
# (task.toml [verifier] network_mode = "no-network") — hence download now, install later.
# Pinning keeps the snapshot comparison stable across rebuilds. No `|| true`: a failed
# download must break the build loudly rather than surface later as a missing plugin.
RUN mkdir -p /opt/verifier-deps \
 && pip download -q --dest /opt/verifier-deps \
      pytest==8.4.2 \
      pytest-asyncio==1.4.0 \
      pytest-textual-snapshot==1.1.0 \
      syrupy==4.8.0 \
      jinja2==3.1.6 \
 && chmod 700 /opt/verifier-deps

# Visual evidence, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied into the image —
# the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
