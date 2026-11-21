"""Give the mocked shooter Racer a real VehicleRenderer in RocketTest and MissileZOrderTest.

Edits only those two new-file sections of tests/test.patch, then rewrites their hunk header
(line count) and git blob hash. The rebuild of each original file is checked against the blob hash
already in the patch before anything is changed.
"""
import hashlib
import sys
from pathlib import Path

PATCH = Path(sys.argv[1])

STUB = (
    b"        // A real Racer always has a VehicleRenderer; code drawing what it carries may use it.\n"
    b"        when(racer.getVehicleRenderer()).thenReturn(new VehicleRenderer(assets, vehicle));\n"
)

EDITS = {
    b"core-tests/src/com/agateau/pixelwheels/bonus/RocketTest.java": [
        (
            b"import com.agateau.pixelwheels.racer.Vehicle;\n",
            b"import com.agateau.pixelwheels.racer.Vehicle;\n"
            b"import com.agateau.pixelwheels.racer.VehicleRenderer;\n",
        ),
        (
            b'        setField(assets, "turboFlame", new Animation<>(0.1f, flameFrames));\n'
            b"\n"
            b"        scene.missile = Missile.create(",
            b'        setField(assets, "turboFlame", new Animation<>(0.1f, flameFrames));\n'
            + STUB
            + b"\n"
            b"        scene.missile = Missile.create(",
        ),
    ],
    b"core-tests/src/com/agateau/pixelwheels/racescreen/MissileZOrderTest.java": [
        (
            b'        setField(assets, Assets.class, "target", new TextureRegion(missileTexture, 16, 16));\n'
            b"        return Missile.create(assets, gameWorld, mock(AudioManager.class), racer);\n",
            b'        setField(assets, Assets.class, "target", new TextureRegion(missileTexture, 16, 16));\n'
            + STUB
            + b"        return Missile.create(assets, gameWorld, mock(AudioManager.class), racer);\n",
        ),
    ],
}


def blob_hash(content: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(content) + content).hexdigest()


def split_sections(data: bytes):
    lines = data.split(b"\n")
    assert lines[-1] == b"", "patch must end with a newline"
    lines = lines[:-1]
    starts = [i for i, line in enumerate(lines) if line.startswith(b"diff --git ")]
    return [lines[a:b] for a, b in zip(starts, starts[1:] + [len(lines)])]


def rebuild(section, edits):
    hunk = next(i for i, line in enumerate(section) if line.startswith(b"@@ "))
    header, body = section[:hunk], section[hunk + 1:]
    assert section[hunk].startswith(b"@@ -0,0 +1,"), "only new-file sections are supported"
    assert all(line.startswith(b"+") for line in body), "unexpected line in new-file hunk"
    content = b"".join(line[1:] + b"\n" for line in body)

    index = next(i for i, line in enumerate(header) if line.startswith(b"index 0000000.."))
    old_short = header[index].split(b"..")[1].split()[0].decode()
    assert blob_hash(content).startswith(old_short), "rebuilt file does not match the patch"

    for old, new in edits:
        assert content.count(old) == 1, f"anchor not found exactly once: {old[:60]!r}"
        content = content.replace(old, new, 1)

    new_lines = content.split(b"\n")[:-1]
    header[index] = header[index].replace(old_short.encode(), blob_hash(content)[:7].encode())
    hunk_line = b"@@ -0,0 +1,%d @@" % len(new_lines)
    print(f"  {section[0].split()[-1].decode()}: {len(body)} -> {len(new_lines)} lines, "
          f"blob {old_short} -> {blob_hash(content)[:7]}")
    return header + [hunk_line] + [b"+" + line for line in new_lines]


data = PATCH.read_bytes()
assert b"\r" not in data, "patch has CR line endings"
out, done = [], set()
for section in split_sections(data):
    path = section[0].split(b" b/", 1)[1]
    if path in EDITS:
        section = rebuild(section, EDITS[path])
        done.add(path)
    out.extend(section)
assert done == set(EDITS), f"sections not found: {set(EDITS) - done}"
PATCH.write_bytes(b"\n".join(out) + b"\n")
print(f"wrote {PATCH} ({PATCH.stat().st_size} bytes)")
