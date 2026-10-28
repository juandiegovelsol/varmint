FROM python:3.11-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends git curl build-essential libffi-dev libssl-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone, pin to base commit, strip .git (anti-cheat: agent cannot inspect fix PR/future history).
# Re-init a single base commit + immutable tag so the verifier can reset test files;
# git apply still works without upstream history.
# Bug patches live OUTSIDE assets/ — assets/ is copied wholesale to an agent-readable
# path below, so anything parked in it is shipped to the model. They land in /tmp only
# long enough to be applied to the base snapshot, and the same RUN deletes them: the
# reverse of a bug patch is the fix, and /tmp is as agent-visible as /app.
COPY bugs/ /tmp/bugs/
RUN git clone https://github.com/Textualize/textual /app \
 && git -C /app checkout 5cb6cd03746afce553c88ab07362130a8880369a \
 && rm -rf /app/.git \
 && for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done \
 && rm -rf /tmp/bugs \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install the repo's own dependencies so verify time does not wait on the network.
# Test-only deps (pytest/pytest-asyncio/pytest-textual-snapshot) are installed by
# tests/test.sh at verify time instead, not baked in here.
RUN pip install --upgrade pip setuptools wheel -q \
 && pip install -e '.[dev]' 2>/dev/null || pip install -e .

# Visual evidence, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied into the image —
# the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
