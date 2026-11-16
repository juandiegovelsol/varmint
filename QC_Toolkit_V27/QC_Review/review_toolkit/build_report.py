#!/usr/bin/env python3
"""Render a task's QC_Report/findings.json into QC_Report_<hash>.html and .md.

Usage (from QC_Review/):
    python3 review_toolkit/build_report.py 10_28/<task-hash>

Reads  <date>/<hash>/QC_Report/findings.json
Writes <date>/<hash>/QC_Report/QC_Report_<hash>.html and QC_Report_<hash>.md
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) != 2:
    sys.exit(__doc__)
REPORT_DIR = (ROOT / sys.argv[1] / "QC_Report").resolve()
data = json.loads((REPORT_DIR / "findings.json").read_text())
dims = data["dimensions"]
gates = data.get("gates", [])
trials = data.get("trials", [])
H = data["task_hash"]

LABEL = {5: "Pass", 3: "Non-Fail", 2: "Fail", 1: "Unauditable"}


def is_issue(d):
    return d["score"] < 5 or not d["wrong"].startswith("Nothing found")


def inline(text):
    """Escape, then render `code` and **bold**."""
    t = html.escape(text)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    return t.replace("\n", "<br>")


def esc(t):
    return html.escape(str(t))


# ---------------------------------------------------------------- Markdown
md = [f"# QC Report: {data['task_id']}", "",
      f"- **Task hash:** `{H}`", f"- **Title:** {data['title']}", f"- **Rubric:** {data['rubric']}",
      f"- **Review date:** {data['review_date']}",
      f"- **Verdict:** **{data['verdict']}**. {data['verdict_reason']}", "",
      "## Scorecard", "", "| # | Dimension | Score | Result | Error category |", "|---|---|---|---|---|"]
md += [f"| {i} | {d['name']} | {d['score']} | {LABEL[d['score']]} | {d['category'] or '—'} |"
       for i, d in enumerate(dims, 1)]
if gates:
    md += ["", "## Delivery gate", "", "| # | Check | Result | Detail |", "|---|---|---|---|"]
    md += [f"| {i} | {g['label']} | {g['status'].upper()} | {g['detail']} |" for i, g in enumerate(gates, 1)]
if trials:
    md += ["", "## Trials", "", "| Trial | Mode | Reward | f2p | p2p | Minutes | Failed tests |", "|---|---|---|---|---|---|---|"]
    md += [f"| {t['id']} | {t['mode']} | {t['reward']} | {t['f2p']} | {t['p2p']} | {t['minutes']} | {'; '.join(t['failed']) or '—'} |"
           for t in trials]
md += ["", "## Issues & suggested fixes", ""]
for d in dims:
    if is_issue(d):
        md += [f"### {d['name']}: {d['score']} {d['category']}".rstrip(), "",
               f"**What is wrong:** {d['wrong']}", "", f"**Suggested fix:** {d['fix']}", ""]
md += ["## Dimension details", ""]
for i, d in enumerate(dims, 1):
    md += [f"### {i}. {d['name']}: {d['score']} ({LABEL[d['score']]}) {d['category']}".rstrip(), "",
           f"**Evidence:** {d['evidence']}", "", f"**What is wrong:** {d['wrong']}", "",
           f"**Suggested fix:** {d['fix']}", ""]
(REPORT_DIR / f"QC_Report_{H}.md").write_text("\n".join(md))

# ---------------------------------------------------------------- HTML pieces
n5 = sum(d["score"] == 5 for d in dims)
n3 = sum(d["score"] == 3 for d in dims)
n2 = sum(d["score"] == 2 for d in dims)
accept = data["verdict"].upper() != "FAIL"
vcls = "accept" if accept else "reject"

grid = "".join(
    f"""<div class="dim s{d['score']} clk"><span class="sc">{d['score']}</span><div class="no">#{i}</div>
<div class="nm">{esc(d['name'])}</div>{f'<div class="ct">{esc(d["category"])}</div>' if d['category'] else ''}
<div class="why">{inline(d['wrong'] if is_issue(d) else d['evidence'])}</div></div>"""
    for i, d in enumerate(dims, 1))

PILL = {"pass": ("ok", "PASS"), "fail": ("no", "FAIL"), "warn": ("nf", "NOTE")}
gate_html = "".join(
    f"""<div class="gate"><div class="i">{i}</div><div class="l">{esc(g['label'])}</div>
<div><span class="pill {PILL[g['status']][0]}">{PILL[g['status']][1]}</span></div><div class="e">{inline(g['detail'])}</div></div>"""
    for i, g in enumerate(gates, 1))

trial_rows = "".join(
    f"""<tr><td><code>{esc(t['id'])}</code></td><td>{esc(t['mode'])}</td>
<td><strong class="{'v5' if t['reward'] == 1 else 'v2'}">{t['reward']}</strong></td><td>{esc(t['f2p'])}</td>
<td>{esc(t['p2p'])}</td><td>{t['minutes']}</td><td>{'<br>'.join(esc(f) for f in t['failed']) or '—'}</td></tr>"""
    for t in trials)

issues_html = "".join(
    f"""<h3>{esc(d['name'])} <span class="pill {'no' if d['score'] == 2 else 'nf' if d['score'] == 3 else 'mute'}">{d['score']}{' · ' + esc(d['category']) if d['category'] else ' · note'}</span></h3>
<blockquote><p><strong>What is wrong.</strong> {inline(d['wrong'])}</p></blockquote>
<p><strong>Suggested fix.</strong> {inline(d['fix'])}</p>"""
    for d in sorted((d for d in dims if is_issue(d)), key=lambda d: d["score"]))

detail_html = "".join(
    f"""<h3>{i}. {esc(d['name'])} <span class="pill {'ok' if d['score'] == 5 else 'nf' if d['score'] == 3 else 'no'}">{d['score']} · {LABEL[d['score']]}</span></h3>
{f'<p class="catline">{esc(d["category"])}</p>' if d['category'] else ''}
<table class="kv"><tbody>
<tr><th>Evidence</th><td>{inline(d['evidence'])}</td></tr>
<tr><th>What is wrong</th><td>{inline(d['wrong'])}</td></tr>
<tr><th>Suggested fix</th><td>{inline(d['fix'])}</td></tr>
</tbody></table>"""
    for i, d in enumerate(dims, 1))

evidence_imgs = sorted(p.name for p in (REPORT_DIR / "evidence").glob("*.png")) if (REPORT_DIR / "evidence").is_dir() else []
evidence_html = "".join(f'<figure><img src="evidence/{esc(n)}" alt="{esc(n)}" loading="lazy"><figcaption>{esc(n)}</figcaption></figure>'
                        for n in evidence_imgs)

CSS = """
:root{--bg:#0e1013;--panel:#15181d;--panel2:#1b1f26;--line:#272c35;--fg:#e7e9ee;--fg-dim:#a3aab8;--fg-faint:#6f7787;
  --pass:#3fb27f;--nf:#d9a13b;--fail:#e0574f;--accent:#6f9dff;--shadow:0 1px 2px rgba(0,0,0,.35),0 8px 24px rgba(0,0,0,.22)}
html.light{--bg:#faf9f7;--panel:#fff;--panel2:#f3f2ef;--line:#e3e1dc;--fg:#1c1e22;--fg-dim:#5c6270;--fg-faint:#8b91a0;
  --pass:#1f8a5c;--nf:#a9741a;--fail:#c0392f;--accent:#2f5fd0;--shadow:0 1px 2px rgba(20,20,25,.06),0 8px 24px rgba(20,20,25,.06)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:'DM Sans',system-ui,sans-serif;font-size:15.5px;line-height:1.65;-webkit-font-smoothing:antialiased}
a{color:var(--accent)}
#bar{position:fixed;top:0;left:0;height:3px;background:var(--accent);width:0;z-index:99;transition:width .1s}
.wrap{display:grid;grid-template-columns:270px minmax(0,1fr);max-width:1500px;margin:0 auto}
aside{position:sticky;top:0;height:100vh;overflow-y:auto;padding:26px 18px 40px;border-right:1px solid var(--line);background:var(--panel)}
aside .brand{font-family:'Instrument Serif',serif;font-size:25px;line-height:1.15;margin-bottom:2px}
aside .sub{font-family:'JetBrains Mono',monospace;font-size:10.5px;color:var(--fg-faint);letter-spacing:.06em;text-transform:uppercase;margin-bottom:20px}
aside a{display:block;padding:4px 8px;border-radius:6px;color:var(--fg-dim);text-decoration:none;font-size:13px;border-left:2px solid transparent}
aside a:hover{background:var(--panel2);color:var(--fg)}
aside a.h3{padding-left:20px;font-size:12.2px;color:var(--fg-faint)}
aside a.on{color:var(--fg);border-left-color:var(--accent);background:var(--panel2)}
.themebtn{margin-top:22px;width:100%;padding:7px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);color:var(--fg-dim);font-family:'DM Sans',sans-serif;font-size:12.5px;cursor:pointer}
.themebtn:hover{color:var(--fg)}
main{padding:34px 44px 120px;min-width:0}
.hero{margin-bottom:26px}
.eyebrow{font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--fg-faint)}
h1.title{font-family:'Instrument Serif',serif;font-weight:400;font-size:46px;line-height:1.05;margin:6px 0 4px;overflow-wrap:anywhere}
.taskid{font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--fg-dim);overflow-wrap:anywhere}
.subtitle{color:var(--fg-dim);margin-top:6px}
.verdict{display:inline-flex;align-items:center;gap:10px;margin-top:16px;padding:9px 16px;border-radius:999px;font-weight:600;font-size:14px;border:1px solid}
.verdict.reject{color:var(--fail);border-color:color-mix(in srgb,var(--fail) 45%,transparent);background:color-mix(in srgb,var(--fail) 11%,transparent)}
.verdict.accept{color:var(--pass);border-color:color-mix(in srgb,var(--pass) 45%,transparent);background:color-mix(in srgb,var(--pass) 11%,transparent)}
.verdict .dot{width:9px;height:9px;border-radius:50%;background:currentColor;flex:none}
.reason{margin-top:12px;color:var(--fg-dim);max-width:820px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:24px 0 30px}
.metric{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:13px 15px;box-shadow:var(--shadow)}
.metric .k{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--fg-faint)}
.metric .v{font-family:'Instrument Serif',serif;font-size:30px;line-height:1.15;margin-top:3px}
.metric .v small{font-family:'DM Sans',sans-serif;font-size:13px;color:var(--fg-dim)}
.metric.p .v{color:var(--pass)} .metric.f .v{color:var(--fail)} .metric.n .v{color:var(--nf)}
section.card{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:22px 24px;margin:0 0 26px;box-shadow:var(--shadow)}
section.card>h2{font-family:'Instrument Serif',serif;font-weight:400;font-size:26px;margin:0 0 4px}
section.card>.hint{color:var(--fg-dim);font-size:13.5px;margin:0 0 18px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(196px,1fr));gap:9px}
.dim{position:relative;border:1px solid var(--line);border-radius:9px;padding:10px 11px 11px 13px;background:var(--panel2);overflow:hidden}
.dim::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--fg-faint)}
.dim.s5::before{background:var(--pass)} .dim.s3::before{background:var(--nf)} .dim.s2::before,.dim.s1::before{background:var(--fail)}
.dim .no{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--fg-faint)}
.dim .nm{font-size:12.6px;line-height:1.3;margin-top:2px;padding-right:22px}
.dim .ct{font-size:11px;color:var(--fail);margin-top:4px}
.dim .sc{position:absolute;top:9px;right:10px;font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:500;padding:1px 6px;border-radius:5px}
.dim.s5 .sc{color:var(--pass);background:color-mix(in srgb,var(--pass) 14%,transparent)}
.dim.s3 .sc{color:var(--nf);background:color-mix(in srgb,var(--nf) 14%,transparent)}
.dim.s2 .sc,.dim.s1 .sc{color:var(--fail);background:color-mix(in srgb,var(--fail) 14%,transparent)}
.dim.s2{border-color:color-mix(in srgb,var(--fail) 40%,var(--line))}
.dim .why{display:none;margin-top:8px;padding-top:8px;border-top:1px dashed var(--line);font-size:12px;color:var(--fg-dim);line-height:1.5}
.dim.open .why{display:block}
.dim.clk{cursor:pointer} .dim.clk:hover{border-color:var(--accent)}
.gates{display:grid;gap:9px}
.gate{display:grid;grid-template-columns:26px 1fr auto;gap:2px 12px;align-items:start;padding:11px 13px;border:1px solid var(--line);border-radius:9px;background:var(--panel2)}
.gate .i{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--fg-faint);padding-top:2px}
.gate .l{font-size:13.5px}
.gate .e{grid-column:2/4;font-size:12.2px;color:var(--fg-dim)}
.pill{font-family:'JetBrains Mono',monospace;font-size:10.5px;padding:2px 8px;border-radius:999px;white-space:nowrap;font-weight:500;vertical-align:middle}
.pill.ok{color:var(--pass);background:color-mix(in srgb,var(--pass) 14%,transparent)}
.pill.no{color:var(--fail);background:color-mix(in srgb,var(--fail) 14%,transparent)}
.pill.nf{color:var(--nf);background:color-mix(in srgb,var(--nf) 14%,transparent)}
.pill.mute{color:var(--fg-dim);background:var(--panel2);border:1px solid var(--line)}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin-top:16px;font-size:12.4px;color:var(--fg-dim)}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px}
.body{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:8px 30px 34px;box-shadow:var(--shadow)}
.body h2{font-family:'Instrument Serif',serif;font-weight:400;font-size:30px;margin:38px 0 10px;padding-top:14px;border-top:1px solid var(--line)}
.body h2:first-of-type{border-top:none;margin-top:22px}
.body h3{font-weight:600;font-size:17px;margin:26px 0 8px}
.body p{margin:11px 0}
.body code{font-family:'JetBrains Mono',monospace;font-size:.86em;background:var(--panel2);border:1px solid var(--line);border-radius:4px;padding:1px 5px;overflow-wrap:anywhere}
.body blockquote{margin:14px 0;padding:2px 16px;border-left:3px solid var(--fail);background:color-mix(in srgb,var(--fail) 6%,transparent);border-radius:0 7px 7px 0;color:var(--fg-dim)}
.body blockquote strong{color:var(--fg)}
.body table{width:100%;border-collapse:collapse;margin:14px 0;font-size:12.9px}
.tablewrap{overflow-x:auto}
.body th,.body td{border:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}
.body th{background:var(--panel2);font-weight:600;font-size:11.4px;letter-spacing:.02em;text-transform:uppercase;color:var(--fg-dim);white-space:nowrap}
.body table.kv th{width:150px}
.body tbody tr:nth-child(even){background:color-mix(in srgb,var(--panel2) 55%,transparent)}
.body td strong.v5{color:var(--pass)} .body td strong.v2{color:var(--fail)}
.catline{color:var(--fail);font-size:13px;margin:-4px 0 6px}
figure{margin:14px 0} figure img{max-width:100%;border:1px solid var(--line);border-radius:8px;display:block}
figcaption{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--fg-faint);margin-top:4px}
@media (max-width:1080px){.wrap{grid-template-columns:1fr}
  aside{position:static;height:auto;border-right:none;border-bottom:1px solid var(--line)}
  main{padding:26px 16px 80px} h1.title{font-size:34px} .body{padding:8px 16px 26px}}
"""

JS = """
function tt(){var l=document.documentElement.classList.toggle('light');try{localStorage.setItem('theme',l?'light':'dark')}catch(e){}}
document.querySelectorAll('.dim.clk').forEach(function(d){d.addEventListener('click',function(){d.classList.toggle('open')})});
var toc=document.getElementById('toc');
var heads=[].slice.call(document.querySelectorAll('section.card>h2, #body h2, #body h3'));
heads.forEach(function(h,i){h.id='h'+i;var a=document.createElement('a');a.href='#h'+i;
  a.textContent=h.childNodes[0].textContent.replace(/\\s+/g,' ').trim();if(h.tagName==='H3')a.className='h3';toc.appendChild(a)});
var links=[].slice.call(toc.querySelectorAll('a'));
function onScroll(){var st=window.scrollY,h=document.body.scrollHeight-innerHeight;
  document.getElementById('bar').style.width=(h>0?st/h*100:0)+'%';var cur=0;
  heads.forEach(function(x,i){if(x.getBoundingClientRect().top<130)cur=i});
  links.forEach(function(a,i){a.classList.toggle('on',i===cur)})}
addEventListener('scroll',onScroll,{passive:true});onScroll();
"""

with_img = [t for t in trials if t["mode"] == "with-image"]
no_img = [t for t in trials if t["mode"] == "no-image"]
wi_pass = sum(t["reward"] == 1 for t in with_img)
ni_pass = sum(t["reward"] == 1 for t in no_img)

page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QC Eval {esc(H)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script>(function(){{try{{if(localStorage.getItem('theme')!=='dark')document.documentElement.classList.add('light')}}catch(e){{document.documentElement.classList.add('light')}}}})();</script>
<style>{CSS}</style></head>
<body><div id="bar"></div><div class="wrap">
<aside><div class="brand">QC Evaluation</div><div class="sub">{esc(data['rubric'])} · {len(dims)} dims</div>
<nav id="toc"></nav><button class="themebtn" onclick="tt()">Toggle theme</button></aside>
<main>
<div class="hero">
  <div class="eyebrow">{esc(data.get('eyebrow', 'QC review'))} · {esc(data.get('date_folder', ''))} · {esc(data['review_date'])}</div>
  <h1 class="title">Eval: {esc(data['task_id'])}</h1>
  <div class="taskid">task {esc(H)}</div>
  <div class="subtitle">{esc(data['title'])}</div>
  <div class="verdict {vcls}"><span class="dot"></span>{'Accept' if accept else 'Reject'}: {esc(data['verdict'])}</div>
  <p class="reason">{inline(data['verdict_reason'])}</p>
</div>
<div class="metrics">
  <div class="metric {'p' if accept else 'f'}"><div class="k">Decision</div><div class="v">{'Accept' if accept else 'Reject'}</div></div>
  <div class="metric p"><div class="k">Dimensions at 5</div><div class="v">{n5}<small>/{len(dims)}</small></div></div>
  <div class="metric {'f' if n2 else 'p'}"><div class="k">Fails (2)</div><div class="v">{n2}</div></div>
  <div class="metric {'n' if n3 else 'p'}"><div class="k">Non-Fails (3)</div><div class="v">{n3}</div></div>
  <div class="metric {'p' if ni_pass == 0 else 'f'}"><div class="k">No-image pass</div><div class="v">{ni_pass}<small>/{len(no_img)} · need 0</small></div></div>
  <div class="metric {'p' if wi_pass == 1 else 'f'}"><div class="k">With-image pass</div><div class="v">{wi_pass}<small>/{len(with_img)} · need 1</small></div></div>
</div>
<section class="card"><h2>Scorecard</h2>
  <p class="hint">Every dimension in rubric order. Click a cell to see what is wrong (or the evidence, if it passed).</p>
  <div class="grid">{grid}</div>
  <div class="legend"><span><i style="background:var(--pass)"></i>5 · Pass</span><span><i style="background:var(--nf)"></i>3 · Non-Fail</span>
  <span><i style="background:var(--fail)"></i>2 · Fail</span><span><i style="background:var(--fg-faint)"></i>1 · Unauditable</span></div>
</section>
<section class="card"><h2>Delivery gate</h2>
  <p class="hint">Process checks run locally or read from the submitted runs. Each failure is scored under the dimension it belongs to, not as an extra dimension.</p>
  <div class="gates">{gate_html}</div>
</section>
<div class="body" id="body">
  <h2>Trials</h2>
  <p>3 no-image runs (pass@3, all must fail) and 4 with-image runs (pass@4, exactly 1 must pass). Rewards come from each run's <code>verifier/reward.txt</code>.</p>
  <div class="tablewrap"><table><thead><tr><th>Trial</th><th>Mode</th><th>Reward</th><th>f2p</th><th>p2p</th><th>Min</th><th>Failed tests</th></tr></thead><tbody>{trial_rows}</tbody></table></div>
  <h2>Issues &amp; suggested fixes</h2>
  {issues_html or '<p>No issues found.</p>'}
  <h2>Dimension details</h2>
  {detail_html}
  {f'<h2>Visual evidence</h2>{evidence_html}' if evidence_html else ''}
</div>
</main></div>
<script>{JS}</script></body></html>"""
(REPORT_DIR / f"QC_Report_{H}.html").write_text(page)
print(f"wrote {REPORT_DIR / f'QC_Report_{H}.html'}\nwrote {REPORT_DIR / f'QC_Report_{H}.md'}")
