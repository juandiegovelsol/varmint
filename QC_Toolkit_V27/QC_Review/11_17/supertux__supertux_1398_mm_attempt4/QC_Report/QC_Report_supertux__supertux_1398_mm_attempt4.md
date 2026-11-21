# QC Report: supertux__supertux_1398_mm

- **Task hash:** `supertux__supertux_1398_mm_attempt4`
- **Title:** Some objects misbehave in the forest (SuperTux/supertux #1398, temporal_interaction)
- **Rubric:** Official V27 (6a676431c4ebbc30851d6f10-V27_removing_misaligned_task_type_redundancy)
- **Review date:** 2026-11-17
- **Verdict:** **PASS**. Re-check after the instruction.md change. No dimension fails, and all 19 score 5. Re-graded: 2, 3, 4, 5, 6, 8, 16 and 18, plus the checksum gate. Dimension 4 is now 5: the text names the element ('the objects Tux grabs'), states three defects with their expected results (wrong side / held in front, thrown the wrong way and sinking / thrown the way he walks and resting on top of the ground, Tux passes through / solid for Tux), and points to the 2-4 s moment for the rest. Difficulty meets Option A: 0/3 no-image and exactly 1/4 with-image (vd2pFpV = 1.0). All 17 hashed files match the trial manifest; lock digest 9054295e = Oracle (1.0) = Nop (0.0) = with-image trials. One risk on dimension 4 (not scored as a fail): 2 of 4 with-image runs saw the rock on the frozen walking leaf and did not treat it as a bug. y3tUnFg read it as the intended 'falling rock hurts' rule; Tq9eHvW thought that rock wasn't one Tux grabbed. In Attempt2 all 4 runs fixed that defect. Other dimensions carry over from the Attempt2 review (only instruction.md and task.toml changed).

## Scorecard

| # | Dimension | Score | Result | Error category |
|---|---|---|---|---|
| 1 | Structure – Task Bundle Files | 5 | Pass | — |
| 2 | Structure – Deliverables & Packaging | 5 | Pass | — |
| 3 | Instruction – Requires Visual Evidence | 5 | Pass | — |
| 4 | Instruction – Symptom Specificity | 5 | Pass | — |
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
| 1 | Oracle (CB, lock 9054295e) | PASS | reward 1.0, f2p 7/7, p2p 3/3, 2.7 min |
| 2 | Nop (CB, lock 9054295e) | PASS | reward 0.0, f2p 0/7, p2p 3/3, 1.4 min |
| 3 | Local oracle / nop / re-run | WARN | Not run, by the user's standing rule (no oracle/nop/harbor). Graded from the CB runs |
| 4 | Changed files vs Attempt2 | PASS | Only instruction.md and task.toml (difficulty_explanation); everything else is byte-identical |
| 5 | pass@3 no-image | PASS | 0/3 (all fail the coin and leaf f2p); asset confirmed missing in all 3 |
| 6 | pass@4 with-image (Option A) | PASS | Exactly 1/4 (vd2pFpV = 1.0) |
| 7 | Trial run time | PASS | 3.8-12.0 min (informational) |
| 8 | Trial / task checksum | PASS | 17/17 hashed files match with_images task_manifest.json; lock 9054295e = Oracle = Nop = with-image trials |
| 9 | Leaks | PASS | New text names symptoms and a time window only; no repo, file, class or mechanism; no hint at coins or the leaf |
| 10 | Dim 4 trajectory risk | WARN | 2/4 with-image runs saw the frozen walking leaf and did not treat it as a bug (y3tUnFg: 'intended rule'; Tq9eHvW: 'not a grabbed rock'). Not scored as a fail |
| 11 | Packaging | WARN | Tasks/ and Trials/ are sibling folders with 3+4 trials; still to be tarred separately for submission |

## Trials

| Trial | Mode | Reward | f2p | p2p | Minutes | Failed tests |
|---|---|---|---|---|---|---|
| task_without_images__GD8a6Uy | no-image | 0.0 | 5/7 | 3/3 | 4.4 | DroppedRockFallsPastCoinsLikeThroughOpenAir; RockDroppedOnAWalkingLeafKnocksItOut |
| task_without_images__Jp3MWJL | no-image | 0.0 | 5/7 | 3/3 | 5.0 | DroppedRockFallsPastCoinsLikeThroughOpenAir; RockDroppedOnAWalkingLeafKnocksItOut |
| task_without_images__Y5KJtPh | no-image | 0.0 | 3/7 | 3/3 | 3.8 | DroppedRockFallsPastCoinsLikeThroughOpenAir; TuxCanStandOnARestingRock; TuxWalkingIntoARestingRockIsStoppedByIt; RockDroppedOnAWalkingLeafKnocksItOut |
| task_with_images__Tq9eHvW | with-image | 0.0 | 6/7 | 3/3 | 12.0 | RockDroppedOnAWalkingLeafKnocksItOut |
| task_with_images__vd2pFpV | with-image | 1.0 | 7/7 | 3/3 | 6.9 | — |
| task_with_images__y3tUnFg | with-image | 0.0 | 4/7 | 3/3 | 11.2 | TuxCanStandOnARestingRock; TuxWalkingIntoARestingRockIsStoppedByIt; RockDroppedOnAWalkingLeafKnocksItOut |
| task_with_images__yLS9rWo | with-image | 0.0 | 4/7 | 3/3 | 4.2 | TuxCanStandOnARestingRock; TuxWalkingIntoARestingRockIsStoppedByIt; RockDroppedOnAWalkingLeafKnocksItOut |

## Issues & suggested fixes

## Dimension details

### 1. Structure – Task Bundle Files: 5 (Pass)

**Evidence:** All 11 fixed files are present and non-empty: task.toml 6386 B, instruction.md 727, evidence_bundle.json 1104, environment/Dockerfile 4307, environment/assets/ASSET_MANIFEST.json 541, solution/fix.patch 4023, solution/solve.sh 349, tests/config.json 751, tests/test.patch 18211, tests/test.sh 10145, tests/verifier.py 8158. The 3 JSON files parse, task.toml parses with tomllib, and `python -I` py_compile of verifier.py passes. recording.mp4 (2571782 B) decodes with OpenCV as h264, 1280x720, 30 fps, 780 frames (26.0 s). The extra files are allowed: README.md and environment/bugs/bug_01..05.patch (injected bugs). [Not re-graded: carried over from the Attempt2 review. Attempt4 differs from Attempt2 only in instruction.md and task.toml difficulty_explanation; code, tests, bug patches, video and Dockerfile are byte-identical.]

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 2. Structure – Deliverables & Packaging: 5 (Pass)

**Evidence:** task108/Attempt4 has `Tasks/` and `Trials/` as sibling root folders, plus Oracle/, Nop/, Check/ and Analyze/. Trials/ holds 7 trials, Option A: without_images/ has 3 (GD8a6Uy, Jp3MWJL, Y5KJtPh) and with_images/ has 4 (Tq9eHvW, vd2pFpV, y3tUnFg, yLS9rWo).

**What is wrong:** Nothing found. Archive `Tasks/` and `Trials/` as separate .tar.gz files when you submit.

**Suggested fix:** On submission: `tar czf Tasks.tar.gz Tasks` and `tar czf Trials.tar.gz Trials` (same for Oracle/Nop).

### 3. Instruction – Requires Visual Evidence: 5 (Pass)

**Evidence:** Text alone now gives three of the six defects (wrong side while carried; thrown the wrong way and sinking into the ground; Tux passes through a resting one). It leaves the coin-column defect and the walking-leaf defect to the video, so a developer still can't fix it completely from the text. Trials confirm this: all 3 no-image runs failed the coin and leaf f2p (GD8a6Uy and Jp3MWJL 5/7, Y5KJtPh 3/7), and all 3 confirmed that /app/.harbor_assets/recording.mp4 did not exist. Path resolves to `/app/.harbor_assets/recording.mp4`. No leak: the new text names symptoms only (no repo, file, class, function or mechanism). 'Between about 2 and 4 seconds' is a time pointer that helps only an agent that has the video.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 4. Instruction – Symptom Specificity: 5 (Pass)

**Evidence:** Table: element = 'the objects Tux grabs' | defects in text = 'while Tux carries one, it is on the wrong side of him', 'when he throws one, it goes the wrong way and ends up sinking into the ground', 'Tux can pass through one that is lying on the ground' | expected in text = '(held in front of him)', '(thrown the way he is walking, coming to rest on top of the ground)', '(solid for Tux, who stops at them or stands on them)' | rest pointed to the video = 'Other problems with these objects are only visible in the recording, for example what happens to the one Tux lets go of on the branch, between about 2 and 4 seconds' | clue left to image = which object, the coin column, the walking leaf, the timing | described correctly = yes, checked against the frames (wrong side 1-2 s and 6.5-7.5 s; thrown backwards and in the dirt 23.5-24.5 s; Tux inside a resting rock 18.5 s and 20.5-21 s; the rock released at 2.5 s stops on the coins at 3.0 s, crawls down them until 3.75 s and is on the ground at 4.0 s). All three checks pass, with the defect stated in text. Trajectories (all 4 read): all 4 runs fixed the coin defect after the 2-4 s pointer (0/4 caught it in Attempt2's 3 failing runs). y3tUnFg and yLS9rWo missed the stated Tux-passes-through defect; that was a code-investigation miss (they never looked at Player::collides), not a perception one. The walking leaf: Tq9eHvW says 'around 20 s a rock appears to be resting on top of the squirrel enemy. I don't think that rock is one Tux grabbed in the clip, so I didn't treat it as one of these bugs'. y3tUnFg says 'in the clip a thrown rock lands on a squirrel and kills it. That's the existing "a falling rock hurts what it lands on" rule ... so I didn't treat it as a bug'. yLS9rWo never mentions it. vd2pFpV passed the leaf test through its Rock::collision rewrite.

**What is wrong:** Nothing found that fails. Risk flag: the rubric's third fail reason ('the with-image trials show agents could not tell the bug from intended behavior') can be cited for the walking-leaf defect. One run (y3tUnFg) explicitly took the freeze for the intended 'rock hurts what it lands on' rule, and one (Tq9eHvW) saw it but ruled it out of scope. In Attempt2 all 4 with-image runs fixed it. This is 1 explicit case in 4 on 1 of 6 defects, short of the 3/4 example the QC prompt gives, so I don't score it as a fail. A strict reviewer could.

**Suggested fix:** No change needed for the score. Don't point the text at the leaf: Tq9eHvW's only miss was the leaf test, so a pointer there would likely turn it into a pass, giving 2/4 and failing Option A. If QC does flag it, the fallback is a time pointer to that moment (for example 'and to the one he drops from the branch a few seconds later') with Option B (8 with-image runs, 1-2 passing). Any edit to instruction.md changes the checksum, so all trials must be re-run.

### 5. Instruction – Task Type: 5 (Pass)

**Evidence:** task_type = temporal_interaction ('Fix a defect that only appears across a sequence of interactions / state transitions'). The new text describes defects at specific transitions (carrying, throwing, landing, resting, the release at 2-4 s), which fits the slug even more directly than Attempt2.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 6. Image – Evidence Quality: 5 (Pass)

**Evidence:** Single asset recording.mp4 (role bug_video, neutral name). The new instruction makes four claims about it, all checked against the frames: (a) carried on the wrong side: Tux faces right with the rock behind him at 1.0-2.0 s, and faces left with it behind him at 6.5-7.5 s; (b) thrown the wrong way and ends up sinking into the ground: thrown while walking right at 23.5 s, it flies left and is embedded in the dirt at 24.5 s; (c) Tux passes through a resting one: 18.5 s, and 20.5-21 s after a jump; (d) the one Tux lets go of on the branch between about 2 and 4 s: released 2.5 s, on top of the coin column 3.0 s, crawling down 3.25-3.75 s, on the ground 4.0 s. All true. The f2p-to-asset mapping is unchanged from Attempt2 (all 6 defects pictured; the golden passes 10/10 on CB Oracle and on vd2pFpV). No run was confused about which asset is the bug (only one asset). Agents call the walking leaf a 'squirrel' (Tq9eHvW, y3tUnFg), but that comes from its sprite, not from anything the text claims.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 7. Metadata – task_type: 5 (Pass)

**Evidence:** `temporal_interaction` is one of the seven values. The evidence is a 26 s uncut clip whose defects only appear across state transitions (carry, release, flight, landing, rest). The guideline lists a '3–8 frame sequence / GIF' as the typical asset; an uncut video is a frame sequence and fits. [Not re-graded: carried over from the Attempt2 review. Attempt4 differs from Attempt2 only in instruction.md and task.toml difficulty_explanation; code, tests, bug patches, video and Dockerfile are byte-identical.]

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 8. Evidence – Chain Consistency: 5 (Pass)

**Evidence:** The instruction ref is unchanged: `/app/.harbor_assets/recording.mp4`. On disk it is 2571782 B with sha256 f7f5bbcf…9d6859, which matches ASSET_MANIFEST.json, evidence_bundle.json (local_path /app/.harbor_assets/recording.mp4) and the with_images task_manifest.json.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 9. Golden Fix – Applies Cleanly: 5 (Pass)

**Evidence:** Local scratch repo with src/badguy/badguy.cpp, src/object/player.cpp, src/object/player.hpp and src/object/rock.cpp at base_commit d2c892e2: bug_01..05 apply in order (`git apply`, all ok), then `git apply --check -v solution/fix.patch` checks all 4 files, exit 0. After applying, the net diff vs base_commit is the single Rock::collision line `moving_object && moving_object->get_group() != COLGROUP_TOUCHABLE` (upstream PR #1449). CB Oracle stdout shows 'captured submission.patch (4023 bytes, 4 files)' and reward 1.0. [Not re-graded: carried over from the Attempt2 review. Attempt4 differs from Attempt2 only in instruction.md and task.toml difficulty_explanation; code, tests, bug patches, video and Dockerfile are byte-identical.]

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 10. Golden Fix – Source-Only Scope: 5 (Pass)

**Evidence:** fix.patch `diff --git` paths = {src/badguy/badguy.cpp, src/object/player.cpp, src/object/player.hpp, src/object/rock.cpp}, which equals task.toml files_edited (same 4). No test, doc, lockfile or changeset path. [Not re-graded: carried over from the Attempt2 review. Attempt4 differs from Attempt2 only in instruction.md and task.toml difficulty_explanation; code, tests, bug patches, video and Dockerfile are byte-identical.]

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 11. Tests – Implementation Overfit: 5 (Pass)

**Evidence:** The assertions only read positions, coin count and badguy presence, with tolerances, so there are no string, enum or format assertions to enumerate. Alternatives (value | correct in repo? | test accepts): (0) coins: ignore touchables in Rock::collision (golden) yes/yes; coin-only dynamic_cast check yes (narrower)/yes; skip only the velocity reset for touchables yes/yes; a rock that collects coins as it falls = invented behaviour (coins are only collected by Tux; the video shows the coins untouched)/no, correctly rejected. Tolerance: within 2 frames of an open-air drop. (1) hold offset: if-branch (golden), or any mirrored offset yes/yes (only 'centre on the facing side'). (2) throw: `m_dir` (golden), or un-inverted side comparison once the hold is fixed yes/yes; any speed ≥ ~64 px/s accepted (16 px in 0.25 s). (3) group restore: in ungrab (golden), or unconditionally after any release yes/yes; 'lies on the floor ±2 px and still ±1 px after 2 s' matches the base rock, which zeroes x velocity on landing. (4) delete the Player::collides override (golden), or keep it but limit it to the carried object (CB-validated) yes/yes; the tests check stand-on ±2 px and stop-at-left-edge +2 px. (5) restore the ICE-only freeze (golden), or have the rock kill_fall badguys directly yes/yes: the test accepts any outcome that removes the leaf (fall or squish). Structure-level: no exact counts, ordering or error text, and float checks use tolerances. Trial cross-check: every failed f2p in the 6 failing trials is a defect the agent left unfixed (base value), never a valid alternative. The passing run gCxmGFG used its own patches across all four files. [Not re-graded: carried over from the Attempt2 review. Attempt4 differs from Attempt2 only in instruction.md and task.toml difficulty_explanation; code, tests, bug patches, video and Dockerfile are byte-identical.]

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 12. Tests – f2p/p2p Identifier Validity: 5 (Pass)

**Evidence:** task.toml f2p (7) and p2p (3) are identical to tests/config.json (checked in Python: equal = True for both lists). Each ID 'RockBehaviour <Name>' matches exactly one JUnit testcase (classname=RockBehaviour, name=<Name>) in the CB Oracle junit.xml: 10 testcases, all status=run. [Not re-graded: carried over from the Attempt2 review. Attempt4 differs from Attempt2 only in instruction.md and task.toml difficulty_explanation; code, tests, bug patches, video and Dockerfile are byte-identical.]

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 13. Tests – p2p Classification: 5 (Pass)

**Evidence:** CarriedRockMovesAlongWithTux, PutDownRockLandsOnTheGround and RockDroppedOnARestingRockStaysOnTop pass on CB Nop (base) and CB Oracle (reward_detail.json), and in all 7 trials. [Not re-graded: carried over from the Attempt2 review. Attempt4 differs from Attempt2 only in instruction.md and task.toml difficulty_explanation; code, tests, bug patches, video and Dockerfile are byte-identical.]

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 14. Tests – Discriminating (f2p): 5 (Pass)

**Evidence:** All 7 f2p fail on CB Nop (reward_detail: 7 × fail) and pass on CB Oracle (7 × pass). [Not re-graded: carried over from the Attempt2 review. Attempt4 differs from Attempt2 only in instruction.md and task.toml difficulty_explanation; code, tests, bug patches, video and Dockerfile are byte-identical.]

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 15. Tests – Determinism: 5 (Pass)

**Evidence:** Tests step the game's own update loop at a fixed FRAME = 1/64 s and drive Tux through the scripting controller, with no wall-clock time, sleep, network or rand in test.patch. SDL_VIDEODRIVER/AUDIODRIVER=dummy, so there is no rendering and no fonts. test.sh installs nothing (an offline cmake rebuild only). Consistency: the 3 p2p pass in all 9 runs (7 trials + oracle + nop), and each f2p outcome lines up with what that agent fixed. Gtest run time is 333 ms. The local oracle re-run was not done, by the user's standing rule. [Not re-graded: carried over from the Attempt2 review. Attempt4 differs from Attempt2 only in instruction.md and task.toml difficulty_explanation; code, tests, bug patches, video and Dockerfile are byte-identical.]

**What is wrong:** Nothing found.

**Suggested fix:** None. Optional: [verifier] network_mode is 'public' although test.sh needs no network. 'no-network' would be tighter, but it changes the checksum, so only do it if you re-run trials anyway.

### 16. Hardening – Difficulty (Model Trial Fails): 5 (Pass)

**Evidence:** Option A, 7 trials. No-image (digest 953249fa): GD8a6Uy 0.0, Jp3MWJL 0.0, Y5KJtPh 0.0 = 0/3, and all 3 confirm the asset was missing ('harbor_assets/recording.mp4: No such file'). With-image (digest 9054295e): Tq9eHvW 0.0, vd2pFpV 1.0, y3tUnFg 0.0, yLS9rWo 0.0 = exactly 1/4. Run times 3.8-12.0 min (informational).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 17. Hardening – Real & Feasible: 5 (Pass)

**Evidence:** Defect 0 is the real upstream issue #1398 (fixed by PR #1449). Bugs 01–05 are coherent, plausible regressions: a sign flip in the hold offset, an inverted throw-direction comparison, a group restore moved to a branch that never runs, a 'grab helper' collides override, and a 'simplified' freeze branch. Each one's fix is a small, natural revert a real developer would write. One with-image run (gCxmGFG) found and fixed all six from the video, which shows the task is solvable. [Not re-graded: carried over from the Attempt2 review. Attempt4 differs from Attempt2 only in instruction.md and task.toml difficulty_explanation; code, tests, bug patches, video and Dockerfile are byte-identical.]

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 18. Gate – Oracle/Nop: 5 (Pass)

**Evidence:** CB Oracle d96jGCA: reward 1.0, 10/10, 5 stage banners. CB Nop D2tfvsm: reward 0.0, f2p 0/7, p2p 3/3, 5 banners. 0 'could not apply' hits in either stderr. Both use lock digest 9054295e, the same as the with-image trials and the current Attempt4 bundle. Local oracle/nop/re-run not run, by the user's standing rule.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 19. Unauditable: 5 (Pass)

**Evidence:** Complete, auditable submission. [Not re-graded: carried over from the Attempt2 review. Attempt4 differs from Attempt2 only in instruction.md and task.toml difficulty_explanation; code, tests, bug patches, video and Dockerfile are byte-identical.]

**What is wrong:** Nothing found.

**Suggested fix:** None.
