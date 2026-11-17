#!/bin/bash
# record.sh <level.stl> <out.mp4> <seconds>  -- plays the level on a virtual X display only and grabs it
LV=$1; OUT=$2; SECS=$3
pkill -9 -x supertux2 2>/dev/null; pkill -9 Xvfb 2>/dev/null; sleep 0.5; rm -f /tmp/.X99-lock
Xvfb :99 -screen 0 1280x720x24 -nolisten tcp >/dev/null 2>&1 &
sleep 1.5
export DISPLAY=:99 SDL_AUDIODRIVER=dummy
cd /app
/build/supertux2 --renderer sdl --window --geometry 1280x720 --disable-sound --disable-music "$LV" > /tmp/game.log 2>&1 &
sleep 3
W=""; for i in $(seq 1 20); do W=$(xdotool search --name SuperTux 2>/dev/null | head -1); [ -n "$W" ] && break; sleep 0.3; done
for k in 1 2 3 4 5 6; do xdotool key --window "$W" Return; sleep 0.5; done
ffmpeg -v error -y -f x11grab -draw_mouse 0 -video_size 1280x720 -framerate 30 -i :99 -t "$SECS" \
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$OUT"
pkill -9 -x supertux2; pkill -9 Xvfb
grep -iE "error|SCRIPT|squirrel" /tmp/game.log | grep -v ALSA | head
