#!/usr/bin/env bash
set -e
for v in bug:/a/recording.mp4 ref:/k/reference_fixed_state.mp4; do
  n=${v%%:*}; f=${v#*:}
  ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,nb_frames:format=duration -of compact "$f"
  mkdir -p /o/$n
  ffmpeg -v error -y -i "$f" -vf "fps=2,scale=640:-1,tile=4x4" -frames:v 3 /o/$n/sheet_%02d.png
  ffmpeg -v error -y -i "$f" -vf "fps=2" /o/$n/f_%03d.png
done
