#!/usr/bin/env bash
# Runs inside a container: /a = assets (ro), /out = frames dir (rw)
set -e
F=/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf
# 2 fps full-res stills for close reading
ffmpeg -v error -y -i /a/recording.mp4 -vf "fps=2" /out/f2_%03d.png
# contact sheets: 2 fps, 4x3 tiles per sheet (6 s per sheet), timestamp burned in
ffmpeg -v error -y -i /a/recording.mp4 -vf "fps=2,scale=400:-1,drawtext=fontfile=$F:text='t=%{pts\:hms}':x=6:y=6:fontsize=18:fontcolor=yellow:box=1:boxcolor=black@0.7,tile=4x3:padding=4:margin=4" /out/sheet_%02d.png
ls /out | wc -l
