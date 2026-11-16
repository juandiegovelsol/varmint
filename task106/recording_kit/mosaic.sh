#!/bin/bash
# mosaic.sh VIDEO OUT [interval] [cols] [rows] [width]
V=$1; O=$2; I=${3:-2}; C=${4:-4}; R=${5:-4}; W=${6:-426}
ffmpeg -loglevel error -y -i "$V" -vf "fps=1/$I,scale=$W:-1,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='%{pts\:hms}':x=5:y=5:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6,tile=${C}x${R}" -frames:v 1 "$O"
