#!/usr/bin/env python3
"""Write the recording scene map (yard.map) with the same datafile writer the hidden tests use.

Layout (tile columns; the player spawns at column 10 of row 29, standing on the floor):
  * columns 2-3, rows 26-29 : unhookable block, its right face 208 units left of the spawn
  * column 40, rows 16-29   : tall grass pillar; from column 28 its face is 368 units away (past the
                              hook's reach), from column 29 it is 336 units away (within reach)
  * column 74, row 29       : one-tile grass block; the second tee spawns right behind it (col 75)
  * everything else above the floor is open sky
usage: make_yard.py OUT.map
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from test_harvest_c01_hookline import write_map  # noqa: E402

W, H = 110, 40
rows = [["."] * W for _ in range(H)]
for r in range(30, 34):
    for c in range(W):
        rows[r][c] = "#"
for r in range(26, 30):
    for c in (2, 3):
        rows[r][c] = "x"
for r in range(16, 30):
    rows[r][40] = "#"
rows[29][74] = "#"
rows[29][10] = "S"
rows[29][75] = "D"
write_map(sys.argv[1], ["".join(r) for r in rows])
print("wrote", sys.argv[1])
