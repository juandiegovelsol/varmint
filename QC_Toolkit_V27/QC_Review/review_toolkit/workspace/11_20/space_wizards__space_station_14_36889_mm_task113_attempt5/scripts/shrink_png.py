"""Palette-quantize (and optionally downscale) PNGs in place. Usage: shrink_png.py <dir> [max_width]"""
import sys, pathlib
from PIL import Image
d = pathlib.Path(sys.argv[1]); maxw = int(sys.argv[2]) if len(sys.argv) > 2 else 1600
for p in sorted(d.glob("*.png")):
    before = p.stat().st_size
    im = Image.open(p).convert("RGB")
    if im.width > maxw:
        im = im.resize((maxw, round(im.height * maxw / im.width)), Image.LANCZOS)
    im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(p, optimize=True)
    print(f"{p.name}: {before/1e6:.2f} MB -> {p.stat().st_size/1e6:.2f} MB  {im.size}")
