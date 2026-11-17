# QC Report: ddnet__ddnet_10943_mm

- **Task hash:** `ddnet__ddnet_10943_mm`
- **Title:** A line in the recording does not match what the recording shows (ddnet/ddnet #10943, visual_bug_fix)
- **Rubric:** Official V27 (6a676431c4ebbc30851d6f10-V27_removing_misaligned_task_type_redundancy)
- **Review date:** 2026-11-16
- **Verdict:** **PASS**. No dimension fails. 18 of 19 dimensions score 5. Dimension 4 (Symptom Specificity) scores 3, [Non-Fail - Image-carried Symptom], which is not a fail. The text names the element ('a line drawn from the player character') and points to two references (the opening screen and what the launched item does next), but it never says what kind of mismatch it is (colour, width or missing). Difficulty meets Option A: 0/3 no-image and exactly 1/4 with-image (MPXcWAa = 1.0). All 16 bundle files match the with-image trial manifest sha256. With-image trials, CB Oracle (1.0) and CB Nop (0.0) share lock digest 4e33592e. fix.patch applies cleanly on base_commit plus the 4 injected bug patches (local git apply --check). All five defects are visible in recording.mp4 (contact sheets in evidence/). Every trial f2p failure is the raw bug value of a defect the agent left unfixed. The passing trial used a non-golden fix (old loop kept, float tunings, a !DoBreak guard), which shows the tests check behaviour, not the golden's code. Non-graded notes: switch [verifier] network_mode from 'public' to 'allowlist'; package Tasks/ and Trials/ as separate .tar.gz files. Local oracle/nop/re-run were not run, by the user's standing rule; the CB runs were used instead.

## Scorecard

| # | Dimension | Score | Result | Error category |
|---|---|---|---|---|
| 1 | Structure – Task Bundle Files | 5 | Pass | � |
| 2 | Structure – Deliverables & Packaging | 5 | Pass | � |
| 3 | Instruction – Requires Visual Evidence | 5 | Pass | � |
| 4 | Instruction – Symptom Specificity | 3 | Non-Fail | [Non-Fail - Image-carried Symptom] |
| 5 | Instruction – Task Type | 5 | Pass | � |
| 6 | Image – Evidence Quality | 5 | Pass | � |
| 7 | Metadata – task_type | 5 | Pass | � |
| 8 | Evidence – Chain Consistency | 5 | Pass | � |
| 9 | Golden Fix – Applies Cleanly | 5 | Pass | � |
| 10 | Golden Fix – Source-Only Scope | 5 | Pass | � |
| 11 | Tests – Implementation Overfit | 5 | Pass | � |
| 12 | Tests – f2p/p2p Identifier Validity | 5 | Pass | � |
| 13 | Tests – p2p Classification | 5 | Pass | � |
| 14 | Tests – Discriminating (f2p) | 5 | Pass | � |
| 15 | Tests – Determinism | 5 | Pass | � |
| 16 | Hardening – Difficulty (Model Trial Fails) | 5 | Pass | � |
| 17 | Hardening – Real & Feasible | 5 | Pass | � |
| 18 | Gate – Oracle/Nop | 5 | Pass | � |
| 19 | Unauditable | 5 | Pass | � |

## Delivery gate

| # | Check | Result | Detail |
|---|---|---|---|
| 1 | Oracle (CB, lock 4e33592e) | PASS | reward 1.0, f2p 5/5, p2p 7/7, 4.9 min |
| 2 | Nop (CB, lock 4e33592e) | PASS | reward 0.0, f2p 0/5, p2p 7/7, 5.5 min |
| 3 | Local oracle / nop / re-run | WARN | Not run, by the user's standing rule (no oracle/nop/harbor). Graded from the CB runs; the bundle is byte-identical to what they used |
| 4 | fix.patch applies | PASS | git apply --check on base_commit + bug_01..04 (local scratch repo): exit 0, 4 files |
| 5 | Verifier completion | PASS | All 9 runs wrote junit.xml + reward.txt; stage banners and reward= present; no 'could not apply test.patch' |
| 6 | pass@3 (no-image) | PASS | 0/3 (Tp2m5X4, VhNR6ZG, eHoqkRt all 0.0); assets dir confirmed empty in all three |
| 7 | pass@4 (with-image, Option A) | PASS | exactly 1/4: MPXcWAa 1.0; 6RqbDM9, St4Uzx3, xMubF2B 0.0 |
| 8 | Trial run time (informational) | PASS | 6.8-9.2 min per trial |
| 9 | Trial/task checksum | PASS | 16/16 bundle files match task_manifest sha256; with-image trials, Oracle and Nop share lock digest 4e33592e (no-image variant 7dda3862, expected) |
| 10 | Packaging | WARN | Tasks/ and Trials/ are correct sibling folders with 3 + 4 trials; still to be archived as separate .tar.gz files at submission |
| 11 | Leaks | PASS | No repo, URL, file, function, setting, colour or mechanism in instruction.md; history flattened; bug patches deleted; timestamps normalised |
| 12 | Evidence-chain integrity | PASS | recording.mp4 sha256 c724ffd8… agrees across file, ASSET_MANIFEST, evidence_bundle, instruction and Dockerfile COPY |
| 13 | Verifier network | WARN | test.sh apt-installs pytest/PIL with [verifier] network_mode = public. Not a V27 fail (only no-network or an incomplete allowlist fails); allowlist is cleaner |

## Trials

| Trial | Mode | Reward | f2p | p2p | Minutes | Failed tests |
|---|---|---|---|---|---|---|
| task_without_images__Tp2m5X4 | no-image | 0.0 | 2/5 | 7/7 | 6.8 | drawn_with_subunit_fire_speed; wall_past_hook_reach_is_not_hookable; width_setting_diagonal_aim |
| task_without_images__VhNR6ZG | no-image | 0.0 | 3/5 | 7/7 | 7.2 | drawn_with_subunit_fire_speed; wall_past_hook_reach_is_not_hookable |
| task_without_images__eHoqkRt | no-image | 0.0 | 4/5 | 7/7 | 6.8 | width_setting_diagonal_aim |
| task_with_images__6RqbDM9 | with-image | 0.0 | 4/5 | 7/7 | 7.5 | wall_past_hook_reach_is_not_hookable |
| task_with_images__MPXcWAa | with-image | 1.0 | 5/5 | 7/7 | 9.2 | � |
| task_with_images__St4Uzx3 | with-image | 0.0 | 4/5 | 7/7 | 7.3 | wall_past_hook_reach_is_not_hookable |
| task_with_images__xMubF2B | with-image | 0.0 | 3/5 | 7/7 | 7.5 | wall_past_hook_reach_is_not_hookable; width_setting_diagonal_aim |

## Issues & suggested fixes

### Instruction – Symptom Specificity: 3 [Non-Fail - Image-carried Symptom]

**What is wrong:** Non-fail flag: the exact defect is carried by the video. The text says only that the line 'does not match' the references.

**Suggested fix:** Optional, not required (3 is a Non-Fail). A line that would score 5, e.g. 'its colour, width or length sometimes disagrees with the legend on the opening screen or with where the launched item actually ends up', also changes instruction.md and so the task checksum. All 7 trials would have to be re-run, and naming the classes risks no-image passes (see task106). Recommendation: leave it as is.

## Dimension details

### 1. Structure – Task Bundle Files: 5 (Pass)

**Evidence:** All 11 fixed files are present and non-empty: task.toml 9118 B, instruction.md 933, evidence_bundle.json 1988, environment/Dockerfile 3657, environment/assets/ASSET_MANIFEST.json 682, solution/fix.patch 10919, solution/solve.sh 349, tests/config.json 1290, tests/test.patch 27360, tests/test.sh 10397, tests/verifier.py 6561. The 3 JSON files parse, task.toml parses with tomllib, and `python -I` py_compile of verifier.py passes. recording.mp4 (777506 B) decodes with OpenCV as h264, 1280x800, 30 fps, 1852 frames (61.7 s). The extra files are allowed: README.md and environment/bugs/bug_01..04.patch (injected bugs).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 2. Structure – Deliverables & Packaging: 5 (Pass)

**Evidence:** task107/Attempt2 has Tasks/ (capital T) and Trials/ as sibling root folders, plus Oracle/, Nop/, Check/ and Analyze/. Trials/without_images holds 3 runs (Tp2m5X4, VhNR6ZG, eHoqkRt) and Trials/with_images holds 4 runs (6RqbDM9, MPXcWAa, St4Uzx3, xMubF2B), so 7 trials in total, which is Option A.

**What is wrong:** Nothing found. Non-graded: the folders are not archived yet.

**Suggested fix:** At submission, archive Tasks/ and Trials/ as separate Tasks.tar.gz and Trials.tar.gz files (and Oracle.tar.gz / Nop.tar.gz), each unpacking to its own top-level folder.

### 3. Instruction – Requires Visual Evidence: 5 (Pass)

**Evidence:** Without the video the text names no repo, file, function, setting, colour, width, tuning or command. It never says 'hook'; the launched item is only 'the item the player launches'. A developer could not tell which line is meant, which of its properties are wrong, or in which situations. The only asset ref is `/app/.harbor_assets/recording.mp4`, which the Dockerfile copies to /app/.harbor_assets/. Leak scan: no repo name, URL, file list or mechanism in instruction.md. The Dockerfile drops upstream history (single base commit, harbor_base tag), normalises timestamps and deletes the bug patches in the same RUN. The trajectories confirm the video is needed: the 3 no-image runs found /app/.harbor_assets empty and fixed between 2 and 4 of the 5 defects by code audit, and all three failed (0.0).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 4. Instruction – Symptom Specificity: 3 (Non-Fail) [Non-Fail - Image-carried Symptom]

**Evidence:** Table: element = 'a line drawn from the player character' (named by type) | defect = 'does not match what the clip itself shows' (text gives only the class 'mismatch'; the exact defects are in the video: hairline on diagonals, green on an unreachable pillar, yellow through a block, red past a grabbed tee, missing after a tuning change) | expected = 'always matches the opening screen of the clip, which shows how it should look and what each of its colours means, and what the item the player launches does right after' (text, by pointing to references) | comparison pointed to = the settings screen at 0:00-0:04 (legend + preview) and the hook's own outcome right after each beat | clue left to the video = which situations, which colour, the width collapse, the console command | described correctly? = yes. Every claim checks out against the frames: the line does mismatch the opening screen (07 s and 13 s are thin vs the wide preview at 01-03 s) and what the hook does next (18-23 s green on the pillar but the player is not pulled; 40-42 s red past buddy while the chain grabs him). 'Separate, independent defects ... fixing one does not fix the others' matches the trials: each run's f2p misses map one-to-one to the defects it left. Trajectory check: all 4 with-image runs read the opening screen as the legend and width reference (St4Uzx3: 'settings screen: red = nothing hookable, green = hookable, yellow = tee, own width 20'). All 4 read the diagonal, tee and fire-speed beats the same way. No run called a pictured defect intended behaviour. The 3 failing runs simply never mention the pillar beat (no 'pillar'/'green line' observation in 6RqbDM9, St4Uzx3 or xMubF2B). That is a missed defect, not confusion with intended behaviour. Why 3, not 5: the text points to the references but never states the defect class ('wrong colour', 'too thin', 'missing'). That matches the rubric's 3 pattern ('the converted chart doesn't match original.png'). One could argue 5 under 'points to a reference only where stating it would give the clue away', because naming the classes would let no-image agents audit those exact code paths.

**What is wrong:** Non-fail flag: the exact defect is carried by the video. The text says only that the line 'does not match' the references.

**Suggested fix:** Optional, not required (3 is a Non-Fail). A line that would score 5, e.g. 'its colour, width or length sometimes disagrees with the legend on the opening screen or with where the launched item actually ends up', also changes instruction.md and so the task checksum. All 7 trials would have to be re-run, and naming the classes risks no-image passes (see task106). Recommendation: leave it as is.

### 5. Instruction – Task Type: 5 (Pass)

**Evidence:** The text describes a rendered on-screen line that looks wrong compared with a reference screen and with the game's behaviour. That is a visual defect in the client's rendering, which fits visual_bug_fix (a visible rendering bug in a still/recorded scene). It is not a regression reading, and nothing time-based or interactive is being graded.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 6. Image – Evidence Quality: 5 (Pass)

**Evidence:** Naming table: file = recording.mp4 | role = bug_video | frames show = the bug state of base+injections (verified with contact_00-22s, contact_24-44s, contact_45-62s, detail_17-26s_pillar, detail_29-44s_tee in evidence/) | claims (role, description, instruction) = a bug recording, settings page, flat grass level, pillar, block with a second player, remote-console command | true? = yes, every beat in the description is visible | agents confused? = no, all 4 with-image runs treated it as the bug recording. The name is neutral. f2p ↔ asset (steps 1-4): (1) drawn_with_subunit_fire_speed, tune 0.9: 45-48 s console shows `tune hook_fire_speed 0.9`, and 51-61 s show no line while the hook chain creeps out (59-60 s). (2) tee_grazed_by_hook_path, 24 units off a tee: 40-41.5 s red line runs past buddy, and 42.0 s the hook chain grabs buddy. (3) width_setting_diagonal_aim, width 20 at 45°: 05 s and 15 s are wide on horizontal aims, 07/09/11/13 s go thin on diagonals, and the preview at 01-03 s is uniformly wide. (4) wall_past_hook_reach_is_not_hookable: 18-23 s green line to the pillar while the player stays put, and 24-26 s one tile closer the player is pulled to the pillar. (5) stops_at_wall_in_front_of_tee: 29.5-33.5 s yellow line runs through the one-tile block to buddy. Cross-checks: MPXcWAa fixed exactly what the video shows, with a non-golden patch, and passed 5/5 f2p. The f2p failure values are the pictured symptoms ('hookable': 1.0 on the unreachable wall = green on the pillar; '0.0 px wide when aiming diagonally' = the hairline; '0 units' at 0.9 = the missing line). 6RqbDM9 and St4Uzx3 fixed four defects but not the !DoBreak one, and only wall_past failed for them. Step 7 (injected bugs_01-04): all four are pictured. A fix that skips any of them leaves a visible defect on the default client path, so it is incomplete, not an alternative.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 7. Metadata – task_type: 5 (Pass)

**Evidence:** task_type = "visual_bug_fix" is one of the seven values and fits a single bug recording of a rendering defect (wrong line colour, width or presence). The tags (multimodal, 2d_video, visual_bug_fix, rendering, hud) agree.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 8. Evidence – Chain Consistency: 5 (Pass)

**Evidence:** File on disk: environment/assets/recording.mp4, 777506 B, sha256 c724ffd8411cbac4…, which equals the trial task_manifest entry. ASSET_MANIFEST.json: same file, bytes and sha256, container_path /app/.harbor_assets/recording.mp4. evidence_bundle.json: same file, bytes and sha256, local_path /app/.harbor_assets/recording.mp4. instruction.md references `/app/.harbor_assets/recording.mp4`. Dockerfile: `COPY assets/recording.mp4 /app/.harbor_assets/`. All four references agree.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 9. Golden Fix – Applies Cleanly: 5 (Pass)

**Evidence:** Local check (scratch git repo built from the 4 touched files at base_commit 174340a8 from raw.githubusercontent): bug_01..04.patch apply in order, then `git apply --check -v solution/fix.patch` passes for ghost.cpp, players.cpp, players.h and gameclient.cpp (exit 0). Applying it gives 4 files, +85/-56, and restores `PhysicalSize() + 2.0f` and `normalize(vec2(Direction.y, -Direction.x))`. CB Oracle trial log: 'Applied fix.patch.' with no patch(1) fallback output, reward 1.0.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 10. Golden Fix – Source-Only Scope: 5 (Pass)

**Evidence:** The diff --git paths in fix.patch are {src/game/client/components/ghost.cpp, players.cpp, players.h, src/game/client/gameclient.cpp}. They match files_edited exactly. There are no test, doc, lockfile or changeset paths. The ghost.cpp one-line removal and the dropped Intra parameter come from upstream PR #10951. No test checks them and task.toml discloses them.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 11. Tests – Implementation Overfit: 5 (Pass)

**Evidence:** The tests are behavioural: they run the real client and server headless, compare a screenshot with the line off against one with it on, classify pixels by nearest legend colour (L1 ≤ 70), and measure reach and width along the aim ray. They never read source. Value-level table (assertion | alternatives | accepted?): subunit speed `reach >= 150` | float tunings in the old loop (MPXcWAa), the upstream rewrite (golden), clamping the step to ≥1 | all pass, because any drawn line along the aim reaches ~362-380 | grazed tee `tee share ≥ 0.8, reach ≤ 230` | radius PhysicalSize()+2 (golden, MPXcWAa), PhysicalSizeVec2().x+2 (CB matrix), PhysicalSize() = 28 also > 24 | all pass; half-size 16 is rejected, which is the bug | diagonal width `7 ≤ px ≤ 14` | normalize(vec2(y,-x)) (golden, MPXcWAa), vec2(-y,x) (other-handed, CB matrix), direction(angle(D) - pi/2) | all give the same perpendicular thickness; the width is measured as pixel count per unit length along the ray, so it does not depend on orientation | wall past reach `best == nothing, hookable < 0.2` | !DoBreak guard (MPXcWAa), the upstream loop (golden), a 'still flying' flag | all pass; this matches CCharacterCore::Tick, where the over-length step sets HOOK_RETRACT_START before the HOOK_FLYING ground check | tee behind wall `best == hookable, reach ≤ 222` | IntersectCharacter(OldPos, FinishPos) (MPXcWAa, CB), a clipped step end | pass. Structure: colour shares are thresholds, not exact counts; reach and width have tolerance bands. The p2p tee_in_front_of_wall rejects the over-correction 'skip the tee test whenever a wall is hit'. Trial cross-check: every failing f2p message is a raw bug value (hookable 1.0, 0.0 px, 0 units), never a valid alternative form. MPXcWAa's structurally different fix passed 12/12.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 12. Tests – f2p/p2p Identifier Validity: 5 (Pass)

**Evidence:** The task.toml f2p (5) and p2p (7) lists equal tests/config.json exactly (python compare: True/True). Each ID `scripts/test_harvest_c01_hookline.py::test_…` resolves through verifier.junit_key to classname `scripts.test_harvest_c01_hookline` plus the test name. Each matches exactly one JUnit testcase in the Oracle report (12 testcases, no duplicates), and reward_detail.json lists all 12 as resolved.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 13. Tests – p2p Classification: 5 (Pass)

**Evidence:** The 7 p2p pass on CB Nop (base + injections: '5 failed, 7 passed') and on CB Oracle ('12 passed'). They also passed 7/7 in all 7 trials.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 14. Tests – Discriminating (f2p): 5 (Pass)

**Evidence:** CB Nop: f2p 0/5, each failing on both attempts with the bug value (e.g. tee_grazed 'tee' == 'hookable' mismatch; diagonal '0.0 px wide'). CB Oracle: f2p 5/5. task.toml's leave-one-out matrix (each injected defect alone fails only its own f2p) agrees with the trials: the runs that left only the !DoBreak defect failed only wall_past_hook_reach_is_not_hookable.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 15. Tests – Determinism: 5 (Pass)

**Evidence:** Headless and pinned: Xvfb with Mesa llvmpipe (LIBGL_ALWAYS_SOFTWARE=1), SDL dummy audio, maps generated from fixed ASCII layouts, aim set with xdotool to fixed offsets, fixed sleeps, and in-engine screenshots with the HUD and tee masked. Fonts come from apt in the image. The @_twice wrapper re-runs a scenario only after a failure; a wrong line fails both attempts, as every trial f2p failure shows ('failed on both attempts'). Consistency: the 7 p2p passed in 9/9 runs (7 trials, Oracle, Nop), and every f2p outcome follows the code change. Network: test.sh apt-installs python3-pytest and python3-pil at test time, and [verifier] network_mode = "public". The V27 [Fail - Network Configuration] text fails only 'no-network' or an allowlist missing domains, so 'public' is not a fail. The installs worked in all 9 runs. Local oracle re-run: not run (user's standing rule: no oracle/nop/harbor runs). Graded from the 9 CB runs.

**What is wrong:** Nothing found. Non-graded: 'public' is wider than needed for test-time apt installs.

**Suggested fix:** Optional: set `[verifier] network_mode = "allowlist"` with `allowed_hosts = ["archive.ubuntu.com", "security.ubuntu.com"]` (the Dockerfile switches the sources to https on those hosts). Note that this changes task.toml and so the task checksum, so all trials would have to be re-run. Only do it if a reviewer asks.

### 16. Hardening – Difficulty (Model Trial Fails): 5 (Pass)

**Evidence:** Option A (7 trials). No-image 0/3: Tp2m5X4 0.0 (f2p 2/5), VhNR6ZG 0.0 (3/5), eHoqkRt 0.0 (4/5). All three found /app/.harbor_assets empty ('No such file or directory', 'the folder is empty'). With-image 1/4: MPXcWAa 1.0 (5/5, 7/7); 6RqbDM9 0.0, St4Uzx3 0.0 (4/5, wall_past only); xMubF2B 0.0 (3/5, wall_past + diagonal width). The runs are told apart by job config path (trial_tasks/…/task_without_images vs task_with_images). Run times (informational): 6.8-9.2 min per trial.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 17. Hardening – Real & Feasible: 5 (Pass)

**Evidence:** The original issue #10943 (hook line missing at hook_fire_speed < 1) plus four injected bugs, each a coherent, realistic slip: a radius halved, a reflection used instead of a rotation, a guard dropped while merging two if-blocks, and a tee test run over the unclipped step. Each one contradicts the game's own physics in CCharacterCore::Tick (30-unit grab radius, retract on the over-length step, tee test only in front of the wall), so a developer comparing the line with the physics would write exactly these fixes. The golden is upstream PR #10951 plus the reversal of the four patches, a fix real developers wrote. All five defects are pictured, and one agent solved all five from the symptom and the video alone (MPXcWAa).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 18. Gate – Oracle/Nop: 5 (Pass)

**Evidence:** CB Oracle (lock 4e33592e, the same as the with-image trials): stage banners '== applying test.patch ==', '== running f2p + p2p tests ==', '== computing reward ==', '12 passed', reward=1.0, and no 'could not apply test.patch' in stdout or stderr. CB Nop (same lock): '5 failed, 7 passed', reward=0.0. A local oracle/nop/re-run was not performed, by the user's standing rule (they run oracle/nop themselves). The bundle is byte-identical to what the CB runs used (16/16 sha256 against task_manifest), and fix.patch applies locally.

**What is wrong:** Nothing found. Local re-run not performed (see evidence).

**Suggested fix:** None.

### 19. Unauditable: 5 (Pass)

**Evidence:** The submission is complete and auditable: bundle, 7 trials with trajectories and JUnit, Oracle, Nop, Check and Analyze.

**What is wrong:** Nothing found.

**Suggested fix:** None.
