"""Turn the pipe tables that build_report.py leaves as text into HTML tables; optionally inline evidence PNGs.
Every table in findings.json is written as: intro text, blank line, rows, blank line, more text.
Usage: python -I postprocess_html.py <in.html> <out.html> [--inline-images <evidence_dir>]"""
import base64
import pathlib
import re
import sys

src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
ev_dir = pathlib.Path(sys.argv[sys.argv.index("--inline-images") + 1]) if "--inline-images" in sys.argv else None
html = src.read_text(encoding="utf-8")

SEP = re.compile(r"^\s*:?-{3,}:?\s*$")


def cells(row):
    return [c.strip() for c in row.strip()[1:-1].split("|")]


def is_row(t):
    t = t.strip()
    return len(t) > 2 and t.startswith("|") and t.endswith("|")


def is_sep(t):
    return is_row(t) and all(SEP.match(c) for c in cells(t))


def render(rows):
    head, body = rows[0], [r for r in rows[2:]]
    th = "".join(f"<th>{c}</th>" for c in cells(head))
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in cells(r)) + "</tr>" for r in body)
    return f'<div class="tablewrap qtw"><table class="qt"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


tokens = html.split("<br>")
out, i, n = [], 0, 0
while i < len(tokens):
    if is_row(tokens[i]) and i + 1 < len(tokens) and is_sep(tokens[i + 1]):
        j, rows = i, []
        while j < len(tokens) and is_row(tokens[j]):
            rows.append(tokens[j]); j += 1
        if out and out[-1] == "":
            out.pop()
        prev = out.pop() if out else ""
        if j < len(tokens) and tokens[j] == "":
            j += 1
        nxt = ""
        if j < len(tokens):
            nxt = tokens[j]; j += 1
        out.append(prev + render(rows) + nxt)
        n += 1
        i = j
    else:
        out.append(tokens[i]); i += 1
html = "<br>".join(out)

css = """
.qtw{margin:10px 0 12px}
table.qt{border-collapse:collapse;width:100%;font-size:12.3px;margin:0}
table.qt th,table.qt td{border:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:top}
table.qt th{background:var(--panel2);font-weight:600;font-size:11px;letter-spacing:.02em;text-transform:uppercase;color:var(--fg-dim);white-space:normal}
table.qt tbody tr:nth-child(even){background:color-mix(in srgb,var(--panel2) 55%,transparent)}
.dim .why table.qt{font-size:10.5px}
.dim .why .qtw{overflow-x:auto}
"""
if ".qtw{" not in html:
    html = html.replace("</style>", css + "</style>", 1)

if ev_dir:
    def inline(m):
        p = ev_dir / m.group(1)
        return f'src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}"'
    html = re.sub(r'src="evidence/([^"]+\.png)"', inline, html)

leftover = sum(1 for t in html.split("<br>") if is_row(t))
dst.write_text(html, encoding="utf-8")
print(f"{dst}: {n} tables rendered, {leftover} stray pipe rows left, {len(html)/1e6:.2f} MB")
