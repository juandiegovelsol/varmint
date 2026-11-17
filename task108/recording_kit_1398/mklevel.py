#!/usr/bin/env python3
"""mklevel.py <out.stl> <spawn_x> <spawn_y> <objects.txt> [script.nut]
Copy of the repo's own world2/walking_leaves.stl with Tux's spawn point moved, the two
creatures near the start removed, extra objects added and an init-script that drives Tux."""
import re, sys
out, sx, sy, objs = sys.argv[1:5]
script = open(sys.argv[5]).read() if len(sys.argv) > 5 else ""
s = open('/app/data/levels/world2/walking_leaves.stl').read()
s = re.sub(r'\(spawnpoint\s*\(name "main"\)\s*\(x \d+\)\s*\(y \d+\)\s*\)',
           '(spawnpoint (name "main") (x %s) (y %s))' % (sx, sy), s, count=1)
for kind, x, y in (("poisonivy", 736, 992), ("fish", 1264, 1120)):
    s, n = re.subn(r'\(%s\s*\n(\s+\([^()]*\)\s*\n)*?\s+\(x %d\)\s*\n\s+\(y %d\)\s*\n\s+\)' % (kind, x, y), '', s, count=1)
    assert n == 1, kind
extra = open(objs).read()
if script:
    esc = script.replace(chr(92), chr(92) * 2).replace('"', chr(92) + '"')
    extra += '\n    (init-script "%s")\n' % esc
i = s.index('(sector') + len('(sector')
j = s.index('\n', s.index('(name "main")', i))
s = s[:j + 1] + extra + '\n' + s[j + 1:]
open(out, 'w').write(s)
