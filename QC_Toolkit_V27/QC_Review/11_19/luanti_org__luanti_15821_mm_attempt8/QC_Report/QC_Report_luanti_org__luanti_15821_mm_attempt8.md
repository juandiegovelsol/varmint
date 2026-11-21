# QC Report: luanti_org__luanti_15821_mm

- **Task hash:** `luanti_org__luanti_15821_mm_attempt8`
- **Title:** Parts of the scene in the video are drawn wrong (luanti 15821, Attempt8)
- **Rubric:** Official V27
- **Review date:** 2026-11-19
- **Verdict:** **FAIL**. Fails on **Hardening – Difficulty**: 2 of the 4 with-image trials pass (`2nxVxqj` and `79YZ3Xy`, both 9/9 f2p + 9/9 p2p). Option A needs exactly 1/4. The no-image side is fine (0/3). Everything else holds: local oracle = 1.0 and nop = 0.0 in a QC-built image (oracle re-run identical), the fix applies cleanly, IDs match, and every f2p tests a defect the clip shows. Symptom Specificity is a non-fail 3 (`[Non-Fail - Image-carried Symptom]`): the text names the elements only abstractly ("parts") and leaves the exact defects to the clip.

## Scorecard

| # | Dimension | Score | Result | Error category |
|---|---|---|---|---|
| 1 | Structure – Task Bundle Files | 5 | Pass | — |
| 2 | Structure – Deliverables & Packaging | 5 | Pass | — |
| 3 | Instruction – Requires Visual Evidence | 5 | Pass | — |
| 4 | Instruction – Symptom Specificity | 3 | Non-Fail | [Non-Fail - Image-carried Symptom] |
| 5 | Instruction – Task Type | 5 | Pass | — |
| 6 | Image – Evidence Quality | 5 | Pass | — |
| 7 | Metadata – task_type | 5 | Pass | — |
| 8 | Evidence – Chain Consistency | 5 | Pass | — |
| 9 | Golden Fix – Applies Cleanly | 5 | Pass | — |
| 10 | Golden Fix – Source-Only Scope | 5 | Pass | — |
| 11 | Tests – Implementation Overfit | 5 | Pass | — |
| 12 | Tests – f2p/p2p Identifier Validity | 5 | Pass | — |
| 13 | Tests – p2p Classification | 5 | Pass | — |
| 14 | Tests – Discriminating (f2p) | 5 | Pass | — |
| 15 | Tests – Determinism | 5 | Pass | — |
| 16 | Hardening – Difficulty (Model Trial Fails) | 2 | Fail | [Fail - Trial Threshold Not Met] |
| 17 | Hardening – Real & Feasible | 5 | Pass | — |
| 18 | Gate – Oracle/Nop | 5 | Pass | — |
| 19 | Unauditable | 5 | Pass | — |

## Delivery gate

| # | Check | Result | Detail |
|---|---|---|---|
| 1 | Oracle (local) | PASS | 1.0: f2p 9/9, p2p 9/9; banners and `reward=1.0` present. |
| 2 | Nop (local) | PASS | 0.0: f2p 0/9, p2p 9/9; banners and `reward=0.0` present. |
| 3 | Oracle re-run (local) | PASS | 1.0, and the `reward_detail.json` is identical to the first oracle run and to the CB oracle. |
| 4 | CB oracle / nop | PASS | CB `Oracle` 1.0 (9/9, 9/9), CB `Nop` 0.0 (0/9, 9/9), banners and `reward=` present. |
| 5 | fix.patch applies at harbor_base | PASS | `git apply --check /solution/fix.patch`: `APPLY_CHECK_OK` |
| 6 | Verifier completion | PASS | All 7 trials and the oracle/nop runs wrote `reward.txt`, `reward.json`, `junit.xml` and `reward_detail.json`. No exceptions in `result.json`. |
| 7 | pass@3 (no-image) | PASS | 0/3 pass (`3x5Uv9x` 0.0, `JTnUnsf` 0.0, `ZTf6Gye` 0.0). Assets confirmed absent. |
| 8 | pass@4 (with-image, Option A) | FAIL | 2/4 pass (`2nxVxqj` 1.0, `79YZ3Xy` 1.0, `EuyuJbj` 0.0, `cqnZGh3` 0.0). Option A needs exactly 1/4. |
| 9 | Trial run time (informational) | PASS | 13.2–18.4 min per trial, all well inside the 90 min agent timeout. |
| 10 | Trial / task checksum | PASS | With-image trials and CB oracle/nop share task checksum `17530948…`; no-image `a0e093…` (assets stripped). `task_manifest.json` lock `a90499…`: 18/18 files match the `Tasks/` on disk. |
| 11 | Packaging | PASS | `Tasks/` and `Trials/` are sibling root folders; 7 trials (3 no-image + 4 with-image). Archive form not checked: the folder holds the extracted trees. |
| 12 | Leaks | PASS | No repo name, URL, issue/PR link, file list or code identifier in `instruction.md`. `ASSET_MANIFEST.json` is not copied into the image. `.git` history is dropped. Agent runs used `network_mode = no-network`. |
| 13 | Evidence chain | PASS | File, manifest (sha256 and bytes), `evidence_bundle.json` local_path and the instruction ref all point to `/app/.harbor_assets/recording.mp4`. |

## Trials

| Trial | Mode | Reward | f2p | p2p | Minutes | Failed tests |
|---|---|---|---|---|---|---|
| task_without_images__3x5Uv9x | no-image | 0.0 | 5/9 | 9/9 | 18.0 | overlay: not pushed just because layer 1; overlay: not closer than geometry; no overlay: no offset; fence along Z |
| task_without_images__JTnUnsf | no-image | 0.0 | 5/9 | 9/9 | 18.2 | overlay: not pushed just because layer 1; overlay: not closer than geometry; no overlay: no offset; fence along Z |
| task_without_images__ZTf6Gye | no-image | 0.0 | 6/9 | 9/9 | 15.0 | overlay: not pushed just because layer 1; overlay: not closer than geometry; no overlay: no offset |
| task_with_images__2nxVxqj | with-image | 1.0 | 9/9 | 9/9 | 13.2 | — |
| task_with_images__79YZ3Xy | with-image | 1.0 | 9/9 | 9/9 | 18.4 | — |
| task_with_images__EuyuJbj | with-image | 0.0 | 7/9 | 9/9 | 17.9 | framed glass along X; fence along Z |
| task_with_images__cqnZGh3 | with-image | 0.0 | 5/9 | 9/9 | 17.8 | overlay: not pushed just because layer 1; overlay: not closer than geometry; no overlay: no offset; framed glass along X |

## Issues & suggested fixes

### Instruction – Symptom Specificity: 3 [Non-Fail - Image-carried Symptom]

**What is wrong:** The text never names the affected element types (stairs, slabs, glass, rails, fence, ladder/sign outline). It uses "parts" plus categories, and the exact defect per element is carried only by the clip. Not a fail under V27; record as `[Non-Fail - Image-carried Symptom]`.

**Suggested fix:** Optional, for a 5: name element types and defects in text without the cause, e.g. "Some stairs face the wrong way and some shaped blocks are missing a side; one glass window has frame bars where its panes meet; two rail corners bend the wrong way; one fence row is not joined; the outline of things on some walls floats away from them; the track and the outline on the grass are partly hidden." Caution: with the task already too easy (2/4, see Difficulty), this would make it easier still, so weigh it against dimension 16. Any change to `instruction.md` changes the task checksum, so all 7 trials must be re-run.

### Hardening – Difficulty (Model Trial Fails): 2 [Fail - Trial Threshold Not Met]

**What is wrong:** 2 of 4 with-image trials pass. Option A requires exactly 1/4, so this is `[Fail - Trial Threshold Not Met]`.

**Suggested fix:** Make the task a little harder and re-run all 7 trials, since any edit changes the checksum. Both passing runs found all seven defects. The failing runs missed the framed-glass X row (2/2) and the Z fence (1/2), so those are the hardest defects; the others were found by every with-image run. The text-only runs show that a code audit guided by the Expected bullets finds 5/7, so the levers are the bullets that localize in text: "also for a part fixed to a wall" points straight at the wallmounted selection box, and "links up with its neighbours" points at the connected drawtypes. Trim one of them, keeping the element named and the text truthful (dimension 4). Alternatively, switch to Option B (3 no-image plus 8 with-image, needing 1–2/8). At the observed rate of about 2/4 that is unlikely to land in range without hardening first.

## Dimension details

### 1. Structure – Task Bundle Files: 5 (Pass)

**Evidence:** All 11 fixed files present and non-empty: `task.toml` (5176 B), `instruction.md` (1154 B), `evidence_bundle.json` (993 B), `environment/Dockerfile` (2970 B), `environment/assets/ASSET_MANIFEST.json` (604 B), `solution/fix.patch` (5364 B), `solution/solve.sh` (349 B), `tests/config.json` (1882 B), `tests/test.patch` (25168 B), `tests/test.sh` (10434 B), `tests/verifier.py` (6623 B). `json.load` passes on all three JSON files; `tomllib` parses `task.toml`; `python3 -m py_compile tests/verifier.py` succeeds. `recording.mp4` decodes: `ffprobe` gives h264 1280x720, 30 fps, 1890 frames, 63.0 s, and 32 frames were extracted with ffmpeg for the contact sheets. Extra items: `environment/bugs/bug_01..06.patch` (injected bugs) and `README.md`. Neither is a fail.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 2. Structure – Deliverables & Packaging: 5 (Pass)

**Evidence:** `task111/Attempt8/` has `Tasks/` (capital T) and `Trials/` as sibling root folders. `Tasks/luanti_org__luanti_15821_mm/` is the bundle. `Trials/` holds `without_images/` (3 runs: `3x5Uv9x`, `JTnUnsf`, `ZTf6Gye`; job `n_attempts: 3`) and `with_images/` (4 runs: `2nxVxqj`, `79YZ3Xy`, `EuyuJbj`, `cqnZGh3`; job `n_attempts: 4`), so 7 trials (Option A layout). The other folders (`Oracle/`, `Nop/`, `Check/`, `Analyze/`) are extras and do not affect packaging. The folder holds the extracted trees, not the `.tar.gz` files, so the archive form itself could not be checked.

**What is wrong:** Nothing found. Note: when submitting, package `Tasks/` and `Trials/` as separate `Tasks.tar.gz` and `Trials.tar.gz` that unpack to those exact top-level folder names.

**Suggested fix:** None.

### 3. Instruction – Requires Visual Evidence: 5 (Pass)

**Evidence:** `instruction.md` points to `/app/.harbor_assets/recording.mp4` (the path resolves; the Dockerfile has `COPY assets/recording.mp4 /app/.harbor_assets/`). The text names no affected part, file or mechanism. It lists only three kinds of problem (how parts are put together, what stays visible close by and far away, how the pointed-at thing is marked) and general rules. Which parts are wrong, and in which direction, is visible only in the clip: east/west stairs built backwards (t≈25–31 s), rail corners bending the wrong way (t≈21 s), bars at the pane joints of the X-row window (t≈45 s), an unjoined fence along Z next to a joined one along X (t≈55 s), outlines floating off the wall for the ladder and sign (t≈39–51 s), the track missing from a distance (t≈6 s) and the outline on the grass hidden close up (t≈1 s). Trials back this up (supporting evidence only, as the rubric says): none of the 3 no-image runs touched `src/client/tile.cpp` (their `submission.patch` lists only `content_mapblock.cpp` and `mapnode.cpp`), and all 3 failed the overlay f2p. All 4 with-image runs located and edited the overlay depth code. Leak scan: no repo name, URL, org, issue/PR link or file list in `instruction.md`.

**What is wrong:** Nothing found. Non-graded note: the Expected line "nothing is drawn even slightly nearer than the surface it belongs to (this matters for blocks that have a second picture painted over their main one…)" comes close to naming the mechanism (overlay-layer depth offset). It is phrased as a visible rule, and text-only agents still didn't find it, so it isn't a leak fail.

**Suggested fix:** None required.

### 4. Instruction – Symptom Specificity: 3 (Non-Fail) [Non-Fail - Image-carried Symptom]

**Evidence:** Prompt table (element | defect, text or image? | expected, text or image? | comparison pointed to | clue left to image | described correctly?):
1. "some of the parts" / "Every part faces the way it was placed and is drawn whole, from every side" | text gives only the category ("how some of the parts are put together"); the actual defect (stairs built backwards, open sides missing) is image-only | text | none named (the clip has correct counterparts but the text does not point to them) | which part, which direction: image | yes.
2. "A part that links up with its neighbours" | text: only "links … correctly"; actual defect (bars at the glass joints, fence along Z unjoined, two rail curves wrong): image | text (generic) | none named | which part, which axis: image | yes.
3. "what stays visible from close by and from far away" / "Nothing disappears into what it rests on … nothing is drawn even slightly nearer than the surface it belongs to" | text (disappearing) | text | none | the trigger is partly given in text ("blocks that have a second picture painted over their main one") | yes.
4. "how the game marks what the player points at" / "one closed box that fits around it, also for a part fixed to a wall" | category in text; exact defect (outline mostly hidden, box floating off the wall): image | text | none | which node: image | yes.
The generic phrase ("Several things go wrong in `recording.mp4`") is followed straight away by the three kinds of problem and the expected rules, so the symptom-specificity check passes. Nothing is described incorrectly. Elements are named only by abstract stand-ins ("parts", "a part that links up with its neighbours", "a part fixed to a wall"), and the exact defects are left to the clip. That is the Image-carried Symptom case (3), not a fail. Trajectory check (all 4 with-image runs): every run read the same symptom classes, and none took a defect for intended behaviour. `EuyuJbj` never investigated the framed-glass or fence code paths (it did not find them). `cqnZGh3` never found the glass bug, and kept a small overlay bias on purpose, saying in its final message: "your spec says nothing should be drawn even slightly nearer, and this is a tiny exception". That was a deliberate deviation, not confusion between bug and intended behaviour. `2nxVxqj` and `79YZ3Xy` found all seven defects.

**What is wrong:** The text never names the affected element types (stairs, slabs, glass, rails, fence, ladder/sign outline). It uses "parts" plus categories, and the exact defect per element is carried only by the clip. Not a fail under V27; record as `[Non-Fail - Image-carried Symptom]`.

**Suggested fix:** Optional, for a 5: name element types and defects in text without the cause, e.g. "Some stairs face the wrong way and some shaped blocks are missing a side; one glass window has frame bars where its panes meet; two rail corners bend the wrong way; one fence row is not joined; the outline of things on some walls floats away from them; the track and the outline on the grass are partly hidden." Caution: with the task already too easy (2/4, see Difficulty), this would make it easier still, so weigh it against dimension 16. Any change to `instruction.md` changes the task checksum, so all 7 trials must be re-run.

### 5. Instruction – Task Type: 5 (Pass)

**Evidence:** `task_type = "visual_regression"` (Guidelines Step IV: decide which change is the accidental regression and reverse only that, keeping intended changes). The instruction describes drawing defects to fix and says "Everything else should keep looking as it does now". The defects are regressions against intact counterparts of the same kind in the same clip (the other stairs, the other window, the X-fence). Upstream issue 15821 is a regression of the overlay polygon offset. The text fits the type reasonably.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 6. Image – Evidence Quality: 5 (Pass)

**Evidence:** Naming table (file | role | what the frames show | what name/role/instruction claim | true? | agents confused?):
`recording.mp4` | `recording` | an uncut 63 s first-person clip of a devtest scene at the injected base: a track loop, stairs on a grass hill, a cobble house with framed-glass windows, ladder, sign and slab, and two fences; the camera stops on parts so the outline appears | neutral name; description: "uncut 63-second player-eye clip … stops on one, so the game marks what the player is pointing at"; instruction: "Several things go wrong in `recording.mp4`" | true (sha256 `bcc16a63…` = manifest; frames in `evidence/`) | no (no run treated the clip as the expected state).
Asset vs f2p, per defect (preconditions from `test.patch` → state in the clip → reachable?):
(1) 3 overlay f2p (`test_tile_polygon_offset.cpp`: a cube with an overlay on every side; `applyMaterialOptions` must not pull layer 1 toward the camera; a node without an overlay gets no offset) → grass ground with an overlay: the outline is drawn dashed or hidden at t≈1 s and the track lying on it is gone at t≈6 s → yes. Cross-check: the fix of what the clip shows (drop the pull on the overlay) passes all 3. Shown by `79YZ3Xy` and `EuyuJbj` (offset removed, overlay f2p pass) and `2nxVxqj` (removed + LESSEQUAL, pass). A fix that keeps a pull (`cqnZGh3`) still hides things resting on the grass and fails, as it should.
(2) Framed glass along X (3-pane row along X; no frame at the joints, frame at both ends) → house window running along X shows bars at the pane joints (t≈45 s), while the Z window is clean → yes.
(3) facedir 1/3 node box (stair; node, selection and collision boxes plus the drawn top) → east/west stairs built backwards (t≈25–31 s), north/south fine → yes.
(4) Node box beside a full block on X (slab next to stone; the open opposite face must be drawn) → see-through stairs and slab sides (t≈25 s, t≈39–47 s) → yes.
(5) Rail curves +X+Z / −X−Z (UV corners turned by 90/270) → two corner kinds of the loop bend the wrong way (t≈21 s) → yes.
(6) Fence posts along Z (bars join the posts, nothing beyond) → the Z fence row stands as separate posts, while the X row is joined (t≈55 s vs t≈57 s) → yes.
(7) Wallmounted Z selection box (param2 4/5) → the outline of the ladder and sign on the Z walls floats on the far side of the node (t≈39–51 s), while the X-wall ladder is fine → yes.
Step 7 (injected defects): all 6 `environment/bugs/` defects appear in the clip. A fix that skips any of them leaves a visible defect in the clip on a supported drawtype (facedir node box, nodebox face culling, raillike, fencelike, glasslike_framed, wallmounted), so it would be an incomplete fix, not an alternative. Complete fix? Yes only with all 7.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 7. Metadata – task_type: 5 (Pass)

**Evidence:** `visual_regression` is one of the seven valid values. The asset is one recording of the regressed state, with intact counterparts of each broken kind in the same clip; the rubric says not to penalize a valid choice even if another type fits better. The tags include `multimodal`, `visual_regression` and `Luanti`.

**What is wrong:** Nothing found. Non-graded note: the Step IV evidence column for `visual_regression` is a before/after pair. A single clip of the broken state would also fit `visual_bug_fix`.

**Suggested fix:** None required.

### 8. Evidence – Chain Consistency: 5 (Pass)

**Evidence:** File `environment/assets/recording.mp4`: 10520876 B, sha256 `bcc16a63d102965661fdf419f5d2145b20c9feb4eaab4d24f685ea262b357513`. `ASSET_MANIFEST.json`: `file: recording.mp4`, same bytes and sha256, `container_path: /app/.harbor_assets/recording.mp4`. `evidence_bundle.json`: `local_path: /app/.harbor_assets/recording.mp4`, role `recording`, `source_kind: captured_from_repo` (an empty `url` is valid for captured evidence). `instruction.md` ref: `/app/.harbor_assets/recording.mp4`. Dockerfile: `COPY assets/recording.mp4 /app/.harbor_assets/`. All four agree.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 9. Golden Fix – Applies Cleanly: 5 (Pass)

**Evidence:** In the QC image (cached apt/clone/cmake layers at `c07499cc…`, plus the Attempt8 `bugs/*.patch` applied, plus a fresh `harbor_base` tag), `git apply --check /solution/fix.patch` printed ``APPLY_CHECK_OK``. `git apply --check /tests/test.patch` printed ``TESTPATCH_CHECK_OK``. The CB oracle log also shows `== captured submission.patch (5364 bytes, 5 files) ==` and reward 1.0.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 10. Golden Fix – Source-Only Scope: 5 (Pass)

**Evidence:** The `diff --git` paths in `fix.patch` are `src/client/content_mapblock.cpp`, `src/client/tile.cpp`, `src/client/tile.h`, `src/mapnode.cpp` and `src/nodedef.cpp`. That set equals `files_edited` exactly (compared in Python: True). No test, doc, lockfile or changeset path.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 11. Tests – Implementation Overfit: 5 (Pass)

**Evidence:** Value-level assertions are float comparisons on `SMaterial::PolygonOffsetSlopeScale` / `PolygonOffsetDepthBias` (`>= 0`, `overlay <= base`, `== 0` for a node without an overlay) and geometry checks with tolerances (`sameBoxes` is order-independent with EPS 1e-3; `covered` is point-in-triangle for either winding; `hasFace` checks normal and plane; rail corners are matched as pos+UV pairs in any vertex order; fence checks are bounds only). The accepted set is the material's float fields, which Irrlicht reads freely, so no string, enum or format spelling is involved.
Equivalence table (alternative | correct in repo context? | test accepts):
• golden: positive offset on layer 0 only when an overlay exists | yes | yes
• remove the overlay offset entirely | valid (meets every instruction rule) | yes, run by the verifier in `79YZ3Xy` and `EuyuJbj` (all 3 overlay f2p pass)
• remove the offset and draw the overlay with `ZBuffer = ECFN_LESSEQUAL` | valid and plausible | yes, verified in `2nxVxqj` (reward 1.0)
• a different positive magnitude on the base (e.g. bias 2, or bias only) when an overlay is present | valid | yes by inspection (only `>=`/`<=`)
• the offset applied where the mesh materials are built instead of in `applyMaterialOptions` | valid | yes by inspection (both layers return 0/0, and 0 <= 0)
• keep a smaller pull on the overlay (`cqnZGh3`: slope 0, bias −1) | not valid: the instruction pins "nothing is drawn even slightly nearer than the surface it belongs to" | no (correctly rejected)
• push every base layer back | not valid: the instruction says "blocks without one are fine as they are", and upstream's own comment in the golden says it intrudes on the neighbour's overlay Z space | no (correctly rejected).
Geometry f2p: every with-image run fixed facedir, nodebox dirs, rails and wallmounted its own way and passed those f2p. All trial failures are defects the run never fixed (glass, fence) or the pinned overlay pull. Fix only what the evidence shows: that is all 7 defects (see dimension 6), which equals the oracle.

**What is wrong:** Nothing found. Non-graded note: removing the offset entirely (no Z-fight guard between overlay and base) passes too. Unit tests can't tell it from the golden, and it meets the stated rules, so this is leniency, not overfit.

**Suggested fix:** None.

### 12. Tests – f2p/p2p Identifier Validity: 5 (Pass)

**Evidence:** The `task.toml` and `tests/config.json` f2p/p2p lists are identical (9 + 9, same order; JSON dumps compared equal). Each ID is a Catch2 `TEST_CASE` name in `test.patch`. The JUnit report has 18 testcases with no duplicate names, in both the CB oracle and the local oracle, oracle re-run and nop JUnit reports. `verifier.py`'s exact-key resolution finds each ID once, so `reward_detail.json` has no `missing` or `ambiguous` entry. The multi-line string literals in the two `applyMaterialOptions` TEST_CASE names are joined by the compiler and match the IDs.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 13. Tests – p2p Classification: 5 (Pass)

**Evidence:** All 9 p2p pass on nop and on oracle, in the CB runs (`Nop` reward_detail p2p 9/9, `Oracle` 9/9) and locally (nop 9/9, oracle 9/9 in both oracle runs).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 14. Tests – Discriminating (f2p): 5 (Pass)

**Evidence:** All 9 f2p fail on nop and pass on oracle: CB `Nop` f2p 0/9 and `Oracle` 9/9; locally nop 0/9 and oracle 9/9 in both oracle runs. Each f2p matches one defect, with a paired p2p for the unaffected direction.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 15. Tests – Determinism: 5 (Pass)

**Evidence:** The tests are pure CPU checks on generated meshes, node boxes and `SMaterial` fields. No GPU, timers, animation, randomness, fonts or network. `test.sh` installs nothing: it restores test paths from `harbor_base`, applies `test.patch`, runs an incremental `cmake --build` and runs `luanti --run-unittests` with a JUnit reporter. Since nothing is installed at test time, `[verifier] network_mode = "public"` raises no network-configuration issue. Oracle re-run: two local oracle runs gave identical `reward_detail.json` (18/18 pass), which is also identical to the CB oracle's. The local nop `reward_detail.json` is identical to the CB nop's.

**What is wrong:** Nothing found. Cosmetic note: `test.sh` passes `"${REPORTS[@]}"`, which is never defined. It expands to nothing and is harmless.

**Suggested fix:** None.

### 16. Hardening – Difficulty (Model Trial Fails): 2 (Fail) [Fail - Trial Threshold Not Met]

**Evidence:** From `verifier/reward.txt` (job configs: `task_without_images` with `n_attempts: 3`, `task_with_images` with `n_attempts: 4`, both `anthropic/claude-opus-5-5`):
No-image: `3x5Uv9x` 0.0 (f2p 5/9), `JTnUnsf` 0.0 (5/9), `ZTf6Gye` 0.0 (6/9), so 0/3 pass. Every no-image trajectory shows `/app/.harbor_assets/recording.mp4: No such file or directory`.
With-image: `2nxVxqj` **1.0** (9/9), `79YZ3Xy` **1.0** (9/9), `EuyuJbj` 0.0 (7/9; missed glass X and fence Z), `cqnZGh3` 0.0 (5/9; missed glass X, and kept a small overlay pull on purpose), so **2/4 pass**.
Total 7 trials, which is the Option A layout. Option A needs exactly 1/4 with-image passes, and 2/4 meets neither option. Checksums: with-image trials `17530948…` equal the CB oracle/nop task checksum; no-image `a0e093…` is the asset-stripped variant; all 18 locked files in `task_manifest.json` match the `Tasks/` files on disk (0 mismatches). Run time (informational): with-image 13.2, 18.4, 17.9 and 17.8 min; no-image 18.0, 18.2 and 15.0 min.

**What is wrong:** 2 of 4 with-image trials pass. Option A requires exactly 1/4, so this is `[Fail - Trial Threshold Not Met]`.

**Suggested fix:** Make the task a little harder and re-run all 7 trials, since any edit changes the checksum. Both passing runs found all seven defects. The failing runs missed the framed-glass X row (2/2) and the Z fence (1/2), so those are the hardest defects; the others were found by every with-image run. The text-only runs show that a code audit guided by the Expected bullets finds 5/7, so the levers are the bullets that localize in text: "also for a part fixed to a wall" points straight at the wallmounted selection box, and "links up with its neighbours" points at the connected drawtypes. Trim one of them, keeping the element named and the text truthful (dimension 4). Alternatively, switch to Option B (3 no-image plus 8 with-image, needing 1–2/8). At the observed rate of about 2/4 that is unlikely to land in range without hardening first.

### 17. Hardening – Real & Feasible: 5 (Pass)

**Evidence:** Seven coherent defects: the upstream overlay polygon offset (issue 15821, fixed by PR 15867, whose code makes up the golden's tile/nodedef part) and six injected one-line bugs of a type real code has: a swapped `nb_triplet` row, swapped facedir ±90 rotations, swapped X entries in `nodebox_tile_dirs`, swapped `rail_kinds` angles, a missing `p2 = cur_node.p;` reset, and swapped wallmounted ±Z rotations. Each fix is the minimal revert a real developer would write. All seven are visible in the clip next to correct counterparts, and 2/4 with-image agents solved all seven from symptom plus clip, so the task is feasible.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 18. Gate – Oracle/Nop: 5 (Pass)

**Evidence:** CB: oracle reward 1.0 (f2p 9/9, p2p 9/9) and nop 0.0 (f2p 0/9, p2p 9/9). Both logs have the stage banners `== applying test.patch ==`, `== running f2p + p2p tests ==`, `== computing reward ==` and `reward=`, with no "could not apply test.patch". Local, in the QC-built image: nop 0.0 (f2p 0/9, p2p 9/9); oracle 1.0 (9/9, 9/9); oracle re-run 1.0 and identical to the first run. All three logs have the full banners and `reward=`, with no "could not apply test.patch". The local `reward_detail.json` files equal the CB's for both oracle and nop. (The local nop `submission.patch` lists two deleted `.harbor_assets/*.mp4` files. Those are leftovers in the cached base image used to build the QC image, not part of the task, and they do not affect the tests.)

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 19. Unauditable: 5 (Pass)

**Evidence:** The task is complete and auditable: bundle, 7 trials with trajectories and verifier output, CB oracle/nop/check/analyze, all reproduced locally.

**What is wrong:** Nothing found.

**Suggested fix:** None.
