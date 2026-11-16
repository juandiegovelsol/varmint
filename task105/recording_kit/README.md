# task105 recording kit (not part of the deliverable)

Re-shoots `recording.mp4` headlessly (Xvfb + Mesa llvmpipe + ffmpeg x11grab) inside a container
built from `Tasks/<task_id>/environment` — no window ever opens on the host.

    docker build -t luanti12536:hard Tasks/luanti_org__luanti_12536_mm/environment
    docker run -d --name lu_rec luanti12536:hard sleep infinity
    # Minetest Game 5.5.1: https://github.com/minetest/minetest_game/archive/refs/tags/5.5.1.zip
    docker cp minetest_game-5.5.1 lu_rec:/app/games/minetest_game
    docker exec lu_rec mkdir -p /rec && docker cp scene lu_rec:/rec/ && docker cp run_rec.sh lu_rec:/rec/ && docker cp minetest.conf lu_rec:/rec/
    docker exec lu_rec bash -lc 'chmod +x /rec/run_rec.sh; /rec/run_rec.sh /rec/final 28'
    docker cp lu_rec:/rec/final/recording.mp4 .

`scene/scene/params.lua` holds the tree/fence/gate layout and the camera path; `reference_all_fixed.mp4`
is the same path rendered with every defect fixed (for reviewers only, never ship it to the agent).
