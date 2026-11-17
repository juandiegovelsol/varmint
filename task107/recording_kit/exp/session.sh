#!/bin/bash
# session.sh MAPNAME [display] : start Xvfb + server + client on /kit/maps/MAPNAME.map, leave running.
# fifos: /tmp/s/server.fifo /tmp/s/client.fifo ; logs /tmp/s/*.log ; screenshots in $HOME/.local/share/ddnet/screenshots
set -e
MAP=$1; D=${2:-99}
pkill -f Xvfb || true; pkill -f DDNet || true; sleep 0.5
rm -rf /tmp/s && mkdir -p /tmp/s/home/.local/share/ddnet/maps
cp /kit/maps/$MAP.map /tmp/s/home/.local/share/ddnet/maps/
export HOME=/tmp/s/home DISPLAY=:$D SDL_AUDIODRIVER=dummy LIBGL_ALWAYS_SOFTWARE=1
Xvfb :$D -screen 0 1280x800x24 >/dev/null 2>&1 &
sleep 1
cd /tmp/s
/app/build/DDNet-Server "sv_rcon_password harvest" "sv_map $MAP" "sv_port 18400" "sv_register 0" "sv_test_cmds 1" "sv_input_fifo server.fifo" > server.log 2>&1 &
for i in $(seq 50); do [ -p server.fifo ] && break; sleep 0.1; done
sleep 1
echo "$EXTRA_TUNE" > server.fifo
/app/build/DDNet "gfx_fullscreen 0" "gfx_screen_width 1280" "gfx_screen_height 800" "cl_input_fifo client.fifo" "cl_save_settings 0" "cl_show_hook_coll_own 2" $CLIENT_ARGS "connect 127.0.0.1:18400" > client.log 2>&1 &
for i in $(seq 100); do [ -p client.fifo ] && break; sleep 0.1; done
echo started
