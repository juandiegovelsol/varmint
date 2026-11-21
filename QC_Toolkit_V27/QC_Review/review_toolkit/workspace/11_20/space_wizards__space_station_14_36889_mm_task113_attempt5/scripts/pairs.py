"""Side-by-side crops of the bench: bug (recording.mp4) vs fixed reference, at chosen 2fps frame indices.
Usage: python -I pairs.py <frames dir> <out.png> idx1 idx2 ..."""
import sys, pathlib
from PIL import Image, ImageDraw
fr, out, idxs = pathlib.Path(sys.argv[1]), sys.argv[2], [int(x) for x in sys.argv[3:]]
box = (180, 100, 1110, 600)
rows = []
for i in idxs:
    a = Image.open(fr / "bug" / f"f_{i:03d}.png").crop(box); b = Image.open(fr / "ref" / f"f_{i:03d}.png").crop(box)
    w, h = a.size; r = Image.new("RGB", (w * 2 + 10, h + 26), "white"); r.paste(a, (0, 26)); r.paste(b, (w + 10, 26))
    d = ImageDraw.Draw(r); t = (i - 1) / 2
    d.text((6, 6), f"recording.mp4 (bug)  t={t:.1f}s", fill="black"); d.text((w + 16, 6), f"fixed reference  t={t:.1f}s", fill="black")
    rows.append(r)
W_, H_ = rows[0].size
sheet = Image.new("RGB", (W_, H_ * len(rows)), "white")
for k, r in enumerate(rows): sheet.paste(r, (0, k * H_))
sheet.save(out); print(out, sheet.size)
