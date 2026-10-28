FROM debian:bookworm-20240701

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    ca-certificates \
    pkg-config \
    make \
    autoconf \
    automake \
    libtool \
    libgtk-3-dev \
    libcairo2-dev \
    libglib2.0-dev \
    libjpeg62-turbo-dev \
    libpng-dev \
    libtiff-dev \
    zlib1g-dev \
    libexpat1-dev \
    libsm-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# [IMPORTANT] Injected-bug diffs go to a TEMP path, never into /app, so they can be baked
# into the base snapshot below without ever reaching the agent-visible tree.
COPY assets/bugs/ /tmp/bugs/

# Clone, pin to the base commit (the repo state the issue was filed against, i.e.
# before the fixing PR), fetch ALL third-party submodules (the header-only Catch2
# test framework needed to build the unit-test suite, plus nanosvg/other bundled
# libs the core GTK build unconditionally compiles against, e.g. src/generic/bmpsvg.cpp
# -> 3rdparty/nanosvg), then STRIP .git so the agent cannot inspect the fix PR / future
# history (anti-cheat). Re-init a single base commit + immutable tag so the verifier
# can reset test files; git apply still works without upstream history.
#
# Anti-cheat: upstream's own pre-fix test tree already carries the SECTION this task's
# test.patch adds, but disabled behind a GTK3-specific guard that names the exact
# platform and calls it a known failure -- reading it hands over localization and the
# exact repro call for free, well beyond what instruction.md states. Delete that whole
# disabled SECTION here (it is not real p2p/f2p coverage yet at this point -- test.patch
# is what adds it, same as it would for a test upstream never wrote at all) so the
# agent's own checkout carries no trace of a disabled/flagged test around this case,
# indistinguishable from simply not having that coverage. tests/test.patch (unchanged
# in mechanism, just regenerated against this base) still does the real work of adding
# the SECTION back at verify time -- f2p/p2p semantics are untouched: same call, same
# assertions, same pass/fail behavior for every correct or incorrect fix.
RUN git clone https://github.com/wxWidgets/wxWidgets /app \
 && git -C /app checkout 08104d819e2b50c2500ce8ff02ac4e73b0ece258 \
 && git -C /app submodule update --init \
 && perl -0777 -pi -e 's/\Q        SECTION("OneDevRegionAndReset Transform Matrix")\E\n\Q        {\E\n\Q#ifdef __WXGTK3__\E\n\Q            WARN("Skipping test known to fail in wxGTK 3");\E\n\Q#else\E\n\Q            OneDevRegionAndReset(dc, bmp, true, true, wxPoint());\E\n\Q#endif\E\n\Q        }\E\n\n//' /app/tests/graphics/clippingbox.cpp \
 && ! grep -q 'Skipping test known to fail in wxGTK 3' /app/tests/graphics/clippingbox.cpp \
 # [IMPORTANT] Apply every injected-bug patch BEFORE the snapshot below, so the defects
 # become part of harbor_base -- the exact source state the agent starts from. These touch
 # product source only (never tests), which is what lets the verifier reset test files to
 # harbor_base and re-apply its own tests without discarding any bug.
 && for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done \
 && find /app -name .git -exec rm -rf {} + \
 && git -C /app init -q \
 && git -C /app -c user.email=harbor@localhost -c user.name=harbor add -A \
 && git -C /app -c user.email=harbor@localhost -c user.name=harbor commit -q -m base \
 && git -C /app tag harbor_base

# Bake the full build at BUILD time - the agent phase is OFFLINE (task.toml [agent]
# network_mode="no-network"), so it cannot fetch a compiler/toolchain, and neither phase
# can afford a from-scratch wxGTK3+Cairo build (would risk their own timeouts even for a
# correct fix). Building the library and the GUI test binary (test_gui, which contains
# ClippingBoxTestCase) now means the agent's and verifier's later `make` invocations only
# need to recompile the handful of files the fix/test patches touch, via the Makefiles'
# own dependency tracking. xvfb/xauth are test-only (needed only to run the GUI test
# binary headless, not to build it or the library) and are installed in tests/test.sh at
# verify time instead, since the verifier phase has network_mode="public".
RUN mkdir -p /app/buildgtk \
 && cd /app/buildgtk \
 && ../configure --with-gtk=3 \
 && make -j"$(nproc)" \
 && cd tests \
 && make -j"$(nproc)" test_gui

# Visual evidence, readable by the agent at /app/.harbor_assets/. tests/ and solution/
# are intentionally NOT copied into the image - the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/
# [IMPORTANT] Drop the injected-bug diffs from BOTH places they exist -- /tmp/bugs (the
# staging copy the apply loop above reads) and the agent-visible assets dir -- because the
# reverse of a bug patch is its fix. Deleting here is sufficient: the agent only ever sees
# the final merged filesystem, not the earlier build layers the files came from.
RUN rm -rf /app/.harbor_assets/bugs /tmp/bugs

CMD ["bash"]
