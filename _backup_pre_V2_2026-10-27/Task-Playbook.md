# Varmint Task Playbook — Full Process, Copy-Paste Commands

Every block pastes whole into the sandbox terminal. No script files needed.
**Always start from the task root** — the folder directly containing `task.toml`:

```bash
cd /home/sandbox/Tasks    # adjust to your task root
ls    # expect: task.toml instruction.md evidence_bundle.json environment/ solution/ tests/
```

**When is Docker needed?**

| Activity | Docker? |
| --- | --- |
| Static file checks (Step II Part A, Step IV cross-checks) | No |
| `git apply --check` of patches on base commit | No — a plain clone works (see 2-B alt) |
| Actually running tests (discrimination spot-check) | Yes — needs the pinned env + deps |
| Step V oracle / nop / trial (`mm_run.sh`) | Docker daemon only — harbor builds the image itself |
| Step V `harbor check` / `harbor analyze` | No — static/LLM analysis of the bundle and the trial output |

**Runner prerequisite.** Steps V's oracle/nop/trial go through the `mmswe-runner` skill. Install once (`unzip mmswe-runner-skill.zip && cd mmswe-runner-skill && bash install.sh`) — it lands at `~/.claude/skills/mmswe-runner/` plus `/run-oracle`, `/run-nop`, `/run-trial`, `/run-all` commands. Oracle and nop need no API key; only the trial does.

---

## Step I — Ride In (verify against GitHub)

### 1.1 Pull the task's claimed identity

```bash
grep -E 'task_id|repository_name|repo_url|issue_number|pr_number|base_commit|fix_commit|task_type|visual_essentiality|cross_file|difficulty' task.toml
```

Open `repo_url` issue + PR in a browser. Confirm: issue text matches `instruction.md` symptom, PR is the real fix, posters match the issue/PR's actual visual evidence (watch for videos/GIFs reduced to a wrong still, cropped/unrelated/corrupt images, missing images, misnamed images — `bug.png` showing the *expected* state).

### 1.2 Evidence chain — all four places agree

```bash
python3 - <<'EOF'
import json, re, os
def flat_strings(x):
    if isinstance(x, str): yield x
    elif isinstance(x, dict):
        for v in x.values(): yield from flat_strings(v)
    elif isinstance(x, list):
        for v in x: yield from flat_strings(v)

assets = set(os.listdir("environment/assets")) - {"ASSET_MANIFEST.json"}
man = set(os.path.basename(s) for s in flat_strings(json.load(open("environment/assets/ASSET_MANIFEST.json"))) if "." in os.path.basename(s))
eb = json.load(open("evidence_bundle.json"))
eb_paths = [s for s in flat_strings(eb) if ".harbor_assets" in s or any(s.endswith(e) for e in (".png",".jpg",".jpeg",".gif",".webp"))]
instr = open("instruction.md", errors="replace").read()
refs = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', instr) + re.findall(r'/app/\.harbor_assets/\S+', instr)

print("assets on disk:      ", sorted(assets))
print("in ASSET_MANIFEST:   ", sorted(man))
print("in evidence_bundle:  ", sorted(set(os.path.basename(p) for p in eb_paths)))
print("referenced in instr: ", sorted(set(os.path.basename(p.rstrip(')')) for p in refs)))
for a in assets:
    problems = []
    if a not in man: problems.append("missing from ASSET_MANIFEST")
    if not any(a in p for p in eb_paths): problems.append("missing from evidence_bundle")
    if not any(a in r for r in refs): problems.append("not referenced in instruction.md")
    print(("WARN " if problems else "OK   "), a, "; ".join(problems))
bad = [p for p in eb_paths if "harbor_assets" in p and not p.startswith("/app/.harbor_assets/")]
if bad: print("WARN local_path not under /app/.harbor_assets/:", bad)
EOF
```

If you replace a poster: update **all four** — the file in `environment/assets/`, `ASSET_MANIFEST.json`, `evidence_bundle.json`, the `instruction.md` reference — then re-run this block until all `OK`.

**Asset files are the one renameable thing in the bundle.** Every other harness file (`task.toml`, `instruction.md`, `evidence_bundle.json`, `environment/Dockerfile`, `environment/assets/ASSET_MANIFEST.json`, `solution/fix.patch`, `solution/solve.sh`, `tests/config.json`, `tests/test.patch`, `tests/test.sh`, `tests/verifier.py`) must keep its exact name and place. The images inside `environment/assets/` you may rename or swap — do it when a filename leaks the repo/solution (`antimatter-tooltip-bug.png`, `after-fix.png`) or misdescribes the frame — always updating the same four places.

### 1.3 Judge visual reliance (manual)

Could the agent solve from text alone? Note the answer — drives Step III (visual lever) and Step IV (`visual_essentiality`).

---

## Step II — Static validation

### 2.1 Required files present and non-empty

```bash
for f in task.toml instruction.md evidence_bundle.json environment/Dockerfile environment/assets/ASSET_MANIFEST.json solution/fix.patch solution/solve.sh tests/config.json tests/test.patch tests/test.sh tests/verifier.py; do if [ -s "$f" ]; then echo "OK    $f"; else echo "FAIL  $f (missing or empty)"; fi; done
```

### 2.2 JSON parses + verifier compiles

```bash
for j in evidence_bundle.json environment/assets/ASSET_MANIFEST.json tests/config.json; do python3 -m json.tool "$j" > /dev/null && echo "OK    $j" || echo "FAIL  $j"; done
python3 -m py_compile tests/verifier.py && echo "OK verifier.py" || echo "FAIL verifier.py"
```

### 2.3 Posters decode

```bash
python3 - <<'EOF'
import glob
try: from PIL import Image
except ImportError: raise SystemExit("WARN: no Pillow -> pip install Pillow, or open images by eye")
imgs = sum((glob.glob(f"environment/assets/*.{e}") for e in ("png","jpg","jpeg","gif","webp")), [])
if not imgs: print("WARN: no images found")
for p in imgs:
    try: Image.open(p).verify(); print("OK   ", p)
    except Exception as e: print("FAIL ", p, e)
EOF
```

### 2.4 Synthetic marker

```bash
if [ -e tests/.s ]; then echo "WARN: SYNTHETIC tests - scrutinize; empty f2p = reject task"; else echo "OK: real PR tests"; fi
```

### 2.5 Golden fix — paths, red flags, solve.sh

```bash
echo "--- fix.patch touches:"; grep '^diff --git' solution/fix.patch | sed 's#^diff --git a/\(.*\) b/.*#  \1#'
echo "--- task.toml files_edited:"; grep -A20 'files_edited' task.toml
echo "--- red flags (should print NOTHING):"; grep '^diff --git' solution/fix.patch | grep -Ei 'test|spec|\.md$|changelog|changeset|lock'
echo "--- solve.sh:"; cat solution/solve.sh
```

### 2.6 Tests — config vs patch, identifiers exist

```bash
echo "--- test.patch touches:"; grep '^diff --git' tests/test.patch | sed 's#^diff --git a/\(.*\) b/.*#  \1#'
python3 - <<'EOF'
import json, os
c = json.load(open("tests/config.json"))
for k in ("test_framework","test_files","f2p","p2p"): print(f"{k}: {c.get(k)}")
if not c.get("f2p"): print("FAIL: f2p empty - can never discriminate")
patch = open("tests/test.patch", errors="replace").read() if os.path.exists("tests/test.patch") else ""
for kind in ("f2p","p2p"):
    for t in (c.get(kind) or []):
        n = t.split("::")[-1]
        print(("OK   " if n in patch else "WARN ") + f" {kind} '{n}' " + ("found" if n in patch else "NOT in test.patch (p2p may live in repo)"))
EOF
```

### 2.7 Binary-baseline reset trap

```bash
if grep -qE '^(GIT binary patch|rename from|rename to)' tests/test.patch; then echo "WARN: binary/rename in test.patch"; grep -n "+++ b/" tests/test.sh && echo "FAIL: test.sh resets via '+++ b/' -> binary paths SKIPPED (silent 0 on re-run); reset must parse 'diff --git' headers" || echo "OK: reset avoids the trap"; else echo "OK: no binary/rename sections"; fi
```

### 2.8 Patches apply on base — WITHOUT Docker (lightweight clone)

```bash
BASE=$(grep -E '^\s*base_commit' task.toml | sed 's/.*=\s*"\{0,1\}\([a-f0-9]*\)"\{0,1\}.*/\1/')
URL=$(grep -E '^\s*repo_url' task.toml | sed 's/.*=\s*"\(.*\)".*/\1/')
echo "base=$BASE url=$URL"
rm -rf /tmp/basecheck && git clone --no-checkout "$URL" /tmp/basecheck && cd /tmp/basecheck && git checkout -q "$BASE"
git apply --check "$OLDPWD/solution/fix.patch" && echo "OK: fix.patch applies on base" || echo "FAIL: fix.patch"
git apply --check "$OLDPWD/tests/test.patch" && echo "OK: test.patch applies on base" || echo "FAIL: test.patch"
git apply "$OLDPWD/solution/fix.patch" && git apply "$OLDPWD/tests/test.patch" && echo "OK: both together" || echo "FAIL: conflict"
cd "$OLDPWD" && rm -rf /tmp/basecheck
```

### 2.9 Run the real test pipeline in Docker (discrimination + idempotency)

No need to figure out the test runner — `tests/test.sh` IS the pipeline (applies test.patch, runs the tests, computes the reward). Run it exactly like harbor does.

**Step 1 — build + start container** (from task root):

```bash
docker build -t task-env environment/
docker run -it --rm -v "$(pwd)/solution:/solution:ro" -v "$(pwd)/tests:/tests:ro" task-env
```

**Step 2 — inside the container (`/app` = base commit, tag `harbor_base`), paste the whole sequence:**

```bash
[ -d node_modules ] && echo "deps OK" || echo "FAIL: npm install failed silently in Dockerfile"

# 1. BASE run -> expect reward 0.0
bash /tests/test.sh

# 2. Apply golden fix, run again -> expect reward 1.0
git apply /solution/fix.patch
bash /tests/test.sh

# 3. Run once more, changing nothing -> must STILL be 1.0 (idempotency / binary-trap check)
bash /tests/test.sh

exit
```

**Expected output pattern** (each run prints stage banners + a reward line):

```text
== applying test.patch ==
== running behavioral test ==
== computing reward ==
{"reward": 0.0, "f2p": {...: "fail"}, "p2p": {...}}     <- base
{"reward": 1.0, "f2p": {...: "pass"}, "p2p": {...}}     <- fix
{"reward": 1.0, ...}                                     <- re-run
```

Read: **0.0 → 1.0 → 1.0** = pass. Notes:

- Base run printing `(test exited non-zero; parsing report)` is NORMAL — that's the f2p failing as intended.
- All three banners + a reward line must appear each run — that proves the verifier reached the end (not the EXIT-trap fake 0).
- Detailed report: `cat /logs/verifier/*` (it's a directory — plain `cat /logs/*` errors).
- Base ≠ 0.0 → tests don't catch the bug. Fix ≠ 1.0 → fix/tests/wiring broken. Third run ≠ 1.0 → binary-baseline reset trap (2.7).
- **Inspect the results, not just the reward**: `p2p: {}` = no regression guards — a mandatory Step III target (add p2p). A single f2p = thin suite. Read the test file itself (test.patch adds it, typically at repo root, e.g. `harbor_test.js`) and confirm it asserts DOM/behavioral effects, not CSS/source strings.
- If you experiment manually in `/app`, reset with `git reset --hard harbor_base && git clean -fd -e .harbor_assets` — the plain `git clean -fd` DELETES `.harbor_assets/` (Dockerfile copies assets after the `harbor_base` tag, so they're untracked).

---

## Step III — Harden (manual work, command support)

Levers (apply what fits): **localization** (strip files-to-change lists, named mechanisms/APIs/CSS, recipes, expected-output previews, all repo traces), **stronger tests** (new f2p edge cases, p2p regression guards — behavioral, discriminating, deterministic, implementation-agnostic), **broader scope** (extend fix.patch toward the PR's cross-file version, sync `files_edited`), **visual reliance**, **anti-cheat** (incl. renaming asset files whose names leak the repo or the expected state — the only bundle files you may rename).

### 3.0 Hardening-advice prompt (copy-paste into your agent window)

This IS the prompt. Copy everything inside the block below into the agent chat. Where a `<<< >>>` marker appears, paste that file's content (display it in the sandbox with `cat <file>` and copy). Attach the poster screenshot if the chat accepts images; otherwise replace that marker with a short description of the visible defect.

```text
# Role

You are a hardening deputy for a multimodal AI-coding benchmark task. The task is a real merged GitHub PR: an agent under evaluation is dropped into the repo at a base commit with ONLY `instruction.md` (symptom text) plus screenshot evidence, and must produce a code fix. It is scored by `tests/test.sh` -> `verifier.py`: reward 1.0 (all f2p + p2p pass), 0.5 (partial), 0.0.

Your job: ADVISE me on how to make this task HARDER, so a capable model fails it, while keeping the validation gate intact. You analyze and recommend; I implement and validate.

# Environment facts

- Task bundle layout: `task.toml`, `instruction.md`, `evidence_bundle.json`, `environment/` (Dockerfile + `assets/` = the screenshots), `solution/` (`fix.patch` = golden fix, `solve.sh`), `tests/` (`config.json`, `test.patch`, `test.sh`, `verifier.py`).
- The environment container clones the repo at `base_commit`, strips `.git`, re-inits, tags `harbor_base`. `test.sh` resets test paths from `harbor_base`, applies `test.patch`, runs ONLY the f2p + p2p tests, and computes the reward — so the evaluated agent cannot cheat by editing tests.
- Screenshots live at `/app/.harbor_assets/` inside the container; `instruction.md` references them there.
- Current gate status: base -> reward 0.0, golden fix -> 1.0, idempotent re-run -> 1.0 (verified).

# Hard constraints (violating any = rejected task)

1. `instruction.md` must NOT leak the solution: no files-to-change list, no named mechanism/API/CSS property, no fix snippet or corrected-output preview, no trace of the source repo (name, URLs, org, issue/PR numbers). Only the symptom + the screenshots.
2. Tests must be implementation-agnostic: any behaviorally-correct fix passes, not just the golden's approach/names/output. Assert observable behavior (input -> output/DOM effect), never source/CSS strings, never grep the candidate's code.
3. Every f2p must FAIL on base and PASS on golden fix. Every p2p must PASS on both. All tests deterministic (no timing/network/unpinned fonts).
4. The gate stays intact: golden fix -> 1.0, base -> 0.0.
5. Stay real: you may extend `solution/fix.patch` to the real PR's fuller scope or a defensible adjacent behavior, but never invent behavior no real developer would write. Keep `files_edited` in `task.toml` synced with the patch.
6. Keep it feasible: after stripping hints, the task must still be solvable from symptom + screenshot alone.
7. Observability limit: the harness can only observe what the test runner can see (DOM/attributes/behavior — jsdom-style; no pixel/layout measurement). If the core visual defect is not directly testable, add p2p regression tests for surrounding behavior AND extend the ask to an adjacent observable behavior as the f2p.

# Hardening levers (in priority order)

1. Harder localization — strip every hint from `instruction.md` (biggest win, most common leak).
2. Stronger/more tests — add edge-case f2p (boundaries, mixed states, error paths), tighten loose assertions, add p2p regression guards (currently see config below — an empty p2p list means NO regression guards; fix that).
3. Broader fix scope — cross-file / multi-symptom version when the real PR supports it (`cross_file = true`).
4. Stronger visual reliance — once the recipe is gone the screenshot becomes essential (`visual_essentiality` -> `required`).
5. Anti-cheat — nothing agent-visible may leak the fix commit or answer.

# Required output — SUGGESTIONS ONLY

Do not rewrite the files for me. I will implement the changes myself. Give me an advisory report:

1. Leak audit of `instruction.md`: quote every line that hints at the fix (file names, mechanisms, APIs, CSS properties, expected-output previews, repo traces) and say why it's a leak and whether to remove or rephrase it.
2. Ranked hardening recommendations (highest impact first). For each: which lever it uses, what exactly I would change (name the specific line/test/file), and why a shallow or recipe-following attempt currently scores 1.0 but would fail after the change.
3. Test-suite gaps: which edge cases / regression paths the current f2p+p2p miss, and for each proposed test describe the behavioral assertion in words (input -> observable effect), whether it's f2p or p2p, and why it would fail on base / pass on fix (f2p) or pass on both (p2p). Sketches are fine; I write the final code.
4. Scope opportunities: does the golden fix support a defensible cross-file / multi-symptom extension? What would it cover and what's the risk to the gate?
5. Feasibility check: after your suggested removals, confirm the task is still solvable from symptom + screenshot alone — name the reasoning chain an agent would need.
6. Metadata implications: which `task.toml` fields my changes would require updating (`visual_essentiality`, `difficulty`, `cross_file`, `f2p`/`p2p`, `tags`) and to what values.
7. Risks/pitfalls specific to this task: overfit-test dangers, determinism concerns, observability limits of this harness.

# The visible defect (the wanted poster)

<<< attach the screenshot(s) here, or describe the visible defect in 1-2 sentences >>>

# Task files

## task.toml
<<< paste content of task.toml >>>

## instruction.md (the agent-facing prompt)
<<< paste content of instruction.md >>>

## evidence_bundle.json
<<< paste content of evidence_bundle.json >>>

## tests/config.json
<<< paste content of tests/config.json >>>

## solution/fix.patch (the golden fix)
<<< paste content of solution/fix.patch >>>

## tests/test.patch (the current tests)
<<< paste content of tests/test.patch >>>

## tests/test.sh (the harness)
<<< paste content of tests/test.sh >>>

## tests/verifier.py
<<< paste content of tests/verifier.py >>>
```

Notes:

- To display a file for copying, in the sandbox terminal: `cat task.toml`, `cat instruction.md`, etc.
- Treat the agent's reply as a proposal: YOU implement, then re-run 2.8/2.9 and Step V. The gate is yours to re-establish.
- Never paste this prompt or the agent's reply into the task bundle, and never reuse their text inside `instruction.md`.

### 3.1 Leak scan after each instruction.md edit

```bash
grep -niE 'github\.com|files to change|issue #|pull request|PR #|repo\b|repository' instruction.md; echo "--- no output above = clean. Also re-read for: named files, APIs, CSS properties, fix/expected-output previews."
```

Also scrub project fingerprints — grep for the repo and org names explicitly:

```bash
grep -niE 'antimatter|IvarK' instruction.md    # substitute this task's repo/org names
```

### 3.2 After editing fix.patch or test.patch — re-verify

Re-run block **2.8** (apply-check) and **2.9** (full 0.0 → 1.0 → 1.0 sequence), plus 2.5/2.6 for path/ID sync. Added p2p tests must show as `"pass"` in BOTH the base run and the fix run of 2.9 — a p2p failing on base is mislabeled (really an f2p).

### 3.3 Feasibility gut check (manual)

With only symptom + poster left: could YOU still find and fix it? If no discoverable path remains, restore the minimum hint.

---

## Step IV — Metadata cross-check (automated where possible)

```bash
python3 - <<'EOF'
import json, re, os
raw = open("task.toml", errors="replace").read()
def field(name):
    m = re.search(rf'^\s*{name}\s*=\s*(.+)$', raw, re.M)
    return m.group(1).strip().strip('"') if m else None
def toml_list(name):
    m = re.search(rf'{name}\s*=\s*\[(.*?)\]', raw, re.S)
    return sorted(re.findall(r'"([^"]+)"', m.group(1))) if m else []

issues = []
# task_id format <owner>__<repo>-<issue>-mm
tid = field("task_id") or ""
print(("OK   " if re.match(r'^[\w.-]+__[\w.-]+-\d+-mm$', tid) else "WARN ") + f" task_id = {tid}")
# Dockerfile checkout == base_commit
base = field("base_commit") or ""
dock = open("environment/Dockerfile", errors="replace").read()
indock = base[:12] in dock if base else False
print(("OK   " if indock else "FAIL ") + f" base_commit {base[:12]} {'found' if indock else 'NOT found'} in Dockerfile checkout")
# files_edited == fix.patch paths
patch_paths = sorted(set(re.findall(r'^diff --git a/(.*?) b/', open("solution/fix.patch", errors="replace").read(), re.M)))
fe = toml_list("files_edited")
print(("OK   " if fe == patch_paths else "FAIL ") + " files_edited == fix.patch paths")
if fe != patch_paths: print("   toml:", fe, "\n   patch:", patch_paths)
# cross_file consistency
cf = (field("cross_file") or "").lower()
print(("OK   " if (len(patch_paths) > 1) == (cf == "true") else "WARN ") + f" cross_file={cf} vs {len(patch_paths)} file(s) in fix.patch")
# f2p/p2p: task.toml == config.json
c = json.load(open("tests/config.json"))
for k in ("f2p","p2p"):
    t, j = toml_list(k), sorted(c.get(k) or [])
    print(("OK   " if t == j else "FAIL ") + f" {k}: task.toml == config.json")
    if t != j: print("   toml:", t, "\n   json:", j)
# task_type valid
tt = field("task_type") or ""
valid = {"visual_bug_fix","visual_regression","design_reference","build_render_repair","temporal_interaction","accessibility_visual","data_viz_correctness"}
print(("OK   " if tt in valid else "FAIL ") + f" task_type = {tt}")
# visual_essentiality
ve = field("visual_essentiality") or ""
print(("OK   " if ve in {"none","helpful","required"} else "FAIL ") + f" visual_essentiality = {ve}" + ("  <- 'none' means task should not exist" if ve == "none" else ""))
# tags
tags = toml_list("tags")
need = {"multimodal", tt} | ({field("framework")} if field("framework") else set())
missing = [t for t in need if t and t not in tags]
print(("OK   " if not missing else "WARN ") + f" tags = {tags}" + (f"  missing: {missing}" if missing else ""))
EOF
```

Manual honesty pass (not automatable): `visual_essentiality` reflects the **hardened** task (recipe stripped → usually `required`); `difficulty_explanation` says concretely why the image is needed and why the fix is non-trivial. These two are the most-commonly-dishonest fields — update them.

Then re-run block **1.2** (evidence chain) if any asset changed.

---

## Step V — Oracle, Nop, Check, Trial, Analyze (High Noon)

Five runs, in order. Re-run 5.1/5.2 after EVERY change from Steps I/III/IV. Docker daemon must be up; harbor builds the env itself.

Output layout the runner writes — four flat siblings, no per-task subfolder:

```text
/home/sandbox/Tasks/     the task
/home/sandbox/Oracle/    oracle output      <- not submitted
/home/sandbox/Nop/       nop output         <- not submitted
/home/sandbox/Trials/    agent trial output <- submitted
```

`ROOT` is inferred as the parent of the task folder (override with `--root`). **Each run overwrites the previous one for that mode** — pass `--keep` to preserve an earlier run.

### 5.1 Oracle + Nop (no API key needed)

```bash
bash ~/.claude/skills/mmswe-runner/mm_run.sh /home/sandbox/Tasks oracle    # must be 1.0 / 1
bash ~/.claude/skills/mmswe-runner/mm_run.sh /home/sandbox/Tasks nop       # must be 0.0 / 0
```

Reward lands in `<mode-dir>/<name>__<rand>/verifier/reward.txt`, also in `result.json` → `verifier_result.rewards`.

```bash
cat Oracle/*/verifier/reward.txt Nop/*/verifier/reward.txt
```

### 5.2 Verify the rewards are real (EXIT-trap caveat)

`test.sh` traps EXIT and writes 0 on a crash — a crashed run and a genuine fail both read 0.0. Confirm the verifier ran to completion:

```bash
grep -rn "reward" Oracle Nop Trials 2>/dev/null | grep -v node_modules | tail -20
grep -rniE "could not apply|error|traceback" Oracle Nop 2>/dev/null | grep -v node_modules | tail -20
```

Idempotency: re-run oracle a second time — must still be 1.0 (catches the binary-reset trap live).

### 5.3 `harbor check` — bundle quality gate

```bash
harbor check Tasks
```

Prints a **Task Quality Checks** table: `Behavior In Task Description`, `Behavior In Tests`, `Informative Test Structure`, `Anti Cheating Measures`, `Structured Data Schema`, `Pinned Dependencies`, `Typos`, `Tests Or Solution In Image`, `Test Deps In Image`, `Hardcoded Solution`, `File Reference Mentioned` — each `pass` / `fail` / `not_applicable` + an explanation.

**Expected failure:** `Behavior In Task Description` usually fails — harbor does not read the image content. Do not "fix" it by adding a recipe to `instruction.md` (that reintroduces the #1 leak). Instead verify by eye: **does the poster actually show the defect the F2P tests assert?** If not, the tests demand behavior neither the text nor the image requests — fix the tests. Every other `fail` row is a real finding: read the explanation and fix it.

### 5.4 Trial — the model must FAIL

```bash
bash ~/.claude/skills/mmswe-runner/mm_run.sh /home/sandbox/Tasks trial     # must be < 1.0
```

Defaults: agent `claude-code`, model `anthropic/claude-opus-4-8`, single attempt, `WebSearch`/`WebFetch`/`EnterPlanMode` disallowed, credentials resolved live-env → `~/.claude/settings.json` `.env` → anonymizer defaults (`ANTHROPIC_BASE_URL=http://localhost:8091`, `ANTHROPIC_API_KEY=anonymizer-placeholder`). Host networking is auto-configured so the container's `localhost` is the VM's (`--no-hostnet` falls back to the proxy bridge; `COMPOSE_SVC=<name>` if harbor's service isn't `main`).

A trial scoring 1.0 has exactly three causes — diagnose which:

| Cause | Evidence | Fix |
| --- | --- | --- |
| Prompt not difficult enough | agent went straight to the right file | Step III localization lever on `instruction.md` |
| Tests were loose | agent's diff is shallow/wrong yet f2p passed | tighten f2p, add edge-case f2p |
| The model cheated | read the agent transcript in `Trials/` — looked up the solution PR, edited tests/verifier | close the leak (repo traces, fix commit), confirm test reset from `harbor_base` |

### 5.5 `harbor analyze` — did it solve or cheat?

```bash
harbor analyze Trials
```

Prints Job Summary (total trials, full pass @1.0 / partial @0.5 / full fail @0.0, pass rate), Success & Failure Analysis (which f2p/p2p passed), Root Causes, Key Takeaway, Summary, and a per-trial table with **Reward Hacking** and **Task Specification**.

**Expected failure:** `Task Specification` usually fails as "instructions not specific enough" — that is the hardening working. Read the feedback anyway and confirm two things: the image genuinely conveys the visual issue, and the tests are not pinned to the golden solution (any valid fix satisfying `instruction.md` must pass). `Reward Hacking = fail` is never expected — treat it as a real leak and close it.

### Decision table

| Result | Meaning | Action |
| --- | --- | --- |
| oracle < 1.0 | fix, tests, or wiring broken | debug before anything else |
| nop > 0.0 | tests don't catch the varmint | tighten/replace tests |
| check fail (other than Behavior In Task Description) | real bundle defect | fix, re-run |
| trial = 1.0 | too easy / loose tests / cheat | 5.4 table, then back to Step III |
| analyze: Reward Hacking fail | agent gamed the harness | close the leak, re-run trial |
| trial < 1.0, everything else clean | done | keep this run's `Trials/` for submission |

---

## Step VI — Justification (template)

Write one entry per change. Graded on substance — generic = rejected.

```text
CHANGE N
Lever:        localization | tests | scope | visual reliance | anti-cheat
Before:       <exact hint/line/test/file as it was — quote it>
After:        <exact state now — the removed line, the added test name + its exact assertion, the files added to scope>
Why harder:   <what a shallow/partial/recipe-following attempt got away with before, and why it can't now>
Gate:         oracle 1.0 / nop 0.0 / trial FAILED re-verified on <date>; harbor check + harbor analyze reviewed
```

---

## Step VII — Submit layout

Both folders at the ROOT, siblings — Trials never inside Tasks:

```bash
cd /home/sandbox
ls -d Tasks Trials && echo "OK: siblings at root" || echo "FAIL: fix layout"
find Tasks -maxdepth 1 && echo --- && ls Trials | head
```

`Trials/` = the output of the run where the model FAILED — `mm_run.sh ... trial` already writes it there, no copying. `Oracle/` and `Nop/` are working output, not part of the deliverable: hand back **two** folders only.

### Final checklist (paste, then answer honestly)

```text
[ ] Verified vs real GitHub issue+PR; poster fixed if wrong (all 4 places updated)
[ ] fix.patch applies on base_commit, source-only, == files_edited
[ ] test.patch/config.json/task.toml agree on test_files, f2p, p2p
[ ] every p2p genuinely passes on base
[ ] no localization hints, no repo traces, no fix/output previews in instruction.md
[ ] still feasible from symptom + poster alone
[ ] all tests behavioral, discriminating, deterministic, implementation-agnostic
[ ] metadata reflects HARDENED task (visual_essentiality, difficulty, cross_file, f2p/p2p)
[ ] oracle 1.0, nop 0.0, trial FAILED — verifier reached end, idempotent on re-run
[ ] harbor check Tasks run; every fail addressed except the expected "Behavior In Task Description"
[ ] poster genuinely shows what the f2p tests assert (the manual check that flag can't do)
[ ] harbor analyze Trials run; Reward Hacking = pass; "Task Specification" fail read and judged
[ ] technical justification per change (lever, before->after, why harder)
[ ] nothing invented; task still a real coherent issue
[ ] Tasks/ + Trials/ siblings at root
```

---

## Reset commands (anytime)

```bash
# inside container:            back to pristine base
# (-e .harbor_assets is REQUIRED: assets are untracked, plain clean deletes them)
git reset --hard harbor_base && git clean -fd -e .harbor_assets && git status
# outside:                     containers started with --rm vanish on exit; image immutable
# scratch clone from 2.8:      rm -rf /tmp/basecheck
```
