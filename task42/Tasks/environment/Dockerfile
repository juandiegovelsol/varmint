FROM python:3.11-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends git curl build-essential libffi-dev libssl-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone, pin to base commit, strip .git (anti-cheat: agent cannot inspect fix PR/future history).
# Re-init a single base commit + immutable tag so the verifier can reset test files;
# git apply still works without upstream history.
RUN git clone https://github.com/Textualize/textual /app \
 && git -C /app checkout 4d4fb73a48724fff130600ef22ddc7e75ec4c8e2 \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install the repo's own runtime dependencies so verify time does not wait on the
# network for them. Test-only deps (pytest, pytest-asyncio, pytest-textual-snapshot) are
# installed at verify time in tests/test.sh instead, since [verifier] network_mode is
# "public" — they do not belong baked into the runtime image.
RUN pip install --upgrade pip setuptools wheel -q \
 && pip install -e .

# Visual evidence, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied into the image —
# the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
