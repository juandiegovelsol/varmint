import glob
import json
import os
import xml.etree.ElementTree as ET

B = r"c:\Users\juand\OneDrive\Documentos\Outlier\varmint\task108\Attempt5"

print("== task digests (lock.json) per run")
for lock in sorted(glob.glob(B + r"\*\*\lock.json") + glob.glob(B + r"\Trials\*\*\lock.json")):
    d = os.path.dirname(lock)
    try:
        j = json.load(open(lock, encoding="utf-8"))
    except Exception as e:
        print(f"  {d[len(B):]}: unreadable ({e})")
        continue
    task = j.get("task") or {}
    print(f"  {d[len(B):]:62s} {str(task.get('digest'))[:19]} {task.get('name')} "
          f"model={(j.get('agent') or {}).get('model_name')}")

print("\n== failure messages and verifier notes")
for v in sorted(glob.glob(B + r"\Trials\*\*\verifier")):
    rid = os.path.basename(os.path.dirname(v))
    print(f"-- {rid}")
    for c in ET.parse(v + r"\junit.xml").getroot().iter("testcase"):
        for ch in c:
            if ch.tag in ("failure", "error"):
                print(f"   {c.get('name')}: {(ch.get('message') or ch.text or '')[:220]}")
    for extra in ("submission-skipped.txt", "test-stderr.txt"):
        p = os.path.join(v, extra)
        if os.path.exists(p):
            print(f"   [{extra}] {open(p, encoding='utf-8', errors='replace').read().strip()[:240]}")
    r = json.load(open(os.path.join(os.path.dirname(v), "result.json"), encoding="utf-8"))
    ae = r.get("agent_execution") or {}
    ar = r.get("agent_result") or {}
    print(f"   timing: trial {r.get('started_at')} -> {r.get('finished_at')} | agent {ae.get('started_at')} -> "
          f"{ae.get('finished_at')} | tokens in/out {ar.get('n_input_tokens')}/{ar.get('n_output_tokens')}")
