"""Write a self-contained copy of the QC report with evidence PNGs inlined as data URIs."""
import base64
import re
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
html = src.read_text(encoding="utf-8")
evidence = src.parent / "evidence"


def inline(m):
    data = base64.b64encode((evidence / m.group(1)).read_bytes()).decode("ascii")
    return f'src="data:image/png;base64,{data}"'


html, n = re.subn(r'src="evidence/([^"]+\.png)"', inline, html)
dst.write_text(html, encoding="utf-8")
print(f"embedded {n} images -> {dst} ({dst.stat().st_size} bytes)")
