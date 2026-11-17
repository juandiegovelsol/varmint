#!/bin/bash
# start.sh : Xvfb :77 + DDNet-Server (yard map) + DDNet client with the dummy, ready for recording.
# fifos /tmp/r/server.fifo /tmp/r/client.fifo ; HOME=/tmp/r/home
set -e
pkill -x Xvfb 2>/dev/null || true; pkill -x DDNet 2>/dev/null || true; pkill -x DDNet-Server 2>/dev/null || true; sleep 0.5
rm -rf /tmp/r && mkdir -p /tmp/r/home/.local/share/ddnet/maps
python3 /kitsrc/scene/make_yard.py /tmp/r/home/.local/share/ddnet/maps/yard.map
export HOME=/tmp/r/home DISPLAY=:77 SDL_AUDIODRIVER=dummy LIBGL_ALWAYS_SOFTWARE=1
Xvfb :77 -screen 0 1280x800x24 >/dev/null 2>&1 &
sleep 1
cd /tmp/r
/app/build/DDNet-Server "sv_rcon_password harvest" "sv_map yard" "sv_port 18500" "sv_register 0" \
  "sv_test_cmds 1" "sv_motd \"\"" "sv_name \"Hook practice\"" "sv_input_fifo server.fifo" > server.log 2>&1 &
for i in $(seq 50); do [ -p server.fifo ] && break; sleep 0.1; done
sleep 1
/app/build/DDNet "gfx_fullscreen 0" "gfx_screen_width 1280" "gfx_screen_height 800" "gfx_vsync 0" \
  "cl_input_fifo client.fifo" "cl_save_settings 0" "player_name \"hooker\"" "dummy_name \"buddy\"" \
  "cl_show_hook_coll_own 2" "cl_hook_coll_size 20" "cl_show_hook_coll_other 0" \
  "cl_mouse_max_distance 1000" "connect 127.0.0.1:18500" > client.log 2>&1 &
for i in $(seq 100); do [ -p client.fifo ] && break; sleep 0.1; done
until grep -q "ClientId=0" server.log; do sleep 0.3; done
sleep 1
echo "rcon_auth harvest" > client.fifo
echo "dummy_connect" > client.fifo
until grep -q "ClientId=1" server.log; do sleep 0.3; done
sleep 1
echo "cl_dummy 0" > client.fifo
sleep 2
W=$(xdotool search --name DDNet | head -1); xdotool windowfocus $W
echo ready
