import hashlib
import json
import os
import py_compile
import re

T = r"c:\Users\juand\OneDrive\Documentos\Outlier\varmint\task109\Attempt4\Tasks\agateau__pixelwheels_362_mm"
FIXED = ["task.toml", "instruction.md", "evidence_bundle.json", "environment/Dockerfile",
         "environment/assets/ASSET_MANIFEST.json", "solution/fix.patch", "solution/solve.sh",
         "tests/config.json", "tests/test.patch", "tests/test.sh", "tests/verifier.py"]
for f in FIXED:
    p = os.path.join(T, f)
    print(f"{f:42s} exists={os.path.exists(p)} bytes={os.path.getsize(p) if os.path.exists(p) else 0}")
for f in ("evidence_bundle.json", "environment/assets/ASSET_MANIFEST.json", "tests/config.json"):
    json.load(open(os.path.join(T, f), encoding="utf-8"))
    print("json ok:", f)
py_compile.compile(os.path.join(T, "tests", "verifier.py"),
                   cfile=os.path.join(os.path.dirname(os.path.abspath(__file__)), "verifier.pyc"), doraise=True)
print("py_compile verifier.py ok")

asset = os.path.join(T, "environment", "assets", "recording.mp4")
sha = hashlib.sha256(open(asset, "rb").read()).hexdigest()
print("disk recording.mp4", os.path.getsize(asset), sha)
man = json.load(open(os.path.join(T, "environment", "assets", "ASSET_MANIFEST.json"), encoding="utf-8"))
eb = json.load(open(os.path.join(T, "evidence_bundle.json"), encoding="utf-8"))
print("ASSET_MANIFEST:", json.dumps(man)[:600])
print("evidence_bundle:", json.dumps(eb)[:900])
ins = open(os.path.join(T, "instruction.md"), encoding="utf-8").read()
print("instruction refs:", re.findall(r"`([^`]*recording[^`]*)`", ins))
docker = open(os.path.join(T, "environment", "Dockerfile"), encoding="utf-8").read()
print("Dockerfile COPY:", re.findall(r"^COPY .*$", docker, re.M))

fix = open(os.path.join(T, "solution", "fix.patch"), encoding="utf-8").read()
paths = set(re.findall(r"^diff --git a/(\S+) b/", fix, re.M))
toml = open(os.path.join(T, "task.toml"), encoding="utf-8").read()
fe = set(re.findall(r'"([^"]+)"', re.search(r"files_edited\s*=\s*\[(.*?)\]", toml, re.S).group(1)))
print("fix.patch paths == files_edited:", paths == fe, len(paths), sorted(paths - fe), sorted(fe - paths))
print("non-source paths:", [p for p in paths if re.search(r"test|\.md$|lock|changes/|CHANGELOG", p, re.I)])
