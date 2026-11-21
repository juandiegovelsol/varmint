"""Annotate clip frames with the six defect locations. Usage: annotate.py <frames dir> <evidence dir>"""
import sys, pathlib
from PIL import Image, ImageDraw, ImageFont
fr, ev = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]); ev.mkdir(parents=True, exist_ok=True)
S = 1.125  # displayed 2000 px -> original 2250 px
try:
    font = ImageFont.truetype("arialbd.ttf", 34)
except OSError:
    font = ImageFont.load_default()
def ann(src, dst, boxes, caption):
    im = Image.open(fr / src).convert("RGB"); d = ImageDraw.Draw(im)
    for (x0, y0, x1, y1, label) in boxes:
        b = [round(v * S) for v in (x0, y0, x1, y1)]
        d.rectangle(b, outline=(220, 30, 30), width=5)
        below = label.endswith(' v')
        label = label[:-2] if below else label
        tx, ty = b[0], (b[3] + 4) if below else max(0, b[1] - 40)
        tw = d.textlength(label, font=font)
        d.rectangle([tx, ty, tx + tw + 12, ty + 40], fill=(220, 30, 30))
        d.text((tx + 6, ty + 2), label, fill="white", font=font)
    canvas = Image.new("RGB", (im.width, im.height + 70), "white")
    canvas.paste(im, (0, 70)); ImageDraw.Draw(canvas).text((20, 15), caption, fill="black", font=font)
    canvas = canvas.resize((1400, round(canvas.height * 1400 / canvas.width)), Image.LANCZOS)
    canvas.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(ev / dst, optimize=True)
ann("t_0.5.png", "01_clip_t0.5_static_defects.png", [
    (400, 315, 680, 365, "D1 untitled chart: x-axis cut"),
    (20, 600, 790, 665, "D1 four-legend row cropped"),
    (240, 1010, 290, 1040, "D1 tick labels collide"),
    (505, 1065, 990, 1245, "D2 spanning chart: toolbar over data v"),
    (820, 1040, 1040, 1068, "D3 x-axis pushed out"),
    (405, 840, 505, 905, "D4 left legend over ticks v"),
    (1150, 830, 1205, 1035, "D4 left toolbar over y-axis"),
    (5, 1520, 1995, 1810, "D6 stretch row: 2nd chart runs off page"),
], "recording.mp4 at t=0.5 s (agent's build, defects 1-4 and 6; red boxes added by QC)")
ann("t_14.8.png", "02_clip_t14.8_after_changes.png", [
    (750, 25, 800, 250, "D5 grown tick labels cut"),
    (1265, 45, 1490, 105, "D5 longer legend overflows"),
    (1480, 25, 1735, 270, "counterpart: shrunk range relaid out"),
], "recording.mp4 at t=14.8 s (after the three charts changed; defect 5)")
