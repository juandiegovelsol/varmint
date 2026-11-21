"""Write QC_Report/findings.json for task108 Attempt5 (fresh V27 review).
Usage: python -I make_findings.py <QC_Report dir> <determinism summary file>"""
import json
import pathlib
import sys

out_dir = pathlib.Path(sys.argv[1])
det = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8").strip().splitlines()
det_base = [l for l in det if l.startswith("base run")]
det_gold = [l for l in det if l.startswith("golden run")]
det_ok = (len(det_base) == 5 and len(det_gold) == 5
          and all("passed=3 " in l and l.count(",") == 7 for l in det_base)
          and all("passed=10 " in l and l.endswith("failed=") for l in det_gold))
det_line = (f"5 fresh processes per state, each with a different `--gtest_shuffle` seed: base gave the same 7 f2p failures "
            f"and 3 p2p passes every time, golden 10/10 every time." if det_ok else
            "Fresh-process runs did NOT agree; see crosscheck/determinism/summary.txt.\n" + "\n".join(det))

N = "Nothing found."

dims = []


def dim(name, score, category, evidence, wrong, fix):
    dims.append(dict(name=name, score=score, category=category, evidence=evidence, wrong=wrong, fix=fix))


dim("Structure – Task Bundle Files", 5, "",
    "All 11 fixed files exist and are non-empty: `task.toml` 7,187 B, `instruction.md` 1,087 B, `evidence_bundle.json` 1,104 B, "
    "`environment/Dockerfile` 4,307 B, `environment/assets/ASSET_MANIFEST.json` 541 B, `solution/fix.patch` 4,023 B, "
    "`solution/solve.sh` 349 B, `tests/config.json` 751 B, `tests/test.patch` 18,211 B, `tests/test.sh` 10,145 B, "
    "`tests/verifier.py` 8,158 B. The three JSON files parse, `task.toml` parses (tomllib), and `py_compile tests/verifier.py` succeeds. "
    "`recording.mp4` decodes (ffprobe: h264 1280x720, 30 fps, 780 frames, 26.000 s; every frame extracted). All text files use LF. "
    "Extra files: `README.md` and `environment/bugs/bug_01..05.patch` (the injected bugs). Neither is a fail.",
    N, "None.")

dim("Structure – Deliverables & Packaging", 5, "",
    "`task108/Attempt5/` has `Tasks/` (capital T) and `Trials/` as root-level siblings. `Tasks/supertux__supertux_1398_mm/` is the bundle. "
    "`Trials/without_images/` holds 3 runs (Cg3CUd4, Gdf5AUp, ktEgqvp) and `Trials/with_images/` holds 4 (6rfz4NT, GHMqPaD, PDeVuwP, yCYGP4T), "
    "so there are 7 trials, the Option A count. The bundle was reviewed as unpacked folders because this local check had no .tar.gz files.",
    "Nothing found. The layout is correct. Only the folder layout could be checked here, not the final archives.",
    "When you package, tar from inside `Attempt5/` so each archive unpacks to its own top-level folder: `tar -czf Tasks.tar.gz Tasks` and "
    "`tar -czf Trials.tar.gz Trials`. Keep `Check/` and `Analyze/` out of both.")

dim("Instruction – Requires the Visual Evidence", 5, "",
    "Without the video, the text names only \"the objects Tux grabs\" and five abstract areas, and states one defect (carried on the wrong side). "
    "It names no object, file, coin, enemy, freeze or mechanism. From the text alone, two defects cannot be diagnosed because the code looks plausible: "
    "the rock crawling down the coin column (upstream #1398, `Rock::collision` treats touchable coins as something to land on) and the "
    "walking leaf freezing (`BadGuy::collision_tile` in `src/badguy/badguy.cpp`, outside the rock code). "
    "The trials agree (corroboration only, not proof): all 3 no-image runs found `/app/.harbor_assets` empty (step 3 in each), fixed 4 of the 6 defects by "
    "reading code, and each missed exactly the coin and leaf f2p (5/7).\n"
    "The image path resolves to `/app/.harbor_assets/recording.mp4` (Dockerfile `COPY assets/recording.mp4 /app/.harbor_assets/`).\n"
    "Leak scan of `instruction.md` (195 words): no repo name, URL, org, issue or PR link, file list or mechanism. \"Tux\" is the in-game character "
    "the agent sees in the repo anyway, so it does not reveal the source. The title \"Some objects misbehave in the forest\" is neutral.",
    N, "None.")

dim("Instruction – Symptom Specificity", 3, "[Non-Fail - Image-carried Symptom]",
    "Prompt table (times are from the clip):\n\n"
    "| element (as written) | defect: text or image? | expected: text or image? | comparison: correct counterpart in the clip? | clue left to image | described correctly? |\n"
    "|---|---|---|---|---|---|\n"
    "| \"while Tux carries one\" | text: \"it is on the wrong side of him\" | implied by \"wrong side\" | not needed (stated in words); all 3 carries in the clip are wrong | which side, both directions | yes: rock behind Tux facing right (1.5–2.3 s, 23.0–23.6 s) and facing left (7.6–9.0 s) |\n"
    "| \"how one is let go\" | image only: thrown while walking right, flies left behind Tux (about 23.7–24.0 s) | not stated, not shown | **no**: the clip's only throw while walking is the buggy one. The two put-downs (2.4 s, 9.2 s) drop straight down as a put-down should, but they are a different kind of release. Only \"look out of place\" applies | direction | yes |\n"
    "| \"how it falls\" | image only: crawls down the 4-coin column, 3.0–3.9 s | shown by the counterpart | **yes**: the 2nd rock's free fall (9.2–9.6 s) and the 1st rock's own fall before it touches the coins (2.5–2.9 s) | what slows it | yes |\n"
    "| \"where it comes to rest\" | image only: thrown rock inside the dirt at 24.0 s, then gone | shown by the counterpart | **yes**: rocks resting on top of the ground (the coin-column rock from 3.9 s, the slope rock from 0 s) | which rock | yes |\n"
    "| \"how it and the other things in the level affect each other\" | image only: coins hold it up; walking leaf turns into an ice block (9.6 s) with the rock resting on it | coins: shown by the counterpart; enemy: not stated, not shown | coins: **yes** (as above). Enemy: **no**, it is the clip's only rock–enemy hit; only \"look out of place in this level\" applies (an ice block in a forest level) | coins, freeze | yes |\n"
    "| \"what happens when Tux meets one that is lying on the ground\" | image only: Tux walks through resting rocks (17.0 s, 18.5 s) and stands inside one (20.0–21.0 s) | not stated, not shown | **no**: every time Tux meets a resting rock in the clip, the bug shows; only \"look out of place\" applies | pass-through, sinking | yes |\n\n"
    "Counterpart check: each bug only triggers in a specific situation, so the clip shows the correct behavior only for the coin crawl (free falls "
    "elsewhere) and the sinking (rocks resting on top of the ground). The throw direction, Tux meeting a resting rock, and the enemy hit have no correct "
    "instance anywhere in the clip, because every instance triggers the bug. For those three, the text's pointer holds only through its second half, "
    "\"or that look out of place in this level\", and the expected result has to come from normal platformer behavior. V27 does not fail a task "
    "because an expected result isn't pictured, and all 4 with-image runs still flagged those three as bugs (below).\n\n"
    "Every with-image trajectory:\n\n"
    "| run | reward | what it read | could it tell bug from intended? |\n"
    "|---|---|---|---|\n"
    "| 6rfz4NT | 1.0 | step 13: \"the rock is held behind Tux, it gets released on the wrong side, it falls too slowly, and it passes through a column of coins\"; step 17: \"Tux walks straight through a rock lying on the ground, and a rock that lands on the leaf enemy freezes it instead of killing it\" | yes, all 6 |\n"
    "| PDeVuwP | 1.0 | measured the rock's y position frame by frame (step 24); its final table lists all 6, e.g. \"the dropped rock stops and starts at each coin it passes\" | yes, all 6 (calls the leaf a \"squirrel\" but reads the freeze correctly) |\n"
    "| GHMqPaD | 0.0 (5/7) | read all 6, including \"Tux could walk right through one lying on the ground\", but blamed the thrown-rock group bug and kept the `Player::collides` override | yes; the cause was wrong, not the symptom |\n"
    "| yCYGP4T | 0.0 (6/7) | read 5; never mentions the coins or the fall speed (\"Rocks dropped straight down weren't affected, which is why the other rocks looked fine\") | missed one subtle defect; nothing was misread as intended |\n\n"
    "No run took a bug for intended behavior. The subtlest symptom (the coin crawl) was read by 3 of 4 runs, so this is not `[Fail - Unspecific Symptoms]`.",
    "Only one defect is stated in words (carried on the wrong side). The other five are named by element only, and the exact defect is left to "
    "comparisons inside the clip. Under V27 that is the `[Non-Fail - Image-carried Symptom]` flag. It is not a fail; record it in the feedback.\n"
    "Non-graded: three of those five defects (throw direction, Tux meeting a resting rock, the enemy hit) have no correct counterpart in the clip, "
    "so \"don't match the same kind of thing elsewhere in the same clip\" does not apply to them; only \"or that look out of place in this level\" does.",
    "Optional; a 3 is acceptable. To reach a 5, each remaining defect would have to be stated in words without the cause. Example: \"When Tux lets go of one while "
    "walking, it goes the wrong way; one that falls past other things in the level slows down; a thrown one doesn't stay on top of the ground; an enemy "
    "it lands on is not knocked out; Tux passes through one lying on the ground.\"\n"
    "**Caution:** in this trial set, the no-image runs fix 4 of 6 defects from code alone and miss only the coin and leaf defects. Stating those two in "
    "words would very likely let no-image runs pass, which breaks dimension 16. Recommendation: keep the 3. Any change to `instruction.md` changes "
    "the task checksum, so all 7 trials must be re-run.\n"
    "If you re-run anyway for dimension 16, you can make the pointer match the clip without adding a hint, e.g. \"Some of them differ from the same "
    "kind of thing elsewhere in the clip; the others look wrong on their own for this game.\" The current sentence is not false (it is an either/or), "
    "only less exact.")

dim("Instruction – Task Type", 5, "",
    "`task_type = \"temporal_interaction\"` means fixing a defect that only appears across a sequence of interactions or state transitions. The instruction "
    "describes defects across a grab → carry → let go → fall → rest → contact sequence. Each one is visible only over time in the 26 s clip "
    "(the fall speed past the coins, the throw direction, sinking after the throw, Tux passing through). The text reasonably falls under the type.",
    N, "None.")

dim("Image – Evidence Quality", 5, "",
    "Naming and truth table:\n\n"
    "| file | role | what the frames show (how verified) | what name / role / instruction claim | true? | agents confused? |\n"
    "|---|---|---|---|---|---|\n"
    "| `recording.mp4` | `bug_video` | the buggy build with all 6 defects (dimension 4 table). Checked against the local nop failure values: rock centre 21 px behind Tux; throw moves −50 px; thrown rock bottom at y 2996 (through the floor); 94 vs 41 frames past the coins; Tux bottom 416 inside the rock (top 384); leaf still standing | neutral name; role is bug video; instruction says \"several things … are not how those objects work in this game\"; description says it is the forest level `world2/walking_leaves.stl` with extra objects, a coin column and a walking leaf. That level exists in the repo with 19 walking leaves and no rocks, so the rocks and coins were added, as described | yes | no: all 4 with-image runs treated it as the buggy state |\n\n"
    "Instruction claim check: \"the other problems show up in the recording as things that don't match the same kind of thing elsewhere in the same "
    "clip, or that look out of place in this level\" is true for every defect as an either/or. Two defects have a correct counterpart in the clip (the "
    "fall past the coins, the sinking). Three have none and only look out of place (the throw direction, Tux meeting a resting rock, the enemy freeze). "
    "The carry side is stated in words. Details in dimension 4.\n\n"
    "Does each f2p grade what the asset shows? (steps 1–4; runs in the locally built task image):\n\n"
    "| f2p | preconditions (test.patch) | asset state | reachable? | only that golden part applied | golden minus that part |\n"
    "|---|---|---|---|---|---|\n"
    "| DroppedRockFallsPastCoinsLikeThroughOpenAir | rock put down while standing at a ledge end (vx = 0, so the solid group is restored), falls past 3 coins; frames compared with an open-air drop; coins kept | 2.4 s: rock put down at the branch end crawls down a 4-coin column (3.0–3.9 s); the coins stay | yes, same branch (vy > 200, `hit.bottom` on a TOUCHABLE coin) | P0 alone: this f2p flips, nothing else | fails only this f2p |\n"
    "| CarriedRockIsHeldInFrontOfTux | walks right, then left, carrying | behind Tux facing right and facing left | yes | P1 alone flips only it | fails only it |\n"
    "| RockThrownWhileWalkingFliesForward | released while walking, both directions | 23.7–24.0 s: released while walking right, flies left | yes (right shown; left is the mirror) | P2 alone flips only it | fails only it |\n"
    "| ThrownRockLandsAndStaysOnTheGround | thrown while walking; lying still on the floor 2 s later | same throw; rock inside the dirt at 24.0 s, then gone | yes | P3 alone flips only it | fails only it |\n"
    "| TuxCanStandOnARestingRock | Tux falls onto a resting rock | 20.0–21.0 s: Tux stands inside a resting rock after a jump | yes | P4 alone flips both Tux tests | fails both Tux tests |\n"
    "| TuxWalkingIntoARestingRockIsStoppedByIt | walks into a resting rock without the action key | 17.0 s and 18.5 s: Tux walks through resting rocks | yes | P4 (as above) | as above |\n"
    "| RockDroppedOnAWalkingLeafKnocksItOut | rock dropped from a ledge onto a walking leaf pacing below | 9.2–9.6 s: rock dropped from the branch onto the leaf on the ?-blocks; the leaf becomes an ice block with the rock on top | yes | P5 alone flips only it | fails only it |\n\n"
    "Applying all six parts gives the same tree as `fix.patch`.\n"
    "Step 5, upstream: issue #1398 \"Throwable objects interact with coins\" (they fall more slowly through a line of coins). PR #1449 changes exactly "
    "`if (moving_object && moving_object->get_group() != COLGROUP_TOUCHABLE)`, and base + `fix.patch` gives upstream's fixed `rock.cpp` blob `e46de4e`. "
    "The clip shows that same symptom.\n"
    "Step 6, trials: both passing runs give causes that hold in the clip's scene. No run copies upstream comments. The failing runs miss different f2p "
    "(coin; the Tux pair), and each miss is an unfixed defect.\n"
    "Step 7, injected bugs (`environment/bugs/bug_01–05`): every one is visible in the clip and graded by its own f2p. Is a fix that skips one complete? No, "
    "in every case. For example, skipping bug_05 keeps `BadGuy::collision_tile` (`src/badguy/badguy.cpp` 318–325) freezing any freezable enemy hit by "
    "HURTS (the ice block at 9.6 s). Skipping bug_04 keeps the `Player::collides` override (`src/object/player.cpp` 1687–1694) that lets Tux pass "
    "resting rocks (17.0 s).",
    N, "None.")

dim("Metadata – task_type Accuracy", 5, "",
    "`temporal_interaction` is one of the seven values and fits the asset: a 26 s uncut video of an interaction sequence (grab, carry, release, fall, "
    "rest, contact) whose defects only show over time. `visual_bug_fix` would also be defensible, and the rubric does not penalize a valid choice.",
    N, "None.")

dim("Evidence – Chain Consistency", 5, "",
    "The four references:\n\n"
    "| reference | file | path | sha256 | bytes |\n"
    "|---|---|---|---|---|\n"
    "| file on disk | `environment/assets/recording.mp4` | (copied by `COPY assets/recording.mp4 /app/.harbor_assets/`) | `f7f5bbcf…d9859` | 2,571,782 |\n"
    "| `ASSET_MANIFEST.json` | `recording.mp4` | container_path `/app/.harbor_assets/recording.mp4` | same | same |\n"
    "| `evidence_bundle.json` | `recording.mp4` | local_path and container_path `/app/.harbor_assets/recording.mp4`, role `bug_video` | same | same |\n"
    "| `instruction.md` | `recording.mp4` | `/app/.harbor_assets/recording.mp4` | n/a | n/a |\n\n"
    "Only the video is copied into the image, not the manifest. `url` and `source_url` are empty with `source_kind: captured_from_repo`, which is allowed.",
    N, "None.")

dim("Golden Fix – Applies Cleanly", 5, "",
    "In the image built locally from `environment/`, at `harbor_base`: `git apply --check /solution/fix.patch` succeeds. The `solve.sh` log shows "
    "`+ git apply /solution/fix.patch` and \"Applied fix.patch.\" with exit 0. Base + `fix.patch` gives upstream's fixed `rock.cpp` (`e46de4e`) and "
    "upstream's base `player.cpp`/`player.hpp`/`badguy.cpp` (`44dfa67`/`983fe05`/`ca20e4b`), so the golden is the upstream fix plus the five bug reverts.",
    N, "None.")

dim("Golden Fix - Source-Only Scope", 5, "",
    "The `diff --git` paths {`src/badguy/badguy.cpp`, `src/object/player.cpp`, `src/object/player.hpp`, `src/object/rock.cpp`} equal "
    "`files_edited` as a set. There is no test, doc, lockfile or changeset path. `test.patch` touches only `tests/rock_behaviour_test.cpp` "
    "(= `config.json` `test_files`). `solve.sh` applies only `fix.patch`.",
    N, "None.")

dim("Tests – Implementation Overfit", 5, "",
    "Every assertion is geometric or behavioral with a tolerance. None compares strings, enums, colours, number formats or source text.\n\n"
    "| assertion | what it accepts | grounded in |\n"
    "|---|---|---|\n"
    "| coins: frames to floor ≤ open-air frames + 2; coin count unchanged | any fix where coins don't hold the rock up (the open-air baseline is measured on the candidate's own build) | issue #1398, clip 3.0–3.9 s; `Coin::collision` never lets a non-player collect (`coin.cpp` 183–191) |\n"
    "| carry: rock centre strictly on the facing side, both directions | any in-front hold offset | clip |\n"
    "| throw: ≥ 16 px forward in 0.25 s | any forward throw of at least about 64 px/s (base throws at 200 px/s) | clip |\n"
    "| landed: bottom within 2 px of the floor and still (±1 px) 2 s after the throw | any landing, including a short slide | clip |\n"
    "| stand / walk into: Tux bottom within 2 px of the rock top; Tux right ≤ rock left + 2 | any solid resting rock | clip |\n"
    "| leaf: no enemy left above the floor 4 s later | the repo's own knock-out, `kill_fall()`, which the rock reaches through `collision_tile(Tile::HURTS)`. A squish would not count: the test calls `Sector::update` directly, which never advances `g_game_time` (only `ScreenManager` does, `screen_manager.cpp` line 507), so the 2 s squish timer never expires | clip; no object in `src/object` calls `kill_squished` (protected, used only for stomps), while the objects that knock enemies out (block bumps, explosions, ice crusher, hurting platform) all call `kill_fall()` |\n\n"
    "Alternatives run in the task image:\n\n"
    "| alternative | valid / plausible (repo precedent) | result |\n"
    "|---|---|---|\n"
    "| ALT-B, six changes written differently from the golden: an early `return ABORT_MOVE` for COLGROUP_TOUCHABLE next to the existing HeavyCoin/Explosion early returns; a flipped ternary for the hold offset; a flipped comparison for the release direction; an unconditional `set_group(COLGROUP_MOVING_STATIC)` in `ungrab` that keeps the landing line; `Player::collides` kept but limited to grabbed objects; a compound `(tile_attributes & Tile::ICE) && is_freezable()` | plausible: each one mirrors code already in `rock.cpp`, `player.cpp` or `badguy.cpp` | 10/10 |\n"
    "| trial 6rfz4NT's submission: `dynamic_cast<Coin*>` skip, override limited to the carried object, plus a wall-stop change | plausible | 10/10 (trial verifier) |\n"
    "| trial PDeVuwP's submission: touchable check, flipped comparisons | plausible | 10/10 (trial verifier) |\n"
    "| upstream PR #1449 coin fix | upstream | identical to the golden coin hunk |\n\n"
    "Step 5, trial failures: every failed assertion in the 5 failing trials is the unfixed base value (94 vs 41 frames; leaf still standing; Tux bottom "
    "416 inside the rock's top at 384; Tux right edge at x 758, past the rock's left edge at x 320). Those are real defects, not equivalent output forms.\n"
    "\"Fix only what the evidence shows\": each golden part alone flips exactly its own f2p, so no f2p grades a state the clip doesn't show.\n"
    "Structure level: the only fixed counts are the one-rock / one-leaf test rooms (setup asserts) and \"coins not used up\", which is base behavior.",
    "Nothing found. The coin test is lenient (a coin-only special case also passes). The leaf test accepts the repo's own knock-out (`kill_fall`) "
    "but not a timer-based squish, because the test loop never advances the game clock. That is not overfit: a rock can't squish an enemy without "
    "changing `BadGuy` (`kill_squished` is protected), and no object in the repo knocks enemies out that way.",
    "None.")

dim("Tests – f2p/p2p Identifier Validity", 5, "",
    "The `task.toml` f2p (7) and p2p (3) lists are identical to `config.json` (same order), with no overlap. Each id, `RockBehaviour <Name>`, matches "
    "exactly one JUnit testcase (classname `RockBehaviour`, name `<Name>`) in the local oracle report. It is an exact key in `verifier.py`'s `resolve()`, "
    "with no suffix ambiguity. `test.sh` builds the gtest filter from the same ids (`RockBehaviour.<Name>`).",
    N, "None.")

dim("Tests – p2p Classification", 5, "",
    "The 3 p2p (CarriedRockMovesAlongWithTux, PutDownRockLandsOnTheGround, RockDroppedOnARestingRockStaysOnTop) pass on the local nop, the local "
    "oracle, the oracle re-run, the CB's nop and oracle, and in all 7 trials.",
    N, "None.")

dim("Tests – Discriminating (f2p)", 5, "",
    "All 7 f2p fail on nop (local and CB) and pass on oracle. The nop failure values are the defects themselves: 94 vs 41 frames past the coins; the "
    "rock centre 21 px behind Tux walking right and 18–20 px behind walking left; the thrown rock moves −50 / +50 px; the thrown rock's bottom is at "
    "y 2996 (through the floor); Tux stands inside or walks through the rock; the leaf is still standing. Per-part isolation shows each f2p flips "
    "only with its own golden part.",
    N, "None.")

dim("Tests – Determinism", 5, "",
    "Simulation runs on a fixed logical step (`FRAME = 1/64` s) through `Sector::update`, with scripted-controller input, `VIDEO_NULL`, and sound "
    "and music disabled. There is no wall clock, no network and no font rendering. `test.sh` installs nothing (cmake configure plus an incremental "
    "build), so `[verifier] network_mode = \"public\"` is more than needed but is not a Network Configuration fail. The local oracle and the oracle "
    "re-run give the same per-test result, and the CB's oracle and nop match. " + det_line,
    "Nothing found. Non-graded note: the test harness can't be repeated inside one process (`--gtest_repeat`). The second iteration segfaults "
    "because `GameEnvironment::TearDown` shuts down SDL/PhysFS. `test.sh` runs each test once per process, so grading is unaffected.",
    "None.")

dim("Hardening – Difficulty (Model Trial Fails)", 2, "[Fail - Trial Threshold Not Met]",
    "Rewards from each run's `verifier/reward.txt`:\n\n"
    "| run | mode | reward | f2p | failed tests |\n"
    "|---|---|---|---|---|\n"
    "| Cg3CUd4 | no-image | 0.0 | 5/7 | coins, leaf |\n"
    "| Gdf5AUp | no-image | 0.0 | 5/7 | coins, leaf |\n"
    "| ktEgqvp | no-image | 0.0 | 5/7 | coins, leaf |\n"
    "| 6rfz4NT | with-image | **1.0** | 7/7 | none |\n"
    "| PDeVuwP | with-image | **1.0** | 7/7 | none |\n"
    "| GHMqPaD | with-image | 0.0 | 5/7 | Tux stand, Tux walk-into |\n"
    "| yCYGP4T | with-image | 0.0 | 6/7 | coins |\n\n"
    "No-image runs used `task_without_images` (checksum `2e1fe540…`), and each saw an empty `/app/.harbor_assets` in step 3. With-image runs used "
    "`task_with_images` (checksum `d75c345b…`, the same as the CB's oracle and nop), and `task_manifest.json` lists the same file hashes as this "
    "bundle. All runs used claude-opus-5-5. Agent time was 2.2–7.0 min (5.0–9.4 min total), which is informational only.",
    "With-image pass@4 is **2/4**, but Option A requires exactly 1 pass and 3 fails. No-image is 0/3, which is correct. The task matches neither option.",
    "Lower the with-image solve rate a little. No-image already has margin: every no-image run misses both the coin and the leaf test.\n"
    "Evidence from this set: what separated passes from fails was the coin crawl (yCYGP4T never noticed it) and the cause of the pass-through "
    "(GHMqPaD). Both passing runs examined the fall closely: 6rfz4NT at step 25 (\"almost constant speed while it passes the coin column\"), and "
    "PDeVuwP tracked the rock's y position per frame at step 24.\n"
    "Options, cheapest first:\n"
    "(1) Drop \"how it falls,\" from the list. The coin crawl stays covered by \"how it and the other things in the level affect each other\", "
    "so dimension 4 stays a 3. Then re-run all 7 trials, because the checksum changes.\n"
    "(2) Re-running unchanged as Option B (8 with-image runs, 1–2 passes) is unlikely to work: at the observed ~50% rate, P(1 or 2 of 8) ≈ 14%.\n"
    "(3) Re-rolling pass@4 at ~50% lands exactly 1/4 only about 25% of the time.\n"
    "Don't name coins, the leaf, enemies or freezing anywhere. Those two hidden defects are what keep the no-image runs at 0/3.")

dim("Hardening - Real & Feasible", 5, "",
    "This is a real issue: upstream #1398 (throwables are slowed by coins), fixed upstream by PR #1449's one-line check, which the golden contains verbatim. "
    "The five injected bugs (`environment/bugs/`) are small, coherent regressions in real code paths: the hold offset, the release direction, the group "
    "restore, a `Player::collides` override and a freeze branch. Each is visible in the clip, and the golden is the natural revert, code a real developer "
    "would write. It is feasible: 2 of 4 with-image runs fixed all six in 3.9–6.3 agent-minutes.",
    N, "None.")

dim("Gate – Oracle/Nop", 5, "",
    "The image was built locally from `Attempt5/Tasks/.../environment` (every layer was a cache hit, so the inputs are identical). Runs used `--network none`.\n\n"
    "| run | reward | f2p | p2p | time |\n"
    "|---|---|---|---|---|\n"
    "| local oracle | 1.0 | 7/7 | 3/3 | 108 s |\n"
    "| local oracle re-run | 1.0 (same per test) | 7/7 | 3/3 | 108 s |\n"
    "| local nop | 0.0 | 0/7 | 3/3 | 46 s |\n"
    "| CB oracle DURkPv8 | 1.0 | 7/7 | 3/3 | 11.7 min |\n"
    "| CB nop ggcCsN9 | 0.0 | 0/7 | 3/3 | 1.8 min |\n\n"
    "The stage banners (`== applying test.patch ==`, `== running f2p + p2p tests ==`, `== computing reward ==`, `reward=`) are present. "
    "There is no \"could not apply test.patch\".",
    "Nothing found. Non-graded cosmetic note: on nop the banner reads `== captured submission.patch (0 bytes, 0` and breaks across lines, because "
    "`grep -c` prints 0 and exits 1, so `|| echo 0` adds a second 0.",
    "None.")

dim("Unauditable", 5, "", "The task is complete and auditable: the bundle, all 7 trials, and the oracle and nop runs are present, and everything was reproduced locally.", N, "None.")

gates = [
    dict(label="Local oracle", status="pass", detail="1.0 (7/7 f2p, 3/3 p2p) in the image built from Attempt5 `environment/`, `--network none`, 108 s."),
    dict(label="Local nop", status="pass", detail="0.0 (0/7 f2p, 3/3 p2p), 46 s."),
    dict(label="Oracle re-run", status="pass", detail="1.0, with the same outcome for every test as the first run."),
    dict(label="CB oracle / nop", status="pass", detail="DURkPv8 1.0, ggcCsN9 0.0; same checksum (`d75c345b…`) as the with-image trials."),
    dict(label="Patch apply", status="pass", detail="`git apply --check /solution/fix.patch` OK at `harbor_base`; solve.sh exit 0."),
    dict(label="Verifier completion", status="pass", detail="Stage banners and `reward=` present; no \"could not apply test.patch\"."),
    dict(label="Per-defect isolation", status="pass", detail="Each golden part alone flips only its own f2p; leaving out any one part fails only its own f2p; the union of the parts equals fix.patch."),
    dict(label="Alternative fix (ALT-B)", status="pass", detail="Six changes written differently from the golden: 10/10."),
    dict(label="Determinism", status="pass" if det_ok else "fail", detail=det_line),
    dict(label="pass@3 no-image", status="pass", detail="0/3 (each 5/7; each misses the coin and leaf tests); `/app/.harbor_assets` empty in every run."),
    dict(label="pass@4 with-image (Option A)", status="fail", detail="**2/4** (6rfz4NT, PDeVuwP = 1.0); Option A needs exactly 1/4."),
    dict(label="Trial run time (informational)", status="warn", detail="Agent 2.2–7.0 min, total 5.0–9.4 min; far under the 90-min budget."),
    dict(label="Trial / task checksum", status="pass", detail="`task_manifest.json` file hashes = this bundle; with-image `d75c345b…` = CB oracle/nop; no-image variant `2e1fe540…` (assets stripped)."),
    dict(label="Packaging", status="pass", detail="`Tasks/` and `Trials/` are root siblings with 3 + 4 trials; reviewed as folders, so tar each separately at submission."),
    dict(label="Leaks", status="pass", detail="No repo name, URL, issue/PR link, file list or mechanism in instruction.md."),
    dict(label="Evidence-chain integrity", status="pass", detail="Disk, manifest, evidence bundle and instruction all point to `/app/.harbor_assets/recording.mp4` with matching sha256 and bytes."),
]

trials = [
    dict(id="task_without_images__Cg3CUd4", mode="no-image", reward=0.0, f2p="5/7", p2p="3/3", minutes=9.1,
         failed=["DroppedRockFallsPastCoinsLikeThroughOpenAir", "RockDroppedOnAWalkingLeafKnocksItOut"]),
    dict(id="task_without_images__Gdf5AUp", mode="no-image", reward=0.0, f2p="5/7", p2p="3/3", minutes=6.2,
         failed=["DroppedRockFallsPastCoinsLikeThroughOpenAir", "RockDroppedOnAWalkingLeafKnocksItOut"]),
    dict(id="task_without_images__ktEgqvp", mode="no-image", reward=0.0, f2p="5/7", p2p="3/3", minutes=5.0,
         failed=["DroppedRockFallsPastCoinsLikeThroughOpenAir", "RockDroppedOnAWalkingLeafKnocksItOut"]),
    dict(id="task_with_images__6rfz4NT", mode="with-image", reward=1.0, f2p="7/7", p2p="3/3", minutes=6.0, failed=[]),
    dict(id="task_with_images__GHMqPaD", mode="with-image", reward=0.0, f2p="5/7", p2p="3/3", minutes=9.4,
         failed=["TuxCanStandOnARestingRock", "TuxWalkingIntoARestingRockIsStoppedByIt"]),
    dict(id="task_with_images__PDeVuwP", mode="with-image", reward=1.0, f2p="7/7", p2p="3/3", minutes=8.4, failed=[]),
    dict(id="task_with_images__yCYGP4T", mode="with-image", reward=0.0, f2p="6/7", p2p="3/3", minutes=9.3,
         failed=["DroppedRockFallsPastCoinsLikeThroughOpenAir"]),
]

data = dict(
    task_hash="supertux__supertux_1398_mm_attempt5_fresh",
    task_id="supertux__supertux_1398_mm",
    title="Some objects misbehave in the forest (task108, Attempt5)",
    rubric="Official V27",
    review_date="2026-11-18",
    date_folder="11_18",
    eyebrow="QC review · fresh, independent run",
    verdict="FAIL",
    verdict_reason=("Only Difficulty fails: with-image pass@4 is 2/4, and Option A needs exactly 1/4. No-image is a correct 0/3. The other 18 dimensions "
                    "pass. Symptom Specificity is a non-fail 3 (the defects other than the carry side are left to the clip). The gate, tests and "
                    "evidence were all verified locally: oracle 1.0, nop 0.0, identical re-run, per-defect isolation, and an alternative fix that scores 10/10."),
    dimensions=dims, gates=gates, trials=trials,
)
assert len(dims) == 19
# exact titles, in order, from the V27 rubric CSV
RUBRIC_TITLES = ["Structure - Task Bundle Files", "Structure - Deliverables & Packaging", "Instruction - Requires the Visual Evidence",
                 "Instruction – Symptom Specificity", "Instruction – Task Type", "Image - Evidence Quality", "Metadata - task_type Accuracy",
                 "Evidence - Chain Consistency", "Golden Fix - Applies Cleanly", "Golden Fix - Source-Only Scope", "Tests - Implementation Overfit",
                 "Tests - f2p/p2p Identifier Validity", "Tests - p2p Classification", "Tests - Discriminating (f2p)", "Tests - Determinism",
                 "Hardening - Difficulty (Model Trial Fails)", "Hardening - Real & Feasible", "Gate - Oracle/Nop", "Unauditable"]
for d_, t_ in zip(dims, RUBRIC_TITLES):
    d_["name"] = t_
(out_dir / "findings.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
print("wrote", out_dir / "findings.json", "| determinism ok:", det_ok)
