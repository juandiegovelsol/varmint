#!/usr/bin/env bash
# Runs inside a container: /a = assets (ro), /out = evidence dir (rw). trim keeps the clip's own timestamps.
set -e
F=/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf
DT="drawtext=fontfile=$F:text='%{pts\:hms}':x=4:y=4:fontsize=15:fontcolor=yellow:box=1:boxcolor=black@0.75"
ffmpeg -v error -y -i /a/recording.mp4 -vf "trim=start=2.2:end=4.2,fps=15,crop=260:330:440:330,$DT,tile=10x3:padding=2:margin=2" -frames:v 1 /out/02_first_rock_carried_behind_then_crawls_down_coin_column_2.2-4.2s.png
ffmpeg -v error -y -i /a/recording.mp4 -vf "trim=start=7.5:end=11.5,fps=5,crop=420:300:230:300,$DT,tile=5x4:padding=2:margin=2" -frames:v 1 /out/03_second_rock_carried_behind_then_leaf_frozen_7.5-11.5s.png
ffmpeg -v error -y -i /a/recording.mp4 -vf "fps=2,scale=400:-1,drawtext=fontfile=$F:text='%{pts\:hms}':x=6:y=6:fontsize=18:fontcolor=yellow:box=1:boxcolor=black@0.7,tile=4x13:padding=4:margin=4" -frames:v 1 /out/01_overview_whole_clip_2fps.png
