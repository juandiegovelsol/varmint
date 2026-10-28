# task10 — libgdx__libgdx-7731-mm — hardening justification

Issue: a nine-piece stretchable panel graphic renders as disconnected fragments when the
source region comes from a sheet packed with the inverted vertical layout.
Golden fix (real PR #7736): `gdx/src/com/badlogic/gdx/graphics/g2d/NinePatch.java`, the
`NinePatch(TextureRegion, int, int, int, int)` constructor — all nine sub-region Y offsets and
heights are multiplied by `sign = region.isFlipY() ? -1 : 1`.

Scope of the golden fix is unchanged (one file, still equal to `files_edited`, still applies
on `base_commit`). Everything below is prompt, test and metadata work.

---

## 1. Localization — `instruction.md` rewritten

**Before** (verbatim, the whole prompt):

> # Flipped NinePatch broken
> The images below show the same `NinePatch` panel, rendered from a `TextureAtlas` region
> packed with `flip = true`.
> … Fix the codebase so the NinePatch renders correctly.

Three separate giveaways in two sentences:

| Removed token | What it handed over |
|---|---|
| `NinePatch` (title + body + closing line, 3×) | the exact class **and** the exact file to edit — `NinePatch.java` |
| `TextureAtlas` | the collaborating type, so the atlas→region→patch chain never had to be traced |
| `flip = true` | the trigger condition **and** the predicate name (`isFlipY`) in one token |

The prompt was effectively `grep -r NinePatch` → open the only constructor that mentions
`flip` → done. That matches the observed trial: solved in ~51 min at reward 1.0.

**After**: the prompt names no type, no method, no property and no file. It states the
symptom in domain words only ("a small source graphic … cut into edge pieces and an interior
piece, so the border keeps its original thickness while the inside scales up"), gives the
repro condition in packer terms ("the packer's inverted vertical layout") and stops. A leak
scan for `ninepatch|textureatlas|isflipy|flip *=|libgdx|badlogic|github|\.java|uv|sign`
returns nothing.

The agent must now: read the "Actual" poster → recognise it as mis-sampling rather than
mis-scaling → infer the defect is in the *cutting* step, not the drawing or packing step →
walk skin → texture-region → the one constructor that carves nine sub-regions → notice that
its offsets advance along the parent's pixel axis while the parent's vertical axis runs the
other way.

`visual_essentiality` was already `required`; with the recipe gone it is now honestly so.
`difficulty` raised `medium` → `hard`, and `difficulty_explanation` rewritten to say
concretely why the poster is load-bearing and why the fix is easy to get half-right.

## 2. Tests — 1 f2p / 0 p2p → 3 f2p / 2 p2p, and made public-API-only

**Before**: one f2p, `testFlippedNinePatchUVCoordinates`. It reached into `NinePatch`'s
**private** state by reflection — the `vertices` float array plus the private `topCenter`,
`middleCenter`, `bottomCenter` index fields — and compared three baked floats against
hard-coded constants for one 30×30 / 10px-border configuration. No p2p at all.

Two problems: it was coupled to internal field names (a rewrite that kept the behaviour but
renamed or restructured that state would have been failed invalidly), and with no p2p a fix
that simply negated unconditionally scored a full 1.0.

**After**: `NinePatchFlipUVTest` drives only the public surface —
`new NinePatch(region, l, r, t, b)` and `patch.draw(batch, x, y, w, h)` — with the `Batch`
supplied as a `java.lang.reflect.Proxy` that records the emitted vertex stream. No private
field of the class under test is touched. (`sun.misc.Unsafe` is still used, but only to
allocate a GL-free `Texture` stub — that is framework plumbing, not the code under test, and
keeps the suite headless and deterministic.)

The assertion is a geometric invariant rather than a magic number: *a patch drawn over its
whole region must map that region onto the target rectangle exactly as a single unsplit
sprite of the same region would*, so each emitted quad is checked against the screen rectangle
**and** the texture rectangle its requested split implies, in whichever orientation the region
is stored. Corner order is recovered from the data, not assumed. Tolerance is 0.9 texel; the
smallest discriminating error is 3 texels.

| id | kind | scenario | discriminates |
|---|---|---|---|
| `testFlippedFullRegionSymmetricSplits` | f2p | 30×30 page, full region, 10px borders, inverted layout | the poster's panel case; base emits v up to 2.0 — off the texture entirely |
| `testFlippedSubRegionAsymmetricSplits` | f2p | 64×64 page, region at (8,40) 24×16, borders 5/7/3/6, inverted | region offset ≠ 0 **and** four different border widths — rejects anything that assumes a full-page region or symmetric splits |
| `testFlippedVerticalSplitsOnly` | f2p | same region, borders 6/6/0/0, inverted | boundary case: one full-height row of three pieces, exercising the `top == 0` branch the old suite never entered |
| `testUnflippedSubRegionAsymmetricSplits` | p2p | identical to f2p #2 with the ordinary layout | **the regression guard**: an unconditional sign flip now costs the run |
| `testFlippedCenterOnlyPatch` | p2p | degenerate single-piece patch on an inverted region | guards the shared load/draw path a rewrite could break |

Verified against six builds (compiled and run locally against a real gdx classpath — base and
golden `NinePatch.java` compiled from `323c151`, four hand-written alternatives):

| build | f2p | p2p | reward |
|---|---|---|---|
| base (nop) | 0/3 | 2/2 | **0.0** |
| golden fix (oracle) | 3/3 | 2/2 | **1.0** |
| unconditional negation (fits the screenshot, ignores the ordinary layout) | 3/3 | **1/2** | 0.5 |
| top row corrected only | 0/3 | 2/2 | 0.0 |
| alternative correct impl #1 — un-flip a copy of the region, take rows in reverse order, flip each piece back | 3/3 | 2/2 | **1.0** |
| alternative correct impl #2 — set each piece's UV rectangle directly, no pixel offsets, no `sign` | 3/3 | 2/2 | **1.0** |

Rows 5 and 6 are the implementation-agnosticism proof: neither shares a line with the golden
(one has no `sign` variable at all, the other never calls the pixel-offset constructor) and
both score 1.0. Rows 3 and 4 are what the old suite could not catch.

## 3. Anti-cheat / harness

* `verifier.py` now parses `--rubric` and writes `reward.json` as a **flat numeric** map
  (`f2p::<name>` / `p2p::<name>` = 1.0/0.0, `rubric_pass` = 1/0/−1). Previously it wrote only
  `reward.txt`, which is why `qc_gate` reported *"Nop/ has no reward.json — an inert f2p test
  cannot be detected"*. The rubric gate can only turn 1.0 into 0.5, never toward 0.0.
* `test.sh` now passes `--rubric` to the verifier (it computed `RUBRIC` and then discarded it),
  and synthesises an all-fail report if `javac` fails or the JVM dies before writing one — so a
  build break scores a real 0.0 instead of an unscored run. Fallback path verified to yield 0.0.
* The suite writes its own JUnit XML (one `<testcase>` per scenario), so per-test outcomes reach
  the verifier instead of one aggregate pass/fail.
* Test reset still reads paths from `diff --git` headers (the binary-baseline trap), and tests
  still reset from `harbor_base` before `test.patch` is applied, so editing tests cannot change
  scoring.

## 4. Rubric

`tests/rubrics.json` replaced the always-pass stub with one criterion covering the only thing
the behavioural suite cannot prove — *generality*, since tests can only sample finitely many
configurations:

> In `gdx/src/com/badlogic/gdx/graphics/g2d/NinePatch.java`, the constructor that cuts a source
> `TextureRegion` into its nine pieces determines the vertical direction of the piece offsets
> from a value it reads off that source region at construction time, so one code path yields
> in-bounds pieces for a region stored either way up.

Factually true of the golden (`region.isFlipY() ? -1 : 1`) and of both alternative correct
implementations above; false of a hard-coded negation. `qc_rubrics.py` static verdict: PASS
(0 Major / 0 Moderate / 0 Minor over 1 criterion).

## 5. Metadata

`title`, `difficulty` (medium → hard), `difficulty_explanation`, `f2p`, `p2p` updated;
`f2p`/`p2p` identical in `task.toml` and `tests/config.json`; `test_framework` rewritten to
describe the new harness. `cross_file` stays `false` (fix is genuinely one file — the real PR
touches one file, and inventing a second would violate "stay real"). `evidence_bundle.json`
descriptions rewritten to state what each poster *shows* rather than to explain the defect's
mechanism, which the old "after" description spelled out in full.

## 6. Gate status

| check | state |
|---|---|
| `qc_structure` | PASS |
| `qc_rubrics` | PASS |
| `qc_judge` | all three real findings fixed. The one remaining `[FAIL]` is a Windows-only artifact of that check: it calls `bash -n` on an `os.path.join` path, and git-bash eats the backslashes (`task10Tasksteststest.sh: No such file or directory`). `bash -n task10/Tasks/tests/test.sh` returns 0. |
| `qc_gate` | **still failing on the stale run artifacts** — `Nop/` predates the `reward.json` change and `Trials/` is the pre-hardening 1.0 run. Both need a re-run in the sandbox; harbor/docker/the mmswe-runner skill are not available on this machine. |

To close the gate, in the sandbox:

```bash
bash ~/.claude/skills/mmswe-runner/mm_run.sh /home/sandbox/Tasks oracle   # expect 1.0
bash ~/.claude/skills/mmswe-runner/mm_run.sh /home/sandbox/Tasks nop      # expect 0.0
bash ~/.claude/skills/mmswe-runner/mm_run.sh /home/sandbox/Tasks oracle   # again -> 1.0 (idempotent)
bash ~/.claude/skills/mmswe-runner/mm_run.sh /home/sandbox/Tasks check
bash ~/.claude/skills/mmswe-runner/mm_run.sh /home/sandbox/Tasks trial    # must now be < 1.0
bash ~/.claude/skills/mmswe-runner/mm_run.sh /home/sandbox/Tasks analyze
```

Then replace `Oracle/`, `Nop/` and `Trials/` with the new runs.
