# Adding More Bugs to a Task

This guide explains how to inject additional bugs into a task so the model has more to solve. There are two parts:

- **Part A — Author the bug** (clone the repo in the sandbox, edit code, export the diff).
- **Part B — Wire it into the task** (drop the diff into `environment/bugs/`, update the `Dockerfile`, add a detecting test + fix).

The repo URL, commit hash, and file paths in the commands below are examples taken from this task (`apache/superset`). Swap in the values from your own task's `task.toml` (`repo_url`, `base_commit`) and the files you're editing.

Keep in mind that this guide uses the superset repository as an example. Make sure you modify the commands according to your task (e.g., repo URL, commit hashes).

## V2 task folder (TASK101 and later)

The task bundle is no longer `Tasks/` itself but the task's own folder inside it, named after its `task_id`:

```
/home/sandbox/
├── Tasks/
│   └── <task_id>/            <- the bundle: task.toml, environment/, solution/, tests/, ...
├── superset/                 <- your scratch clone (Part A): beside Tasks/, never inside it
└── fix_add.patch             <- scratch, never inside Tasks/
```

Every bundle path in this guide is written as `$T/...`. Set `T` once per terminal, from the sandbox root:

```shell
cd /home/sandbox
T="$(cd Tasks/*/ && pwd)"; echo "$T"     # -> /home/sandbox/Tasks/<task_id>
```

(V1 tasks, before TASK101, had the bundle directly in `Tasks/`: there `T=/home/sandbox/Tasks`.)

**Required bundle layout (QC checks it).** Bug patches live in `environment/bugs/`, **not** in `environment/assets/`. `assets/` holds only the evidence files listed in `ASSET_MANIFEST.json`:

```
Tasks/<task_id>/
├── README.md, instruction.md, task.toml, evidence_bundle.json
├── environment/
│   ├── Dockerfile               <- COPY bugs/ /tmp/bugs/  (never assets/bugs/)
│   ├── bugs/                    <- bug_01.patch, bug_02.patch, ... (build input only)
│   └── assets/                  <- ASSET_MANIFEST.json + the screenshots, nothing else
├── solution/                    <- fix.patch, solve.sh
└── tests/                       <- config.json, test.patch, test.sh, verifier.py
```

## How it works (mental model)

The model receives the repo exactly as it exists after the Docker build, snapshotted as the `harbor_base` git tag. Any source change baked in **before** that snapshot becomes a bug the model must find and fix.

- A **bug patch** turns good code into buggy code (`good -> buggy`). This is what the `Dockerfile` applies.
- A **fix patch** is the reverse (`buggy -> good`). This goes into `solution/fix.patch` so the oracle solution still scores 100%.
- A bug is only gradable if a **test** in `tests/test.patch` fails on the buggy state and passes once fixed (registered under `f2p` in `task.toml` **and** `tests/config.json` — the verifier reads its test list from `config.json`).

## Part A — Author the bug

Do this in stages — don't run everything at once. First clone and check out the right commit, then modify the code, and only after that export the diffs.

Run these from the sandbox root, `/home/sandbox` (the directory that contains `Tasks/`), with `T` set as above. The repo is cloned into a `superset/` folder right there — a sibling of `Tasks/`, never inside it: anything inside `Tasks/` ships with the deliverable.

The repo URL, commit hash, and file paths below are examples specific to this task (`apache/superset`). Swap in your own task's `repo_url` and `base_commit` from `task.toml`, and the files you're editing.

**1. Open a terminal in the sandbox and clone the repo, then check out the exact `base_commit` the `Dockerfile` uses:**

```shell
git clone https://github.com/apache/superset

git -C superset checkout ff1cf5f24ed29835843853dcd5af9a27918fe6b5   # must match base_commit in task.toml
```

**2. Now modify the codebase to introduce the bug.**

Open the file(s) under `superset/` in your editor and make a real, deliberate defect — something a test can detect (wrong output, off-by-one, a dropped branch, etc.). For example, in this task you might edit:

```
superset/superset-frontend/plugins/plugin-chart-echarts/src/utils/formatters.ts
```

Take your time here: this hand-written change is the bug. Don't rush it into the same step as the commands below.

**3. Once the bug is in place, export the two diffs (writing the bug patch straight into the task):**

```shell
# The bundle does not ship an environment/bugs/ folder - create it once
mkdir -p "$T/environment/bugs"

# Bug patch (good -> buggy): the Dockerfile applies this
git -C superset diff > "$T/environment/bugs/bug_01.patch"

# Fix patch (buggy -> good): the reverse, kept for the oracle fix in step 4
git -C superset diff -R > fix_add.patch
```

**The oracle needs a fix for your bug too.** Since you broke known-good code, the fix is just reverting to that correct code — which is exactly what `git diff -R` captures above, so you normally don't hand-write a separate fix. You must still merge `fix_add.patch` into `$T/solution/fix.patch` (Part B, step 4) so the oracle repairs both the original and the new bug and still scores 100%. Exception: if the *correct* behavior differs from what the base commit had (not a pure regression), author the real fix by hand instead of using the reverse diff.

**Don't forget the tests.** A bug is only gradable if a test catches it. After authoring the bug, you **must** modify `$T/tests/test.patch` to add tests that fail on the buggy state and pass once fixed, and register their names under `f2p` in `$T/task.toml` and `$T/tests/config.json` (see Part B, step 3). Skipping this means the model gets no signal or reward for solving the new bug.

**Notes:**

- **Pin the commit exactly.** Editing at `HEAD` or another commit may make the `git apply` in the `Dockerfile` fail or land in the wrong place.
- **Use the working-tree diff (uncommitted).** `git diff` compares your edits against the checked-out commit, which is exactly `good -> buggy`. If you commit first, diff against the commit: `git diff <base_commit>`.

## Part B — Wire the bug into the task

### 1. Place the bug patch

Keep bug patches in the task's `environment/bugs/` (only `.patch` files here, never test files):

```
Tasks/<task_id>/environment/bugs/bug_01.patch
```

`bugs/` is build input, not evidence: it sits beside `assets/`, never inside it, gets no `ASSET_MANIFEST.json` / `evidence_bundle.json` entry, and is deleted from the image (step 2). Older bundles with `environment/assets/bugs/` must be moved: `mv "$T/environment/assets/bugs" "$T/environment/bugs"`, and update the Dockerfile `COPY`.

### 2. Update the Dockerfile to copy → apply → delete

The bug must be applied before the `harbor_base` snapshot, and the patch files must not survive anywhere in the final image (the reverse of a bug patch is the fix).

Three things leak a bug if you get them wrong:

- **The patches themselves.** `/tmp/bugs/` is part of the final image unless you delete it — `rm -rf /tmp/bugs` in the same `RUN` as the apply loop. The same goes for `/app/.harbor_assets/bugs` if the Dockerfile copies the whole `assets/` folder.
- **File timestamps.** `git apply` makes the patched files the newest in the repo (`find /app -newer package.json` lists them). The V2 template already has a step that sets one timestamp on every file. The apply loop must run **before** that step.
- **The snapshot.** The apply loop must run before `git init … tag harbor_base`, or the bug isn't in the state the model starts from.

**V2 Dockerfiles (TASK101+)** use separate `RUN`s: clone or fetch `base_commit`, install deps, set one timestamp on every file, record `harbor_base`, then copy the named screenshots. Leave all of them as they are. Add the copy, the apply loop and the delete **after the install** (so editing a bug patch doesn't re-run `npm ci`) and **before the timestamp step**. Example from TASK102 (`epam/ai-dial-admin-frontend`); swap in your own repo, commit and install command:

```shell
RUN git clone https://github.com/epam/ai-dial-admin-frontend.git /app \
 && git -C /app -c advice.detachedHead=false checkout 5e1a82bfdf99bde855f4931d795d6e01cdb127d2   # unchanged
RUN npm ci                                                                    # unchanged
ENV CI=true                                                                   # unchanged

# [IMPORTANT] Injected bugs: copied to a temp path, applied BEFORE the timestamp step and the
# harbor_base snapshot, and deleted in the same RUN so no patch reaches the final image.
COPY bugs/ /tmp/bugs/
RUN set -e; for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done; \
    rm -rf /tmp/bugs

# One timestamp for every file: which file changed last must not point at the bug.
RUN find /app -mindepth 1 -exec touch -h -t 202301010000 {} +                # unchanged, AFTER the apply

# Drop upstream history and record the task base; the fix commit must stay unreachable from here.
RUN rm -rf /app/.git \
 && git -C /app init -q \
 && ... \
 && git -C /app tag harbor_base                                               # unchanged

# Visual evidence for the agent only (never the whole assets/ folder, never tests/ or solution/).
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/current.png assets/mockup.png /app/.harbor_assets/                # unchanged
```

Keep the screenshot `COPY` naming the files one by one (or `assets/*.png`), so only evidence reaches `.harbor_assets/`. If your Dockerfile has no timestamp step (older V2 tasks such as TASK101), add the reset to the apply `RUN`, after `rm -rf /tmp/bugs`:

```shell
    cd /app; git ls-files -z | xargs -0 touch -h -r package.json; \
    find . -path ./node_modules -prune -o -path ./.git -prune -o -type d -print0 | xargs -0 touch -h -r package.json
```

**V1 Dockerfiles (before TASK101)** clone, check out, drop `.git` and tag `harbor_base` in a single `RUN`, and copy the whole `assets/` folder. Put the apply loop inside that `RUN`, between `rm -rf /app/.git` and `git init`. Delete both copies of the patches:

```shell
COPY assets/bugs/ /tmp/bugs/

RUN git clone https://github.com/apache/superset /app \
 && git -C /app checkout ff1cf5f24ed29835843853dcd5af9a27918fe6b5 \
 && rm -rf /app/.git \
 && for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done \
 && rm -rf /tmp/bugs \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/
RUN rm -rf /app/.harbor_assets/bugs        # [IMPORTANT] whole-folder COPY: remove the patches again
```

Note: `rm` is enough for anti-cheat. The agent only sees the final merged filesystem, not intermediate build layers. A deleted patch can't be read even though an earlier layer held it. A patch you never delete, like a leftover `/tmp/bugs/`, can be read.

### 3. Add a detecting test

`$T/tests/test.patch` is itself a diff that **adds** test cases to the repo's test file. To add a test for your new bug you grow that patch — and just like `fix.patch`, you don't hand-edit it, you regenerate it from the clone. The trick is to diff **only the test file** so your source-bug edits don't end up in it.

Run from the sandbox root, reusing the `superset/` clone from Part A. The test-file path and the commit hash below are examples specific to this task — swap in your own task's `base_commit` (from `task.toml`) and the test file you're extending:

```shell
cd superset

# 1) Start from the tests the task already adds, so you extend rather than
#    overwrite them. --index stages the files test.patch CREATES - plain
#    `git apply` leaves them untracked, and step 3's diff would silently drop them.
git apply --index "$T/tests/test.patch"

# 2) Open the test file and add your new test case(s), e.g.:
#    superset-frontend/plugins/plugin-chart-echarts/test/utils/formatters.test.ts
#    Each new test must FAIL on the buggy state and PASS once fixed.
#    Created a brand-new test file? Stage it too:  git add -N <that file>

# 3) Regenerate test.patch as the diff of ONLY the test files vs base_commit -
#    every path the old test.patch touched, plus any you added. Diffing explicit
#    paths keeps your source bug out of test.patch; --binary keeps image baselines.
git diff --binary ff1cf5f24ed29835843853dcd5af9a27918fe6b5 -- \
  superset-frontend/plugins/plugin-chart-echarts/test/utils/formatters.test.ts \
  > "$T/tests/test.patch"
cd ..
```

List every test path the original `test.patch` touched (`grep '^diff --git' "$T/tests/test.patch"` before step 3) — a path left out of the `git diff` disappears from the task.

Then register the new test's name under `f2p` in **both** `$T/task.toml` (the `[metadata]` table) and `$T/tests/config.json` (tests that must keep passing go under `p2p`). The two lists must be identical: the verifier reads `config.json` to decide which tests count, and QC fails a task whose two lists differ. Each name is the full test title as JUnit reports it, with the `describe` blocks joined by ` > ` (e.g. `EllipsisHeader alignment > is not special-cased to one header label`). It must match exactly and be unique across the listed files. The V2 reward is binary: every f2p and p2p test must be found **exactly once** in the report and pass. A misspelled or duplicated name scores 0.

If the new test lives in a file the task did not test before, also add that file to `config.json` → `test_files` and to the runner command in `$T/tests/test.sh`. In V2 harnesses that is the `run_tests()` block near the top, which names each test file explicitly. A test in an unlisted file never runs and reads as `missing`. If the new test relies on a new helper or config file outside `test.patch`, add that path to `PROTECTED_DIRS` in the same block, so a candidate can't overwrite it.

**Never put source changes in `test.patch`.** The verifier resets the `test.patch` paths to `harbor_base` and re-applies `test.patch`, so it must contain test files only — diffing the explicit test path (step 3 above) guarantees that.

### 4. Extend the oracle fix

This is where `fix_add.patch` (from Part A) gets folded into the oracle fix.

`$T/solution/fix.patch` already fixes the original bug, and the oracle must now fix **both** the original and the new bug. This matters because `solve.sh` applies **only** `/solution/fix.patch` (`git apply`, falling back to `patch -p1`). It never applies your bug patches or `fix_add.patch` — so your new fix won't take effect unless it lives inside `fix.patch`.

**You do not hand-edit `fix.patch`.** Don't open it and paste in hunks. Instead you let git regenerate the file: rebuild the exact buggy state the oracle runs against (`harbor_base` = base commit + all bug patches), apply every fix on top, then dump a fresh diff that **overwrites** `fix.patch`. Run from the sandbox root, reusing the `superset/` clone from Part A. (The paths and file names below are examples specific to this task — substitute your own.)

```shell
cd superset

# 1) Recreate harbor_base = base + every injected bug, committed as baseline.
#    First discard your manual edits from Part A (already saved as patches).
#    --index everywhere: a patch that CREATES a file leaves it untracked otherwise,
#    and the commit / the diff below would miss it.
git reset -q --hard && git clean -fdq
git apply --index "$T"/environment/bugs/*.patch
git -c user.email=h@l -c user.name=h commit -qm buggy-baseline

# 2) Apply the fixes ON TOP of that buggy commit:
git apply --index "$T/solution/fix.patch"   # the existing oracle fix
git apply --index ../fix_add.patch          # your new fix (reverse of your bug)

# 3) Diff the fixed tree against the buggy commit -> ONE combined patch.
#    This line REPLACES fix.patch with the merged result. Git does the merge.
git diff --binary HEAD > "$T/solution/fix.patch"
cd ..
```

After step 3, `$T/solution/fix.patch` **is** the merged patch: the diff between the buggy baseline and the fully-fixed tree. This works whether your bug is in the same file as the original fix or a different one. If it now touches a new file, add that file to `files_edited` in `$T/task.toml` (and set `cross_file = true` once it spans more than one).

**Why regenerate instead of hand-merge?** `fix.patch` must be a diff from the buggy `harbor_base` state, **not** the clean base commit — otherwise the hunks for the injected bug won't line up when `solve.sh` runs. Letting `git diff` produce it guarantees correct line numbers.

**Shortcut (disjoint files only):** if your new bug is in a completely different file than the existing fix, a `.patch` is just stacked `diff --git` blocks, so you can append instead of regenerating: `cat fix_add.patch >> "$T/solution/fix.patch"`. If the two fixes touch the same file, the stacked line numbers won't apply — use the regenerate method above.

### 5. Verify locally

`tests/` and `solution/` are not baked into the image — harbor mounts them at `/tests` and `/solution` — so mount them yourself:

```shell
docker build -t task-env "$T/environment"

# Buggy state -> the new f2p test should FAIL
docker run --rm -v "$T/tests:/tests:ro" task-env bash -lc 'bash /tests/test.sh; cat /logs/verifier/reward.txt'

# After the oracle fix -> all tests should PASS
docker run --rm -v "$T/tests:/tests:ro" -v "$T/solution:/solution:ro" task-env \
  bash -lc 'bash /solution/solve.sh && bash /tests/test.sh; cat /logs/verifier/reward.txt'

# Leak check -> all three must print nothing
docker run --rm task-env bash -lc '
  ls /tmp/bugs /app/.harbor_assets/bugs 2>/dev/null
  ls /app/.harbor_assets | grep -v -e "\.png$" -e "\.jpe\?g$" -e "\.gif$" -e "\.webp$"
  find /app -mindepth 1 -newer /app/package.json \
    -not -path "/app/.git*" -not -path "/app/.harbor_assets*" | head'
```

The buggy run should show reward `0`, with your new f2p test `fail` in `/logs/verifier/reward_detail.json`. If it shows `missing`, the test never ran or its name doesn't match. The oracle run should show `1`.

Then re-establish the real gate through the runner (Task-Playbook Step V): `bash ~/.claude/skills/mmswe-runner/mm_run.sh /home/sandbox/Tasks/*/ oracle` (1.0) and `... nop` (0.0).

## Key rules

- Apply bugs **before** the `git init … tag harbor_base` step, or the snapshot won't contain them, and **before** the V2 timestamp step (`find /app -mindepth 1 -exec touch …`), or the patched files stand out by mtime.
- **Never** put test files in a bug patch. The verifier resets `test.patch` paths to `harbor_base` and re-applies its own tests, so those edits are discarded.
- Every bug needs a matching `f2p` test — in `task.toml` **and** `tests/config.json` — or the model gets no reward for solving it.
- Keep `solution/fix.patch` in sync so the oracle still passes, and `files_edited` in sync with it.
- V2 layout: bug patches in `environment/bugs/` (Dockerfile `COPY bugs/ /tmp/bugs/`), never in `environment/assets/`; `assets/` holds only the manifest-listed evidence.
- No bug patch may survive in the final image. Run `rm -rf /tmp/bugs` in the apply `RUN`. Keep the V2 screenshot `COPY` naming the files one by one. If the Dockerfile copies the whole `assets/` folder, also `rm -rf /app/.harbor_assets/bugs`.
- Scratch work (the repo clone, `fix_add.patch`) stays outside `Tasks/`: everything inside `Tasks/<task_id>/` is the deliverable.
