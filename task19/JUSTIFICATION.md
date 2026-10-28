# Hardening justification — `recharts__recharts-6814-mm`

Baseline before hardening: model trial scored **reward 1.0** (`claude-code__claude-opus-4-8`,
`Trials/result.json`), 3/3 f2p and 2/2 p2p.

---

## 0. Root cause of the passing trial: the answer was inside the image

Reading `Trials/Tasks__ue66Whv/agent/trajectory.json` (steps 11–15), the model did not diagnose
the defect from the screenshot at all. It ran:

```
cat node_modules/recharts/package.json | grep version; ls node_modules/.pnpm | grep -i recharts
grep -n "notZero\|realTotalAngle\|minAngle\|totalPaddingAngle\|absDeltaAngle" \
     /app/node_modules/.pnpm/recharts@3.10.1_*/node_modules/recharts/es6/polar/Pie.js
```

`@recharts/devtools` (a devDependency of the repo) transitively installs **published
`recharts@3.10.1`**, a release *newer than the fix*, whose compiled `es6/polar/Pie.js` already
contains `effectiveMinAngle` / `needsMinAngleAdjustment`. The model diffed `/app/src` against it
and transcribed the fix. Step 13 in its own words: *"Let me compare against the real recharts
3.8.0 source to identify the seeded bug."*

No amount of prompt vagueness would have mattered while the corrected implementation was sitting
in `node_modules`.

---

## 1. Anti-cheat — closed the leaked reference implementation

**Lever:** anti-cheat hardening.

**Before → after:** `environment/Dockerfile` ended at `pnpm install --no-frozen-lockfile`, leaving
`/app/node_modules/.pnpm/recharts@3.10.1_*/` in the image. Added a post-install stage that removes
every published copy of the package (`node_modules/.pnpm/recharts@*`, `node_modules/recharts`, the
`www/` tree, and any nested `*/node_modules/recharts` dir or symlink), plus the pnpm
content-addressed store under `/root/.cache/pnpm` and `/root/.local/share/pnpm/store` which holds
the same tarball contents (node_modules hardlinks keep whatever is still referenced alive). A
build-time assertion then greps `/app` for `effectiveMinAngle` / `needsMinAngleAdjustment` and
**fails the image build** if any reachable file still contains them, so the leak cannot silently
reappear when the dependency tree moves.

**Why it is safe:** `vitest.config.mts` sets `resolve.alias: { recharts: path.resolve(dirname,
'src') }`, so nothing at test time ever resolves through the published package — imports of
`recharts` (including the one inside `@recharts/devtools`) go to `/app/src`.

**Why it raises difficulty:** the previous winning strategy — locate a newer compiled build,
diff, transcribe — no longer exists. The agent has to derive the geometry itself.

---

## 2. Broader fix scope — one guard became three coupled invariants

**Lever:** broader fix scope (`solution/fix.patch`, still `src/polar/Pie.tsx` only, so
`cross_file` stays `false`).

**Before:** the golden was the upstream patch verbatim — skip redistribution when no non-zero
sector's natural angle (`percent * absDeltaAngle`) is below `minAngle`. ~10 added lines, one
condition.

**After:** the golden implements three interlocking corrections:

| # | Correction | Concrete arithmetic |
|---|---|---|
| 1 | Skip the reservation when nothing needs it | `needsMinAngleAdjustment` with strict `<`, so a sector landing *exactly* on the floor does not trigger it |
| 2 | Measure natural size against the arc actually available | `distributableAngle = max(absDeltaAngle - totalPaddingAngle, 0)`, used instead of `absDeltaAngle` in the threshold test |
| 3 | Cap the reservation at what the arc can hold | `effectiveMinAngle = min(minAngle, distributableAngle / notZeroItemCount)` |

Correction 2 is not cosmetic: with `paddingAngle={5}`, four sectors and `minAngle={34}`, the
`96/1000` sector is `34.56°` of the raw circle but only **`32.64°`** of the `340°` the sectors
actually share. The upstream one-line guard therefore skips the reservation and ships a sector
*below the floor it promised* — a regression the buggy base code does **not** have. Correction 3
is likewise a real defect in base: 12 non-zero sectors × `minAngle={40}` reserves `480°` out of
`360°`, so `realTotalAngle` goes to `-120°` and the largest sector is drawn with a **negative**
sweep, backwards over its neighbours (total drawn arc `720°` instead of `360°`).

**Why it raises difficulty:** the single guard that used to score 1.0 now fails two tests. An
agent that reasons only about "skip when nothing is below the threshold" — which is the natural,
and the published, reading of the symptom — loses both `sectors stay inside the pie span…` (f2p)
and `every non-zero segment keeps at least minAngle when padding shrinks…` (p2p). Each of the
three corrections is independently load-bearing.

---

## 3. Stronger tests — 3 f2p / 2 p2p → 5 f2p / 5 p2p

**Lever:** stronger / more tests. All added tests are behavioral (they read only the rendered SVG
`d` attribute through the repo's existing `getPieSectorAngles` helper) and never inspect source.

### New f2p (fail on base, pass on golden)

**`minAngle does not redistribute when padding is present and every segment clears the threshold`**
`paddingAngle={6}`, `minAngle={10}`, data `[400,300,200,100]`. Padding takes `4×6=24°`, so `336°`
is shared → natural `[134.4, 100.8, 67.2, 33.6]`, all clear the floor.
Base draws `[128.4, 98.8, 69.2, 39.6]` (every boundary moved) → fails. Golden draws the natural
angles → passes. *The old suite had no test with `paddingAngle` at all*, so the entire interaction
between padding and the reservation was unmeasured.

**`sectors stay inside the pie span when minAngle cannot be granted to every segment`**
12 non-zero values, `minAngle={40}`. Asserts every sector sweep is `> 0` and the sweeps sum to
`≤ 360.001°`. Base sums to **`720°`** (one sector at `293.2°` because its true sweep is `-66.8°`)
→ fails. Golden sums to `360°`. Deliberately written as a *property*, not as fixed angles, so any
sane fallback — cap the floor, or drop the reservation entirely — passes.

### New p2p (pass on base **and** golden; kill the shallow fix)

**`every non-zero segment keeps at least minAngle when padding shrinks the available span`**
`paddingAngle={5}`, `minAngle={34}`, data `[500,204,200,96]`. Asserts every sweep `≥ 34°`.
Base: min sweep `53.584°` ✓. Golden: `53.584°` ✓. **Upstream one-line fix: `32.64°` ✗.**
This is the trap that makes correction 2 mandatory, and it is a legitimate p2p — it guards a
guarantee the base code already honoured.

**`zero-value segments stay collapsed while minAngle is applied to the rest`**
Data `[50, 0, 5]`, `minAngle={40}`. Asserts that exactly **two** sectors occupy arc, each `≥40°`,
and that the drawn arc sums to `360°`. Passes on base and golden; fails any fix that drops the
`val !== 0` condition while restructuring the arithmetic (that fix draws three sectors at
`258.18 / 40 / 61.8`, so the occupied count becomes 3). Deliberately counts *occupied* sweeps
rather than rendered elements — the first draft asserted three rendered sectors and failed on
both base and golden, because recharts does not emit a path for a zero-value entry at all. Caught
by the container run, not by inspection.

**`render 4 equal sectors in PieChart with 4 data points`** (existing repo test, newly promoted to
p2p) — regression guard on the default, no-`minAngle` path.

**Why it raises difficulty:** previously a partial fix could not exist — there was one condition
to get right. Now the reward is binary across five f2p and five p2p, and the two most likely
partial attempts (upstream's guard; a guard that forgets the overflow case) each land on a red
test.

### Implementation-agnosticism

- The exact-angle assertions (f2p 1–4, p2p `still redistributes`) pin outputs for which exactly
  one correct answer exists — the natural proportional split, or the documented reservation
  arithmetic that base and golden share verbatim. There is no alternative correct geometry to
  reject.
- Every assertion about the *under-determined* cases (overflow fallback, floor guarantee) is a
  tolerance-based property, not a value: `> 0`, `≤ 360.001`, `≥ 34 - 0.001`. A differently
  implemented but behaviourally correct fix passes.
- All values verified numerically against a faithful re-implementation of `computePieSectors` →
  `getSectorPath` → `calculateAnglesFromPath`, including the 4-decimal rounding the SVG path
  round-trip introduces; no assertion sits near a rounding boundary.
- No test greps source; `verifier.py` derives reward purely from the JUnit report.

---

## 4. Harder localization + visual reliance

**Lever:** harder localization / stronger visual reliance.

**Before:** `instruction.md` said *"including values that land exactly on a threshold, and pies
that span only part of a circle"* — a literal enumeration of the two edge-case f2p tests, which
told the agent both what to special-case and that a threshold comparison existed.

**Also removed (second pass):** an intermediate draft still *described* the trigger semantically —
"unless a sector would otherwise come out too small to be seen", "the minimum size promised to a
sector that carries a non-zero value". That is effectively `minAngle`'s own doc comment in
`src/polar/Pie.tsx` ("The minimum angle of each unzero data"). An agent could have grepped the
prop docs, matched the paraphrase, and reached the reservation arithmetic **without ever opening
the poster**. Cut.

**After:** every clause in the prompt is a dangling reference *into the image*. Nothing is
described; things are only pointed at:

> Both charts in the screenshot draw **the same dataset**. They differ by **the one extra setting
> visible on the second**, and on **this dataset** that setting should have made no difference at
> all […] The amount **that setting** asks for should be committed:
> - to nobody, when every sector in the chart already reaches it on its own;
> - against the arc the sectors are actually given to divide, not the arc before the chart's other
>   spacing has been taken out of it;
> - never to a sector holding no value;
> - and never in a total larger than the arc can supply.

**Why it cannot be solved without the image.** Strip the screenshot and every referent goes
undefined: which dataset, which of `Pie`'s geometry props the second chart adds, and which way the
boundaries moved. None of the four invariants can be *instantiated*, so none can be localized —
there is nothing to grep for, because the text never names the behaviour, it only constrains "the
amount that setting asks for". The image supplies all three missing pieces at once: the editor
pane shows the two `<Pie>` elements side by side, identical but for the minimum-angle prop; the
values `(300, 30, 10, 10, 10)` are legible; and the browser pane shows the boundary rotation on
data whose natural angles all clear that minimum.

**Coverage is still complete, so the tests stay fair:** bullet 1 → f2p 1 and f2p 2 ("already
reaches it" is satisfied *at* the value, which is the strict comparison; an earlier draft said
"falls short of it", which a reader could have taken as "at or below" and implemented as `<=`,
producing an invalid fail on f2p 2) and f2p 4; bullet 2 → f2p 4 and
p2p `floor kept when padding shrinks span`; bullet 3 → p2p `zero-value segments`; bullet 4 → f2p
`sectors stay inside the pie span`; closing sentence → f2p 3 (partial pie) and the proportional
p2p guards. Nothing is tested that was not asked for, and nothing is handed over.

There is no "files to change", no API name, no snippet, no corrected-output preview, and no
repo/org/issue/PR trace anywhere in the prompt. `visual_essentiality` raised `helpful` →
`required` accordingly.

---

## 5. Metadata

- `visual_essentiality`: `helpful` → **`required`** (see §4).
- `difficulty`: `medium` → **`hard`**; `difficulty_explanation` rewritten to name the three
  independent corrections and why the screenshot is the only source of the trigger.
- `f2p` / `p2p` in `task.toml` updated to match `tests/config.json` exactly (5 + 5).
- `cross_file` stays `false` — the fix genuinely remains within `src/polar/Pie.tsx`;
  `files_edited` still equals what `fix.patch` touches.
- `title` reworded so the metadata itself does not name the prop.
- `evidence_bundle.json` description replaced with an accurate account of what the poster shows
  (data values, the two renders, and that the prop is visible only in the image).
- `task_type` unchanged: `data_viz_correctness` — the poster is a chart with a
  segment-geometry defect.

---

## 6. Validation trap fixed

`tests/test.sh` reset step read paths with `grep '^+++ b/'`. Per the guidelines' known trap that
skips binary/rename hunks and silently scores 0 on re-run. Replaced with extraction from the
`diff --git a/… b/…` headers so the reset is complete and the verifier stays idempotent. (This
patch is text-only today; the change removes the latent failure mode.)

---

## 7. Gate — re-validated in the real container

The image was built from the hardened `environment/Dockerfile` and `tests/test.sh` was executed
inside it. Measured, not predicted:

| Candidate | f2p | p2p | reward |
|---|---|---|---|
| **nop** (untouched base) | 0/5 | 5/5 | **0.0** |
| **oracle** (`solution/fix.patch`) | 5/5 | 5/5 | **1.0** |
| **naive** (the merged upstream patch, applied verbatim) | 4/5 | 4/5 | **0.0** |

The naive row is the point of the hardening: it fails exactly the two intended traps —
`sectors stay inside the pie span when minAngle cannot be granted to every segment` (f2p) and
`every non-zero segment keeps at least minAngle when padding shrinks the available span` (p2p).
An agent that reproduces the real upstream fix now scores zero.

Also confirmed in-container:

- The anti-cheat stage builds clean and its assertion does **not** trip.
  `ls /app/node_modules/.pnpm/recharts@*` → *No such file or directory*;
  `find /app -path '*/node_modules/*' -name recharts` → empty;
  `grep -rls -e effectiveMinAngle -e needsMinAngleAdjustment /app` → empty.
- The verifier reaches the end every time (stage banners plus a real `reward=` line, never an
  EXIT-trap 0), and `test.sh` is idempotent: a second consecutive run on the same container also
  returns 1.0.
- `fix.patch` and `test.patch` both apply cleanly on `base_commit` (`git apply --check`).

Still to run in the sandbox (needs the harness, not just Docker):

```bash
bash ~/.claude/skills/mmswe-runner/mm_run.sh /home/sandbox/Tasks check
bash ~/.claude/skills/mmswe-runner/mm_run.sh /home/sandbox/Tasks trial    # expect < 1.0
bash ~/.claude/skills/mmswe-runner/mm_run.sh /home/sandbox/Tasks analyze
```
