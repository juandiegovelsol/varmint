"""Write QC_Report/findings.json for task114 Attempt4 (bokeh 15456 layouts, V27 review).
Usage: python -I make_findings.py <QC_Report dir> <local_runs dir>"""
import json
import pathlib
import sys
import xml.etree.ElementTree as ET

out_dir, lr = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
cfg = json.loads((lr / "Tasks/bokeh__bokeh_15456_mm/tests/config.json").read_text(encoding="utf-8"))
F2P, P2P = cfg["f2p"], cfg["p2p"]


def junit(mode):
    res = {}
    for tc in ET.parse(lr / mode / "verifier/junit.xml").getroot().iter("testcase"):
        res[tc.get("name")] = "fail" if any(c.tag in ("failure", "error") for c in tc) else "pass"
    return res


J = {m: junit(m) for m in ("oracle", "nop", "oracle_rerun")}
R = {m: (lr / m / "verifier/reward.txt").read_text().strip() for m in ("oracle", "nop", "oracle_rerun")}
cnt = {m: (sum(J[m].get(t) == "pass" for t in F2P), sum(J[m].get(t) == "pass" for t in P2P)) for m in J}
same = J["oracle"] == J["oracle_rerun"]

# cross-check: golden minus one part
XC = [json.loads(l) for l in (lr / "crosscheck/summary.txt").read_text().splitlines() if l.startswith("{")]
xc_done = (lr / "crosscheck/summary.txt").read_text().strip().endswith("DONE")

SHORT = {
    F2P[0]: "row: outer legends/axes/toolbars inside",
    F2P[1]: "row: fixed frames aligned, some titled",
    F2P[2]: "column: axes inside, tick widths differ",
    F2P[3]: "nested rows+columns uncropped",
    F2P[4]: "grid: spanning plot uncropped",
    F2P[5]: "grid: fixed frames aligned, some titled",
    F2P[6]: "legend on the left clear",
    F2P[7]: "toolbar on the left clear",
    F2P[8]: "change: tick labels widen",
    F2P[9]: "change: legend label longer",
    F2P[10]: "change: column tick labels widen",
    F2P[11]: "stretch row: stay within the row",
    P2P[0]: "p2p grid of alike plots",
    P2P[1]: "p2p legend on the right",
    P2P[2]: "p2p Row spacing",
    P2P[3]: "p2p PlotView element style",
    P2P[4]: "p2p change: tick labels narrow",
}
PART = {
    "part1": ("D1 FlexBoxView never calls align_borders() (upstream #15456)", "flex_box.ts measure_layout override",
              "pair row: untitled chart's x-axis cut; four-legend row cropped; column tick labels collide (t=0.5 s)"),
    "part2": ("D2 align_borders() swaps c0/c1 (bug_01)", "alignments.ts",
              "grid: spanning chart's frame cut on the right, toolbar over the data (t=0.5 s)"),
    "part3": ("D3 BorderLayout ignores align_border.top (bug_02)", "border.ts",
              "grid: untitled 1e6 chart's frame stretched, x-axis pushed out (chart a beside it correct)"),
    "part4": ("D4 left panel DOM not reversed (bug_03)", "plot_canvas.ts",
              "grid: left legend 'a' covers chart a's ticks; 'tools' chart: left toolbar covers the y-axis (right-side legends correct)"),
    "part5": ("D5 has_size_changed uses '>' (bug_04)", "side_panel.ts",
              "t=14.8 s: grown tick labels cut ('e+9'), longer legend runs out of its chart (shrinking chart relaid out correctly)"),
    "part6": ("D6 stretch flex '1 0 auto' (bug_05)", "flex_box.ts flex value",
              "bottom row: first stretch_width chart takes the whole row, the second runs off the page"),
}

xc_rows = []
for d in XC:
    k = d["state"].split()[-1]
    fails = [f.split(": ", 1)[1] for f in d["failing"]]
    xc_rows.append(f"| {PART[k][0]} | {PART[k][2]} | {d['reward']} | " + "; ".join(SHORT.get(f, f) for f in fails) + " |")
xc_table = ("| part removed from the golden | visible in recording.mp4 | reward | tests that fail |\n|---|---|---|---|\n" + "\n".join(xc_rows))
uncovered = [t for t in F2P if not any(t.split(": ", 1)[-1] in [f.split(": ", 1)[1] for f in d["failing"]] for d in XC)]
p2p_broken = [f for d in XC for f in d["failing"] if f.startswith("p2p")]

N = "Nothing found."
dims = []


def dim(score, category, evidence, wrong, fix):
    dims.append(dict(name="", score=score, category=category, evidence=evidence, wrong=wrong, fix=fix))


loc = (f"Local runs (image `qc114a4:task` built from the bundle, every layer a cache hit of the CB's build; `--network none`): oracle **{R['oracle']}** "
       f"({cnt['oracle'][0]}/12 f2p, {cnt['oracle'][1]}/5 p2p), nop **{R['nop']}** ({cnt['nop'][0]}/12, {cnt['nop'][1]}/5), "
       f"oracle re-run **{R['oracle_rerun']}** ({cnt['oracle_rerun'][0]}/12, {cnt['oracle_rerun'][1]}/5); per-test outcome of the re-run identical: {'yes' if same else 'NO'}.")

# 1
dim(5, "",
    "All 11 fixed files exist and are non-empty: `task.toml` 7,976 B, `instruction.md` 1,029 B, `evidence_bundle.json` 1,084 B, `environment/Dockerfile` 2,104 B, "
    "`environment/assets/ASSET_MANIFEST.json` 404 B, `solution/fix.patch` 3,845 B, `solution/solve.sh` 349 B, `tests/config.json` 2,001 B, `tests/test.patch` 28,098 B, "
    "`tests/test.sh` 10,586 B, `tests/verifier.py` 6,488 B. The three JSON files parse, `task.toml` parses (tomllib), and `python -m py_compile tests/verifier.py` is OK. "
    "`recording.mp4` decodes (ffprobe: h264 2250x2060, 10 fps, 152 frames, 15.2 s). Extra files: `README.md` and `environment/bugs/bug_01..05.patch` "
    "(injected bugs, applied in the Dockerfile and deleted in the same layer), which are allowed. All files are LF.",
    N, "")
# 2
dim(5, "",
    "`Tasks/bokeh__bokeh_15456_mm/` and `Trials/` are sibling root folders (plus `Oracle/`, `Nop/`). `Trials/without_images/` holds 3 trials (MAFQ7Vr, WfXan7T, Zniq5zv) "
    "and `Trials/with_images/` holds 4 (9bbieGm, Nd6MBin, dmWFzr6, jeqnwEM): 7 trials, Option A. The with-image `task_manifest.json` hashes all 17 bundle files, and every "
    "hash matches the reviewed bundle. The without-image job is the same task with the assets removed (checksum `c37afe36…` vs `50694809…`).",
    "Nothing found. This attempt was handed over as extracted folders (plus `Tasks_attempt4.tar.gz`), not as one archive per folder; that is fine for a local check.",
    "When submitting, pack `Tasks/` and `Trials/` into their own `.tar.gz` files.")
# 3
dim(5, "",
    "Text only: the instruction names the element types (charts, the area the points are drawn in, labels and controls), the aspects that go wrong (final dimensions, "
    "the drawing area, the position of labels and controls) and three general rules. It never says which chart, which side, which change or which layout is wrong. "
    "With the text alone a developer cannot tell what to fix or confirm it is complete. Trials confirm it: all 3 no-image runs scored 0.0. Every one missed the left-panel "
    "overlap (D4: 'legend on the left' and 'toolbar on the left' f2p) and the stretch row (D6). Zniq5zv also missed D5. Each found `/app/.harbor_assets` empty "
    "(`ls -la` shows only `.` and `..`). Image path `/app/.harbor_assets/recording.mp4` resolves (present in the image). Leak scan of `instruction.md`: no repo name, URL, "
    "issue number, file, model or class name (Row, Column, GridBox, FlexBox, Legend, toolbar, axis, frame, sizing_mode, align, border are all absent), and no mechanism. "
    "'row or column' and 'side by side / stacked' are plain words. The only hits are 'whole', 'overlaps' (expected rules) and 'frames' (the ffmpeg tip, meaning video frames).",
    N, "")
# 4
dim4_table = (
    "| defect | element named (type) | defect: text or image? | expected: text or image? | in-clip counterpart | clue left to image | described correctly? |\n"
    "|---|---|---|---|---|---|---|\n"
    "| D1 Row/Column borders not aligned | 'charts side by side … stacked charts', 'labels and controls' | image (untitled chart's x-axis cut, four-legend row cropped) | text: 'share one height … line up', 'shown whole' | yes: titled chart of the pair, the grid | which layout, which chart | yes |\n"
    "| D2 spanning chart borders | 'the area the points are drawn in', 'labels and controls' | image (frame cut on the right, toolbar over data) | text: 'keeps the size it was given', 'without overlaps' | yes: the plots above it | which grid chart, the span | yes |\n"
    "| D3 frame stretched | 'the area the points are drawn in' | image | text: 'keeps the size it was given' | yes: chart a beside it | which chart, why (title) | yes |\n"
    "| D4 left panel overlap | 'labels and controls' | image (legend over ticks, toolbar over y-axis) | text: 'without overlaps' | yes: right-side legend and toolbar | which side | yes |\n"
    "| D5 no relayout on growth | 'some charts change what they show', 'at every moment' | image (e+9 cut, legend runs out) | text: 'at every moment … shown whole' | yes: the chart whose range shrinks | which change, grow vs shrink | yes |\n"
    "| D6 stretch row | 'every chart stays within the row or column' | image (2nd chart off the page) | text | no: the only stretch row is buggy; only 'looks out of place' holds | which row | yes |"
)
dim(3, "[Non-Fail - Image-carried Symptom]",
    "Instruction: \"`recording.mp4` some charts change what they show. Several things about these charts go wrong in this clip: in the final dimensions of the charts, "
    "in the area the points are drawn in, and in the position of the labels and controls.\" Expected: labels and controls 'shown whole, within the chart's dimensions "
    "and without overlaps' at every moment; the drawing area 'keeps the size it was given'; side-by-side charts share one height, stacked ones one width, drawing areas "
    "line up, every chart 'stays within the row or column it is placed in'.\n\n"
    "Check 1 (element by type): passes. Charts, the drawing area, and labels and controls are type nouns, and none hints at the fix. Check 2 (specificity): passes. The general "
    "'go wrong' is followed right away by the three aspects and the rules. Check 3 (image dependency): passes. Which chart, which side and which change stay in the clip, "
    "and every claim in the text is true of the clip (QC frames t=0.5 s and t=14.8 s, evidence 01/02).\n\n"
    + dim4_table +
    "\n\nWhy 3, not 5: the 'What happens' part names only the aspects ('go wrong in …'). The concrete defects (cut off, drawn over another part, stretched, running off the page) "
    "appear only in the clip, or by inverting the Expected rules. That is the rubric's image-carried case.\n\n"
    "With-image trajectories (all 4 read): every run read the clipped e+9 tick labels and the overflowing legend (D5) and the row/grid alignment defects (D1-D3). "
    "D4 was found by Nd6MBin ('the left-side legend \"a\" covers the y-axis \"1.8\" label. The original clip shows the same overlap'), jeqnwEM ('on the \"tools\" chart … the toolbar covers the "
    "y-axis tick labels') and dmWFzr6. 9bbieGm could not render anything ('there's no Chrome here') and missed it. D6 was found only by dmWFzr6 ('a stretch-width chart next to a fixed one "
    "took the full row width and pushed the fixed chart off-screen'). 9bbieGm, Nd6MBin and jeqnwEM never mention the bottom row. None of them called it correct, so this is a "
    "perception miss, not a run that 'couldn't tell the bug from intended'. No run took a defect for intended behaviour.",
    "Non-fail flag: the exact defects are carried by the clip, not stated in the text. D6 has no correct stretch row in the clip to compare with. Minor wording: the first "
    "sentence lacks a preposition ('`recording.mp4` some charts change …' should read 'In `recording.mp4`, some charts change …').",
    "Optional, for a 5: add one symptom line without causes, e.g. 'Some labels and controls are cut off or drawn over other parts, one drawing area is stretched, and one "
    "chart runs out of its row.' Warning: stating the symptoms gives text-only runs a search target, and 0/3 no-image is a hard requirement. Changing `instruction.md` changes "
    "the task checksum, so all 7 trials must be re-run. If you only fix the missing 'In', the re-run is required too.")
# 5
dim(5, "",
    "`task_type = \"temporal_interaction\"` (Guidelines Step IV: 'Fix a defect that only appears across a sequence of interactions / state transitions', evidence an ordered "
    "sequence). The instruction describes a clip in which 'some charts change what they show' and requires labels and controls to be whole 'at every moment of the clip'. "
    "D5 only appears after a state change: 3 f2p tests compare the layout after a change with a fresh render. So the text reasonably falls under the type.",
    "Nothing found. Non-graded note: 4 of the 6 defects (D1-D4) and D6 are static layout defects visible in the first frame, which `visual_bug_fix` (also in `tags`) would fit too. "
    "The temporal type is defensible because the evidence is a time sequence and one defect class exists only across a state change.", "")
# 6
dim6_names = (
    "| file | role field | what the frames show (how verified) | what name/role/instruction claim | true? | agents confused? |\n|---|---|---|---|---|---|\n"
    "| recording.mp4 | bug_video | the injected build (all six defects; sha256 equals the kit's recording_all_bugs.mp4, recorded from the task image). Frames t=0.5 s and t=14.8 s checked by QC (evidence 01/02) | neutral name; 'charts … change what they show', 'several things go wrong'; description: '15 s browser recording of several groups of scatter charts; partway through, some charts change what they show' | yes | no: every with-image run treated it as the buggy state |"
)
dim(5, "",
    "Naming table:\n\n" + dim6_names + "\n\n"
    "The asset vs the f2p: each injected part was removed from the golden, one at a time, in the task image (`git apply` of the bug patch on top of the golden, verifier run, "
    "`git apply -R`; part 1 = reverse of the golden's FlexBox `measure_layout` hunk). Result:\n\n" + xc_table + "\n\n"
    + ("Every part fails at least one f2p, and every f2p is failed by at least one part. " if not uncovered else f"f2p not covered by any part: {uncovered}. ")
    + ("No p2p breaks in any state. " if not p2p_broken else f"p2p broken: {p2p_broken}. ")
    + "Every part is visible in the clip (table column 2), so 'fix what the clip shows' = the whole golden = oracle 1.0, and 'fix only what the f2p check' changes every "
    "boxed area of the clip. Preconditions match the clip's scenes: the f2p scenes are the same layouts at smaller scale (pair row with one title, four legends on four "
    "sides, column of 0-1 / 0-1e5 / 0-1e9 ranges, grid with a 2-column span, left legend, left toolbar, a y range growing to 1e9, a legend label growing, a stretch_width row). "
    "Note: FlexBox registers each child with a span of `r1: r0 + 1, c1: c0 + 1` (inclusive Container convention), so D2 also shows in rows/columns once D1 is fixed. That is why "
    "'golden minus part2' fails the column tests too, and it is consistent.\n\n"
    "Step 7 (injected parts 2-6): skipping any of them leaves a real bug on a public path: GridBox `col_span` children (D2), fixed-frame plots with/without a title in a grid "
    "(D3), `add_layout(legend, 'left')` / `toolbar_location='left'` (D4), updating a `Range1d.end` or a legend label after display (D5), `sizing_mode='stretch_width'` in a "
    "`row` (D6). Complete fix? yes only with all six. Each expected result is stated by an Expected rule, and five of six have a correct counterpart in the clip.",
    N, "")
# 7
dim(5, "",
    "`temporal_interaction` is one of the seven values. The evidence is a 15 s video in which three charts change state, which matches 'ordered screenshot / GIF sequence'. "
    "A video instead of 3-8 frames is accepted practice (video-only bundles are valid per the review notes).",
    N, "")
# 8
dim(5, "",
    "Disk: `environment/assets/recording.mp4` sha256 `17bc0da3…7e0e`, 198,548 B. `ASSET_MANIFEST.json`: same file, sha256, bytes, `container_path /app/.harbor_assets/recording.mp4`. "
    "`evidence_bundle.json`: same sha256/bytes, `local_path /app/.harbor_assets/recording.mp4`, `source_kind captured_from_repo` with empty `url`. `instruction.md` references "
    "`/app/.harbor_assets/recording.mp4`. Dockerfile: `COPY assets/recording.mp4 /app/.harbor_assets/`; `ls /app/.harbor_assets` in the image shows `recording.mp4`.",
    N, "")
# 9
dim(5, "",
    "In the built image at `harbor_base` (`git describe --exact-match` = harbor_base): `git apply --check /solution/fix.patch` OK and `git apply --check /tests/test.patch` OK. "
    "Local oracle `solve.sh exit=0`, 'Applied fix.patch.'",
    N, "")
# 10
dim(5, "",
    "`fix.patch` paths = `files_edited` exactly (5 files): `bokehjs/src/lib/core/layout/border.ts`, `core/layout/side_panel.ts`, `models/layouts/alignments.ts`, "
    "`models/layouts/flex_box.ts`, `models/plots/plot_canvas.ts`. No test, doc, lockfile or changeset path. Test files (`plots_in_layouts.ts`, `gen_junit.mjs`, `tests.json`) "
    "live only in `test.patch` and equal `config.json` `test_files`.",
    N, "")
# 11
dim11_table = (
    "| part | golden form | alternative | source | valid / plausible? | test result |\n|---|---|---|---|---|---|\n"
    "| D1 | `FlexBoxView.measure_layout` override calling `align_borders()` | call `align_borders()` once in the shared `LayoutDOMView.measure_layout` (and drop the CSSGridBox copy) | Nd6MBin, 9bbieGm submissions | valid and plausible (same pattern, one level up) | accepted: Nd6MBin passed all 4 D1 f2p (11/12, failed only D6) |\n"
    "| D5 | `this.bbox.width != width` | `Math.abs(this.bbox.width - width) >= 1` | dmWFzr6 | valid and plausible | accepted (12/12) |\n"
    "| D5 | `!=` | `<` (relayout only on growth) | 9bbieGm, WfXan7T | not correct: shrinking no longer relays out, a regression of base behaviour | rejected by p2p 'tick labels narrow' (plot 215 px wide after the change vs 184 px fresh): correct rejection |\n"
    "| D6 | flex `1 0 0px` | `1 1 0px`, `1 0 0%`, `flex-basis: 0` + `min-width: 0` | by reading the assertion | valid | accepted by construction: the test only checks both charts lie inside the 900 px row (±1 px) |\n"
    "| D4 | `append(...reversed(left_els))` | reverse the layout order instead, or any z-order that keeps the boxes apart | by reading the assertion | valid | accepted: the test compares drawn boxes only (no DOM order, no CSS string) |\n"
    "| D2/D3 | `cols[c0].left`, `Math.max(…, align_border.top)` | equivalent arithmetic, or applying the aligned top border in `_set_geometry` | by reading the assertion | valid | accepted: frame size and alignment are checked ±1 px |"
)
dim(5, "",
    "No assertion compares a string, enum, colour, unit or serialized value. Every check is geometric: drawn boxes from `getBoundingClientRect()` / layout bboxes with a "
    "1 px tolerance (`near`, `inside`, `overlap > 1`). The output-form table is therefore empty, and alternative strategies were checked instead:\n\n" + dim11_table + "\n\n"
    "Structure-level checks, each with a stated cause: exactly 2 axes (the figure declares 2), as many legends as the model declares, toolbar present iff `toolbar_location` is set, "
    "title iff it has text ('all labels and controls … shown whole'); frame size 150x150 / 200x200 / 380x120 ±1 px (set via `frame_width`/`frame_height`: 'keeps the size it was "
    "given'); changed-vs-fresh geometry ±1 px ('at every moment of the clip …', i.e. a correct relayout reproduces a fresh render). 'Fix only what the evidence shows' = all six "
    "parts (dim 6 cross-check), which the oracle passes. The only rejections in the trials are missing parts (D4, D6) and the `<` regression. None is a valid alternative.",
    N, "")
# 12
dim(5, "",
    "`task.toml` f2p (12) and p2p (5) lists are identical to `config.json`, with no overlap. `verifier.py` `load_junit` keys each testcase by 'classname name' and by name. "
    "Every configured id matches exactly one testcase by name in the oracle JUnit (17 testcases, no duplicates). The runner summary reads '17 passed, 0 skipped, 2434 deselected of "
    "total 2451 tests'. `gen_junit.mjs` requires the summary to account for every selected test.",
    N, "")
# 13
dim(5, "",
    "All 5 p2p pass on local nop, local oracle, oracle re-run, CB oracle (8aRTPDe) and CB nop (d2vMq8Y). They also pass in all 6 'golden minus one part' states.",
    N, "")
# 14
dim(5, "",
    loc + " All 12 f2p fail on nop and pass on oracle, both locally and in the CB's runs (8aRTPDe 12/12, d2vMq8Y 0/12).",
    N, "")
# 15
dim(5, "",
    "The re-run gives the same per-test outcome as the first oracle run, and the CB's oracle agrees test for test. `test.sh` installs nothing: it runs `node make build` "
    "(incremental) and `node make test:unit --grep`, and the local runs passed with `--network none`. Chromium is the build pinned by `playwright-core` (installed at image "
    "build); fonts come from `fonts-liberation`/`fonts-dejavu-core` in the image. Timing: tests wait on `view.ready` plus a 300 ms settle, and assert with 1 px tolerance. No "
    "unexplained failure in 7 trials + 3 local runs + 6 cross-check runs. The only p2p failures (9bbieGm, WfXan7T) are caused by their `<` edit (dim 11).",
    "Nothing found. Non-graded: `[verifier] network_mode = \"public\"` is broader than needed; nothing is fetched at test time, so `no-network` would also work.", "")
# 16
dim(5, "",
    "Option A, 7 trials, all on checksum `50694809…` (with-image, = CB oracle/nop) / `c37afe36…` (no-image job). No-image: MAFQ7Vr 0.0 (7/12), WfXan7T 0.0 (7/12, p2p 4/5), "
    "Zniq5zv 0.0 (4/12), each with `/app/.harbor_assets` empty. With-image: **dmWFzr6 1.0 (12/12)**, 9bbieGm 0.0 (7/12, p2p 4/5), jeqnwEM 0.0 (11/12, missed D6), "
    "Nd6MBin 0.0 (11/12, missed D6). pass@3 no-image = 0/3, pass@4 with-image = exactly 1/4. Run time (informational): agent 2.3-7.7 min no-image, 3.1-15.4 min with-image. "
    "No exceptions.",
    N, "")
# 17
dim(5, "",
    "D1 is the real upstream issue (#15456, PR #15487: Row/Column must call `align_borders()` like CSSGridBox). D2-D6 are one-token regressions of real code paths: "
    "a swapped index, a dropped `Math.max` term, a dropped `reversed()`, `!=` to `>`, and a flex basis. Each produces a coherent, visible layout defect, and the fix for each "
    "is the obvious one-line change a bokeh developer would write (the golden). Trials show the fixes are reachable: dmWFzr6 found and fixed all six from the clip.",
    N, "")
# 18
dim(5, "",
    loc + " Stage banners present ('captured submission.patch', 'applying test.patch', 'running f2p + p2p tests', 'computing reward', `reward=`). No 'could not apply test.patch'. "
    "The CB's runs agree (Oracle 8aRTPDe 1.0, Nop d2vMq8Y 0.0, same checksum as the with-image trials).",
    N, "")
# 19
dim(5, "", "A complete, auditable task: every claim was checked against the bundle, the image, local runs and the trial logs.", N, "")

RUBRIC_TITLES = ["Structure - Task Bundle Files", "Structure - Deliverables & Packaging", "Instruction - Requires the Visual Evidence",
                 "Instruction - Symptom Specificity", "Instruction - Task Type", "Image - Evidence Quality", "Metadata - task_type Accuracy",
                 "Evidence - Chain Consistency", "Golden Fix - Applies Cleanly", "Golden Fix - Source-Only Scope", "Tests - Implementation Overfit",
                 "Tests - f2p/p2p Identifier Validity", "Tests - p2p Classification", "Tests - Discriminating (f2p)", "Tests - Determinism",
                 "Hardening - Difficulty (Model Trial Fails)", "Hardening - Real & Feasible", "Gate - Oracle/Nop", "Unauditable"]
assert len(dims) == 19
for d_, t_ in zip(dims, RUBRIC_TITLES):
    d_["name"] = t_

gates = [
    dict(label="Local oracle", status="pass" if R["oracle"] == "1.0" else "fail", detail=f"{R['oracle']} ({cnt['oracle'][0]}/12 f2p, {cnt['oracle'][1]}/5 p2p), `--network none`."),
    dict(label="Local nop", status="pass" if R["nop"] == "0.0" else "fail", detail=f"{R['nop']} ({cnt['nop'][0]}/12 f2p, {cnt['nop'][1]}/5 p2p)."),
    dict(label="Oracle re-run", status="pass" if same and R["oracle_rerun"] == "1.0" else "fail", detail=f"{R['oracle_rerun']}; same outcome per test: {'yes' if same else 'no'}."),
    dict(label="CB oracle / nop", status="pass", detail="8aRTPDe 1.0 (12/12, 5/5), d2vMq8Y 0.0 (0/12, 5/5); checksum `50694809…` = with-image trials."),
    dict(label="Patch apply", status="pass", detail="`git apply --check` OK for fix.patch and test.patch at `harbor_base`."),
    dict(label="Verifier completion", status="pass", detail="Stage banners and `reward=` present; runner summary covers all 17 selected tests."),
    dict(label="Per-part cross-check", status="pass" if xc_done and not uncovered and not p2p_broken else "warn",
         detail=f"{len(XC)} 'golden minus one part' runs: every part fails ≥1 f2p, every f2p covered, no p2p broken."),
    dict(label="pass@3 no-image", status="pass", detail="0/3 (7/12, 7/12, 4/12); `/app/.harbor_assets` empty in each."),
    dict(label="pass@4 with-image (Option A)", status="pass", detail="Exactly 1/4: dmWFzr6 (12/12). jeqnwEM and Nd6MBin missed only the stretch row; 9bbieGm had no browser."),
    dict(label="Trial run time (informational)", status="pass", detail="Agent 2.3-15.4 min; total 4.0-16.8 min."),
    dict(label="Trial / task checksum", status="pass", detail="`task_manifest.json` hashes all 17 bundle files = reviewed bundle."),
    dict(label="Packaging", status="pass", detail="`Tasks/` and `Trials/` root siblings, 3 + 4 trials."),
    dict(label="Leaks", status="pass", detail="Type nouns only (charts, the drawing area, labels and controls); no repo, file, model name or mechanism."),
    dict(label="Evidence-chain integrity", status="pass", detail="Disk, manifest, evidence bundle, instruction and Dockerfile agree on `recording.mp4` (sha256 `17bc0da3…`)."),
    dict(label="Symptom flag (dim 4)", status="warn", detail="Non-fail 3: exact defects carried by the clip; the stretch defect has no in-clip counterpart."),
]

trials = [
    dict(id="task_without_images__MAFQ7Vr", mode="no-image", reward=0.0, f2p="7/12", p2p="5/5", minutes=9.0,
         failed=["row: outer legends", "nested uncropped", "legend on the left", "toolbar on the left", "stretch row"]),
    dict(id="task_without_images__WfXan7T", mode="no-image", reward=0.0, f2p="7/12", p2p="4/5", minutes=4.4,
         failed=["row: outer legends", "nested uncropped", "legend on the left", "toolbar on the left", "stretch row", "p2p: tick labels narrow ('<' edit)"]),
    dict(id="task_without_images__Zniq5zv", mode="no-image", reward=0.0, f2p="4/12", p2p="5/5", minutes=4.0,
         failed=["row: outer legends", "nested uncropped", "legend on the left", "toolbar on the left", "3 change tests", "stretch row"]),
    dict(id="task_with_images__9bbieGm", mode="with-image", reward=0.0, f2p="7/12", p2p="4/5", minutes=4.9,
         failed=["row: outer legends", "nested uncropped", "legend on the left", "toolbar on the left", "stretch row", "p2p: tick labels narrow ('<' edit)"]),
    dict(id="task_with_images__dmWFzr6", mode="with-image", reward=1.0, f2p="12/12", p2p="5/5", minutes=16.8, failed=[]),
    dict(id="task_with_images__jeqnwEM", mode="with-image", reward=0.0, f2p="11/12", p2p="5/5", minutes=12.8, failed=["stretch row"]),
    dict(id="task_with_images__Nd6MBin", mode="with-image", reward=0.0, f2p="11/12", p2p="5/5", minutes=14.8, failed=["stretch row"]),
]

data = dict(
    task_hash="bokeh__bokeh_15456_mm_attempt4",
    task_id="bokeh__bokeh_15456_mm",
    title="Charts placed together lose parts of themselves (task114, Attempt4)",
    rubric="Official V27",
    review_date="2026-11-20",
    date_folder="11_20",
    eyebrow="QC review · bokeh 15456 layouts · task114 Attempt4",
    verdict="PASS",
    verdict_reason=("All 19 dimensions pass. Difficulty meets Option A: no-image 0/3, with-image exactly 1/4 (dmWFzr6). Local oracle 1.0, nop 0.0 and the re-run are identical "
                    "to the CB's runs. A per-part cross-check shows each of the six defects is visible in the clip and graded by at least one f2p. Symptom Specificity is a "
                    "non-fail 3: element types and expected rules are in the text, and the exact defects are left to the clip."),
    dimensions=dims, gates=gates, trials=trials,
)
(out_dir / "findings.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
print("wrote", out_dir / "findings.json", "| rewards:", R, "| same:", same, "| xc parts:", len(XC), "done:", xc_done, "| uncovered:", uncovered, "| p2p broken:", p2p_broken)
