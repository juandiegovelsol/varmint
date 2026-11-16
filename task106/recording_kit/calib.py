# find bounding boxes of the probe quads: non-sky pixels, connected regions (run in container)
import sys
from PIL import Image


def regions(path):
    im = Image.open(path).convert("RGB")
    W, H = im.size
    px = im.load()

    def sky(p):
        r, g, b = p
        return (b > 200 and r < 190 and g > 150) or (r > 200 and g > 200 and b > 200 and abs(r - b) < 40)

    seen = bytearray(W * H)
    out = []
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            if seen[y * W + x] or sky(px[x, y]):
                continue
            stack = [(x, y)]
            seen[y * W + x] = 1
            x0 = x1 = x
            y0 = y1 = y
            n = 0
            while stack:
                cx, cy = stack.pop()
                n += 1
                x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
                for nx, ny in ((cx + 2, cy), (cx - 2, cy), (cx, cy + 2), (cx, cy - 2)):
                    if 0 <= nx < W and 0 <= ny < H and not seen[ny * W + nx] and not sky(px[nx, ny]):
                        seen[ny * W + nx] = 1
                        stack.append((nx, ny))
            if n > 150:
                out.append((x0, y0, x1, y1, n, px[(x0 + x1) // 2, (y0 + y1) // 2]))
    return out


for p in sys.argv[1:]:
    print(p)
    for r in sorted(regions(p)):
        print("  ", r)
