#!/usr/bin/env bash
set -e
F=/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf
DT="drawtext=fontfile=$F:text='%{pts\:hms}':x=4:y=4:fontsize=14:fontcolor=yellow:box=1:boxcolor=black@0.7"
# 1) first drop past the coin column: 2.2-4.2 s at 15 fps, crop around branch end + coins
ffmpeg -v error -y -ss 2.2 -t 2.0 -i /a/recording.mp4 -vf "fps=15,crop=260:330:440:330,$DT,tile=10x3:padding=2:margin=2" -frames:v 1 /out/strip_coins.png
# 2) second rock: 7.5-11.5 s at 5 fps, crop bonus-block area
ffmpeg -v error -y -ss 7.5 -t 4.0 -i /a/recording.mp4 -vf "fps=5,crop=420:300:230:300,$DT,tile=5x4:padding=2:margin=2" -frames:v 1 /out/strip_leaf.png
# 3) floor part 14-26 s at 2 fps, full frame scaled
ffmpeg -v error -y -ss 14 -t 12 -i /a/recording.mp4 -vf "fps=4,scale=640:-1,$DT,tile=4x3:padding=2:margin=2" /out/strip_floor_%02d.png
ls -la /out/strip_*
