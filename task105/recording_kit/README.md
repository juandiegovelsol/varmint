# task105 recording kit (not part of the deliverable)

Re-shoots `recording.mp4` headlessly (Xvfb + Mesa llvmpipe + ffmpeg x11grab) inside a container
built from `Tasks/<task_id>/environment` -- no window ever opens on the host. The container needs
`xdotool` (`apt-get install -y xdotool`) on top of the task image.

    docker build -t luanti12536:hard Tasks/luanti_org__luanti_12536_mm/environment
    docker run -d --name lu_rec luanti12536:hard sleep infinity
    docker exec lu_rec bash -lc 'apt-get update && apt-get install -y xdotool'
    # Minetest Game 5.5.1: https://github.com/minetest/minetest_game/archive/refs/tags/5.5.1.zip
    docker cp minetest_game-5.5.1 lu_rec:/app/games/minetest_game
    docker exec lu_rec mkdir -p /rec && docker cp scene lu_rec:/rec/ && docker cp run_rec.sh lu_rec:/rec/ && docker cp minetest.conf lu_rec:/rec/
    docker exec lu_rec bash -lc 'chmod +x /rec/run_rec.sh; /rec/run_rec.sh /rec/final 49'
    docker cp lu_rec:/rec/final/recording.mp4 .

`run_rec.sh OUT 49 t1 t2 ...` takes PNG snapshots at those scene times instead of a video.

`scene/scene/params.lua` holds the layout (tree, fence and gate, water channel, rail track with two
ramps, a curve and a branch, torch post, 3 x 2 glass window) and the camera path; `minetest.conf`
turns on `connected_glass`. `reference_all_fixed.mp4` is the same path rendered with every defect
fixed (base commit + upstream fix): for reviewers only, never ship it to the agent.

Shot list (scene time = video time): 0-12 tree, 12-15 fence at the trunk, 15-21 water channel,
21-27 rail track, 27-36 around the torch post, 36-42 glass window, 42-49 terrace from above.
