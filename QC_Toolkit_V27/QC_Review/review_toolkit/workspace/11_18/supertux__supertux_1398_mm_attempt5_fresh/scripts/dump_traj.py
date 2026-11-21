"""Condense a harbor trajectory.json into readable text.
Usage: python -I dump_traj.py <trajectory.json> <out.txt> [obs_chars]"""
import json, sys, re
src, out = sys.argv[1], sys.argv[2]
obs_n = int(sys.argv[3]) if len(sys.argv) > 3 else 600
d = json.load(open(src, encoding="utf-8"))
lines = []
def clip(s, n):
    s = re.sub(r'"data": "[A-Za-z0-9+/=]{200,}"', '"data": <base64 image>', s)
    return s if len(s) <= n else s[:n] + f" ...[+{len(s)-n} chars]"
for st in d["steps"]:
    sid, src_ = st.get("step_id"), st.get("source")
    msg = st.get("message") or ""
    if isinstance(msg, list):
        msg = " ".join(m.get("text", "") if isinstance(m, dict) else str(m) for m in msg)
    rc = st.get("reasoning_content") or (st.get("extra") or {}).get("reasoning_content") or ""
    head = f"### step {sid} [{src_}] {st.get('timestamp','')}"
    lines.append(head)
    if rc:
        lines.append("THINK: " + clip(str(rc), 4000))
    if msg and sid != 1:
        lines.append("MSG: " + clip(str(msg), 6000))
    for tc in st.get("tool_calls") or []:
        args = tc.get("arguments") or {}
        if tc.get("function_name") in ("Bash",):
            a = args.get("command", "")
        elif tc.get("function_name") in ("Read",):
            a = args.get("file_path", "")
        elif tc.get("function_name") in ("Edit", "Write", "MultiEdit"):
            a = json.dumps(args)[:3000]
        else:
            a = json.dumps(args)[:1500]
        lines.append(f"CALL {tc.get('function_name')}: " + clip(str(a), 3000))
    obs = (st.get("observation") or {}).get("results") or []
    for o in obs:
        c = o.get("content")
        if isinstance(c, list):
            c = " ".join(x.get("text", "<image>") if isinstance(x, dict) else str(x) for x in c)
        c = str(c)
        if c.startswith('{"type": "image"'):
            c = "<image>"
        lines.append("OBS: " + clip(c, obs_n))
open(out, "w", encoding="utf-8").write("\n".join(lines))
print(out, len(lines))
