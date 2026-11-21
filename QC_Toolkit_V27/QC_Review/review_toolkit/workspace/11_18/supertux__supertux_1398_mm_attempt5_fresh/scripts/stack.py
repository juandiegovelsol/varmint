"""Stack horizontal crops of 2-fps stills with time labels. Usage: stack.py <frames_dir> <out.png> <first_idx> <last_idx> <y0> <y1>"""
import sys
from PIL import Image, ImageDraw
d, out, a, b, y0, y1 = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
ims = []
for i in range(a, b + 1):
    im = Image.open(f"{d}/f2_{i:03d}.png").convert("RGB").crop((0, y0, 1280, y1))
    dr = ImageDraw.Draw(im)
    t = (i - 1) * 0.5
    dr.rectangle((0, 0, 92, 22), fill=(0, 0, 0))
    dr.text((4, 4), f"t={t:.1f}s", fill=(255, 255, 0))
    ims.append(im)
H = sum(im.height + 3 for im in ims)
canvas = Image.new("RGB", (1280, H), (255, 255, 255))
y = 0
for im in ims:
    canvas.paste(im, (0, y)); y += im.height + 3
canvas.save(out)
print(out, canvas.size)
