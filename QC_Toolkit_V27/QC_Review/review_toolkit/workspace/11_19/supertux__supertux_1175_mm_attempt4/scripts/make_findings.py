"""Write QC_Report/findings.json for task112 Attempt4 (SuperTux 1175, V27 review).
Usage: python -I make_findings.py <QC_Report dir> <workspace dir>"""
import json
import pathlib
import sys

out_dir, ws = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
lr = ws / "local_runs"


def det(mode):
    return json.loads((lr / mode / "logs/verifier/reward.json").read_text())


R = {m: det(m) for m in ("oracle", "nop", "oracle_rerun")}
xl = (ws / "xcheck/loo.summary.txt").read_text().splitlines()
xo = (ws / "xcheck/only.summary.txt").read_text().splitlines()


import ast

F2P = [t.split()[-1] for t in json.loads((lr / "Tasks/supertux__supertux_1175_mm/tests/config.json").read_text())["f2p"]]


def xrow(lines, label, mode="fails"):
    for l in lines:
        if l.startswith(label + ":"):
            body = l.split(":", 1)[1].strip()
            if "BUILD FAILED" in body:
                return "BUILD FAILED"
            failed = ast.literal_eval(body[body.index("["):])
            if mode == "fails":
                return f"fails only: {', '.join(failed)}" if failed else "all 20 pass"
            fixed = [t for t in F2P if t not in failed]
            p2p_bad = [t for t in failed if t not in F2P]
            return f"f2p passing: {', '.join(fixed) or 'none'}" + (f"; p2p broken: {p2p_bad}" if p2p_bad else "; p2p 10/10")
    return "missing"


PARTS = [
    ("P2_graze_tux", "player.cpp `collision_tile`: 6 px hurtbox (upstream)", "Tux dies at the spike edge (scene 1, 6.0-6.3 s)",
     "marginal_graze_is_not_lethal, graze_from_the_other_side_is_not_lethal"),
    ("P1_graze_creature", "badguy.cpp `collision_tile`: 6 px hurtbox (upstream)", "hopping creature dies landing beside the shelf spike (0.75-1.0 s)",
     "creature_beside_spikes_survives"),
    ("P3_squish", "badguy.cpp `collision`: squish test uses Tux's bottom edge (bug_01)", "snowball flattened by side contact with big Tux (scene 2, ~10-11 s)",
     "creature_walking_into_tux_hurts_him"),
    ("P4_one_step", "player.cpp `kill`: `else if` (bug_02)", "fire-helmet Tux drops straight to small on one hit (scene 3, ~21-22 s)",
     "powered_up_tux_loses_one_step_per_hit"),
    ("P5_invincible", "player.cpp `kill`: `started()` not `check()` (bug_03)", "star-protected Tux still dies on the spike patch (scene 3, ~24-25 s)",
     "invincible_tux_is_not_hurt_by_spikes"),
    ("P6_blast", "explosion.cpp ctor: centre the blast on its source (bug_04)", "blast drawn below the floor, down-right of the bomb; Tux beside it unhurt (scene 4, 32.5 s)",
     "blast_reaches_left_neighbour, blast_reaches_right_neighbour, blast_reaches_tux_just_above"),
    ("P7_icicle", "stalactite.cpp: right range uses SHAKE_RANGE_X (bug_05)", "left icicle reacts while Tux is still far to its right; the right one waits (scene 5, 34-41 s)",
     "icicle_ignores_tux_far_to_its_right"),
]

xtable = "| part (golden hunk) | what the clip shows | f2p it should own | golden minus this part | only this part |\n| --- | --- | --- | --- | --- |\n"
for p, hunk, clip, f2p in PARTS:
    xtable += f"| {hunk} | {clip} | {f2p} | {xrow(xl, 'all_but_' + p)} | {xrow(xo, 'only_' + p, 'only')} |\n"

N = "Nothing found."
dims = []


def dim(score, category, evidence, wrong, fix):
    dims.append(dict(name="", score=score, category=category, evidence=evidence, wrong=wrong, fix=fix))


# 1 Structure - bundle files
dim(5, "",
    "All 11 fixed files exist and are non-empty: `task.toml` 3,845 B, `instruction.md` 1,199 B, `evidence_bundle.json` 1,071 B, "
    "`environment/Dockerfile` 4,805 B, `environment/assets/ASSET_MANIFEST.json` 586 B, `solution/fix.patch` 3,904 B, `solution/solve.sh` 349 B, "
    "`tests/config.json` 2,600 B, `tests/test.patch` 40,868 B, `tests/test.sh` 10,118 B, `tests/verifier.py` 6,730 B. "
    "The 3 JSON files and `task.toml` parse; `python -m py_compile tests/verifier.py` is OK (`scripts/bundle_checks.py`). "
    "`recording.mp4` decodes: h264, 1280x800, 24 fps, 41.83 s (ffprobe in the task image). "
    "Extra files: `environment/bugs/bug_01..05.patch` (injected defects, applied and deleted in one Dockerfile RUN) and `README.md`. Neither is a fail.",
    N, "")

# 2 Packaging
dim(5, "",
    "`task112/Attempt4/` holds `Tasks/` and `Trials/` as sibling root folders (plus the CB `Oracle/` and `Nop/` runs). "
    "`Trials/without_images/` has 3 trials and `Trials/with_images/` has 4: 7 trials, Option A. "
    "All 7 share the task path pattern `/home/sandbox/.cache/mm_run/trial_tasks/supertux__supertux_1175_mm/task_with(out)_images`.",
    "Nothing found. Non-graded note: this review read the extracted folders; ship `Tasks/` and `Trials/` as separate .tar.gz archives on submission.",
    "")

# 3 Requires visual evidence
dim(5, "",
    "Read without the video, the text lists five aspects (\"how close something has to come before it is harmed\", \"how a meeting between Tux and a creature ends\", "
    "\"what a hit costs Tux, and what keeps him safe\", \"where some harm lands\", \"when some things react to Tux\") and general rules. "
    "It never names an object, file, function, direction, place or time. The leak scan finds no repo name, URL, issue/PR number, file, class or mechanism "
    "(only \"edge\" and \"else\" in plain English). \"Tux\" is the game's hero, which the agent sees in `/app` anyway.\n\n"
    "Trial evidence: all 3 no-image runs fail. Each one misses the 3 spike-graze tests: the graze is the missing upstream leniency, so no line looks wrong. "
    "b6Xarts and bt7R7Gy also miss the 3 blast tests. The asset path `/app/.harbor_assets/recording.mp4` resolves (Dockerfile `COPY assets/recording.mp4 /app/.harbor_assets/`), "
    "and the no-image runs confirm the folder was empty (DKqEdbS / bt7R7Gy: `No such file or directory`; b6Xarts: `ls -la .harbor_assets` → `total 8`).",
    N, "")

# 4 Symptom specificity
dim4_table = (
    "| defect | element as named in the text | defect stated in text? | expected stated in text? | in-clip counterpart | clue left to the clip | described correctly? |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
    "| Tux spike graze | \"how close something has to come before it is harmed\" | yes: \"a slight touch at an edge does not, although in the clip it does\" | yes: \"Only real contact harms Tux or a creature\" | no: every spike approach in the clip is a graze or a full step on | which hazard, where, how deep | yes |\n"
    "| creature spike graze | same sentence (\"Tux or a creature\") | yes (same sentence) | yes | no | which creature, which spike | yes |\n"
    "| side contact flattens a creature | \"how a meeting between Tux and a creature ends\" | no (image) | implied: \"ends the usual way for both of them\" | yes: Tux jumps on the 2nd snowball (correct squish) | side vs top contact | yes |\n"
    "| one hit strips fire → small | \"what a hit costs Tux\" | implied | yes: \"Every hit costs Tux the same single step\" | yes: big Tux → small in scene 2 | which power-up | yes |\n"
    "| star doesn't protect from the level | \"what keeps him safe\" | implied | yes: \"while he is protected nothing can harm him\" | yes: star Tux beats the snowball he touches | which kind of harm | yes |\n"
    "| blast offset down-right | \"where some harm lands\" | no (image) | yes, abstract: \"Harm lands where it comes from\" | no: single blast | direction, size of offset | yes |\n"
    "| icicle reacts early from the right | \"when some things react to Tux\" | no (image) | yes: \"Things react to Tux when he comes near them, as one of them does in the clip\" | yes: the right icicle waits | which side, how far | yes |\n"
)
dim(3, "[Non-Fail - Image-carried Symptom]",
    "The prompt names each defective aspect and gives an expected rule, with a pointer to the clip for the graze and the icicle. "
    "For 3 of 7 defects (side-contact flattening, blast offset, early icicle) the exact defect is only in the clip:\n\n"
    + dim4_table +
    "\nAll 7 statements are true about the clip: five scenes, 41.8 s; edge deaths at 0.75-1.0 s and 6.3 s; blast below the floor at 32.5 s.\n\n"
    "With-image trajectories: **all 4 runs read the edge death as a bug, and none took it for intended behaviour.** "
    "B3yATpy: \"Scene 1: small Tux dies just from brushing the spike's edge\". dPQmVQG: \"Small Tux dies when he only touches the outer edge of a spike, so that's the 'edge' bug\". "
    "fsFz2Ma: \"Jumpy dies grazing a spike, and Tux dies standing next to them\". yFgGjzZ: \"walking Tux dies with his bbox right edge at ~382 while the spike tile starts at 384 — no real contact\". "
    "All 4 also fixed the 5 injected defects. The two failures are wrong fixes, not misreadings: dPQmVQG made `intersects()` strict (not on the tile-hurt path), "
    "and yFgGjzZ shrank Tux's hurtbox by 6 px but the creature's by only 1 px.",
    "The exact defect for side-contact flattening, the blast and the icicle is carried by the clip, and the element words are abstract (\"something\", \"things\", \"harm\"). "
    "That is a non-fail 3 under V27, not a fail: each aspect is named with its context, and no run confused a bug with intended behaviour.",
    "Optional, to reach 5: state the squish, one-step, star and icicle defects in words. Every no-image run already fixes those 4 by reading code, so stating them shouldn't change the "
    "no-image result. Example: \"a creature that walks into Tux from the side is flattened as if he had landed on it; a powered-up Tux loses everything in one hit; Tux under a star still dies on hazards; "
    "a hanging hazard reacts while Tux is still far to one side of it\". Keep the graze and blast lines as they are. "
    "Any change to `instruction.md` changes the task checksum, so every trial must be re-run.")

# 5 Task type
dim(5, "",
    "`task_type = \"temporal_interaction\"`. Every defect is an interaction outcome that plays out over time: when contact counts as harm, how a meeting ends, "
    "what a hit costs, what protects Tux while a timer runs, where a blast lands, and when a hanging hazard triggers as Tux approaches. "
    "The text describes exactly that (\"when some things react to Tux\", \"while he is protected\", \"how a meeting … ends\"). No mismatch.",
    N, "")

# 6 Evidence quality
naming = (
    "| file | role field | what the frames show (how verified) | what name/role/instruction claim | true? | agents confused? |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
    "| `recording.mp4` (neutral name) | `bug_video` | the post-injection base: 5 scenes, edge deaths, side flatten, one-hit strip, star Tux dies on spikes, offset blast, early icicle "
    "(contact sheet + zoomed strips; matches nop failing all 10 f2p) | \"Five short scenes in one lit ice cave… several of the outcomes do not follow the game's usual rules\"; instruction: \"(42 seconds) … five short scenes\" | yes | no: all 4 runs treat it as the buggy state |\n"
)
dim(5, "",
    "**Names and roles:**\n\n" + naming +
    "\n**Does the asset show what the f2p grades?** Cross-checks run in the task image (`scripts/crosscheck.sh`: test.patch applied, then golden minus one part, and only one part, "
    "each with an incremental rebuild and all 20 tests):\n\n" + xtable +
    "\nEach golden part owns exactly the f2p tied to the defect the clip shows, and each defect is in the clip, so fixing the clip passes the f2p and the reverse. "
    "The submitted trials agree: DKqEdbS fixed everything except the graze and failed exactly the 3 graze tests; yFgGjzZ missed only the creature graze; "
    "b6Xarts/bt7R7Gy missed the graze + blast and failed exactly those 6.\n\n"
    "Step 7 (injected defects bug_01..05): skipping any one leaves a real gameplay bug on the core path (squish, damage, star, explosion, icicle), so a fix that skips it is incomplete. "
    "Each one's outcome is shown in the clip. Upstream: issue 1175 (Tux grazes a spike edge and dies) matches scene 1. "
    "`graze_from_the_other_side` tests the mirror case, which the clip doesn't show; a one-sided hurtbox isn't a fix a developer would write, so that is a note, not a mismatch.\n\n"
    "Trial signals: B3yATpy (pass) recalled upstream (\"matches upstream SuperTux's 6px-shrunk hurtbox\"; its curl was blocked). "
    "fsFz2Ma (pass) measured the clip (\"Tux dies with his box about 5px short of the spike\") and wrote its own margin in `collision_system.cpp`, so the clip carries the fix without recall.",
    "Nothing found. Non-graded: the clip shows grazes from one side only (Tux and the creature approach from the left).",
    "")

# 7 task_type metadata
dim(5, "",
    "`temporal_interaction` is one of the seven allowed values and fits a video of timed interactions (contact, hits, protection timer, proximity trigger).",
    N, "")

# 8 Evidence chain
dim(5, "",
    "Disk `environment/assets/recording.mp4`: sha256 `f53c2fa9a3b2edb6…ddc68`, 3,553,582 B. `ASSET_MANIFEST.json`: same file, sha256, bytes, `container_path /app/.harbor_assets/recording.mp4`. "
    "`evidence_bundle.json`: same sha256/bytes, `local_path /app/.harbor_assets/recording.mp4`, `source_kind captured_from_repo`, empty url. "
    "`instruction.md` refers to `/app/.harbor_assets/recording.mp4`. Dockerfile: `COPY assets/recording.mp4 /app/.harbor_assets/`. All four agree.",
    N, "")

# 9 Applies cleanly
dim(5, "",
    "In the task image at `harbor_base`: `git apply --check /solution/fix.patch` → OK (cross-check container log). "
    "Local oracle `solve.sh` exit 0 (\"Applied fix.patch.\"). The image build was 14/14 cache hits from the bundle's own `environment/`.",
    N, "")

# 10 Source-only scope
dim(5, "",
    "`diff --git` paths = `files_edited` = {src/badguy/badguy.cpp, src/badguy/stalactite.cpp, src/object/explosion.cpp, src/object/player.cpp}. "
    "No test, doc, lockfile or changeset path.",
    N, "")

# 11 Overfit
alt = (
    "| alternative | source | complete fix of the clip? | test result |\n"
    "| --- | --- | --- | --- |\n"
    "| hurtbox shrunk 6 px in Player + BadGuy `collision_tile` | golden / B3yATpy | yes | pass 10/10 |\n"
    "| per-axis margin `min(SHIFT_DELTA, half size)` on hurting tiles in `CollisionSystem::collision_tile_attributes` | fsFz2Ma | yes | pass 10/10 |\n"
    "| hurtbox shrink of t px, any t in (~3, ~15.9) | derived from fixture geometry (graze overlap 2.8-3 px; full overlap: 31.8 px box at x 320.1 on a 32 px tile); not run | yes | pass by geometry |\n"
    "| hurtbox 6 px for Tux, 1 px for creatures | yFgGjzZ | **no**: the clip's creature overlaps the spike by ≈2.8 px (same as fixture x 291 + 31.8 vs 320), so it still dies | fails `creature_beside_spikes_survives` (correct) |\n"
    "| strict `intersects()` (`<=`) | dPQmVQG | **no**: tile hurts go through `get_tiles_overlapping`, not `intersects()`; Tux still dies in the clip | fails 3 graze tests (correct) |\n"
    "| blast centred another way (`pos - size/2`, `set_pos(pos); move(-size/2)`) | plausible | yes | pass: tests only need Tux beside or above the bomb to be hit |\n"
    "| invincibility via `get_timeleft() > 0` or `started()` | plausible | yes | pass: tests read only alive/size |\n"
    "| icicle range with `std::abs(dx) < SHAKE_RANGE_X` | plausible | yes | pass: both sides use the X range |\n"
    "| one step per hit via early `return` instead of `else if` | plausible | yes | pass |\n"
)
dim(5, "",
    "Assertions read only outcomes: Tux's y within ±6 px of the small (289.2) or big (257.2) resting height, or \"down\" (far from both), and whether a creature's dead-script printed. "
    "There is no exact count, ordering, string, float equality or log text. Equivalence table:\n\n" + alt +
    "\nEvery rejected variant leaves the clip's defect in place, so rejecting it is the test working. A correct fix written another way (fsFz2Ma's collision-system margin) passed.",
    N, "")

# 12 IDs
dim(5, "",
    "`task.toml` f2p/p2p = `tests/config.json` f2p/p2p (identical lists, no overlap). Each of the 20 ids matches exactly one JUnit testcase (`HazardBehaviour <name>`) in the local oracle and nop reports.",
    N, "")

# 13 p2p
dim(5, "",
    f"All 10 p2p pass on local nop ({R['nop']['p2p_passed']}/10) and local oracle ({R['oracle']['p2p_passed']}/10), and in all 7 trials (10/10 each).",
    N, "")

# 14 f2p
dim(5, "",
    f"All 10 f2p fail on local nop ({R['nop']['f2p_passed']}/10 pass) and pass on local oracle ({R['oracle']['f2p_passed']}/10). "
    "The leave-one-out cross-check (dim 6) shows each f2p is owned by exactly one golden part.",
    N, "")

# 15 Determinism
dim(5, "",
    "The runner drives the real binary (`--renderer null`, no sound) through fixture levels whose init-scripts set positions and print at fixed script times. "
    "The checks are outcome-level (alive/dead, resting height ±6 px), so small frame-timing jitter can't flip them. No network and no font-dependent output. "
    "`test.sh` installs nothing: it runs an incremental cmake build and the tests, so the verifier's `network_mode = \"public\"` is unused. "
    f"Local oracle re-run: reward {R['oracle_rerun']['reward']}, per-test outcome identical to the first run; the CB oracle/nop match the local results; p2p is 10/10 in all 7 trials.",
    N, "")

# 16 Difficulty
dim(2, "[Fail - Trial Threshold Not Met]",
    "No-image: 0/3 pass (DKqEdbS 7/10 f2p, b6Xarts 4/10, bt7R7Gy 4/10), which is correct. "
    "With-image: **2/4 pass** (B3yATpy 1.0, fsFz2Ma 1.0; dPQmVQG 0.0 at 7/10, yFgGjzZ 0.0 at 9/10). Option A needs exactly 1/4. "
    "Every trial is claude-opus-5-5 via claude-code. The with-image checksum `da364b00…` equals the CB oracle/nop checksum; the no-image checksum `67ea7c05…` is the harbor no-asset variant. "
    "Run time (informational): with-image 35.5 / 13.9 / 19.7 / 28.5 min; no-image 5.7 / 9.0 / 9.8 min.",
    "With-image pass@4 = 2/4, over the Option A limit of exactly 1. Only the spike-graze tests separate passing from failing runs: every run fixes the injected squish, one-step, star and icicle defects.",
    "Cheapest route: switch to Option B and run 4 more with-image trials on this same checksum. 2/8 meets Option B (1-2 of 8) if all 4 new runs fail, but at the observed ~50% pass rate that is unlikely (~6-13%). "
    "Otherwise make the graze slightly harder for video runs (e.g. drop \"although in the clip it does\" back toward Attempt1's wording, which scored 0/4), and re-run all 7 trials. "
    "Note: this is the only failing dimension. If your team accepts 2/4 (as you mentioned for task108), the task otherwise meets V27.")

# 17 Real & feasible
dim(5, "",
    "The upstream defect (issue 1175 / PR 1741: hazards hurt on a 1 px graze) is real. The 5 injected defects are believable one-token slips: the wrong box edge in the squish test, "
    "a lost `else`, `check()` vs `started()`, a blast placed on its own centre, and an X/Y constant swap. Each fix is a one-liner a real developer would write. "
    "2 of 4 video runs solved it end to end, and one of them (fsFz2Ma) didn't use upstream recall.",
    N, "")

# 18 Gate
dim(5, "",
    f"Local: oracle **{R['oracle']['reward']}** ({R['oracle']['f2p_passed']}/10 f2p, {R['oracle']['p2p_passed']}/10 p2p), nop **{R['nop']['reward']}** "
    f"({R['nop']['f2p_passed']}/10, {R['nop']['p2p_passed']}/10), oracle re-run **{R['oracle_rerun']['reward']}**, identical per test. Stage banners "
    "(`== applying test.patch ==`, `== running f2p + p2p tests ==`, `== computing reward ==`) and `reward=` are present; no \"could not apply\". "
    "CB runs: Oracle FYVU89L 1.0 (10/10, 10/10), Nop so3yL2B 0.0 (0/10, 10/10).",
    N, "")

# 19 Unauditable
dim(5, "", "A complete, auditable bundle with all runs.", N, "")

gates = [
    dict(label="Local oracle", status="pass", detail=f"reward {R['oracle']['reward']}, 10/10 f2p, 10/10 p2p"),
    dict(label="Local nop", status="pass", detail=f"reward {R['nop']['reward']}, 0/10 f2p, 10/10 p2p"),
    dict(label="Oracle re-run", status="pass", detail="reward 1.0, per-test outcome identical"),
    dict(label="Patch apply", status="pass", detail="`git apply --check /solution/fix.patch` OK at harbor_base; image build all cache hits"),
    dict(label="Verifier completion", status="pass", detail="stage banners + reward= present in every run; no test.patch errors"),
    dict(label="pass@3 (no-image)", status="pass", detail="0/3 (DKqEdbS, b6Xarts, bt7R7Gy all 0.0)"),
    dict(label="pass@4 (with-image, Option A)", status="fail", detail="2/4 (B3yATpy, fsFz2Ma pass); Option A needs exactly 1/4"),
    dict(label="Trial run time (informational)", status="pass", detail="5.7-35.5 min, all well under the 90-min agent timeout"),
    dict(label="Trial / task checksum", status="pass", detail="with-image = CB oracle/nop checksum `da364b00…`; task_manifest.json hashes match all 17 bundle files"),
    dict(label="Packaging", status="pass", detail="`Tasks/` and `Trials/` root siblings, 3 + 4 trials"),
    dict(label="Leaks", status="pass", detail="No repo, URL, file, object, direction, time or mechanism in instruction.md"),
    dict(label="Evidence-chain integrity", status="pass", detail="disk, manifest, evidence bundle, instruction and Dockerfile agree on `recording.mp4` (sha256 `f53c2fa9…`)"),
]

trials = [
    dict(id="task_without_images__DKqEdbS", mode="no-image", reward=0.0, f2p="7/10", p2p="10/10", minutes=5.7,
         failed=["marginal_graze_is_not_lethal", "creature_beside_spikes_survives", "graze_from_the_other_side_is_not_lethal"]),
    dict(id="task_without_images__b6Xarts", mode="no-image", reward=0.0, f2p="4/10", p2p="10/10", minutes=9.0,
         failed=["marginal_graze_is_not_lethal", "creature_beside_spikes_survives", "graze_from_the_other_side_is_not_lethal",
                 "blast_reaches_left_neighbour", "blast_reaches_right_neighbour", "blast_reaches_tux_just_above"]),
    dict(id="task_without_images__bt7R7Gy", mode="no-image", reward=0.0, f2p="4/10", p2p="10/10", minutes=9.8,
         failed=["marginal_graze_is_not_lethal", "creature_beside_spikes_survives", "graze_from_the_other_side_is_not_lethal",
                 "blast_reaches_left_neighbour", "blast_reaches_right_neighbour", "blast_reaches_tux_just_above"]),
    dict(id="task_with_images__B3yATpy", mode="with-image", reward=1.0, f2p="10/10", p2p="10/10", minutes=35.5, failed=[]),
    dict(id="task_with_images__dPQmVQG", mode="with-image", reward=0.0, f2p="7/10", p2p="10/10", minutes=13.9,
         failed=["marginal_graze_is_not_lethal", "creature_beside_spikes_survives", "graze_from_the_other_side_is_not_lethal"]),
    dict(id="task_with_images__fsFz2Ma", mode="with-image", reward=1.0, f2p="10/10", p2p="10/10", minutes=19.7, failed=[]),
    dict(id="task_with_images__yFgGjzZ", mode="with-image", reward=0.0, f2p="9/10", p2p="10/10", minutes=28.5,
         failed=["creature_beside_spikes_survives"]),
]

data = dict(
    task_hash="supertux__supertux_1175_mm_attempt4",
    task_id="supertux__supertux_1175_mm",
    title="Harm in the ice cave does not follow the game's own rules (task112, Attempt4)",
    rubric="Official V27",
    review_date="2026-11-19",
    date_folder="11_19",
    eyebrow="QC review · SuperTux 1175 · Attempt4",
    verdict="FAIL",
    verdict_reason=("Only Difficulty fails: with-image pass@4 is 2/4 (B3yATpy, fsFz2Ma), and Option A needs exactly 1/4. No-image 0/3 is correct. "
                    "The other 18 dimensions pass. Symptom Specificity is a non-fail 3: three of the seven defects are left to the clip. Gate, tests and evidence were verified locally "
                    "(oracle 1.0, nop 0.0, identical re-run, per-part cross-checks)."),
    dimensions=dims, gates=gates, trials=trials,
)
(out_dir / "findings.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
print("wrote", out_dir / "findings.json")

# Dimension names (V27 rubric order), filled after the fact so build_report shows them.
NAMES = ["Structure – Task Bundle Files", "Structure – Deliverables & Packaging", "Instruction – Requires Visual Evidence",
         "Instruction – Symptom Specificity", "Instruction – Task Type", "Image – Evidence Quality", "Metadata – task_type",
         "Evidence – Chain Consistency", "Golden Fix – Applies Cleanly", "Golden Fix – Source-Only Scope",
         "Tests – Implementation Overfit", "Tests – f2p/p2p Identifier Validity", "Tests – p2p Classification",
         "Tests – Discriminating (f2p)", "Tests – Determinism", "Hardening – Difficulty (Model Trial Fails)",
         "Hardening – Real & Feasible", "Gate – Oracle/Nop", "Unauditable"]
assert len(NAMES) == len(dims) == 19
for d, n in zip(dims, NAMES):
    d["name"] = n
(out_dir / "findings.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
print("names filled")
