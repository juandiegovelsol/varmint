"""Generate the PNG textures used by the recording scene and by the hidden probe tests.

usage: make_textures.py SCENE_TEX_DIR PROBE_TEX_DIR
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

FONT = {  # 5x7 glyphs
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
}


def tile(letter, bg, size=32):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([2, 2, size - 3, size - 3], fill=bg + (255,))
    # small dark corner mark at the top-left so orientation is readable at any frame
    d.rectangle([4, 4, 6, 6], fill=(20, 20, 20, 255))
    g = FONT[letter]
    sc = 3
    ox = (size - 5 * sc) // 2
    oy = (size - 7 * sc) // 2
    for y, row in enumerate(g):
        for x, c in enumerate(row):
            if c == "1":
                d.rectangle([ox + x * sc, oy + y * sc, ox + x * sc + sc - 1, oy + y * sc + sc - 1],
                            fill=(15, 15, 15, 255))
    return im


def strip(letters, colors):
    out = Image.new("RGBA", (32, 32 * len(letters)))
    for i, (l, c) in enumerate(zip(letters, colors)):
        out.paste(tile(l, c), (0, 32 * i))
    return out


BLACK = (24, 26, 34, 255)
WHITE = (240, 242, 245, 255)
ORANGE = (255, 150, 20, 255)
EYE = (10, 10, 10, 255)


def penguin_cell(view, step):
    """32x32 cell, transparent background. view: 0 front, 1 looking left, 2 back,
    3 looking right, 4 from above, 5 from below. step: 0/1 walk phase."""
    im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = 1 if step else -1  # foot shift
    if view == 0:  # facing the viewer: white belly, two eyes, beak in the middle
        d.ellipse([7, 3, 24, 28], fill=BLACK)
        d.ellipse([10, 9, 21, 27], fill=WHITE)
        d.ellipse([10, 5, 21, 14], fill=WHITE)
        d.rectangle([12, 8, 13, 9], fill=EYE)
        d.rectangle([18, 8, 19, 9], fill=EYE)
        d.polygon([(14, 11), (17, 11), (15, 14)], fill=ORANGE)
        d.ellipse([4, 12, 9, 22], fill=BLACK)
        d.ellipse([22, 12, 27, 22], fill=BLACK)
        d.rectangle([10 + f, 28, 14 + f, 30], fill=ORANGE)
        d.rectangle([17 - f, 28, 21 - f, 30], fill=ORANGE)
    elif view == 2:  # backing the viewer: all black, little tail, no face
        d.ellipse([7, 3, 24, 28], fill=BLACK)
        d.ellipse([4, 12, 9, 22], fill=BLACK)
        d.ellipse([22, 12, 27, 22], fill=BLACK)
        d.polygon([(13, 26), (18, 26), (15, 30)], fill=BLACK)
        d.rectangle([11 + f, 29, 13 + f, 30], fill=ORANGE)
        d.rectangle([18 - f, 29, 20 - f, 30], fill=ORANGE)
    elif view in (1, 3):  # profile looking to the viewer's left (mirrored for right)
        d.ellipse([9, 3, 24, 28], fill=BLACK)  # body
        d.ellipse([9, 10, 17, 27], fill=WHITE)  # belly on the front (left) side
        d.ellipse([10, 4, 18, 13], fill=WHITE)  # face
        d.rectangle([12, 7, 13, 8], fill=EYE)  # one eye, near the beak
        d.polygon([(10, 9), (3, 11), (10, 12)], fill=ORANGE)  # long beak pointing left
        d.ellipse([16, 12, 22, 23], fill=(10, 12, 18, 255))  # flipper
        d.polygon([(23, 24), (27, 28), (22, 27)], fill=BLACK)  # tail at the back
        d.rectangle([9 + 2 * f, 28, 15 + 2 * f, 30], fill=ORANGE)  # feet point forward
        d.rectangle([14 - 2 * f, 28, 19 - 2 * f, 30], fill=ORANGE)
        if view == 3:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
    elif view == 4:  # from above: black back, beak tip at the top
        d.ellipse([8, 6, 23, 27], fill=BLACK)
        d.ellipse([5, 11, 10, 22], fill=BLACK)
        d.ellipse([21, 11, 26, 22], fill=BLACK)
        d.polygon([(14, 6), (17, 6), (15, 2)], fill=ORANGE)
    elif view == 5:  # from below: white belly and both feet
        d.ellipse([8, 6, 23, 27], fill=WHITE)
        d.rectangle([10, 26, 14, 29], fill=ORANGE)
        d.rectangle([17, 26, 21, 29], fill=ORANGE)
    return im


def penguin_sheet():
    out = Image.new("RGBA", (32 * 6, 32 * 2), (0, 0, 0, 0))
    for v in range(6):
        for s in range(2):
            out.paste(penguin_cell(v, s), (32 * v, 32 * s))
    return out


def main():
    scene, probe = Path(sys.argv[1]), Path(sys.argv[2])
    scene.mkdir(parents=True, exist_ok=True)
    probe.mkdir(parents=True, exist_ok=True)
    front = [(255, 220, 0), (240, 50, 50), (200, 60, 250), (70, 90, 255)]
    back = [(60, 200, 80), (255, 140, 30), (40, 210, 220), (250, 130, 190)]
    strip("ABCD", front).save(scene / "yard_board_front.png")
    strip("EFGK", back).save(scene / "yard_board_back.png")
    penguin_sheet().save(scene / "yard_penguin.png")

    # probe textures: solid fields only, so a test can classify them by colour
    halves = Image.new("RGBA", (16, 16), (40, 200, 40, 255))  # left half green
    ImageDraw.Draw(halves).rectangle([8, 0, 15, 15], fill=(255, 128, 0, 255))  # right half orange
    halves.save(probe / "sprite_probe_halves.png")
    views = [(255, 57, 57), (40, 200, 40), (72, 83, 255), (255, 240, 0), (255, 255, 255), (20, 20, 20)]
    sheet = Image.new("RGBA", (16 * 6, 16), (0, 0, 0, 255))
    for i, c in enumerate(views):
        ImageDraw.Draw(sheet).rectangle([16 * i, 0, 16 * i + 15, 15], fill=c + (255,))
    sheet.save(probe / "sprite_probe_views.png")


if __name__ == "__main__":
    main()
