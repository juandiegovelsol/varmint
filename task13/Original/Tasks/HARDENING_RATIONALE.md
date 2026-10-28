# Hardening rationale — `IvarK__AntimatterDimensionsSourceCode-2613-mm`

## Note on provenance of the "before" state

This bundle is **not under version control** (`git rev-parse` in `/home/sandbox/Tasks`
returns *not a git repository*, and there are no `.orig` backups). There is therefore no
`git diff` to review. The before-state below was recovered from the session transcript
(`~/.claude/projects/-home-sandbox/8df53323-…jsonl`, records 29 and 147), which contains
the verbatim pre-edit reads of both files. File mtimes corroborate which files changed:

```
solution/fix.patch    mtime=2026-07-29 14:25:13   owner=sandbox   <- untouched, predates this session
instruction.md        mtime=2026-07-31 18:06:45   owner=cb        <- edited
tests/test.patch      mtime=2026-07-31 18:14:49   owner=sandbox   <- edited
```

Recommend `git init` + an initial commit on this bundle so future hardening is diffable.

---

## Change 1 — `solution/fix.patch`: **zero changes**, deliberately

**1) Lever used:** none. Explicit non-application of any lever.

**2) Before → After:** byte-identical. `sha256 =
0c901d3e06ac0147b5fb47a2344810c28c58146b6729a3c0aa320014d118200e`, pre-image blob
`fb7c637c`, post-image blob `e31db007`, applies to `base_commit cc08c9f8` with
`git apply --check` at zero fuzz. Content unchanged:

```css
+::-webkit-scrollbar-corner {
+  -webkit-appearance: none;
+  appearance: none;
+}
```

**3) Engineering justification:** `fix.patch` is not a difficulty knob, it is the
provenance anchor. Its blob hashes tie the bundle to `fix_commit 63df293` and
`pr_number 2617`. Editing it to demand more of the candidate — e.g. adding per-theme
corner rules — would make `fix_commit`, `pr_number`, and `files_edited` describe a patch
that does not exist upstream. The bundle would then be measuring a synthetic requirement
while claiming to measure a real PR. Every hardening lever available here operates on
the *instruction* (how much is given away) or the *verifier* (how much precision is
demanded), never on the oracle. This non-change is the reason the bundle is still
auditable against upstream.

---

## Change 2 — `instruction.md`: Harder Localization

**1) Lever used:** Harder Localization — strip navigational context so the model must
localize the defect from the observable symptom rather than from metadata.

**2) Before → After:**

Before (8 lines, transcript record 147):
```markdown
# horizontal + vertical scroll looks bad on chrome

**Repository:** IvarK/AntimatterDimensionsSourceCode
**Issue:** [#2613](https://github.com/IvarK/AntimatterDimensionsSourceCode/issues/2613)

---

![image](/app/.harbor_assets/bug.png)
```

After (13 lines, current):
```markdown
# horizontal + vertical scroll looks bad on chrome

A user reports that when a scrollable region ends up showing a horizontal and a
vertical scrollbar at the same time, it renders badly in Chrome and looks out of
place against the rest of the UI. The problem is visible on load — no interaction
is needed to reproduce it.

They attached a screenshot of what they saw:

![Screenshot attached to the report, showing the problem in Chrome](/app/.harbor_assets/bug.png)

Please look at the screenshot to determine exactly what is rendering incorrectly,
then fix it so the affected area no longer looks out of place.
```

Removed: the repository identifier and the live GitHub issue URL. Added: a
symptom-only description of what the user observed and an explicit instruction to read
the screenshot. Not removed: the upstream issue title, which is metadata a real bug
report would carry.

**3) Engineering justification — and its measured limit:**

The intended mechanism is closing an oracle channel. `https://github.com/IvarK/
AntimatterDimensionsSourceCode/issues/2613` is a live URL whose thread contains the
diagnosis and, via the linked PR, the patch itself. A model with web access could
retrieve the answer without reasoning about the screenshot at all, and the task would be
measuring retrieval instead of visual debugging. Stripping the URL also removes the
repository name, which was the only text in the file that let the model skip
orientation.

**This lever did not measurably increase difficulty, and I cannot claim it did.**
Post-hardening the model scores 6/6 (mean 1.000). No pre-hardening trial was ever run,
so the lever's effect was never A/B tested and its magnitude is unknown — only its
direction is knowable a priori. The engineering reason it under-delivered is that the
leak it closed was *navigational*, not *diagnostic*: the trial logs show the model never
needed either removed line. It read the screenshot, then searched the stylesheets and
found that `::-webkit-scrollbar-corner` is targeted by no rule anywhere in the repo —
which is a much stronger signal than a repo name. Two independent belt-and-braces
controls also made the URL unreachable in practice: `[agent] network_mode =
"no-network"` and `--ak disallowed_tools=WebSearch,WebFetch`. So the lever is correct
defensively (it removes a channel that would leak if either control were relaxed) but it
was never the binding constraint on difficulty.

A residual leak I did **not** remove: the title itself names both scrollbars and the
browser, which is most of the way to the corner. Removing it would depart from the
upstream issue title, so it stays, and `visual_essentiality = "required"` remains
unproven as a result.

---

## Change 3 — `tests/test.patch`, lever A: precision raising via a second f2p

**1) Lever used:** Precision Raising — add an f2p that fails on base and passes on the
oracle, but which is *also* sensitive to inputs the original test could not distinguish.

**2) Before → After:**

Before — one container, one pixel:
```js
const BOXES = /* did not exist */
// single .scroll-box on #1a1a1a
const idx = (cy * png.width + cx) * 4;         // centre pixel only
const isWhite = R >= 200 && G >= 200 && B >= 200;
if (!isWhite) { writeReport(true, …); process.exit(0); }
```

After — three containers with deliberately non-theme backgrounds, every corner pixel:
```js
const BOXES = [
  { id: 'dark',    bg: '#1a1a1a', rgb: [26, 26, 26],   top: 20  },
  { id: 'magenta', bg: '#ff00ff', rgb: [255, 0, 255],  top: 250 },
  { id: 'teal',    bg: '#00807f', rgb: [0, 128, 127],  top: 480 },
];
const whites = all.filter(isWhite).length;
if (whites > 0)                    problems.push(`${b.id}: ${whites}/${all.length} corner pixels are white …`);
else if (!near(c, b.rgb, COLOR_TOLERANCE))
                                   problems.push(`${b.id}: corner is ${fmt(c)} but the container background is ${fmt(b.rgb)} …`);
```

The corner square measures 16×15 = **240 px** per container (confirmed by the base-commit
run, which reports `240/240 corner pixels are white` for both magenta and teal). Inspected
area went from 1 pixel on 1 container to 240 pixels on each of 2 additional containers.

Measured effect on constructed candidates:

| Candidate                                       | Before | After |
| ----------------------------------------------- | -----: | ----: |
| Corner hard-coded to one theme colour `#1a1a1a` |    1.0 |   0.5 |
| Scrollbar block deleted from the stylesheet     |    1.0 |   0.0 |
| Base commit (nop)                               |    0.0 |   0.0 |
| Oracle                                          |    1.0 |   1.0 |

**3) Engineering justification:** the original assertion was `centre pixel is not white`
on a container whose background was `#1a1a1a`. That is a one-bit predicate over a single
sample, and it is satisfied by an entire family of patches that do not fix the bug:

- `::-webkit-scrollbar-corner { background: #1a1a1a }` — paints the corner the dark
  theme's colour. Correct-looking on that one container, wrong on any scroll container
  with a different background. The old test could not see the difference because its
  only container *was* `#1a1a1a`; the new test renders magenta and teal, colours chosen
  precisely because no theme in the repo uses them, so a hard-coded value cannot
  coincidentally satisfy them.
- Partial suppression that leaves white inset or edge pixels — a real WebKit failure
  mode, since the surrounding thumb rule uses `border: 0.2rem solid transparent` with
  `background-clip: content-box`. A centre-pixel probe steps over edge artifacts by
  construction; counting all 240 pixels cannot.

The predicate went from "one sample is not white" to "zero of 240 pixels are white **and**
the centre matches this specific container's own background within ±10 per channel,
for two differently-coloured containers". A patch that merely repaints rather than
suppresses now fails on 2 of 3 containers.

Where this is *not* a difficulty increase: it is a false-positive elimination. See the
final section.

---

## Change 4 — `tests/test.patch`, lever B: regression guarding via a new p2p

**1) Lever used:** Regression Guarding — assert the behaviour *adjacent* to the fix so
that suppressing the corner by damaging its surroundings is not rewarded.

**2) Before → After:**

Before: `p2p = []` in `task.toml`, and no p2p test existed.

After:
```js
const expectedW = Math.round(SB_WIDTH_REM * measured.rootFontSizePx);   // 1.6rem @ root 10px = 16px
if (g.sbW !== expectedW) problems.push(`${b.id}: vertical scrollbar is ${g.sbW}px wide, expected ${expectedW}px …`);

const samples = [8, 20, 32, 44, 56, 68].map(dy => px(xs, g.y + dy));
const greyish = samples.filter(s => near(s, THUMB_GREY, THUMB_TOLERANCE)).length;
if (greyish < samples.length - 1) problems.push(`${b.id}: … the custom thumb styling was lost`);
```
registered as `p2p = ["scrollbar_chrome::test_custom_scrollbar_metrics_and_thumb_preserved"]`
in both `task.toml` and `tests/config.json`.

Verified to be a genuine pass-to-pass: on the base commit it **passes** while both f2p
tests fail — from the base-commit report just re-run:

```
scrollbar_corner       -> failure: corner pixel rgb(255,255,255) is white
scrollbar_corner_edge  -> failure: magenta 240/240 white, teal 240/240 white
scrollbar_chrome       -> (no failure element)          [p2p] scrollbar chrome -> PASS
"all_f2p": false, "all_p2p": true, reward 0.0
```

**3) Engineering justification:** there is a degenerate strategy that satisfies the f2p
signal without fixing anything — remove the surrounding `::-webkit-scrollbar` rules. In
WebKit, the corner widget only exists because the page opts into custom scrollbars; delete
`::-webkit-scrollbar { width: 1.6rem }` and Chrome falls back to native/overlay scrollbars,
the corner widget disappears, no white pixel is rendered, and the old single f2p reports
PASS. Measured: the gutted-stylesheet candidate scored **1.0** before this test existed.

The p2p makes that strategy self-defeating by pinning the two properties the degenerate
fix necessarily destroys: the 16px custom width (native scrollbars are narrower, so
`offsetWidth - clientWidth` changes) and the `grey` custom thumb (native thumbs are not
`rgb(128,128,128)`). Both are read from rendered output — `offsetWidth - clientWidth` from
the live DOM, thumb colour from decoded screenshot pixels — so the check is agnostic to
how the stylesheet is written.

Second, structural: this made the 0.5 reward branch **reachable at all**. With
`len(F2P) == 1` and `P2P == []`, `verifier.py` reduced to a binary classifier — if the
single f2p passed, `all_f2p` was true and `all_p2p` was vacuously true (`verifier.py:80`),
giving 1.0; if it failed, `f2p_passing` was empty, giving 0.0. The `elif f2p_passing`
branch at `verifier.py:84` was dead code. With 2 f2p and 1 p2p, partial credit now
expresses a real state, which is how the hard-coded-colour candidate lands on 0.5 instead
of being forced into a pass/fail bucket it doesn't belong in.

---

## Change 5 — `tests/test.patch`, lever C: fail-closed signal guard

**1) Lever used:** Fail-Closed Guarding — remove a fallback that let the suite report
success when it had no signal to measure.

**2) Before → After:**

Before:
```js
// Scrollbar size fallback in px if element measurement gives 0.
const FALLBACK_SB_PX = 16;
…
const sbW = info.sbW > 0 ? info.sbW : FALLBACK_SB_PX;
const sbH = info.sbH > 0 ? info.sbH : FALLBACK_SB_PX;
```

After:
```js
const noSignal = Object.entries(measured.boxes)
  .filter(([, g]) => !(g.sbW > 0 && g.sbH > 0))
  .map(([id, g]) => `${id}(sbW=${g.sbW},sbH=${g.sbH})`);
if (noSignal.length) {
  throw new Error(
    `No traditional scrollbars rendered for: ${noSignal.join(', ')}. ` +
    `Overlay or zero-width scrollbars mean the corner widget does not exist, so ` +
    `these tests cannot discriminate.  Check that Chromium ran headful under Xvfb.`);
}
```

**3) Engineering justification — this was the most consequential defect fixed, and it is
candidate-independent:** `sbW == 0` means the browser rendered overlay scrollbars, i.e.
**there is no corner widget on the page**. The old code interpreted that as "measurement
glitched" and clipped a 16×16 region anyway. That region lands on plain container
background, which is `#1a1a1a` — not white — so the assertion passed.

The failure mode is therefore: any environment regression that loses headful rendering
(Xvfb not up yet, `headless: false` silently ignored, a Chromium upgrade changing overlay
behaviour) causes **the base commit to score 1.0**. The bug is unobservable, so nothing is
white, so the test reports the fix present. A false 1.0 for an empty patch is strictly
worse than a crash, because a crash is visible in the logs and a 1.0 is not.

This interacted with a second real defect fixed in `test.sh`: the Xvfb readiness loop
probed with `DISPLAY=:99 node -e "process.exit(0)"`, which exits 0 whether or not the
display is listening, because Node never opens a display connection. The loop therefore
broke on iteration 1 and Chromium could launch against a dead display — exactly the
condition that triggers the fail-open above. It now polls for the X11 socket
(`[ -S /tmp/.X11-unix/X99 ]`) and aborts if Xvfb died. The guard and the readiness fix
together convert "silently score 1.0 for nothing" into "error out with a diagnostic
naming the containers that had no scrollbars".

---

## Change 6 — `tests/test.patch`, lever D: complete crash accounting

**1) Lever used:** Fail-Closed Guarding, applied to the report writer.

**2) Before → After:**

Before, `writeErrorReport` emitted a single hardcoded testcase:
```js
<testcase classname="scrollbar_corner" name="test_corner_not_white" time="0">
  <error message="Test crashed">…</error>
```

After, it enumerates every registered test:
```js
const ALL_TESTS = [
  ['scrollbar_corner',      'test_corner_not_white'],
  ['scrollbar_corner_edge', 'test_corner_matches_container_background'],
  ['scrollbar_chrome',      'test_custom_scrollbar_metrics_and_thumb_preserved'],
];
function writeErrorReport(err) {
  writeReport(ALL_TESTS.map(([classname, name]) => ({
    classname, name, status: 'error', message: `Test crashed: ${String(err)}`,
  })));
}
```

**3) Engineering justification:** with three tests, a mid-suite exception discards the
partially-filled `results` array. Without `ALL_TESTS`, the emitted XML would contain only
the tests that had already run, and `verifier.py:68` maps absent identifiers to
`'missing'`. The exposure is bounded but real: a crash occurring after f2p 1 passed would
report `f2p1=pass, f2p2=missing, p2p=missing` → `all_f2p` false, `f2p_passing` non-empty →
**reward 0.5** for a suite that never finished. Now every crash path writes all three as
errors → `f2p_passing` empty → reward 0.0.

Worth stating precisely: because `match()` returns `'missing'` rather than `'pass'`, a
missing test could never have inflated the reward to 1.0. This lever closes a 0.5, not a
1.0. It is a modest correctness fix, not a difficulty lever, and I am not claiming more
for it.

---

## Change 7 — `tests/test.patch`, lever E: derived constant instead of a magic number

**1) Lever used:** Durability — express the expectation in the app's own terms so the
assertion tracks the stylesheet rather than a hardcoded pixel value.

**2) Before → After:** Before, `const FALLBACK_SB_PX = 16` was the only place 16 appeared,
and it was a fallback rather than an expectation. After:

```js
const SB_WIDTH_REM = 1.6;                        // matches ::-webkit-scrollbar { width: 1.6rem }
…
rootFontSizePx: parseFloat(getComputedStyle(document.documentElement).fontSize),
const expectedW = Math.round(SB_WIDTH_REM * measured.rootFontSizePx);
```

**3) Engineering justification:** the repo sets `html { font-size: 62.5% }`, so `1.6rem`
resolves to 16px *given that root size*. Hardcoding 16 would make the p2p a false
regression report for any candidate that legitimately changed the root font-size, and
would silently stop testing the intended property if the rem base moved. Reading the live
computed root font-size keeps the assertion anchored to "the scrollbar is as wide as this
stylesheet says", which is the behaviour worth protecting. This is not a difficulty lever
either — it prevents a future false negative.

---

## Why part 3 is only partly answerable — and what the honest claim is

The requested framing ("a shallow or recipe-following model could pass before but will
fail now") assumes the hardening raised the model's failure rate. **It did not, and no
verifier change could have.** The precise reason:

A verifier is a classifier over candidate patches. Hardening moves its decision boundary.
The boundary can be moved inward through the region of *wrong-but-plausible* patches —
that is what changes 3, 4, 5 and 6 do. It cannot be moved through the region of *correct*
patches, because a correct fix scoring 1.0 is the definition of a working verifier. So
hardening can only raise **precision** (fewer false positives), never **difficulty**
(the probability that a competent model lands outside the accepting region).

The measured data separates these cleanly:

- **Precision improved, provably.** Two candidates that previously scored a full 1.0 —
  the hard-coded corner colour and the gutted stylesheet — now score 0.5 and 0.0. Those
  are measured runs, not arguments. One candidate-independent false-1.0 path (the
  `FALLBACK_SB_PX` fail-open) was eliminated entirely.
- **Difficulty did not improve.** `claude-opus-4-8` scores 6/6, mean 1.000, ~1m45s per
  trial. The model produces a genuinely correct fix — and notably a *different* one from
  the oracle: all six trials wrote `background: transparent`, where the golden patch
  writes `appearance: none`. Both score 1.0, which is the strongest available evidence
  that the tests are implementation-agnostic rather than golden-patch-shaped.

So the defensible version of part 3 is: **a shallow fix from the specific families I
constructed would have collected full credit before and cannot now.** What I cannot show
is that any real model produces those families. I built the hard-coded-colour and
gutted-stylesheet candidates by hand precisely because the model never generated them.
Their value is prospective and adversarial — a weaker future model, or one optimising
against the reward signal, can no longer be paid for a patch that only works on one
background or that deletes the feature instead of fixing it. That is a real property of
the bundle, and it is a different property from being hard.

The one lever that *could* have raised difficulty is change 2, and it is also the one
whose effect I cannot quantify, because no pre-hardening trial exists to compare against.
Its ceiling was low regardless: the decisive clue the model used was not in the text at
all. It was in the repository — `::-webkit-scrollbar-corner` is styled nowhere, while
width and thumb are styled — and in the screenshot the task is built around. Both are
load-bearing parts of the task and neither can be removed without destroying it.
