import glob
import json
import os
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(r"c:\Users\juand\OneDrive\Documentos\Outlier\varmint\task109\Attempt4\Tasks"
                     r"\agateau__pixelwheels_362_mm\tests\config.json"))
f2p, p2p = cfg["f2p"], cfg["p2p"]
for v in sorted(glob.glob(os.path.join(HERE, "*", "verifier"))):
    name = os.path.basename(os.path.dirname(v))
    j = os.path.join(v, "junit.xml")
    if not os.path.exists(j):
        print(f"{name:26s} (no junit yet)")
        continue
    rew = open(os.path.join(v, "reward.txt")).read().strip()
    res, msg = {}, {}
    for c in ET.parse(j).getroot().iter("testcase"):
        nm = c.get("classname") + " " + c.get("name")
        bad = [ch for ch in c if ch.tag in ("failure", "error")]
        res[nm] = "FAIL" if bad else "PASS"
        if bad:
            msg[nm] = (bad[0].get("message") or "")[:170]
    ff = [t for t in f2p if res.get(t) != "PASS"]
    pf = [t for t in p2p if res.get(t) != "PASS"]
    print(f"{name:26s} reward={rew} f2p={7-len(ff)}/7 p2p={2-len(pf)}/2")
    for t in ff + pf:
        print(f"    FAIL {t.split()[1]}: {msg.get(t, 'missing')}")
