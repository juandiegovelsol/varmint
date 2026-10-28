# Step VI — Technical justification (task1, IvarK__AntimatterDimensionsSourceCode-3414-mm)

Gate re-established locally by replaying `tests/test.sh`'s exact stage sequence (reset
test paths → apply `test.patch` → run `harbor_test.js` → `verifier.py`) against a clone
pinned at `53574d87f7d9`: **base 0.0 → golden fix 1.0 → re-run 1.0**, all three stage
banners on every run. Still to run in the sandbox: `harbor run` for oracle / nop / trial.

Scope: three symptoms, one file, two rules. Symptoms 1 and 2 are the real PR
(`53574d87f7d9..096a639dd`, three commits). Symptom 3 is a defensible adjacent defect
visible in the same panel, added deliberately to raise difficulty.

---

## CHANGE 1 — scope: from one commit to the PR's full span

**Lever:** scope

**Before:** `solution/fix.patch` carried only `1e557f62e`, a 2-line deletion of the
`transform: translateY(-0.1rem)` workaround. `fix_commit` pointed at that commit.

**After:** the patch covers the PR's full span, including `d3a4bdd47` ("Additional fix",
credit to Dys) which stops the list painting its own top edge. `fix_commit` updated to
`096a639dd`.

**Why harder:** the base tree holds two independent causes of the same artifact, and the
first masks the second. Removing the transform alone — the obvious single-line reading of
the poster, and what the old task paid 1.0 for — now scores **0.5**. Measured: the
transform-only patch fails `selector-list-adds-no-second-edge-at-header-seam`.

---

## CHANGE 2 — scope: the scrollbar/frame collision

**Lever:** scope

**Before:** in the base render, any list long enough to scroll shows the scrollbar and the
frame's right edge as two parallel strips. Measured in `before_open.png`: grey track at
x=794–803, thumb at x=796–801, frame edge at x=804. Not addressed by the PR.

**After:** the frame keeps every border it had and keeps clipping; its clip edge is pushed
out to the border box so the list can reach across the right border, and the list's
overhang is padding rather than content so the rows never paint over that border:

```css
.l-select-notation,
.l-select-theme {
  overflow: clip;
  overflow-clip-margin: 0.1rem;
  background-color: var(--color-base);
  border: 0.1rem var(--color-good);
  border-style: solid;
  border-top-color: transparent;
  border-radius: var(--var-border-radius, 0.4rem);
}

.l-select-notation__inner,
.l-select-theme__inner {
  overflow-y: auto;
  flex-direction: column;
  max-height: 24.9rem;
  scrollbar-color: var(--color-good-dark) var(--color-disabled);
  scrollbar-width: thin;
  margin-right: -0.1rem;
  padding-right: 0.1rem;
}
```

**Three constraints have to hold at once, and each one kills an approach that looks
right.** They are what make this symptom worth having in the task:

1. *A scrollbar is laid out inside its own scroll box; the frame's edge is painted outside
   that box.* They can only stop being two strips if the scroll box reaches over the edge.
   Redrawing the edge somewhere the scrollbar covers — an inset `box-shadow` — is the
   obvious alternative and is wrong: inset ink lands inside the padding box, the rows are
   opaque and full-width, and they paint straight over it. Every edge disappears.
2. *The rows overhang with the list.* A bare `margin-right: -0.1rem` hides the border on
   every box whose list is short enough not to scroll a scrollbar over it. The overhang
   has to be padding, not content, hence the matching `padding-right`. Net content width
   is unchanged from base.
3. *A scroll box cannot round the corners of its own scrollbar — only an ancestor's
   rounded clip can.* So the frame cannot simply stop clipping to let the overhang
   through; that squares the scrollbar off against the curve. `overflow-clip-margin`
   pushes the clip edge out to the border box instead, which keeps the rounded clip and
   still lets the overhang survive.

The conditional behaviour then falls out: where the list overhangs it is padding, so a
short list leaves the border showing through, and a scrolling list drops an opaque
scrollbar on top of it.

Property order matches `.stylelintrc.json`'s `order/properties-order`
(`overflow` 12 … `background-color` 140 < `border` 148 < `border-radius` 171; and on the
list `overflow-y` 14 < `max-height` 71 < `scrollbar-width` 98 < `margin-right` 195 <
`padding-right` 203). `overflow-clip-margin` is not in that list, so it is placed next to
`overflow`.

**Honest limits:** upstream never fixed this, so it is an added symptom, not harvested —
real and visible in a base build, but an extension. `overflow-clip-margin` needs
Chrome 90+ / Firefox 102+ / Safari 16+; the game ships as web and Electron, so that is
fine, and where it is unsupported the fix degrades to the base rendering rather than
breaking.

---

## CHANGE 2b — three wrong turns, and the tests that now catch each one

Recorded because they are the trap this task sets, and because each one shipped to a
browser before being caught.

| attempt | what the browser showed | now caught by |
| --- | --- | --- |
| frame drawn with inset `box-shadow`s instead of borders | every edge vanished — rows paint over inset ink | `scrollbar-covers-the-frame-edge` (no edge left to cover) + `keeps-clipping-and-side-edges` |
| frame stops clipping, list overhangs with `border-radius: inherit` | right border gone on non-scrolling boxes; scrollbar corners square | `right-edge-survives-behind-the-rows` + `keeps-clipping-and-side-edges` |
| overhang added but frame still clips at the padding box | no change at all — overhang cut straight back off | `scrollbar-covers-the-frame-edge` |

Two test-side corrections came out of this. `edgePaints` (border **or** inset shadow) was
split: the "must contribute nothing" assertion still uses it, but "this edge must stay
visible" now requires border ink specifically, because the browser demonstrated that inset
ink does not survive the rows. And `scrollbar-covers-the-frame-edge` was passing
vacuously when the right border had zero width — deleting the edge made the assertion
trivially true — so it now fails outright if there is no visible edge to cover.

---

## CHANGE 3 — tests: replace a source-string match with resolved-render assertions

**Lever:** tests

**Before:** one f2p whose body was `t.includes('translateY')` — a substring grep of the
candidate's CSS. Source-matching (disallowed), and overfit both ways: `translateY(0)` and
`matrix(1,0,0,1,0,0)` are correct and would have been failed, while any unrelated rule
containing the substring would have flipped the result.

**After:** `harbor_test.js` is a resolver. It reads the stylesheets the document actually
links (parsed from `public/index.html` in document order, so the runtime-swapped theme
sheets are not all folded in at once), plus the `<style>` blocks of any component that
renders these boxes; matches selectors against the real element/ancestor chain from the
component templates; applies specificity, source order and `!important`; expands the
`border` / `border-*` / `border-radius` / `overflow` / `margin` / `box-shadow` shorthands;
resolves `var()` against the unqualified `:root`; and asserts on the resulting **used
values** — the quantities `getComputedStyle` reports. It never greps for a property, a
value, a selector or a file.

Three f2p, all flipping base→fix:

| f2p | assertion | base | fix |
| --- | --- | --- | --- |
| `collapsed-selector-box-not-offset-from-its-clip-box` | resolved vertical translation is 0px | −1px | 0 |
| `selector-list-adds-no-second-edge-at-header-seam` | top edge lays no ink, by border **or** inset shadow | `solid 0.1rem #5ac467` | none |
| `selector-list-scrollbar-covers-the-frame-edge` | there is a visible right edge, the scroll box reaches at least its width past the containing block, and the frame's clip does not cut that reach off | reach 0px, clip edge at the padding box | reach 1px, clip edge pushed out 1px |

The third measures the overhang from a negative `margin-right` **or** an over-100% `width`
— both spellings are accepted and they add. Two resolver bugs were fixed to make it
honest: `inherit` now takes the parent's resolved value (an inherited radius previously
read as a lost corner), and the CSS Overflow rule that `visible` computes to `auto` when
the other axis scrolls is now applied (without it a scroll area could not be recognised as
the box that clips).

**Implementation-agnosticism verified** — all of these score 1.0:

| variant |
| --- |
| golden: `overflow-clip-margin` + `margin-right: -0.1rem` + `padding-right: 0.1rem` |
| `width: calc(100% + 0.1rem)` instead of the negative margin |
| `px` units, `margin`/`padding` shorthands, `border-top-width: 0`, `border-top-style: none` |
| `transform: translateY(0)` / `matrix(1,0,0,1,0,0)` instead of removing the declaration |
| the whole fix written into a component `<style>` block |
| scrollbar narrowed to `0.6rem` but kept |

---

## CHANGE 4 — tests: pass-to-pass regression guards

**Lever:** tests

**Before:** `p2p: []`. Any patch that made the symptoms disappear scored 1.0, including
destructive ones.

**After:** three p2p, each verified to pass on base **and** golden:

- `selector-box-keeps-rounded-corners` — at least one resolved corner radius non-zero.
- `selector-box-keeps-clipping-and-side-edges` — the frame itself still clips, with
  non-zero rounding (only its rounded clip can shape the scrollbar's corners), and its
  left, right and bottom edges each still carry border ink. The right edge is in this p2p
  on purpose: it has to survive so it still shows on boxes whose list does not scroll.
- `selector-box-right-edge-survives-behind-the-rows` — whatever the list reaches across,
  its rows must not: overhang minus `padding-right` has to stay at zero, or the opaque
  rows hide the border on every non-scrolling box.
- `selector-list-keeps-bounded-scroll-area` — the list still scrolls, still has a non-zero
  `max-height`, `scrollbar-width` is not `none`, and the `::-webkit-scrollbar` width
  **resolved through the cascade** is > 0.

**Why harder — measured.** Six cheap patches that satisfy the f2p now score 0.5:

| cheap patch | now fails |
| --- | --- |
| draw the frame with inset shadows instead | scrollbar-covers-the-frame-edge + keeps-clipping-and-side-edges |
| `border-right-color: transparent` — delete the edge instead of covering it | scrollbar-covers-the-frame-edge + keeps-clipping-and-side-edges |
| add the overhang but leave the frame clipping it off | scrollbar-covers-the-frame-edge |
| unclip the frame, letting the rows cover the edge and the scrollbar square off | right-edge-survives-behind-the-rows + keeps-clipping-and-side-edges |
| `border-radius: 0` — square the corners | keeps-rounded-corners + keeps-clipping-and-side-edges |
| `::-webkit-scrollbar { width: 0 }` | keeps-bounded-scroll-area |
| `scrollbar-width: none` | keeps-bounded-scroll-area |

The last two are the "do not remove the scrollbar" guard. The first version of this p2p
**leaked**: it scanned raw rules for any `width > 0` declaration, so a later override
setting the pseudo-element to `width: 0` still scored 1.0. It now resolves the winning
declaration through specificity and source order, which closes it.

---

## CHANGE 5 — localization: cut to the minimum that stays solvable

**Lever:** localization + visual reliance

**Before:** `instruction.md` was one line — *"There's a small visual rendering artifact in
the options UI. See screenshots for before/after."* No symptom, and no reference to the
posters at all, so the evidence chain was broken.

**After:** 148 words. Three numbered symptoms in purely perceptual terms, split across the
two captures at the state each one is visible in, and one closing line of constraints. Symptoms 1 and 2 are deliberately left as bare pointers —
*"Shut, a box doesn't look shut"* and *"Open, the line where the header meets the list"* —
because the captures show both and the prompt should not do the perceiving for the
agent. Symptom 3 gets one sentence more, because its required end state (edge covered when
the list scrolls, edge still present when it does not) is a specification that cannot be
read off a defect capture at all; without it, deleting the edge would be an unfair fail.

Leak-scanned clean for `github.com`, `repo`/`repository`, `antimatter`, `IvarK`,
`Hirame`, `commit`, `issue #`, `PR #`, `files to change`, and for every mechanism token:
`transform`, `translate`, `border`, `margin`, `overflow`, `clip`, `box-shadow`, `inset`,
`radius`, `css`, `stylesheet`, `.css`, `l-select`, `expanding`, `vue`, `.vue`,
`padding box`. The closing constraint line was rewritten twice to get there — "contents
clipped to the rounded corners" became "the rows stay inside the box's curved corners",
which states the same requirement without naming the two properties the fix moves.

**Why harder:** the old prompt described no symptom at all, so it was unsolvable rather
than easy — and with empty `f2p`/`p2p` and a broken verifier path (CHANGE 6) it could not
discriminate anyway. The new one is solvable but hands over nothing.

---

## CHANGE 6 — anti-cheat and harness correctness (defects in the delivered bundle)

**Lever:** anti-cheat

1. **The verifier never ran.** Shipped as `tests/verifyer.py`; `test.sh` invokes
   `python3 /tests/verifier.py`. The call failed silently, no `reward.txt` was written, and
   `trap ensure_reward EXIT` wrote `0`. Oracle would have read **0.0**, indistinguishable
   from a real fail. Renamed.
2. **Binary-baseline reset trap.** `test.sh` derived reset paths from `grep '^+++ b/'`.
   Binary and rename sections emit no such line, so those paths would be skipped and any
   re-run would silently score 0. Now parses `diff --git a/… b/…` headers.
3. **Metadata disagreed with itself.** `task.toml` had `f2p = []`/`p2p = []` while
   `config.json` declared one f2p; `config.json` had `test_files: []` while `test.patch`
   adds `harbor_test.js`. Both now agree on all six identifiers.
4. **`task_id` malformed.** `…-pr3414-mm` does not match `<owner>__<repo>-<issue>-mm`.
   Corrected in both files. Test identifiers re-prefixed `pr3414::` → `ecb::` so nothing
   in the test surface names the PR.

`verifier.py`'s `match_idents` was also reordered to try an exact key, then a
`classname::name` key, then a substring — a substring hit could previously shadow an exact
one depending on dict order.

---

## CHANGE 7 — evidence: corrected-state poster removed, defect captures re-shot as a pair

**Lever:** anti-cheat / evidence honesty / visual reliance

`after.png` was the PR's capture taken after its **first** commit only. Two things make it
wrong for this task: its header/list seam is two device-pixel rows (y=106 and y=107 at
x=200) where the fixed build draws one, and it still shows the un-fixed scrollbar/frame
adjacency that symptom 3 now asks to be corrected. Presented as "how it should look" it
would have contradicted the prompt. Moved out of the bundle to
`../task1_after_STALE_pre-fix-reference.png`; `task_type` changed `visual_regression` →
`visual_bug_fix`.

The PR's own `before.png` was then replaced by two captures taken from a local build of
the base commit, because one frame could not carry all three symptoms cleanly — symptom 1
needs a shut box, symptoms 2 and 3 need an open one, and the PR's single frame showed the
shut box only in the corner the reporter had scribbled a circle on.

| file | state | carries |
| --- | --- | --- |
| `before_closed.png` | both selectors shut, four ordinary buttons below | symptom 1, with an in-image control |
| `before_open.png` | notation selector expanded, theme selector shut | symptoms 2 and 3, plus symptom 1 again on the left |

The pair is what makes symptom 1 findable at all. It is a one-pixel row that blends rather
than a line that appears, so it is only legible by comparison: in `before_closed.png` both
selector boxes close on **27,146,48** while every edge of the four ordinary buttons beside
them measures **27,187,54**. Putting those side by side in one frame is the whole
affordance — the earlier single poster relied on a hand-drawn circle to point at it, which
is evidence the reporter did not think it was findable either.

Measured evidence now recorded per file in `evidence_bundle.json`:

| symptom | where | defect | reference in same image |
| --- | --- | --- | --- |
| 1 | `before_closed.png`, y=104 | 27,146,48 | 27,187,54 at y=10, 124, 219, 238, 333 |
| 1 | `before_open.png`, x=200 y=102 | 27,146,48 | — |
| 2 | `before_open.png`, x=600 y=102 | 27,146,48 | 27,187,54 at y=144…494; left edge x=419 26,187,53 |
| 3 | `before_open.png`, y=13-98 and y=108-534 | track x=794-803 163,163,163, thumb x=796-801 19,134,38, **edge x=804 18,59,28**, background x=805 17,16,20 | — |

Four places kept in agreement per the guidelines: the files in `environment/assets/`,
`ASSET_MANIFEST.json` (two `bug`-role entries), `evidence_bundle.json` (two entries), and
the two image references in `instruction.md`. The Dockerfile copies `assets/` wholesale so
it needed no change.

Side effect: with no corrected reference to copy from, the agent must derive the target
state from the defect captures plus the prompt, which raises visual reliance further.
`visual_essentiality` stays `required` and is now unambiguous.

---

## Verifying the render (the one part the harness cannot check)

The harness resolves used values; it cannot rasterise. After applying `fix.patch`:

| # | where | expect |
| --- | --- | --- |
| 1 | a box whose list scrolls, right side | grey track runs to the outside of the box, no green strip beside it |
| 2 | a box whose list does **not** scroll, right side | green edge plainly visible, as in base |
| 3 | scrollbar top-right and bottom-right | follows the curve, not a square corner |
| 4 | left and bottom edges, every box | present, unchanged from base |
| 5 | any box collapsed | one crisp line under the header, no hairline below it |
| 6 | any box expanded, header/list seam | one full-intensity row, not two, not a dim blended one |
| 7 | first and last rows | still cut to the rounded corners |

```bash
python -c "
from PIL import Image
im=Image.open('after.png').convert('RGB')
print('seam  ', [(y, im.getpixel((200,y))) for y in range(104,110)])
print('right ', [(x, im.getpixel((x,300))) for x in range(392,402)])"
```

Rows 1–4 and 7 are what the three failed attempts got wrong, in that order; all are now
covered by `scrollbar-covers-the-frame-edge` (f2p),
`right-edge-survives-behind-the-rows` and `keeps-clipping-and-side-edges` (p2p).

---

## Not changed, and why

- **`tests/.S`** left as the pipeline wrote it. The guidelines spell the synthetic marker
  `.s`; renaming a marker whose consumer cannot be inspected is not worth the risk, and
  `f2p` is non-empty, which is what it gates.
- **The Dockerfile's `npm install 2>/dev/null || true`.** `harbor_test.js` uses only the
  Node standard library, so a silent dependency failure cannot affect the reward.
- **`ExpandingControlBox.vue`.** The root cause of the sub-pixel leak is
  `updateHeightInfo()` using integer-rounded `offsetHeight` where
  `getBoundingClientRect().height` is exact. Testing that means driving the component's
  internals, which pins the golden's method and `$refs` names — the overfit that produces
  invalid fails. It is the obvious next lever if the trial still passes.
- **`theme-S12.css`.** An earlier draft touched it, because replacing the frame's border
  with shadows broke that theme's `border-color: #747474` override. The accepted fix keeps
  the border, so the override keeps working and the file is untouched. `cross_file` is
  back to `false` — one file, two rules.
- **stylelint not run.** It needs the repo's `node_modules`, absent here. Property order
  was checked by hand against `.stylelintrc.json`'s order list; run `npx stylelint` inside
  the container if you want the confirmation.
