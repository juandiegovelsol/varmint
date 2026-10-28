FROM python:3.11-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends git curl build-essential libffi-dev libssl-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone, pin to base commit, strip .git (anti-cheat: agent cannot inspect fix PR/future history).
# Re-init a single base commit + immutable tag so the verifier can reset test files;
# git apply still works without upstream history.
RUN git clone https://github.com/Textualize/textual /app \
 && git -C /app checkout ee4abfaf82da6ca966c54401a6a531f665519902 \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install the REPO'S OWN dependencies only. Their versions are constrained by the
# pyproject/lock at the pinned base commit above, so this layer is reproducible.
#
# Deliberately NOT here:
#   * `pip install --upgrade pip setuptools wheel` — unpinned, so a later rebuild would
#     silently build against a different resolver and build backend. The base image's own
#     pip/setuptools/wheel are what this image is built with.
#   * pytest / pytest-asyncio — test-only packages. tests/test.sh installs them at verify
#     time at explicit pinned versions, so the pins live next to the tests that need them.
#   * pytest-textual-snapshot — genuinely unused: these tests drive App.run_test() and
#     assert on rendered cells, and no test references a snapshot fixture.
#
# No `2>/dev/null || true`: a failed dependency install must fail the BUILD, not survive
# into an image whose verifier cannot collect tests.
RUN pip install --no-cache-dir -e '.[dev]' -q || pip install --no-cache-dir -e . -q

# Visual evidence, readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are intentionally NOT copied into the image —
# the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
