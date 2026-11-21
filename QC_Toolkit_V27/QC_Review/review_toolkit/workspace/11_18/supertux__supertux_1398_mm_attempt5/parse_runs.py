import glob
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime

B = r"c:\Users\juand\OneDrive\Documentos\Outlier\varmint\task108\Attempt5"
T = B + r"\Tasks\supertux__supertux_1398_mm"

cfg = json.load(open(T + r"\tests\config.json"))
f2p, p2p = cfg["f2p"], cfg["p2p"]
toml = open(T + r"\task.toml", encoding="utf-8").read()


def arr(key):
    m = re.search(r"^\s*" + key + r"\s*=\s*\[(.*?)\]", toml, re.S | re.M)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else None


for k in ("fail_to_pass", "f2p", "FAIL_TO_PASS"):
    if arr(k) is not None:
        print("task.toml", k, "== config f2p:", arr(k) == f2p)
for k in ("pass_to_pass", "p2p", "PASS_TO_PASS"):
    if arr(k) is not None:
        print("task.toml", k, "== config p2p:", arr(k) == p2p)


def ts(o, k):
    s = (o or {}).get(k)
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


runs = sorted(glob.glob(B + r"\Trials\*\*\verifier"))
runs += [glob.glob(B + r"\Oracle\*\verifier")[0], glob.glob(B + r"\Nop\*\verifier")[0]]
for v in runs:
    d = os.path.dirname(v)
    rid = os.path.basename(d)
    rew = open(v + r"\reward.txt").read().strip()
    r = json.load(open(d + r"\result.json"))
    tot = round((ts(r, "finished_at") - ts(r, "started_at")).total_seconds() / 60, 1)
    ae = r.get("agent_execution") or {}
    am = None
    if ts(ae, "started_at") and ts(ae, "finished_at"):
        am = round((ts(ae, "finished_at") - ts(ae, "started_at")).total_seconds() / 60, 1)
    cases = list(ET.parse(v + r"\junit.xml").getroot().iter("testcase"))
    names = [c.get("classname") + " " + c.get("name") for c in cases]
    res = {}
    for c, nm in zip(cases, names):
        tags = [ch.tag for ch in c]
        res[nm] = "FAIL" if ("failure" in tags or "error" in tags) else ("SKIP" if "skipped" in tags else "PASS")
    ff = [t.split()[1] for t in f2p if res.get(t) != "PASS"]
    pf = [t.split()[1] for t in p2p if res.get(t) != "PASS"]
    idc = sorted(set(names.count(i) for i in f2p + p2p))
    extra = [n.split()[1] for n in names if n not in f2p + p2p]
    print(f"{rid:40s} reward={rew} total={tot}m agent={am}m f2p={7-len(ff)}/7 p2p={3-len(pf)}/3 "
          f"idcount={idc} failed_f2p={ff} failed_p2p={pf} extra_cases={extra}")
