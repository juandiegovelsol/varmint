"""Static bundle checks. Usage: bundle_checks.py <task_dir> <oracle_junit.xml> <nop_junit.xml>"""
import sys, json, hashlib, re, pathlib, py_compile, tomllib
import xml.etree.ElementTree as ET
T = pathlib.Path(sys.argv[1]); oj, nj = sys.argv[2], sys.argv[3]
print("== dim 1: fixed files")
fixed = ["task.toml", "instruction.md", "evidence_bundle.json", "environment/Dockerfile",
         "environment/assets/ASSET_MANIFEST.json", "solution/fix.patch", "solution/solve.sh",
         "tests/config.json", "tests/test.patch", "tests/test.sh", "tests/verifier.py"]
for f in fixed:
    p = T / f
    print(f"  {f:42s} exists={p.exists()} bytes={p.stat().st_size if p.exists() else 0}")
for f in ["evidence_bundle.json", "environment/assets/ASSET_MANIFEST.json", "tests/config.json"]:
    json.loads((T / f).read_text(encoding="utf-8")); print(f"  JSON ok: {f}")
toml = tomllib.loads((T / "task.toml").read_text(encoding="utf-8")); print("  TOML ok: task.toml")
py_compile.compile(str(T / "tests/verifier.py"), cfile=str(pathlib.Path(sys.argv[0]).parent / "_verifier.pyc"), doraise=True)
print("  py_compile ok: tests/verifier.py")
extra = sorted(str(p.relative_to(T)).replace("\\", "/") for p in T.rglob("*") if p.is_file() and str(p.relative_to(T)).replace("\\", "/") not in fixed)
print("  extra files:", extra)

print("== dim 10: fix scope")
fix = (T / "solution/fix.patch").read_text(encoding="utf-8")
paths = sorted(set(re.findall(r"^diff --git a/(\S+) b/", fix, re.M)))
fe = sorted(toml["metadata"]["files_edited"])
print("  diff paths :", paths); print("  files_edited:", fe); print("  equal:", paths == fe)
print("  test/doc/lock paths in fix:", [p for p in paths if re.search(r"(^|/)(tests?|docs?)/|\.md$|lock|changeset|CHANGELOG", p)])
tp = (T / "tests/test.patch").read_text(encoding="utf-8")
cfg = json.loads((T / "tests/config.json").read_text(encoding="utf-8"))
print("  test.patch paths:", sorted(set(re.findall(r"^diff --git a/(\S+) b/", tp, re.M))), " config test_files:", cfg["test_files"])

print("== dim 12: ids")
print("  f2p equal:", toml["metadata"]["f2p"] == cfg["f2p"], " p2p equal:", toml["metadata"]["p2p"] == cfg["p2p"])
print("  f2p/p2p overlap:", set(cfg["f2p"]) & set(cfg["p2p"]))
def cases(path):
    out = {}
    for tc in ET.parse(path).getroot().iter("testcase"):
        tags = {c.tag for c in tc}
        out.setdefault(f"{tc.get('classname','')} {tc.get('name','')}", []).append("fail" if tags & {"failure", "error"} else "skip" if "skipped" in tags else "pass")
    return out
o, n = cases(oj), cases(nj)
print("  junit testcases (oracle):", len(o))
for t in cfg["f2p"] + cfg["p2p"]:
    exact = [k for k in o if k == t]; suffix = [k for k in o if k.endswith(t)]
    print(f"  {'f2p' if t in cfg['f2p'] else 'p2p'} {t:60s} exact={len(exact)} suffix={len(suffix)} oracle={o.get(t)} nop={n.get(t)}")

print("== dim 8: evidence chain")
asset = T / "environment/assets/recording.mp4"
sha = hashlib.sha256(asset.read_bytes()).hexdigest(); size = asset.stat().st_size
man = json.loads((T / "environment/assets/ASSET_MANIFEST.json").read_text(encoding="utf-8"))
ev = json.loads((T / "evidence_bundle.json").read_text(encoding="utf-8"))
print(f"  disk: recording.mp4 sha256={sha} bytes={size}")
for m in man: print("  manifest:", {k: m.get(k) for k in ("file", "container_path", "sha256", "bytes", "role")})
for e in ev: print("  evidence:", {k: e.get(k) for k in ("file", "local_path", "container_path", "sha256", "bytes", "role", "url", "source_kind")})
ins = (T / "instruction.md").read_text(encoding="utf-8")
print("  instruction refs:", re.findall(r"/app/\.harbor_assets/\S+?(?=`|\s)", ins), " backtick names:", re.findall(r"`([^`]+\.(?:mp4|png|gif|jpg|webm))`", ins))
dock = (T / "environment/Dockerfile").read_text(encoding="utf-8")
print("  Dockerfile COPY:", re.findall(r"^COPY .*assets.*$", dock, re.M), " base_commit in Dockerfile:", toml["metadata"]["base_commit"] in dock)

print("== dim 3: leak scan of instruction.md")
for pat in ["space", "station", "wizard", "firelock", "github", "http", "issue", "36889", "46007", r"\.cs", r"\.yml", "meta.json", "rsi", "atmos", "plasma", "gas", "threshold", "door", "glass", "edge", "lattice", "temperature", "pressure", "animation", "frame", "element", "danger", "smooth", "controlled", "aligned"]:
    hits = [m.start() for m in re.finditer(pat, ins, re.I)]
    if hits: print(f"  '{pat}': {len(hits)} hit(s) ->", [ins[max(0,h-30):h+40].replace(chr(10),' ') for h in hits[:3]])
print("  word count:", len(ins.split()))
