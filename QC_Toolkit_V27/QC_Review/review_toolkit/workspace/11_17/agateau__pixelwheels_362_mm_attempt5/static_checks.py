import hashlib
import json
import py_compile
import tomllib
from pathlib import Path

ROOT = Path(r"c:\Users\juand\OneDrive\Documentos\Outlier\varmint\task109")
A4 = ROOT / "Attempt4" / "Tasks" / "agateau__pixelwheels_362_mm"
A5 = ROOT / "Attempt5" / "Tasks" / "agateau__pixelwheels_362_mm"
HERE = Path(__file__).parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()[:8]


print("== files that differ from Attempt4 (sha256, CRLF count A4 -> A5)")
for p in sorted(A5.rglob("*")):
    if p.is_file():
        rel = p.relative_to(A5)
        q = A4 / rel
        if not q.exists():
            print(f"  NEW  {rel}")
        elif sha(p) != sha(q):
            crlf = (q.read_bytes().count(b"\r\n"), p.read_bytes().count(b"\r\n"))
            print(f"  DIFF {rel}  {sha(q)} -> {sha(p)}  CRLF {crlf[0]} -> {crlf[1]}")
for q in sorted(A4.rglob("*")):
    if q.is_file() and not (A5 / q.relative_to(A4)).exists():
        print(f"  MISSING {q.relative_to(A4)}")

toml = tomllib.loads((A5 / "task.toml").read_text(encoding="utf-8"))
cfg = json.loads((A5 / "tests" / "config.json").read_text(encoding="utf-8"))
print("== task.toml parses; f2p/p2p equal config.json:",
      toml["metadata"]["f2p"] == cfg["f2p"], toml["metadata"]["p2p"] == cfg["p2p"])
print("   task_type:", toml["metadata"]["task_type"], "| tags:", toml["metadata"]["tags"][:4])
for name in ("evidence_bundle.json", "environment/assets/ASSET_MANIFEST.json"):
    json.loads((A5 / name).read_text(encoding="utf-8"))
py_compile.compile(str(A5 / "tests" / "verifier.py"), cfile=str(HERE / "verifier.pyc"), doraise=True)
print("== JSON files parse, verifier.py compiles")

instr = (A5 / "instruction.md").read_text(encoding="utf-8")
banned = ["rocket", "missile", "footbridge", "bridge", "pixelwheels", "agateau", "github", "flame",
          "sideways", "crosswise", "radian", "degree", "angle", "east", "west", "north", "south"]
print("== instruction.md leak words:", [w for w in banned if w in instr.lower()] or "none")
print("   longest line:", max(len(line) for line in instr.splitlines()))
