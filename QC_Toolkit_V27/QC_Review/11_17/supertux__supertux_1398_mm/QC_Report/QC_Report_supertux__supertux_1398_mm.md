# QC Report: supertux__supertux_1398_mm

- **Task hash:** `supertux__supertux_1398_mm`
- **Title:** Some objects misbehave in the forest (SuperTux/supertux #1398, temporal_interaction)
- **Rubric:** Official V27 (6a676431c4ebbc30851d6f10-V27_removing_misaligned_task_type_redundancy)
- **Review date:** 2026-11-17
- **Verdict:** **PASS**. No dimension fails. 18 of 19 dimensions score 5. Dimension 4 (Symptom Specificity) scores 3, [Non-Fail - Image-carried Symptom], which is not a fail: the text names the element ('the objects Tux grabs') and the four situations (carried, let go, falling, lying on the ground), but every concrete defect is left to recording.mp4. Difficulty meets Option A: 0/3 no-image and exactly 1/4 with-image (gCxmGFG = 1.0). All 17 hashed bundle files match the with-image trial manifest sha256, and the with-image trials, CB Oracle (1.0) and CB Nop (0.0) share lock digest 3e06674b. The 5 bug patches and then fix.patch apply cleanly on base_commit (local git apply --check, exit 0); the net base-to-fixed diff is exactly upstream PR #1449's one-line Rock::collision change. All six defects are visible in recording.mp4 (contact sheets in evidence/). Every trial f2p failure is a defect the agent missed, not a correct alternative fix rejected. Non-graded notes: the task.toml difficulty_explanation is stale against the current instruction; no-image runs reach 5/7 f2p, so the visual margin rests on the coin and leaf defects. Local oracle/nop/re-run were not run, by the user's standing rule; the CB runs were used instead.

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
| 16 | Hardening – Difficulty (Model Trial Fails) | 5 | Pass | — |
| 17 | Hardening – Real & Feasible | 5 | Pass | — |
| 18 | Gate – Oracle/Nop | 5 | Pass | — |
| 19 | Unauditable | 5 | Pass | — |

## Delivery gate

| # | Check | Result | Detail |
|---|---|---|---|
| 1 | Oracle (CB, lock 3e06674b) | PASS | reward 1.0, f2p 7/7, p2p 3/3, 6.5 min |
| 2 | Nop (CB, lock 3e06674b) | PASS | reward 0.0, f2p 0/7, p2p 3/3, 1.4 min |
| 3 | Local oracle / nop / re-run | WARN | Not run, by the user's standing rule (no oracle/nop/harbor). Graded from the CB runs; the bundle is byte-identical to what they used |
| 4 | fix.patch applies | PASS | git apply --check on base_commit + bug_01..05 (local scratch repo): exit 0, 4 files |
| 5 | Verifier completion | PASS | All 9 runs wrote reward.txt and junit.xml with 10 testcases |
| 6 | pass@3 no-image | PASS | 0/3 (J278gLi, qeJn4aJ, ryN2gr3 all 0.0); assets dir confirmed empty |
| 7 | pass@4 with-image (Option A) | PASS | Exactly 1/4 (gCxmGFG = 1.0) |
| 8 | Trial run time | PASS | 4.2–14.5 min (informational) |
| 9 | Trial / task checksum | PASS | 17/17 hashed bundle files match with_images task_manifest.json sha256; lock digest 3e06674b = Oracle = Nop = with-image trials |
| 10 | Packaging | WARN | Tasks/ and Trials/ are sibling folders with 3+4 trials; still to be tarred separately for submission |
| 11 | Leaks | PASS | instruction.md names no repo, URL, file, class, mechanism or number |
| 12 | Evidence-chain integrity | PASS | disk = ASSET_MANIFEST = evidence_bundle = instruction ref (/app/.harbor_assets/recording.mp4, 2571782 B, f7f5bbcf…) |
| 13 | difficulty_explanation in sync | WARN | Non-graded: task.toml still describes an older instruction ('everything else in the level react to them normally', one expected line per behaviour) and says 'harbor not run' |

## Trials

| Trial | Mode | Reward | f2p | p2p | Minutes | Failed tests |
|---|---|---|---|---|---|---|
| task_without_images__J278gLi | no-image | 0.0 | 5/7 | 3/3 | 4.4 | DroppedRockFallsPastCoinsLikeThroughOpenAir; RockDroppedOnAWalkingLeafKnocksItOut |
| task_without_images__qeJn4aJ | no-image | 0.0 | 3/7 | 3/3 | 6.4 | DroppedRockFallsPastCoinsLikeThroughOpenAir; TuxCanStandOnARestingRock; TuxWalkingIntoARestingRockIsStoppedByIt; RockDroppedOnAWalkingLeafKnocksItOut |
| task_without_images__ryN2gr3 | no-image | 0.0 | 5/7 | 3/3 | 4.2 | DroppedRockFallsPastCoinsLikeThroughOpenAir; RockDroppedOnAWalkingLeafKnocksItOut |
| task_with_images__96kcbNY | with-image | 0.0 | 3/7 | 3/3 | 12.4 | DroppedRockFallsPastCoinsLikeThroughOpenAir; RockThrownWhileWalkingFliesForward; TuxCanStandOnARestingRock; TuxWalkingIntoARestingRockIsStoppedByIt |
| task_with_images__JxFcKRP | with-image | 0.0 | 6/7 | 3/3 | 14.5 | DroppedRockFallsPastCoinsLikeThroughOpenAir |
| task_with_images__WWyLFjR | with-image | 0.0 | 4/7 | 3/3 | 5.4 | DroppedRockFallsPastCoinsLikeThroughOpenAir; TuxCanStandOnARestingRock; TuxWalkingIntoARestingRockIsStoppedByIt |
| task_with_images__gCxmGFG | with-image | 1.0 | 7/7 | 3/3 | 13.5 | — |

## Issues & suggested fixes

### Instruction – Symptom Specificity: 3 [Non-Fail - Image-carried Symptom]

**What is wrong:** The text names the element and gives context, but never says what kind of defect it is (position, direction, collision). Every concrete defect is carried only by the video. Under V27 this is [Non-Fail - Image-carried Symptom] = 3, not a fail.

**Suggested fix:** No change required, since it isn't a fail. Do not add defect classes to the text: no-image runs already reach 5/7 f2p by code audit, and only the coin-column and walking-leaf defects keep them at 0/3. Any hint at coins, falling past things, or what happens to an enemy would likely let no-image runs pass. If you ever want a 5, state only classes the no-image runs already find (for example 'held on the wrong side, thrown the wrong way, sinks into the ground or lets Tux pass through it'), and note that editing instruction.md changes the task checksum, so all 7 trials must be re-run.

## Dimension details

### 1. Structure – Task Bundle Files: 5 (Pass)

**Evidence:** All 11 fixed files are present and non-empty: task.toml 6386 B, instruction.md 727, evidence_bundle.json 1104, environment/Dockerfile 4307, environment/assets/ASSET_MANIFEST.json 541, solution/fix.patch 4023, solution/solve.sh 349, tests/config.json 751, tests/test.patch 18211, tests/test.sh 10145, tests/verifier.py 8158. The 3 JSON files parse, task.toml parses with tomllib, and `python -I` py_compile of verifier.py passes. recording.mp4 (2571782 B) decodes with OpenCV as h264, 1280x720, 30 fps, 780 frames (26.0 s). The extra files are allowed: README.md and environment/bugs/bug_01..05.patch (injected bugs).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 2. Structure – Deliverables & Packaging: 5 (Pass)

**Evidence:** task108/Attempt2 has `Tasks/` (capital T) and `Trials/` as sibling root folders, plus Oracle/, Nop/, Check/ and Analyze/. Trials/ holds 7 trials, Option A: without_images/ has 3 (J278gLi, qeJn4aJ, ryN2gr3) and with_images/ has 4 (96kcbNY, JxFcKRP, WWyLFjR, gCxmGFG).

**What is wrong:** Nothing found. The folders are not yet archived; package `Tasks/` and `Trials/` as separate .tar.gz files when you submit.

**Suggested fix:** On submission: `tar czf Tasks.tar.gz Tasks` and `tar czf Trials.tar.gz Trials` (same for Oracle/Nop).

### 3. Instruction – Requires Visual Evidence: 5 (Pass)

**Evidence:** Text alone: 'Several things that happen with the objects Tux grabs in the video are not how those objects work in this game' and 'behave like they normally do ... while Tux carries them, when he lets go of them, while they fall, and once they are lying on the ground'. It never says which object, which behaviours are broken or how, so a developer can't fix it correctly, confidently and completely from the text. The trials confirm this: all 3 no-image runs failed (each missed the coin-column defect, and every one also missed the walking-leaf defect). The image path resolves to `/app/.harbor_assets/recording.mp4` (Dockerfile `COPY assets/recording.mp4 /app/.harbor_assets/`). No leak: no repo name, URL, file, class, function, mechanism or number in instruction.md. 'Tux' and 'forest level' only name the game context the agent is already in.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 4. Instruction – Symptom Specificity: 3 (Non-Fail) [Non-Fail - Image-carried Symptom]

**Evidence:** Table: element = 'the objects Tux grabs' (named by type: grabbable objects) | defect = image only ('not how those objects work in this game'; the kind of defect is never stated in text) | expected = text, generic: 'behave like they normally do in this game' in four named situations (carried, let go, falling, lying on the ground) | comparison image = none (recording.mp4 is the bug video) | clue left to image = yes: which object, held on the wrong side, thrown backwards, falls into the ground, Tux passes through it, crawls down the coin column, freezes the leaf | described correctly = yes (all six defects are about the grabbed rock in those four situations). The general phrase is not standing alone: the element and the four situations follow right away, so check 2 passes. Trajectories (all 4 with-image runs read): gCxmGFG found all six defects. JxFcKRP found 5/6 and never noticed the coin column. WWyLFjR found 4/6 and never opened player.hpp. 96kcbNY found 3 defects and took one frame of Tux overlapping a resting rock for a pick-up. None of them treated an observed defect as intended behaviour; the 3 misses on the coin column are detection misses (the failing runs never mention coins outside source code), so the 'agents couldn't tell' fail does not apply.

**What is wrong:** The text names the element and gives context, but never says what kind of defect it is (position, direction, collision). Every concrete defect is carried only by the video. Under V27 this is [Non-Fail - Image-carried Symptom] = 3, not a fail.

**Suggested fix:** No change required, since it isn't a fail. Do not add defect classes to the text: no-image runs already reach 5/7 f2p by code audit, and only the coin-column and walking-leaf defects keep them at 0/3. Any hint at coins, falling past things, or what happens to an enemy would likely let no-image runs pass. If you ever want a 5, state only classes the no-image runs already find (for example 'held on the wrong side, thrown the wrong way, sinks into the ground or lets Tux pass through it'), and note that editing instruction.md changes the task checksum, so all 7 trials must be re-run.

### 5. Instruction – Task Type: 5 (Pass)

**Evidence:** task_type = temporal_interaction: 'Fix a defect that only appears across a sequence of interactions / state transitions' (Guidelines Step IV). The instruction describes behaviour across the grab → carry → release → fall → rest sequence, and each defect shows up only at one of those transitions. That fits the slug.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 6. Image – Evidence Quality: 5 (Pass)

**Evidence:** Naming table: recording.mp4 | role bug_video | frames show the buggy build (verified frame by frame, see evidence/ contact sheets): 1.0–2.0 s Tux walks right with the rock behind him; 2.5–4.0 s the dropped rock stops on the coin column and crawls down it; 6.5–7.5 s Tux faces left, rock again behind; 9.5–10 s a rock dropped on the walking leaf turns it into an ice block; 18.5 s Tux overlaps a resting rock; 20.5–21 s Tux stands inside a rock after jumping on it; 23.5–24.5 s a rock thrown while walking right flies left and ends up embedded in the dirt | name is neutral, role/description/instruction claim a buggy gameplay clip | true | agents confused: no (no run treated the video as a target or reference). f2p ↔ asset: (0) coin test drops a rock through a coin column = 2.5–4.0 s; (1) held-in-front, both directions = 1–2 s and 6.5–7.5 s; (2) thrown while walking flies forward = 23.5–24 s; (3) thrown rock stays on the floor = 24–24.5 s; (4) Tux stands on and is stopped by a resting rock = 18.5 s and 20.5–21 s; (5) rock dropped on a walking leaf knocks it out = 9.5–10 s. Fixing exactly what the video shows is the full golden (all 6 defects are pictured), which passes 10/10 (CB Oracle and gCxmGFG). Step 7, injected bugs 01–05: a fix that skips any of them leaves a defect that is visible in the clip, so it is an incomplete fix, not a valid alternative. Clip recorded from this task's post-injection build (source_kind captured_from_repo), consistent with the 5 bug patches.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 7. Metadata – task_type: 5 (Pass)

**Evidence:** `temporal_interaction` is one of the seven values. The evidence is a 26 s uncut clip whose defects only appear across state transitions (carry, release, flight, landing, rest). The guideline lists a '3–8 frame sequence / GIF' as the typical asset; an uncut video is a frame sequence and fits.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 8. Evidence – Chain Consistency: 5 (Pass)

**Evidence:** File on disk environment/assets/recording.mp4: 2571782 B, sha256 f7f5bbcf…9d6859. ASSET_MANIFEST.json: file recording.mp4, container_path /app/.harbor_assets/recording.mp4, same bytes and sha256. evidence_bundle.json: same file, bytes and sha256, local_path /app/.harbor_assets/recording.mp4. instruction.md references `/app/.harbor_assets/recording.mp4`. Dockerfile copies it to /app/.harbor_assets/. All four references agree.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 9. Golden Fix – Applies Cleanly: 5 (Pass)

**Evidence:** Local scratch repo with src/badguy/badguy.cpp, src/object/player.cpp, src/object/player.hpp and src/object/rock.cpp at base_commit d2c892e2: bug_01..05 apply in order (`git apply`, all ok), then `git apply --check -v solution/fix.patch` checks all 4 files, exit 0. After applying, the net diff vs base_commit is the single Rock::collision line `moving_object && moving_object->get_group() != COLGROUP_TOUCHABLE` (upstream PR #1449). CB Oracle stdout shows 'captured submission.patch (4023 bytes, 4 files)' and reward 1.0.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 10. Golden Fix – Source-Only Scope: 5 (Pass)

**Evidence:** fix.patch `diff --git` paths = {src/badguy/badguy.cpp, src/object/player.cpp, src/object/player.hpp, src/object/rock.cpp}, which equals task.toml files_edited (same 4). No test, doc, lockfile or changeset path.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 11. Tests – Implementation Overfit: 5 (Pass)

**Evidence:** The assertions only read positions, coin count and badguy presence, with tolerances, so there are no string, enum or format assertions to enumerate. Alternatives (value | correct in repo? | test accepts): (0) coins: ignore touchables in Rock::collision (golden) yes/yes; coin-only dynamic_cast check yes (narrower)/yes; skip only the velocity reset for touchables yes/yes; a rock that collects coins as it falls = invented behaviour (coins are only collected by Tux; the video shows the coins untouched)/no, correctly rejected. Tolerance: within 2 frames of an open-air drop. (1) hold offset: if-branch (golden), or any mirrored offset yes/yes (only 'centre on the facing side'). (2) throw: `m_dir` (golden), or un-inverted side comparison once the hold is fixed yes/yes; any speed ≥ ~64 px/s accepted (16 px in 0.25 s). (3) group restore: in ungrab (golden), or unconditionally after any release yes/yes; 'lies on the floor ±2 px and still ±1 px after 2 s' matches the base rock, which zeroes x velocity on landing. (4) delete the Player::collides override (golden), or keep it but limit it to the carried object (CB-validated) yes/yes; the tests check stand-on ±2 px and stop-at-left-edge +2 px. (5) restore the ICE-only freeze (golden), or have the rock kill_fall badguys directly yes/yes: the test accepts any outcome that removes the leaf (fall or squish). Structure-level: no exact counts, ordering or error text, and float checks use tolerances. Trial cross-check: every failed f2p in the 6 failing trials is a defect the agent left unfixed (base value), never a valid alternative. The passing run gCxmGFG used its own patches across all four files.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 12. Tests – f2p/p2p Identifier Validity: 5 (Pass)

**Evidence:** task.toml f2p (7) and p2p (3) are identical to tests/config.json (checked in Python: equal = True for both lists). Each ID 'RockBehaviour <Name>' matches exactly one JUnit testcase (classname=RockBehaviour, name=<Name>) in the CB Oracle junit.xml: 10 testcases, all status=run.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 13. Tests – p2p Classification: 5 (Pass)

**Evidence:** CarriedRockMovesAlongWithTux, PutDownRockLandsOnTheGround and RockDroppedOnARestingRockStaysOnTop pass on CB Nop (base) and CB Oracle (reward_detail.json), and in all 7 trials.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 14. Tests – Discriminating (f2p): 5 (Pass)

**Evidence:** All 7 f2p fail on CB Nop (reward_detail: 7 × fail) and pass on CB Oracle (7 × pass).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 15. Tests – Determinism: 5 (Pass)

**Evidence:** Tests step the game's own update loop at a fixed FRAME = 1/64 s and drive Tux through the scripting controller, with no wall-clock time, sleep, network or rand in test.patch. SDL_VIDEODRIVER/AUDIODRIVER=dummy, so there is no rendering and no fonts. test.sh installs nothing (an offline cmake rebuild only). Consistency: the 3 p2p pass in all 9 runs (7 trials + oracle + nop), and each f2p outcome lines up with what that agent fixed. Gtest run time is 333 ms. The local oracle re-run was not done, by the user's standing rule.

**What is wrong:** Nothing found.

**Suggested fix:** None. Optional: [verifier] network_mode is 'public' although test.sh needs no network. 'no-network' would be tighter, but it changes the checksum, so only do it if you re-run trials anyway.

### 16. Hardening – Difficulty (Model Trial Fails): 5 (Pass)

**Evidence:** Option A, 7 trials. No-image (task digest d1f29904, path …/task_without_images): J278gLi 0.0, qeJn4aJ 0.0, ryN2gr3 0.0 = 0/3. All 3 trajectories confirm /app/.harbor_assets was empty ('harbor_assets/ is empty and there's no recording.mp4 anywhere'). With-image (digest 3e06674b, path …/task_with_images): 96kcbNY 0.0, JxFcKRP 0.0, WWyLFjR 0.0, gCxmGFG 1.0 = exactly 1/4. Run times 4.2–14.5 min (informational).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 17. Hardening – Real & Feasible: 5 (Pass)

**Evidence:** Defect 0 is the real upstream issue #1398 (fixed by PR #1449). Bugs 01–05 are coherent, plausible regressions: a sign flip in the hold offset, an inverted throw-direction comparison, a group restore moved to a branch that never runs, a 'grab helper' collides override, and a 'simplified' freeze branch. Each one's fix is a small, natural revert a real developer would write. One with-image run (gCxmGFG) found and fixed all six from the video, which shows the task is solvable.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 18. Gate – Oracle/Nop: 5 (Pass)

**Evidence:** CB Oracle m5spaQX: reward 1.0, 10/10, banners '== captured submission.patch', '== applying test.patch ==', '== running f2p + p2p tests ==', '== computing reward ==', 'reward=1.0'. CB Nop qaGFXDz: reward 0.0, f2p 0/7, p2p 3/3, same banners, 'reward=0.0'. No 'could not apply test.patch' in either stderr (0 hits). Both use lock digest 3e06674b, which equals the with-image trials and the current bundle. Local oracle/nop/re-run not run, by the user's standing rule.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 19. Unauditable: 5 (Pass)

**Evidence:** Complete, auditable submission.

**What is wrong:** Nothing found.

**Suggested fix:** None.
