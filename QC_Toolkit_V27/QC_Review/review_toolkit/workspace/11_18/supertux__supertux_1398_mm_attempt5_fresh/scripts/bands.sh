#!/usr/bin/env bash
set -e
F=/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf
DT="drawtext=fontfile=$F:text='%{eif\:t+$1\:d}.%{eif\:mod((t+$1)*100\,100)\:d:2}s':x=4:y=4:fontsize=18:fontcolor=yellow:box=1:boxcolor=black@0.7"
# $1 = start second, $2 = duration, $3 = fps, $4 = out name
ffmpeg -v error -y -ss $1 -t $2 -i /a/recording.mp4 -vf "fps=$3,crop=1280:230:0:290,$DT,tile=1x12:padding=2" /out/$4_%02d.png
