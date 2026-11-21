"""Split fix.patch into one patch per defect. Usage: split_fix.py <fix.patch> <outdir>"""
import sys, re, pathlib
src, outdir = sys.argv[1], pathlib.Path(sys.argv[2])
text = open(src, encoding="utf-8").read()
files = re.split(r'(?m)^(?=diff --git )', text)
files = [f for f in files if f.strip()]
# (file, hunk_index) -> part
assign = {
    ("src/badguy/badguy.cpp", 0): "P5_leaf",
    ("src/object/player.cpp", 0): "P2_throwdir",
    ("src/object/player.cpp", 1): "P1_carry",
    ("src/object/player.cpp", 2): "P4_collides",
    ("src/object/player.hpp", 0): "P4_collides",
    ("src/object/rock.cpp", 0): "P3_group",
    ("src/object/rock.cpp", 1): "P0_coins",
    ("src/object/rock.cpp", 2): "P3_group",
    ("src/object/rock.cpp", 3): "P3_group",
}
parts = {}
for f in files:
    path = re.match(r'diff --git a/(\S+) ', f).group(1)
    head, *hunks = re.split(r'(?m)^(?=@@ )', f)
    for i, h in enumerate(hunks):
        p = assign[(path, i)]
        parts.setdefault(p, {}).setdefault(path, [head]).append(h)
for p, byfile in parts.items():
    body = "".join("".join(chunks) for chunks in byfile.values())
    (outdir / f"{p}.patch").write_bytes(body.replace("\r\n", "\n").encode())
    print(p, sorted(byfile), sum(len(c) - 1 for c in byfile.values()), "hunks")
assert sum(len(c) - 1 for b in parts.values() for c in b.values()) == 9
