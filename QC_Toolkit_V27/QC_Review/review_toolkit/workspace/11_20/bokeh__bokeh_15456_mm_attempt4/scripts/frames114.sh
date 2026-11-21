#!/usr/bin/env bash
set -e
f=/a/recording.mp4
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,nb_frames:format=duration -of compact "$f"
for t in 0.5 3 6 9 12 14.8; do ffmpeg -v error -y -ss $t -i "$f" -frames:v 1 /o/t_${t}.png; done
ffmpeg -v error -y -i "$f" -vf "fps=1,scale=480:-1,tile=4x4" -frames:v 1 /o/sheet.png
