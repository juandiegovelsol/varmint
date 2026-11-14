# QC Report: epam__ai_dial_admin_frontend_5175_mm

- **Task hash:** `6ae8aa650378b9290c6db56c`
- **Title:** Problem in the top rows (epam/ai-dial-admin-frontend #5175, design_reference)
- **Rubric:** Official V27 (6a676431c4ebbc30851d6f10-V27_removing_misaligned_task_type_redundancy)
- **Review date:** 2026-11-13
- **Verdict:** **PASS**. All 19 dimensions score 5. Local oracle 1.0 (twice, identical), nop 0.0 with 0/6 f2p and 158/158 p2p, fix.patch applies at harbor_base, every shipped run's harbor digest matches the current bundle, and trials meet Option A (0/3 no-image, 1/4 with-image). Overfit probes: valid alternative fixes pass; all trial failures are genuine misses of defects visible in the evidence.

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
| 1 | Local oracle | PASS | reward 1.0, f2p 6/6, p2p 158/158 (harbor 0.18.0, docker) |
| 2 | Local nop | PASS | reward 0.0, f2p 0/6, p2p 158/158 |
| 3 | Oracle re-run (idempotent) | PASS | 1.0, identical per-test detail |
| 4 | fix.patch applies at harbor_base | PASS | git apply --check OK in built image |
| 5 | Verifier completion | PASS | stage banners + reward= in all runs; test.patch applied |
| 6 | pass@3 no-image | PASS | 0/3 (f2p 3/6, 4/6, 1/6); assets dir empty in all three |
| 7 | pass@4 with-image | PASS | exactly 1/4 (VwBbefV) |
| 8 | Trial run time (informational) | PASS | 9.3–18.6 min per attempt |
| 9 | Trial/task checksum | PASS | Oracle, Nop, with_images = acc44f2c…; without_images = af6512ab… (stripped copy of current bundle) |
| 10 | Packaging | WARN | Received as folders; reviewer created the tar.gz archives. Layout Tasks/ + Trials/ is correct |
| 11 | Leaks | PASS | no repo/file/component/mechanism in instruction; manifest not shipped; tests/solution not in image; history squashed, timestamps normalized |
| 12 | Evidence-chain integrity | PASS | files, manifest, evidence_bundle, instruction refs and Dockerfile COPY agree (sha256 + bytes) |
| 13 | Local network deviation | WARN | [agent] no-network relaxed in reviewer copy only (host kernel lacks nft fib inet); no effect on oracle/nop |

## Trials

| Trial | Mode | Reward | f2p | p2p | Minutes | Failed tests |
|---|---|---|---|---|---|---|
| task_without_images__A8VBbry | no-image | 0.0 | 3/6 | 158/158 | 9.3 | X every column header sentence-case; X numeric headers right-aligned; C Test Case name/Delta sentence-case |
| task_without_images__BNTsYWK | no-image | 0.0 | 4/6 | 158/158 | 10.9 | X every column header sentence-case; C Test Case name/Delta sentence-case |
| task_without_images__bztzCeS | no-image | 0.0 | 1/6 | 157/158 | 10.3 | X sentence-case; X numeric right; X group labels; C sentence-case; C group labels; p2p CompareRunIndexHeader centers badge-only |
| task_with_images__AaKCc7L | with-image | 0.0 | 5/6 | 158/158 | 12.5 | X numeric headers right-aligned (exact_match, all-empty metric) |
| task_with_images__KZULBK3 | with-image | 0.0 | 3/6 | 158/158 | 18.6 | X sentence-case (Test Case name uppercase); C sentence-case; C group rows height (28px kept) |
| task_with_images__VwBbefV | with-image | 1.0 | 6/6 | 158/158 | 12.1 | — |
| task_with_images__Wy9KgVD | with-image | 0.0 | 3/6 | 158/158 | 11.9 | X sentence-case (Test Case name uppercase); X numeric right ('score'); C sentence-case |

## Issues & suggested fixes

## Dimension details

### 1. Structure – Task Bundle Files: 5 (Pass)

**Evidence:** All 11 fixed files present and non-empty (instruction.md 1299 B, task.toml 20831 B, evidence_bundle.json 2258 B, Dockerfile 1778 B, ASSET_MANIFEST.json 850 B, fix.patch 12341 B, solve.sh 349 B, test.sh 10291 B, verifier.py 6919 B, config.json 17294 B, test.patch 40678 B). All three JSON files parse (UTF-8). `py_compile` of verifier.py inside the task image: OK; `bash -n tests/test.sh`: OK. current.png = PNG 1849x350 RGB, mockup.png = PNG 1833x689 RGBA, both decode. Extra `environment/bugs/` (bug_01.patch, bug_02.patch) is the injected-bug folder, not a fail.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 2. Structure – Deliverables & Packaging: 5 (Pass)

**Evidence:** Submission was handed over as unpacked folders (Tasks/, Trials/, Oracle/, Nop/, Check/, Analyze/); the reviewer packaged each into <name>.tar.gz under QC_Review/11_13/6ae8aa650378b9290c6db56c/. `Tasks/` (capital T) and `Trials/` are root-level siblings; Tasks/ holds one task folder. Trials/without_images has 3 attempts and Trials/with_images has 4 (7 total, Option A).

**What is wrong:** Nothing found. Note: archive names could not be judged because folders, not archives, were provided.

**Suggested fix:** When submitting, ship Tasks.tar.gz and Trials.tar.gz that unpack to `Tasks/` and `Trials/`.

### 3. Instruction – Requires Visual Evidence: 5 (Pass)

**Evidence:** Both image refs resolve to `/app/.harbor_assets/current.png` and `/app/.harbor_assets/mockup.png`, and the text points to each by name. With images set aside, the text does not say which table(s), which labels are wrong, the target letter case/spacing/size/weight, or which columns count as numeric; all of that is only in the images ("same size, weight, letter case and letter spacing as in `mockup.png`"). No leak: no repo, file, component, ag-grid, CSS class or mechanism is named. All 3 no-image trials failed (f2p 3/6, 4/6, 1/6); each trajectory shows `/app/.harbor_assets/` empty (`ls -la` output, Read -> "File does not exist").

**What is wrong:** Nothing found. Non-graded: the text alone let no-image agents fix group weight and row spacing (C-height passed in 3/3 no-image runs, group-label f2p in 2/3), so the image carries the letter-case, size and alignment parts.

**Suggested fix:** None.

### 4. Instruction – Symptom Specificity: 5 (Pass)

**Evidence:** element | defect | expected | comparison image | clue left to image | described correctly? — "labels" in "the outlined rows at the top of the table" ("column labels and group labels alike") | text: "inconsistent in size, positioning, weight or typography" | text: same size/weight/letter case/letter spacing as mockup; numeric/score labels at the right edge like the values; other labels left; rows evenly spaced | `mockup.png` ("should look like `mockup.png`") | which labels are uppercase or misaligned, the target values, which group labels are lighter, the 28px group row | yes. Trajectories (all 4 with-image runs): every agent read the same symptom (mixed uppercase/size, SCORE/EXACT_MATCH left of right-aligned values, lighter metric group labels, uneven compare-grid rows). None took the bug for intended behavior. Failures were incomplete fixes: Wy9KgVD and KZULBK3 assumed EllipsisHeader was already sentence case; AaKCc7L right-aligned only metrics with some value.

**What is wrong:** Nothing found. Non-graded: "It should look and work correctly." is boilerplate, and the defect phrase is an "or" list; both are acceptable because context and bullets follow immediately.

**Suggested fix:** None.

### 5. Instruction – Task Type: 5 (Pass)

**Evidence:** task_type = "design_reference" (Guidelines Step IV: design mockup + current-state screenshot; "edit the code so the rendered output matches the reference design"). The instruction asks for the header rows to look like `mockup.png` and points to `current.png` as the current state.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 6. Image – Evidence Quality: 5 (Pass)

**Evidence:** Naming table — file | role | what frames show (how verified) | claim | true? | agents confused? — current.png | current_state | buggy header: 'TEST CASE NAME'/'TOTAL TURNS'/'HTTP'/'DURATION' 10px uppercase; '# RUN NUM…'/'SCORE'/'EXACT_MATCH'/'ANSWER' 14px uppercase; 'Total req…' sentence case; SCORE/EXACT_MATCH labels left over right-aligned values; 'DeepEval…'/'Exact Match' groups lighter than 'Execution'/'Extracted'. Verified against the local nop failure messages: Test Case name {10px, 600, uppercase, .06em}; 'score' not right-aligned; 'DeepEval: Answer Relevancy' {14px, 400} | current state of the run results table | true | no. mockup.png | design_mockup | Run Comparison 'Execution Results' grid with sentence-case semibold labels, right-aligned numeric labels, header rows at 40px intervals (y≈91/131/171). It is the reporter's post-fix verification comment image on upstream issue #5175 (asset id 09d22110…) | reference look, same kind of table on another page | true | no. f2p mapping (steps 1–4): X-case, X-right, X-group = defects pictured in current.png; C-case, C-group, C-height = the compare grid, which the instruction says must also look like mockup.png. Probes in the task image: extraction-only part of golden -> X-case/X-right/X-group/C-group pass, C-case and C-height fail (those need the compare-grid part motivated by mockup.png + text); reverting only the injected bugs -> X-right, X-group, C-group pass, X-case/C-case/C-height fail; golden -> all pass. Step 7: bug_01 (metric header alignment taken from the first sample) is pictured (SCORE/EXACT_MATCH left, EXACT_MATCH all dashes), so a fix that skips it, or one that only prefers a non-null sample, leaves the pictured defect. Complete fix? no (trial AaKCc7L proves it). bug_02 (regular-weight group labels) is pictured as the lighter metric group labels.

**What is wrong:** Nothing found. Non-graded: evidence_bundle.json calls mockup.png "the existing, correctly styled sibling grid"; it is the post-fix verification screenshot, and at base the compare grid still has 28px group rows and an uppercase Test Case name. The agent-facing text is accurate. The compare grid's base state is not pictured (only its target); this is acceptable under V27.

**Suggested fix:** Optional: reword the mockup.png description in evidence_bundle.json to "post-fix Run Comparison grid (upstream verification screenshot)".

### 7. Metadata – task_type: 5 (Pass)

**Evidence:** "design_reference" is one of the seven values and fits the images: a design/reference screenshot (mockup.png) plus a current-state screenshot (current.png).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 8. Evidence – Chain Consistency: 5 (Pass)

**Evidence:** On disk: current.png 36666 B sha256 2c52a812…a95da; mockup.png 84717 B sha256 4b11c662…85271. ASSET_MANIFEST.json and evidence_bundle.json list identical file/bytes/sha256, and `local_path`/`container_path` are `/app/.harbor_assets/<file>`. instruction.md refs `/app/.harbor_assets/current.png` and `/app/.harbor_assets/mockup.png`. Dockerfile: `COPY assets/current.png assets/mockup.png /app/.harbor_assets/` (images only; the manifest is not shipped).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 9. Golden Fix – Applies Cleanly: 5 (Pass)

**Evidence:** In the built task image at `harbor_base` (`git describe` = harbor_base; only `?? .harbor_assets/` untracked): `git apply --check /p/fix.patch` -> FIX_APPLY_CHECK_OK. Local oracle log: "captured submission.patch (12341 bytes, 7 files)".

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 10. Golden Fix – Source-Only Scope: 5 (Pass)

**Evidence:** The 7 `diff --git` paths in fix.patch equal task.toml `files_edited` exactly (set compare: equal, symmetric difference empty): EllipsisHeader.tsx, EllipsisHeaderGroup.tsx, ExecutionResultsTab.tsx, ExecutionResults/constants.ts, ExecutionResults/utils/columns.ts, Runs/View/utils.ts, Runs/grid-column-layout.ts. All are .ts/.tsx source; no tests, docs, lockfiles or changesets; no overlap with test.patch.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 11. Tests – Implementation Overfit: 5 (Pass)

**Evidence:** Assertions read the computed look under the real stylesheet (ui-kit CSS + app global.scss via Sass + Tailwind, cascade with layers/specificity/inline/var()), not class names. Accepted sets: size 13–15px, weight 500–700, text-transform none/unset, letter-spacing normal or ≤0.2px/≤0.0125em; right alignment via the label row's justify-content/direction or the label's text-align/justify. Probe table (value | valid in repo | renders same | test accepts): golden `normal-case tracking-normal` | yes | yes | yes. Global SCSS `.dial-kit-grid .ag-header .ag-header-cell-text {text-transform:none; letter-spacing:normal}` instead of utilities | yes | yes | yes. `!normal-case !tracking-normal` | yes | yes | yes. `groupHeaderHeight: 40` instead of removing the override | yes | yes | yes. ag-grid `type: 'rightAligned'` instead of `...rightAlignedColumn` on metric columns | yes | yes | yes. Global rule `.ag-header .ag-header-cell-text {…}` (specificity 0,2,0) | NO: the kit's `.dial-kit-grid .ag-header .ag-header-cell-text` (0,3,0) wins in a browser too, so labels stay uppercase | — | rejected correctly. Trial cross-check: every failing f2p in the 6 failing trials is a real miss: Test Case name still uppercase/.06em (no case undo), 'score' left (bug_01 not fixed), 'exact_match' left (non-null-sample shallow fix; the column is all dashes in current.png), and 28px group rows kept (KZULBK3). `columnRowHeight === '40px'` is pinned by the mockup (header rows at 40px intervals, same as the existing 40px column row). Text-left and Delta-right guards are p2p and pass on base.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 12. Tests – f2p/p2p Identifier Validity: 5 (Pass)

**Evidence:** task.toml and tests/config.json f2p (6) and p2p (158) lists are identical (UTF-8 compare). Against the local oracle JUnit (166 testcases, no duplicate names), each of the 164 IDs matches exactly one testcase name, and verifier.py's own `resolve` returns pass for all of them.

**What is wrong:** Nothing found. Non-graded: 2 tests in EllipsisHeader.spec.tsx ('EllipsisHeader alignment > …') run but are in neither list; both pass on oracle.

**Suggested fix:** Optional: add the two EllipsisHeader alignment tests to p2p or drop the file from run_tests.

### 13. Tests – p2p Classification: 5 (Pass)

**Evidence:** Local nop (harbor 0.18.0): p2p 158/158 pass. Local oracle and re-run: 158/158 pass. Matches the CB's Nop/Oracle reward_detail.json.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 14. Tests – Discriminating (f2p): 5 (Pass)

**Evidence:** Local nop: all 6 f2p fail (reward 0.0, f2p 0/6). Local oracle: 6/6 pass. Base-image probe failure messages: Test Case name {10px, 600, uppercase, .06em}; 'score' header not right-aligned; 'DeepEval: Answer Relevancy' {14px, 400}; 'Accuracy' {14px, 400}; group rows ≠ 40px.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 15. Tests – Determinism: 5 (Pass)

**Evidence:** jsdom + vitest with fixed fixtures, no timers, animation, network or font measurement (widths stubbed to 4000; the stylesheet is compiled from repo files). test.sh installs nothing (deps come from `npm ci` at build time), so no network is needed at grading ([verifier] network_mode = "public" is harmless). Oracle run 1 and re-run: identical reward 1.0 and identical per-test detail (6/6, 158/158). The CB's sandbox oracle agrees.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 16. Hardening – Difficulty (Model Trial Fails): 5 (Pass)

**Evidence:** Option A. No-image: A8VBbry 0.0 (f2p 3/6), BNTsYWK 0.0 (4/6), bztzCeS 0.0 (1/6) = 0/3. With-image: AaKCc7L 0.0 (5/6), KZULBK3 0.0 (3/6), VwBbefV 1.0 (6/6), Wy9KgVD 0.0 (3/6) = exactly 1/4. Digests: with_images lock.json = sha256:acc44f2c…f530 = current bundle (harbor Packager.compute_content_hash); without_images = sha256:af6512ab…fc7c = the runner's image-stripped copy of the current bundle, rebuilt locally. No-image runs had an empty `/app/.harbor_assets/`. Run time 9.3–18.6 min (informational).

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 17. Hardening – Real & Feasible: 5 (Pass)

**Evidence:** The upstream issue (#5175, "Align Extraction result and Execution Results grids with the design") is the real defect, and the golden fix is upstream commit a1bbd20 plus reversal of the two injected bugs. Injected bugs are coherent regressions a real codebase could have: bug_01 picks metric header alignment from the first sampled value; bug_02 sets the shared group label to regular weight. Both are visible in current.png, and their fixes are ordinary (always right-align metric columns; semibold class). VwBbefV solved it from the evidence.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 18. Gate – Oracle/Nop: 5 (Pass)

**Evidence:** Local harbor 0.18.0 (Docker Desktop). Oracle: reward 1.0 (6/6, 158/158). Nop: 0.0 (0/6, 158/158). Oracle re-run: 1.0, identical. Every run shows the stage banners (`== applying test.patch ==`, `== running f2p + p2p tests ==`, `== computing reward ==`) and `reward=`, with no "could not apply test.patch". Shipped Oracle/Nop lock digests = current bundle digest. Deviation: this Docker host kernel lacks CONFIG_NFT_FIB_INET, so harbor cannot enforce `[agent] network_mode = "no-network"`. In the reviewer's local copy only, the agent phase was set to public. Oracle/nop make no network use, so rewards are unaffected.

**What is wrong:** Nothing found.

**Suggested fix:** None.

### 19. Unauditable: 5 (Pass)

**Evidence:** Complete bundle, runs and trajectories; fully audited.

**What is wrong:** Nothing found.

**Suggested fix:** None.
