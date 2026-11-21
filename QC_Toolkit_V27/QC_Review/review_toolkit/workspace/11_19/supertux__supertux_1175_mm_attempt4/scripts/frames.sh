set -e
cd /out
ffprobe -v error -show_entries format=duration:stream=width,height,r_frame_rate,codec_name -of default=nw=1 /a/recording.mp4
ffmpeg -loglevel error -y -i /a/recording.mp4 -vf "fps=1,scale=320:-1,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\:hms}':x=4:y=4:fontsize=16:fontcolor=yellow:box=1:boxcolor=black@0.6" f_%02d.png
ls f_*.png | wc -l
ffmpeg -loglevel error -y -i f_%02d.png -vf tile=6x7:padding=4:color=black contact_1fps.png
