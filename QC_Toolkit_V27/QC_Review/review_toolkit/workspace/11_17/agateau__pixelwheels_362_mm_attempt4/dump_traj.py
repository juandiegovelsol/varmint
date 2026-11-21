import glob
import json
import os

B = r"c:\Users\juand\OneDrive\Documentos\Outlier\varmint\task109\Attempt4\Trials"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "traj")
os.makedirs(OUT, exist_ok=True)


def text_of(content, limit):
    """Flatten an observation/message payload to text, replacing images with a marker."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content[:limit]
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                t = c.get("type")
                if t == "image" or "image" in str(t) or "source" in c and isinstance(c.get("source"), dict) and c["source"].get("type") == "base64":
                    path = c.get("path") or (c.get("source") or {}).get("path") or ""
                    parts.append(f"[IMAGE {path}]")
                elif "text" in c:
                    parts.append(str(c["text"])[:limit])
                else:
                    s = json.dumps(c)
                    parts.append("[IMAGE?]" if "base64" in s else s[:limit])
            else:
                parts.append(str(c)[:limit])
        return "\n".join(parts)
    if isinstance(content, dict):
        s = json.dumps(content)
        return "[IMAGE?]" if "base64" in s and len(s) > 5000 else s[:limit]
    return str(content)[:limit]


for tj in sorted(glob.glob(B + r"\*\*\agent\trajectory.json")):
    rid = os.path.basename(os.path.dirname(os.path.dirname(tj)))
    t = json.load(open(tj, encoding="utf-8"))
    lines = []
    keys = set()
    for s in t["steps"]:
        keys.update(s.keys())
        sid = s.get("step_id")
        src = s.get("source")
        msg = s.get("message") or ""
        rc = s.get("reasoning_content") or ""
        if src == "user" and sid == 1:
            lines.append(f"### {sid} USER PROMPT (len {len(msg)})")
            continue
        if rc:
            lines.append(f"### {sid} THINK: {rc[:4000]}")
        if msg:
            lines.append(f"### {sid} {src.upper()} MSG: {text_of(msg, 6000)}")
        for tc in s.get("tool_calls") or []:
            args = tc.get("arguments") or {}
            cmd = args.get("command") or args.get("file_path") or json.dumps(args)
            lines.append(f"### {sid} CALL {tc.get('function_name')}: {str(cmd)[:1500]}")
        obs = s.get("observation") or {}
        for r in obs.get("results") or []:
            lines.append(f"### {sid} OBS: {text_of(r.get('content'), 1200)}")
    with open(os.path.join(OUT, rid + ".txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(rid, "steps", len(t["steps"]), "keys", sorted(keys), "chars", sum(len(x) for x in lines))
