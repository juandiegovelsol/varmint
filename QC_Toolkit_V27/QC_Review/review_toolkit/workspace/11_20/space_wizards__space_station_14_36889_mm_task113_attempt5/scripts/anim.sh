#!/usr/bin/env bash
# lane 6 door tile, every frame from t=1.8s to 4.2s, tiled 12 per row
ffmpeg -v error -y -ss 1.8 -i /a/recording.mp4 -t 2.4 -vf "crop=110:110:937:330,scale=110:110,tile=12x6" -frames:v 1 /o/anim_bug.png
ffmpeg -v error -y -ss 1.8 -i /k/reference_fixed_state.mp4 -t 2.4 -vf "crop=110:110:937:330,scale=110:110,tile=12x6" -frames:v 1 /o/anim_ref.png
