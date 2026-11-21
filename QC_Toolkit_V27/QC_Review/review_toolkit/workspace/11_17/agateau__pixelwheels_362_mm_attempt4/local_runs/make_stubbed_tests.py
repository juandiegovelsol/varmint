"""Copy tests/ and stub Racer.getVehicleRenderer() in the RocketTest and MissileZOrderTest mocks (same line count)."""
import os
import shutil

SRC = r"c:\Users\juand\OneDrive\Documentos\Outlier\varmint\task109\Attempt4\Tasks\agateau__pixelwheels_362_mm\tests"
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests_stubbed")
os.makedirs(DST, exist_ok=True)
for f in ("config.json", "test.sh", "verifier.py"):
    shutil.copyfile(os.path.join(SRC, f), os.path.join(DST, f))

raw = open(os.path.join(SRC, "test.patch"), "rb").read()
assert b"\r\n" not in raw
lines = raw.decode("utf-8").split("\n")
target = "+        when(racer.getVehicle()).thenReturn(vehicle);"
repl = (target + " com.agateau.pixelwheels.racer.VehicleRenderer qcRenderer ="
        " mock(com.agateau.pixelwheels.racer.VehicleRenderer.class);"
        " when(qcRenderer.getBatchColor()).thenReturn(com.badlogic.gdx.graphics.Color.WHITE);"
        " when(racer.getVehicleRenderer()).thenReturn(qcRenderer);")
for idx in (152, 720):  # test.patch lines 153 (RocketTest) and 721 (MissileZOrderTest)
    assert lines[idx] == target, (idx, lines[idx])
    lines[idx] = repl
open(os.path.join(DST, "test.patch"), "wb").write("\n".join(lines).encode("utf-8"))
print("stubbed test.patch written", len(lines), "lines")
