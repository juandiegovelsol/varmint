"""Split fix.patch into one patch per defect. Usage: split_fix.py <fix.patch> <outdir>"""
import sys, re, pathlib
src, outdir = sys.argv[1], pathlib.Path(sys.argv[2])
text = open(src, encoding="utf-8").read().replace("\r\n", "\n")
files = [f for f in re.split(r'(?m)^(?=diff --git )', text) if f.strip()]
assign = {
    ("src/badguy/badguy.cpp", 0): "P1_graze_creature",
    ("src/badguy/badguy.cpp", 1): "P3_squish",
    ("src/badguy/stalactite.cpp", 0): "P7_icicle",
    ("src/object/explosion.cpp", 0): "P6_blast",
    ("src/object/player.cpp", 0): "P2_graze_tux",
    ("src/object/player.cpp", 1): "P5_invincible",
    ("src/object/player.cpp", 2): "P4_one_step",
}
parts, n = {}, 0
for f in files:
    path = re.match(r'diff --git a/(\S+) ', f).group(1)
    head, *hunks = re.split(r'(?m)^(?=@@ )', f)
    for i, h in enumerate(hunks):
        parts.setdefault(assign[(path, i)], {}).setdefault(path, [head]).append(h); n += 1
for p, byfile in parts.items():
    (outdir / f"{p}.patch").write_bytes("".join("".join(c) for c in byfile.values()).encode())
    print(p, sorted(byfile))
assert n == 7, n
