#!/bin/bash
# usage: run_rec.sh OUTDIR DURATION [snap times...]   (runs inside the container)
set -u
OUT=$1; DUR=$2; shift 2
mkdir -p "$OUT"
pkill -f Xvfb 2>/dev/null; pkill -f bin/minetest 2>/dev/null; sleep 1
Xvfb :98 -screen 0 1280x720x24 -nolisten tcp >/dev/null 2>&1 &
sleep 2
export DISPLAY=:98
W=/tmp/recworld; rm -rf $W; mkdir -p $W/worldmods
cp -r /kit/scene/yard $W/worldmods/
printf 'gameid = minetest_game\nbackend = sqlite3\nplayer_backend = sqlite3\nauth_backend = sqlite3\ncreative_mode = true\nenable_damage = false\n' > $W/world.mt
printf 'mg_name = v7\nseed = 135797531\n[end_of_params]\n' > $W/map_meta.txt
cd /app
./bin/minetest --config /kit/minetest.conf --world $W --go --name rec --password "" > "$OUT/client.log" 2>&1 &
PID=$!
for i in $(seq 1 600); do [ -f $W/scene_loaded ] && break; sleep 0.5; done
sleep 1; xdotool mousemove 640 360; sleep 0.3; xdotool keydown F2; sleep 0.25; xdotool keyup F2; sleep 0.3; xdotool keydown F1; sleep 0.25; xdotool keyup F1
for i in $(seq 1 600); do [ -f $W/scene_started ] && break; sleep 0.5; done
if [ ! -f $W/scene_started ]; then echo "scene never started"; tail -30 "$OUT/client.log"; kill $PID; exit 1; fi
if [ "$#" -gt 0 ]; then
  python3 - "$OUT" "$@" <<'PYX'
import subprocess, sys, time
out = sys.argv[1]; t0 = time.time()
for t in sys.argv[2:]:
    while time.time() - t0 < float(t): time.sleep(0.02)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "x11grab", "-draw_mouse", "0", "-video_size", "1280x720",
                    "-i", ":98", "-frames:v", "1", f"{out}/snap_{t}.png"])
PYX
else
  ffmpeg -loglevel error -y -f x11grab -draw_mouse 0 -framerate 30 -video_size 1280x720 -i :98 -t "$DUR" \
    -c:v libx264 -preset veryslow -crf 26 -pix_fmt yuv420p -movflags +faststart "$OUT/recording.mp4"
fi
grep "\[scene\]" "$OUT/client.log" | head -20
grep -i "error" "$OUT/client.log" | head -10
kill $PID; sleep 1; pkill -f "Xvfb :98"
