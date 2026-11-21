set -e
cd /out
F=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
L="drawtext=fontfile=$F:text='%{pts\:hms}':x=4:y=4:fontsize=14:fontcolor=yellow:box=1:boxcolor=black@0.6"
# ss, dur, fps, crop w:h:x:y, cols, name
strip() { ffmpeg -loglevel error -y -ss "$1" -t "$2" -i /a/recording.mp4 -vf "fps=$3,crop=$4,scale=iw*$7:-1:flags=neighbor,setpts=PTS+$1/TB,$L,tile=$5x1:padding=3:color=black" -frames:v 1 "$6.png"; }
strip 0.0 1.5 4 340:260:840:170 6 strip_s1_creature_graze 1
strip 5.6 2.0 3 380:220:400:430 6 strip_s1_tux_graze 1
strip 30.0 3.0 2 520:300:180:440 6 strip_s4_blast 0.75
strip 34.0 8.0 1 1280:800:0:0 8 strip_s5_icicles 0.25
ls -la *.png
