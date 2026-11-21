"""Summarize harbor trial/oracle/nop runs. Usage: python -I parse_runs.py <Attempt dir>"""
import json, sys, pathlib
from datetime import datetime
root = pathlib.Path(sys.argv[1])
def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
rows = []
# Only the CB run folders: never Check/ or Analyze/ (earlier harbor review output)
for res in sorted(root.glob("Oracle/*/result.json")) + sorted(root.glob("Nop/*/result.json")) + sorted(root.glob("Trials/*/*/result.json")):
    d = json.loads(res.read_text())
    if "trial_name" not in d:
        continue
    tdir = res.parent
    rew_txt = (tdir / "verifier/reward.txt").read_text().strip() if (tdir / "verifier/reward.txt").exists() else "?"
    det = json.loads((tdir / "verifier/reward_detail.json").read_text()) if (tdir / "verifier/reward_detail.json").exists() else {}
    failed = [k for k, v in det.items() if v != "pass"]
    vr = (d.get("verifier_result") or {}).get("rewards", {})
    ae = d.get("agent_execution") or {}
    st, fi = ts(d.get("started_at")), ts(d.get("finished_at"))
    a_st, a_fi = ts(ae.get("started_at")), ts(ae.get("finished_at"))
    rows.append(dict(
        trial=d["trial_name"], path=d["config"]["task"]["path"], checksum=d.get("task_checksum"),
        reward_txt=rew_txt, f2p=f"{vr.get('f2p_passed')}/{vr.get('f2p_total')}", p2p=f"{vr.get('p2p_passed')}/{vr.get('p2p_total')}",
        total_min=round((fi - st).total_seconds() / 60, 1) if st and fi else None,
        agent_min=round((a_fi - a_st).total_seconds() / 60, 1) if a_st and a_fi else None,
        exception=(d.get("exception_info") or {}).get("exception_type") if d.get("exception_info") else None,
        model=((d.get("agent_info") or {}).get("model_info") or {}).get("name"),
        failed=failed))
for r in rows:
    print(json.dumps(r))
