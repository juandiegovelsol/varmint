# task107 hardening kit (NOT part of the deliverable)

Everything runs headless inside Docker (Xvfb + Mesa llvmpipe + ffmpeg x11grab); no window opens on
the host.

    docker build -t ddnet10943:dev -f Dockerfile.dev .          # ddnet @ base_commit, .git kept, tag `base`
    docker run -d --name dd107 -v "$PWD:/kitsrc" ddnet10943:dev sleep infinity
    docker exec dd107 bash -c 'mkdir -p /kit && cp -r /kitsrc/* /kit/'

| file | what it does |
|---|---|
| `mkbugs.py OUT` | the 4 injected defects as exact-string edits; writes `bug_01..04.patch` (good -> buggy) |
| `mkbundle.sh OUT` | regenerates bugs, the merged `fix.patch` (buggy baseline -> base + upstream fix, checked) and `test.patch` from git |
| `fix_orig.patch` | the original task's oracle (upstream PR #10951), base-relative |
| `tests/test_harvest_c01_hookline.py` | the hidden test file (source of `tests/test.patch`); includes the DDNet map writer |
| `state.sh "<bugs>|all|none" [fixorig]` | reset `src/`, apply chosen bugs (+ upstream fix), rebuild |
| `runtests.sh LABEL [-k]` | run the hidden tests against the current build -> `/kit/runs/LABEL.log` |
| `matrix.sh "label|bugs|extra" ...` | rebuild each state and run the tests (`extra`: fixorig, alt, wrong_*) |
| `altfix.py alt|wrong_radius|wrong_reach|wrong_width` | non-oracle fix (must pass) / wrong fixes (must fail) on the all-bugs tree |
| `final_check.sh BUNDLE` | replays the bundle: base + bundle bugs + bundle test.patch, config ids; then bundle fix.patch |
| `hookmap.cpp` | C++ map generator used for the first experiments (the tests use the Python writer instead) |
| `scene/make_yard.py`, `scene/start.sh`, `scene/record.py` | recording map, scene start-up (server, client, dummy), shot list + ffmpeg capture |
| `recording.mp4` | the shipped video (copy of `Tasks/.../environment/assets/recording.mp4`) |

Recording (all-bugs build in a second container):

    docker run -d --name dd107rec -v "$PWD:/kitsrc" ddnet10943:dev sleep infinity
    docker exec dd107rec bash -c 'mkdir -p /kit && cp -r /kitsrc/* /kit/ && cd /app && python3 /kit/mkbugs.py /kit/bugs \
      && for p in /kit/bugs/*.patch; do git apply $p; done && cd build && ninja DDNet DDNet-Server'
    docker exec dd107rec bash -c '/kitsrc/scene/start.sh && sleep 14 && python3 /kitsrc/scene/record.py /tmp/r/recording.mp4'

Gotchas found on the way:
- `+hook` / `+fire` sent through the client fifo are pressed and released in the same frame
  (`CConsole::ExecuteLine`); hold them with xdotool mouse buttons (right button = hook) instead.
- The menu cursor is software-driven by relative motion: park it with a big negative
  `mousemove_relative`, then move by (target / 2) px; click with mousedown, 0.12 s, mouseup.
- In game, 1 xdotool pixel = 2 aim units (inp_mousesens 200); `cl_mouse_max_distance 1000` keeps
  the aim target unclamped so a relative move sets an exact integer target.
- `dummy_connect` hands control to the dummy; send `cl_dummy 0` afterwards. Set `sv_motd ""`.
- Name plates are drawn over the line; tests run with `cl_nameplates 0`.
- `pkill -f DDNet` inside `bash -c '...DDNet...'` kills the shell itself; use `pkill -x`.
