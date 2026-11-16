# task106 recording + validation kit (not part of the deliverable)

Re-shoots `recording.mp4` and re-runs the hidden probe tests headlessly (Xvfb + Mesa llvmpipe +
ffmpeg x11grab) inside a dev container; no window ever opens on the host.

    # dev image: task apt list + xdotool, luanti 041d67c from a local `git archive` tarball
    # (cloning luanti inside Docker was very slow here), full build with BUILD_UNITTESTS
    docker build -t lu15105:dev -f Dockerfile.dev <dir holding luanti_base.tar>
    docker run -d --name lu106 lu15105:dev sleep infinity
    docker cp <kit dir> lu106:/kit                       # needs bugs/, fix_orig.patch, probe/ too
    docker cp minetest_game-5.8.0 lu106:/app/games/minetest_game
    docker exec lu106 bash -c '/kit/state.sh all && /kit/run_rec.sh /kit/rec_buggy 32'

- `state.sh "<bugs>|all|none" [fixorig]`: reset src/ irr/, apply bug patches (+ upstream fix), rebuild.
- `matrix.sh "label|bugs|extra" ...`: rebuild each state and run the probe test driver.
- `altrun.sh alt|wrong`: buggy tree + non-oracle fixes (all must pass) / compensating wrong fixes
  (must fail). `altfix.py` holds both sets.
- `mkbugs.py OUT`: regenerates bug_01..04.patch from exact-string edits; `mkbundle.sh` regenerates
  test.patch and the merged fix.patch from a committed buggy baseline.
- `make_textures.py`: board strips, the 6-view penguin sheet and the probe textures.
- `scene/yard`: the recording world mod (Minetest Game 5.8.0, v7 seed 135797531); `params.lua` has
  the layout, the penguin loop and the camera path.
- `reference_all_fixed.mp4`: same path rendered with every defect fixed. For reviewers only, never
  ship it to the agent.

Shot list (scene time = video time): 0-3 walk in, 3-15 hold on the yard (penguin: 3-5 right,
5-7 towards camera, 7-12 left, 12-14 away), 15-23 walk round the left board, 23-32 hold behind.

Gotcha: `static_save = false` on a camera-facing sprite in the devtest probe world (player at y=200)
made the billboard invisible on the clean build; the probe entities therefore keep the default.
