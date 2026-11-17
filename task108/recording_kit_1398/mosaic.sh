#!/bin/bash
# mosaic.sh <video> <out.png> <fps> <cols>x<rows> [start]
ffmpeg -v error -y -ss ${5:-0} -i "$1" -vf "fps=$3,scale=480:-1,drawtext=text='%{pts\:hms}':x=5:y=5:fontcolor=white:box=1:boxcolor=black,tile=$4" -frames:v 1 "$2"
