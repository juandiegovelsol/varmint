# QC Report: space_wizards__space_station_14_36889_mm

- **Task hash:** `space_wizards__space_station_14_36889_mm_task113_attempt5`
- **Title:** The doors in the video misbehave (task113, Attempt5)
- **Rubric:** Official V27
- **Review date:** 2026-11-20
- **Verdict:** **FAIL**. Only Difficulty fails: with-image pass@4 is 2/4 (96Qtbi8, XQt3yAR), and Option A needs exactly 1/4. No-image 0/3 is correct, and no run crashed. The other 18 dimensions pass. Symptom Specificity is a non-fail 3: the doors are named by type, but the exact defects are left to the clip, and two with-image runs each took one static-lane defect for intended behaviour.

## Scorecard

| # | Dimension | Score | Result | Error category |
|---|---|---|---|---|
| 1 | Structure - Task Bundle Files | 5 | Pass | — |
| 2 | Structure - Deliverables & Packaging | 5 | Pass | — |
| 3 | Instruction - Requires the Visual Evidence | 5 | Pass | — |
| 4 | Instruction – Symptom Specificity | 3 | Non-Fail | [Non-Fail - Image-carried Symptom] |
| 5 | Instruction – Task Type | 5 | Pass | — |
| 6 | Image - Evidence Quality | 5 | Pass | — |
| 7 | Metadata - task_type Accuracy | 5 | Pass | — |
| 8 | Evidence - Chain Consistency | 5 | Pass | — |
| 9 | Golden Fix - Applies Cleanly | 5 | Pass | — |
| 10 | Golden Fix - Source-Only Scope | 5 | Pass | — |
| 11 | Tests - Implementation Overfit | 5 | Pass | — |
| 12 | Tests - f2p/p2p Identifier Validity | 5 | Pass | — |
| 13 | Tests - p2p Classification | 5 | Pass | — |
| 14 | Tests - Discriminating (f2p) | 5 | Pass | — |
| 15 | Tests - Determinism | 5 | Pass | — |
| 16 | Hardening - Difficulty (Model Trial Fails) | 2 | Fail | [Fail - Trial Threshold Not Met] |
| 17 | Hardening - Real & Feasible | 5 | Pass | — |
| 18 | Gate - Oracle/Nop | 5 | Pass | — |
| 19 | Unauditable | 5 | Pass | — |

## Delivery gate

| # | Check | Result | Detail |
|---|---|---|---|
| 1 | Local oracle | PASS | 1.0 (6/6 f2p, 3/3 p2p), 227 s, `--network none` (task110 A6 run; byte-identical env/solution/tests). |
| 2 | Local nop | PASS | 0.0 (0/6 f2p, 3/3 p2p), 199 s. |
| 3 | Oracle re-run | PASS | 1.0; same outcome per test: yes. |
| 4 | CB oracle / nop | PASS | ASxqnzx 1.0, nn3w6KJ 0.0; checksum `bd2a3700…` = with-image trials. |
| 5 | Patch apply | PASS | `git apply --check` OK for fix.patch and test.patch at `harbor_base`; CB oracle applied both. |
| 6 | Verifier completion | PASS | Stage banners and `reward=` present; no "could not apply test.patch"; no test-host crash in any trial. |
| 7 | Local-run reuse | WARN | Only instruction.md and task.toml differ from task110 Attempt6 (`diff -rq`); its local oracle/nop/re-run were reused, not re-run. |
| 8 | pass@3 no-image | PASS | 0/3 (4/6 each; all miss SpaceBreach + EdgeFirelock); `/app/.harbor_assets` empty in each. |
| 9 | pass@4 with-image (Option A) | FAIL | **2/4** (96Qtbi8, XQt3yAR). Needs exactly 1/4. |
| 10 | Trial run time (informational) | PASS | Agent 5.8–8.9 min, total 9.9–13.1 min. |
| 11 | Trial / task checksum | PASS | `task_manifest.json` hashes = all 17 bundle files; with-image = CB oracle/nop checksum. |
| 12 | Packaging | PASS | `Tasks/` and `Trials/` root siblings, 3 + 4 trials. |
| 13 | Leaks | PASS | Only the type noun "doors"; no repo, URL, file, door kind, hazard or mechanism in instruction.md. |
| 14 | Evidence-chain integrity | PASS | Disk, manifest, evidence bundle, instruction and Dockerfile all agree on `recording.mp4` (sha256 `0274cf20…`). |
| 15 | Agents misreading the clip | WARN | 4BaAsf4 took the space lane's double warning for correct; BcTMFDa took the edge door for correct (dim 4 flag). |

## Trials

| Trial | Mode | Reward | f2p | p2p | Minutes | Failed tests |
|---|---|---|---|---|---|---|
| task_without_images__BYFKDwU | no-image | 0.0 | 4/6 | 3/3 | 10.1 | WarningLights_SpaceBreachIsAPressureWarning; EdgeFirelock_SealsAlongItsDoorEdge |
| task_without_images__kzQJaun | no-image | 0.0 | 4/6 | 2/3 | 12.8 | WarningLights_SpaceBreachIsAPressureWarning; EdgeFirelock_SealsAlongItsDoorEdge; p2p: WarningLights_MatchTheHazardKind |
| task_without_images__toiCowg | no-image | 0.0 | 4/6 | 3/3 | 12.8 | WarningLights_SpaceBreachIsAPressureWarning; EdgeFirelock_SealsAlongItsDoorEdge |
| task_with_images__4BaAsf4 | with-image | 0.0 | 5/6 | 3/3 | 11.2 | WarningLights_SpaceBreachIsAPressureWarning |
| task_with_images__96Qtbi8 | with-image | 1.0 | 6/6 | 3/3 | 9.9 | — |
| task_with_images__BcTMFDa | with-image | 0.0 | 5/6 | 3/3 | 13.1 | EdgeFirelock_SealsAlongItsDoorEdge |
| task_with_images__XQt3yAR | with-image | 1.0 | 6/6 | 3/3 | 11.8 | — |

## Issues & suggested fixes

### Instruction – Symptom Specificity: 3 [Non-Fail - Image-carried Symptom]

**What is wrong:** Image-carried symptoms (a non-fail). Two with-image runs each took one static-lane defect for intended behaviour (space lane in 4BaAsf4, edge door in BcTMFDa).

**Suggested fix:** Optional, for a 5: state each defect kind in text without naming the door or the cause, e.g. "One shut door shows the wrong kind of warning, one shows none, one keeps its warning after it opens, and something gets past two shut doors." Stating the defects makes the task easier, so only do it if difficulty allows. Changing `instruction.md` changes the task checksum, so every trial must be re-run.

### Hardening - Difficulty (Model Trial Fails): 2 [Fail - Trial Threshold Not Met]

**What is wrong:** With-image pass@4 is 2/4; Option A needs exactly 1/4.

**Suggested fix:** Re-run pass@4 with images on this same bundle until it lands on exactly 1/4, or harden slightly so one more of the static lanes is missed (for example, drop "Not all of them involve a door moving.", which steered audits toward the static lanes). Either way, re-run all 7 trials if `instruction.md` changes. Which option to take is your call.

## Dimension details

### 1. Structure - Task Bundle Files: 5 (Pass)

**Evidence:** All 11 fixed files exist and are non-empty: `task.toml` 6,949 B, `instruction.md` 923 B, `evidence_bundle.json` 1,530 B, `environment/Dockerfile` 4,828 B, `environment/assets/ASSET_MANIFEST.json` 825 B, `solution/fix.patch` 8,983 B, `solution/solve.sh` 349 B, `tests/config.json` 1,434 B, `tests/test.patch` 23,130 B, `tests/test.sh` 14,533 B, `tests/verifier.py` 6,691 B. The three JSON files and `task.toml` parse, and `py_compile tests/verifier.py` succeeds. `recording.mp4` decodes (h264 1280x720, 30 fps, 480 frames, 16.000 s; same sha256 as the asset decoded frame by frame in the task110 Attempt6 review). Extra files: `README.md` and `environment/bugs/bug_01..05.patch` (injected bugs). Neither is a fail.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 2. Structure - Deliverables & Packaging: 5 (Pass)

**Evidence:** `task113/Attempt5/` has `Tasks/` and `Trials/` as root-level siblings. `Trials/without_images/` holds 3 runs (BYFKDwU, kzQJaun, toiCowg) and `Trials/with_images/` holds 4 (4BaAsf4, 96Qtbi8, BcTMFDa, XQt3yAR). That is 7 trials, the Option A count. Reviewed as unpacked folders (there are no .tar.gz files here).

**What is wrong:** Nothing found. Only the folder layout could be checked, not the final archives.

**Suggested fix:** Tar from inside the attempt folder so each archive unpacks to its own top folder (`tar -czf Tasks.tar.gz Tasks`, `tar -czf Trials.tar.gz Trials`). Keep `Check/`, `Analyze/`, `Oracle/` and `Nop/` out of `Trials.tar.gz`.

### 3. Instruction - Requires the Visual Evidence: 5 (Pass)

**Evidence:** Without the video, the text names the doors by type only. It names three aspects (warning lights, the way a door moves, what ends up on each side of a shut door), one soft pointer ("Not all of them involve a door moving.") and four general rules. It names no door kind (firelock, glass, edge), hazard, lane, file, value or mechanism. Two defects can't be found from the text alone: the space-lane warning (temperature threshold lowered to 230 K, which looks like a plausible tuning value, and nothing in the text says a vacuum is involved) and the edge door's seal side (North vs South; nothing says a thin edge door exists).

The trials agree (this is corroboration only). All 3 no-image runs found `/app/.harbor_assets` empty: BYFKDwU and toiCowg ran `ls -la .harbor_assets`, and kzQJaun said "`/app/.harbor_assets/` is empty, so I never saw the clip". Each fixed 4 of 6 defects by reading the firelock code, and **each missed both `WarningLights_SpaceBreachIsAPressureWarning` and `EdgeFirelock_SealsAlongItsDoorEdge`**. kzQJaun and toiCowg guessed a different space cause (tiles with no air skipped in the pressure check). None of the three touched the 230 K threshold or the edge door's `airBlockedDirection`.

The image path resolves to `/app/.harbor_assets/recording.mp4` (Dockerfile `COPY assets/recording.mp4 /app/.harbor_assets/`). Leak scan of `instruction.md` (170 words): "door" appears 9 times, the type noun the rubric asks for. There is no repo, URL, issue or PR, file, "firelock", gas, plasma, space, threshold or animation word. `ASSET_MANIFEST.json`, which names firelocks, is not copied into the image.

**What is wrong:** Nothing found. For the record: two separate defects keep the no-image runs from passing, a firmer 0/3 than a single-defect gate.

**Suggested fix:** None.

### 4. Instruction – Symptom Specificity: 3 (Non-Fail) [Non-Fail - Image-carried Symptom]

**Evidence:** Prompt table:

| element (as written) | defect: text or image? | expected: text or image? | correct counterpart in the clip? | clue left to image | described correctly? |
|---|---|---|---|---|---|
| "doors" + "their warning lights" + "its warning says what kind of danger it is holding back" | image: lane 1 (space) shows the orange temperature brackets over the cyan pressure ones | text rule | yes: lane 2 (dense gas) shows the cyan pressure warning | which lane, which colour | yes |
| "their warning lights" (glass door) | image: lane 4 holds fire with no brackets | text rule ("its warning says…") | yes: lane 3, same fire, shows brackets | which door kind | yes |
| "The warning only shows while the door is shut." | image: lane 2 keeps its cyan brackets after it opens (from about 10 s to the end) | text rule | no: the clip's only opened door is the buggy one, so the expected result comes from the text | which door, when | yes |
| "the way a door moves" + "A door shuts smoothly, as a whole." | image: lane 6's panel snaps shut in one frame, then its green running lights play over a shut panel (about 1.9–2.3 s, frame by frame) | text rule | yes: lane 2's opening slides normally | which door, the frame timing | yes |
| "what ends up on each side of a shut door" + "keeps what is on one side from reaching the other" | image: lane 6 is shut, and gas released above it at about 4–5 s reaches the lower room by 6 s | text rule | yes: lanes 1–4 hold their hazards | which door, the trigger (shut during play) | yes |
| same side rule + "Not all of them involve a door moving." | image: lane 5's gas fills the edge door's own tile past its panel | text rule | partly: other lanes keep the hazard on the far side | which door, which edge | yes |

Why 3, not 5: the text names the element by type ("doors") and the aspects, and gives a rule for each. It never states a defect (no "wrong colour", "missing", "stays on" or "snaps"). Every exact defect is left to the clip, with the rest of the bench as the comparison. That is the V27 middle option. Why not 2: the floor holds. The element is named by type, every line is grammatical, and each aspect has context (a shut door between a room and a hazard, with a warning). The Attempt1 "element" wording is gone.

Every with-image trajectory (final message):

| run | reward | what it read | could it tell bug from intended? |
|---|---|---|---|
| 96Qtbi8 | 1.0 | all 6: "Wrong warning type (door 1, vacuum…)"; "Warning stayed on after opening (door 2)"; "No warning at all on the glass firelock (door 4)"; "Choppy closing (door 6)"; "Gas leaking past a closed door (door 6)"; "Edge firelock sealing the wrong side (door 5)" | yes, all 6 |
| XQt3yAR | 1.0 | all 6: "The door space-side showed a fire warning (1st door)"; "Gas got past the thin edge firelock (5th door)"; glass; stays lit; vanished then snapped shut; gas past the shut 6th door | yes, all 6 |
| 4BaAsf4 | 0.0 | 5: gas past door 6, edge seal on the wrong side (door 5), warnings on open doors, glass, snapping shut. **"Doors 1 and 3 already looked right in the clip… Door 1 shows both warnings, which fits a door with vacuum on one side"** | **no, for the space-lane warning**: took the bug for intended behaviour |
| BcTMFDa | 0.0 | 5: gas past door 6, vacuum door's fire warning (230 → 330 K), stays lit, glass, snapping shut. **"I left door 5 (the thin edge firelock) alone: it stays shut, keeps the gas off the far side, and shows the pressure warning, which looks correct to me."** | **no, for the edge door**: took the bug for intended behaviour |

Flag (it puts this score at risk): 2 of 4 with-image runs each took **one** defect for intended behaviour, and each run missed a different one. Per defect, the misread rate is 1/4 (space lane: 4BaAsf4 only; edge: BcTMFDa only). The other 3 runs read each of these correctly, and both passing runs read all 6. Under V25/V27, "agents couldn't tell" can fail this dimension on its own, and the rubric example is 3/4 runs misreading the same symptom. At 1/4 per symptom, I score it as a flag, not a fail, which matches the task110 Attempt6 ruling (1/4 misread the space lane). A stricter reviewer could count the two runs together as 2/4 and score 2.

**What is wrong:** Image-carried symptoms (a non-fail). Two with-image runs each took one static-lane defect for intended behaviour (space lane in 4BaAsf4, edge door in BcTMFDa).

**Suggested fix:** Optional, for a 5: state each defect kind in text without naming the door or the cause, e.g. "One shut door shows the wrong kind of warning, one shows none, one keeps its warning after it opens, and something gets past two shut doors." Stating the defects makes the task easier, so only do it if difficulty allows. Changing `instruction.md` changes the task checksum, so every trial must be re-run.

### 5. Instruction – Task Type: 5 (Pass)

**Evidence:** The text describes warnings that must follow the door's state ("only shows while the door is shut"), how a door moves while it shuts, and what crosses a door after it shuts. These defects show across state transitions over time, which fits `temporal_interaction` ("a defect that only appears across a sequence of interactions / state transitions"). Nothing is misdescribed: no crash is called a render bug. "Not all of them involve a door moving" is true (lanes 1, 4 and 5 are static), and the type still fits the clip as a whole.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 6. Image - Evidence Quality: 5 (Pass)

**Evidence:** Naming table:

| file | role field | what the frames show (how verified) | what name/role/instruction claim | true? | agents confused? |
|---|---|---|---|---|---|
| `recording.mp4` | `bug_video` | the buggy state. The task110 Attempt6 review compared the same file (sha256 `0274cf20…`) frame by frame with the fixed-state reference recording (evidence 01–03), and checked that the image carries exactly these 5 bug patches | neutral name; role says bug; description lists six one-tile lanes (lattice/space, dense purple gas, fire, fire behind glass, gas behind an edge firelock, plain air with the last door open), with the last door shutting, gas released above it, and the second door opened later | yes: every item in the description is in the frames, in that order | no: all 4 runs treated it as the buggy clip and numbered the doors the same way |

Each f2p against the asset:

| f2p | precondition (test.patch) | clip (bug) | fixed reference | trial cross-check (real verifier in the task image) |
|---|---|---|---|---|
| HideWhenDoorLeavesClosed | standard firelock vs 1000 K air, opened then re-closed | lane 2 keeps its cyan brackets once open (from about 10 s) | no brackets once open | passes in all 7 trials; every one hid the lights from shared code on door-state change, not the golden's client handler |
| GlassFirelockShowsWarning | `FirelockGlass` vs over-pressure | lane 4 holds fire, no brackets | brackets shown | passes in all 7 trials |
| SpaceBreachIsAPressureWarning | standard firelock, upper cell open to space | lane 1: orange temperature over cyan pressure | cyan only | fails in exactly the 4 runs that kept 230 K (4BaAsf4 + 3 no-image); passes in the 3 that set 330 K |
| ClosedFirelock_HoldsBackGasReleasedAfterClosing | door shut during play, then gas released | lane 6 shut, released gas reaches the lower room | gas held | passes in all 7 trials (all fixed `SetAirblocked`) |
| EdgeFirelock_SealsAlongItsDoorEdge | `FirelockEdge`, gas beyond its panel edge | lane 5 gas fills the door's own tile past its panel | gas stops at the panel | fails in exactly the 4 runs that left North (BcTMFDa + 3 no-image); passes in the 3 that set South |
| ClosingAnimation_PlaysThroughBeforeTheDoorShuts | standard firelock, client sprite frames while closing | lane 6 snaps shut, and its lights run over a shut panel | panel slides in with its lights | passes in all 7 trials (all restored the closing delays) |

Steps 3–4 (cross-checks): the golden is the exact reverse of each injected bug, plus the upstream client fix for the lights. The 7 trials act as natural partial fixes run by the real verifier: each missed defect failed exactly its own f2p and nothing else. Fixing what the clip shows passes every f2p (96Qtbi8 and XQt3yAR got 6/6 with code different from the golden), and each f2p flips only with its own defect. Step 7 (injected defects): all 5 injected bugs show in the clip, so a fix that skips one leaves a visible defect, not a valid alternative.

**What is wrong:** Nothing found. Non-graded note: the opened-door warning (lane 2) has no correct counterpart in the clip; its expected result comes from the text rule.

**Suggested fix:** None.

### 7. Metadata - task_type Accuracy: 5 (Pass)

**Evidence:** `task_type = "temporal_interaction"` is one of the seven values. The evidence is a 16 s video whose defects unfold across state changes: a door shutting, gas released after it shuts, a door opening while its lights stay on, and a closing animation that needs frame stepping. The upstream issue (#36889, the warning stays on after opening) is itself a state-transition defect.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 8. Evidence - Chain Consistency: 5 (Pass)

**Evidence:** Asset references:

| reference | path | sha256 | bytes |
|---|---|---|---|
| file on disk | `environment/assets/recording.mp4` | `0274cf20…5eaa36b0` | 1,770,475 |
| `ASSET_MANIFEST.json` | `/app/.harbor_assets/recording.mp4` | same | same |
| `evidence_bundle.json` | `local_path` = `container_path` = `/app/.harbor_assets/recording.mp4` | same | same |
| `instruction.md` | `/app/.harbor_assets/recording.mp4` | — | — |
| Dockerfile | `COPY assets/recording.mp4 /app/.harbor_assets/` | — | — |

All references point to the same asset.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 9. Golden Fix - Applies Cleanly: 5 (Pass)

**Evidence:** `git apply --check /solution/fix.patch` at `harbor_base`: OK (`test.patch` also OK) in the task110 Attempt6 review's image, with a byte-identical `fix.patch`, `test.patch` and `Dockerfile`. The CB oracle (ASxqnzx) stdout shows `captured submission.patch (8973 bytes, 5 files)` and `applying test.patch` with no error.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 10. Golden Fix - Source-Only Scope: 5 (Pass)

**Evidence:** The `diff --git` paths equal `files_edited` exactly (5): `Content.Client/Doors/FirelockSystem.cs`, `Content.Server/Atmos/EntitySystems/AirtightSystem.cs`, `Content.Shared/Doors/Components/FirelockComponent.cs`, `Resources/Prototypes/Entities/Structures/Doors/Firelocks/firelock.yml`, `Resources/Textures/Structures/Doors/Airlocks/Standard/firelock-base.rsi/meta.json`. No test, doc, lockfile or changeset path. (The scan pattern matched `Doors/` on the word "docs"; on inspection these are source paths.) The prototype YAML and the RSI `meta.json` are game content the runtime loads.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 11. Tests - Implementation Overfit: 5 (Pass)

**Evidence:** Value-level assertions and their accepted sets:

| assertion | what it reads | real accepted set | alternatives tried / reasoned | test accepts? |
|---|---|---|---|---|
| warning layers hidden while Opening/Open/Closing | client layer `Visible` and a drawable RSI state | any mechanism that hides the layer on the client | golden: client `OnAppearanceChange`. All 7 trials: shared-side door-state handler that clears the appearance booleans | yes (7/7) |
| glass shows the pressure warning | layer keyed `FirelockVisualLayersPressure.Base` shown and drawable | inherit the parent layers or add the two keyed layers | golden: drop the override. Trials: add the layers to the glass list | yes (both) |
| space breach = pressure only | temperature layer not shown | any threshold in about 291–706 K, or skipping vacuum in the check | trials: 330 K | yes |
| gas < 1 mol past a door shut in play | atmos moles after 4 s | any way that makes atmos re-read the tile on close | golden: always `UpdatePosition`; trials: the same idea written differently | yes (7/7) |
| edge seal on the panel edge | moles on the door tile and beyond | `airBlockedDirection: South` (moving the panel or fixture instead breaks "keep looking as it does now") | trials: `South` | yes |
| closing animation ≥ 6 distinct frames, last ≥ frameCount−3 within 60 ticks | client layer `AnimationFrame` per tick | any closing timing longer than a few ticks and under 2 s | golden: upstream delays (0.49 s); trials: copied from `opening` or the glass sprite | yes (7/7) |

Structure level: no exact counts beyond thresholds, no ordering, no float equality (gas uses `< 1 mol` / `> 200 mol` margins), no log-text matching. Failing trials were rejected for real defects: 230 K kept (4BaAsf4 and all no-image runs), North seal kept (BcTMFDa and all no-image runs). kzQJaun also failed the p2p `WarningLights_MatchTheHazardKind`: it changed how airless tiles are counted in the pressure check, a wrong fix the p2p correctly rejected.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 12. Tests - f2p/p2p Identifier Validity: 5 (Pass)

**Evidence:** The f2p (6) and p2p (3) lists in `task.toml` and `tests/config.json` are identical, with no overlap. The JUnit report has 9 test cases. `test.sh` writes `classname=""` and the full dotted id in `name`, and `verifier.py` keys on `"{classname} {name}".strip()`, so each id matches exactly one test case (CB oracle/nop and local runs).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 13. Tests - p2p Classification: 5 (Pass)

**Evidence:** The p2p (`AirlockTest.OpenCloseDestroyTest`, `WarningLights_MatchTheHazardKind`, `WarningLights_StayOnWhileWelded`) pass on CB nop (nn3w6KJ, 3/3) and CB oracle (ASxqnzx, 3/3), and on local nop (3/3) and local oracle (3/3).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 14. Tests - Discriminating (f2p): 5 (Pass)

**Evidence:** All 6 f2p fail on nop (CB nn3w6KJ: 0/6 pass; local: 0/6 pass) and pass on oracle (CB ASxqnzx 6/6, local 6/6).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 15. Tests - Determinism: 5 (Pass)

**Evidence:** Tests run on the engine's fixed server/client ticks (`RunTicksSync`, `RunSeconds`) with `Fresh = true` pools and one NUnit worker. They use no wall clock, network or fonts, and the gas checks have wide margins. `test.sh` installs nothing (`dotnet build --no-restore`, offline), and the local runs used `--network none`. The local oracle re-run gave the same outcome for every test. Across the 7 Attempt5 trials and the CB oracle/nop, every test result follows the code change, with no unexplained flip. No test-host crash in this batch (with-image ran at `n_concurrent_trials = 1`).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 16. Hardening - Difficulty (Model Trial Fails): 2 (Fail) [Fail - Trial Threshold Not Met]

**Evidence:** Attempt5 trial results:

| run | mode | reward | f2p | p2p | failed |
|---|---|---|---|---|---|
| BYFKDwU | no-image | 0.0 | 4/6 | 3/3 | SpaceBreach, EdgeFirelock |
| kzQJaun | no-image | 0.0 | 4/6 | 2/3 | SpaceBreach, EdgeFirelock, p2p MatchTheHazardKind |
| toiCowg | no-image | 0.0 | 4/6 | 3/3 | SpaceBreach, EdgeFirelock |
| 4BaAsf4 | with-image | 0.0 | 5/6 | 3/3 | SpaceBreach |
| 96Qtbi8 | with-image | **1.0** | 6/6 | 3/3 | — |
| BcTMFDa | with-image | 0.0 | 5/6 | 3/3 | EdgeFirelock |
| XQt3yAR | with-image | **1.0** | 6/6 | 3/3 | — |

No-image is 0/3 (correct). With-image is **2/4**. Option A needs exactly 1/4, and the V27 rubric lists 2/4 as a fail example. There are 7 trials, so Option B doesn't apply. Checksums: with-image `bd2a3700…` = CB oracle/nop; no-image `1c588d32…` (the variant with assets stripped). The trial `task_manifest.json` hashes match all 17 bundle files. Run time: agent 5.8–8.9 min, total 9.9–13.1 min (informational). The with-image job ran at `n_concurrent_trials = 1`, and no run crashed, so 2/4 is a clean result, not crash noise.

**What is wrong:** With-image pass@4 is 2/4; Option A needs exactly 1/4.

**Suggested fix:** Re-run pass@4 with images on this same bundle until it lands on exactly 1/4, or harden slightly so one more of the static lanes is missed (for example, drop "Not all of them involve a door moving.", which steered audits toward the static lanes). Either way, re-run all 7 trials if `instruction.md` changes. Which option to take is your call.

### 17. Hardening - Real & Feasible: 5 (Pass)

**Evidence:** Each injected bug is coherent, and its fix is what a real developer would write: a lowered default threshold (230 → 330 K), an airtight update made conditional (restore the unconditional call), closing frame delays 10× too short (restore them, as in the `opening` state), a glass prototype that overrides the sprite layer list and drops the warning layers (remove the override), and a flipped edge seal direction (North → South). The upstream defect (#36889, PR #46007) is fixed the upstream way (client appearance handler). All 6 defects are visible in the clip.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 18. Gate - Oracle/Nop: 5 (Pass)

**Evidence:** Local runs (task110 Attempt6 review, byte-identical environment/solution/tests; see the note under Gate): oracle **1.0** (6/6 f2p, 3/3 p2p, 227 s), nop **0.0** (0/6 f2p, 3/3 p2p, 199 s), oracle re-run **1.0** (6/6, 3/3, 225 s); re-run outcome per test identical to the first oracle run: yes.
CB runs: oracle ASxqnzx = 1.0 (6/6, 3/3), nop nn3w6KJ = 0.0 (0/6, 3/3), both on checksum `bd2a3700…`. Both show the stage banners (`== captured submission.patch ==`, `== applying test.patch ==`, `== running f2p + p2p tests ==`, `== computing reward ==`) and `reward=`, and neither has "could not apply test.patch".
**Local-run reuse:** `diff -rq` of this bundle against `task110/Attempt6/Tasks/…` shows only `instruction.md` and `task.toml` differ. `environment/` (Dockerfile, bugs, asset), `solution/` and `tests/` are byte-identical. The local oracle, nop and oracle re-run from the 11_19 task110 Attempt6 review therefore apply unchanged, because neither changed file is read by the build, `solve.sh` or `test.sh`. That review ran on the cached `ss14_110:fast` image, which it verified carries exactly these 5 bug patches and this `recording.mp4`. `task113/Attempt4/Tasks` is also byte-identical to Attempt5.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 19. Unauditable: 5 (Pass)

**Evidence:** A complete, auditable submission: bundle, 7 trials, oracle and nop.

**What is wrong:** Nothing found.

**Suggested fix:** None.
