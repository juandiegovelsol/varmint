# Plain-language glossary for QC findings

Finding ids exist so `--approve <id>` can name a fix and so `qc_report.json` can be parsed.
**They are not English.** Never paste one at a CB as though it explained itself. Say what is wrong
in a sentence they could repeat to a colleague, and add the id in parentheses only when they will
need to type it.

| Instead of the id | Say something like |
|---|---|
| `instr_solvable_without_image` | "Can this be fixed without looking at the screenshots?" |
| `instr_lint_leak` | "the instruction names something the Lean Instruction Playbook says to cut — a repo name, URL, issue or PR link, a source file, a function or code name, a size, or error text. Each one points the agent at the cause instead of leaving it to the images" — **advisory, never blocks** |
| `instr_lint_cause_word` | "the instruction uses a word the golden fix's own changed lines use (e.g. *radius* on a radius fix). If it names the thing that looks wrong, keep it; if it names the cause, cut it" — **advisory, never blocks** |
| `instr_lint_vague` | "the instruction doesn't say what's wrong — a general phrase stands alone (*something does not render correctly*, *charts come out wrong*) with nothing right after it saying what's affected, what kind of problem it is, or which image shows the correct result; or the affected element is never named by type (*it flickers*); or the element is named but the text never says what kind of problem it is nor points to the correct result. Name the element, and either give one plain word for the defect (*empty*, *spiky*, *missing*) or point to the image that shows the correct result, without naming the cause" — **advisory, never blocks**. The first evidence line says whether a model (Sonnet 5) or the phrase scan read it |
| `instr_lint_time_window` | "a time window (*0:02–0:05*) or a region (*in the frame centre*) is doing all the explaining. It's fine next to the element and a plain defect word, as in luanti; on its own it's an unspecific symptom" — **advisory, never blocks** |
| `instr_lint_hints_fix` | "the instruction describes the cause, the mechanism or the fix (*the radius is computed from the wrong axis*). Say what looks wrong; why it happens is for the agent to find" — **advisory, never blocks**, model read only |
| `instr_lint_clue_leak` | "the text gives away a clue the image is meant to keep: which instance, what triggers it, how big it is, when it happens, the error text, or an expected result precise enough to point at the cause. Keep the element and the kind of problem in the text, and point to a reference image (*should look like reference.png*) when the expected result would give it away" — **advisory, never blocks**, model read only |
| `instr_lint_undescribed_defect` | "the tests grade a behaviour the instruction never states and never points to an image for, so the agent can't know it's part of the task and will read the mismatch as intended — e.g. a test checks the moons are numbered from one, and the text only describes how one moon is drawn. Name the element and the kind of problem, or point to an image that shows it" — **advisory, never blocks**, model read only. Each line names the test |
| `instr_lint_vouches_defect` | "a sentence or image caption tells the agent to trust exactly what a graded defect changes — *what the screenshots show about this moon and its neighbours is correct*, or a caption calling the labels *the game's own names*, when the names are the defect. Narrow it to what really is correct, and state the defect" — **advisory, never blocks**, model read only |
| `instr_lint_misdescribed` | "the instruction calls the problem a different kind than it is — e.g. a console crash described as a problem in a rendered image — so the agent would look in the wrong place" — **advisory, never blocks**, model read only. Judged against the difficulty explanation when `task.toml` has one |
| `instr_lint_no_image_truth` | "the instruction never says the images are correct apart from the defect, so anything else they show — labels, numbering, an injected second bug — gives the agent no signal" — **advisory, never blocks** |
| `instr_lint_vague_truth` | "a sentence says the images are *correct* without saying what is correct — *what the screenshots show … is correct*, *everything else is correct*. The agent is told to trust the images but not which parts, so name them (*the moon names, their numbering and the orbit order … are correct*)" — **advisory, never blocks** |
| `instr_lint_no_reference` | "the instruction doesn't point to what correct looks like — an expected screenshot, or the good part of the same recording" — **advisory, never blocks** |
| `instr_lint_clean` | "the instruction wording scan found nothing" (an OK line, not a finding) |
| `instr_lint_symptom_clean` | "the instruction read found no unnamed element, standalone general phrase, bare time window or region, hint at the fix, clue leak, misdescription, undescribed graded defect or sentence vouching for one" — the line names who read it: the model, or *static phrase scan* when no model was reachable, which checks only the first three (an OK line, not a finding) |
| `tests_agnostic` / `tests_overfit_*` | "Would a different valid fix still pass the tests?" — the whole family is **candidate-only and never blocks**. Each one names *what the test pins* and *which other implementation that pin would reject*; none of them says how to rewrite the test, because the call is the CB's |
| `tests_overfit_internal_state` | "this test reads something the golden fix invented and a caller can't see — so it's testing this particular decomposition, not the behaviour the instruction asks for. Using the repo's own privates is fine; using ones the fix created is what this flags" |
| `tests_overfit_private_import` | "the test file imports a name the golden fix introduces, so a fix that solves the same thing without declaring that name dies at import, before any assertion runs" |
| `tests_overfit_mock_internal` | "the test mocks a piece the golden fix created. That presumes the solution is split up that way — mocking a real boundary (network, filesystem, clock) is fine and isn't flagged" |
| `tests_overfit_call_assert` | "the test asserts something *was called*, with given arguments — an assertion about how the work is done, not about what comes out" |
| `tests_overfit_structure_pin` / `tests_overfit_instance_pin` | "the test pins the shape of the result (exact key set/order, or the concrete type) rather than the result. Fair if that shape is a documented public schema; not fair if it's this implementation's own arrangement" |
| `tests_overfit_setup_internal` | "the test primes internals the golden fix introduced before acting, so it can only run against an implementation that has them" |
| `tests_overfit_mechanism` | "the instruction asks for an outcome (an alignment, say) that CSS can reach several ways — flexbox, grid, positioning — and the test asserts the one the golden picked. Every other correct answer fails on its choice, not its result" |
| `tests_overfit_magnitude` | "the golden happened to use 10px and the test asserts 10. A fix that lands the same visual result at 11 fails an assertion it actually satisfies. Only fires for numbers the fix ADDED and the instruction never states" |
| `tests_overfit_unnamed_assertions` | "the patch also changes assertions inside tests QC can't put a name to — those hunks edit one line deep in an existing test, so the diff's context shows the enclosing function and never the test's name. Same pin as the per-test findings; this one says how far it reaches" |
| `tests_overfit_coverage` | "how many of the declared f2p QC could actually inspect. Not a defect — it's there so a short list of candidates isn't read as 'the rest are clean'" |
| `tests_overfit_no_assertion` | "QC could see no assertion in this test at all — a test asserting nothing passes for any implementation, including a broken one. QC slices test bodies textually, so confirm it read the whole test first" |
| `tests_ident_source_unavailable` | "QC couldn't see your pre-existing test names. The bundle doesn't ship the repo, so only `test.patch` was searchable, and reading the files from the repository at `base_commit` didn't work either — the finding says why (no network, a private repo, no `base_commit`). **The Oracle run does not answer this**: `p2p_passed == p2p_total` counts names that *resolved*, and under a containment matcher a name resolves just as happily to a test it only partly matches" |
| `tests_ident_collision_*` | "two of your declared test names might resolve to the *same* testcase, so the verifier would score an arbitrary one of them. **PENDING, not a failure** — open the `tests/verifier.py` line the finding cites, decide whether both names can match the same key, then re-run with `--adjudicated <id>=cleared:\"why\"` or `=confirmed:\"why\"`. The ruling is recorded and replayed by later audits, so you type it once; it lapses by itself if `tests/` or `solution/` changes" |
| `tests_ident_parametrized_*` | "your test names are built in a loop whose parameter list QC can't read, so it can't tell how many real test names end with your identifier. Same deal: read the loop and record a verdict" |
| `tests_ident_missing_*` / `tests_ident_dynamic_*` | "this specific test name isn't in the test source QC could see — confirm it matches exactly one real test" |
| `overfit_not_settled_statically` | "whether your tests only accept YOUR fix was not decided here, and this line is always printed so an empty candidate list is never read as a clean bill. The rubric judges overfit against precedent in the repo and against the posters; this check sees neither. Run `TEST_FITNESS.md` — it also covers underfitting, which nothing static reaches" |
| `tests_ident_truncated_*` | "this declared name isn't any test's name — it's the start (or the middle) of a longer one, and the full title is in the finding. Your verifier matches by containment, so it *scores anyway*: the reward reads 1.0 and nothing ever tells you the name is wrong. `fix.py` rewrites it in `task.toml` and `tests/config.json` together" |
| `tests_ident_truncated_ambiguous_*` | "same thing, except the truncated name sits inside **two or more** real test names, so there's no single right answer to rewrite it to. **PENDING** — decide which test you meant, then fix it by hand in both files" |
| `tests_ident_ok` | "every declared name is a real test's name in full, resolves to exactly one test, and none of them collide under your verifier's matcher. Read the wording: when the pre-existing tests couldn't be read it says so rather than claiming the names were resolved" |
| `reward_json_nonnumeric` | "`verifier.py` writes values harbor can't read, so runs record no reward at all" |
| `judge_drift` | "`tests/judge.py` differs from the template — usually just the other judge backend, worth a look but not a failure" |
| `judge_missing` | "a rubric ships but `tests/judge.py` isn't there, so it can never be graded" |
| `rubric_file` | "`tests/config.json` doesn't point at the rubric, so it never runs" |
| `rubric_task_id` | "the task id disagrees between `rubrics.json`, `task.toml` and `config.json`" |
| `test_sh_judge` | "`tests/test.sh` doesn't wire the judge in properly" |
| `submission_capture_missing` | "`tests/test.sh` doesn't save what the agent actually wrote, so once the container is gone the only way to re-score this trial against edited tests is paying for another agent run. Advisory — the task is correct as it stands. `fix.py` wires it in" |
| `submission_capture_late` | "the capture is wired, but it runs AFTER `test.patch` is applied, so the saved patch contains the task's own tests as well as the agent's work. The reward is unaffected; the saved submission is just wrong. Move the block above the restore loop" |
| `submission_capture_ok` | "the agent's submission is saved to `submission.patch` before the tests are applied, so this trial can be re-scored later without re-running the agent" |
| `submission_capture` | "the mechanical repair for `submission_capture_missing` — inserts the canonical block after `cd /app`. Only offered when `test.sh` has that anchor and defines $STDOUT_LOG/$STDERR_LOG; otherwise it is left to a human" |
| `rubrics_shape` | "`rubrics.json` doesn't match the expected shape" |
| `rubric_thresholds` | "too many rubric criteria have quality problems to pass the thresholds" |
| `rubric_stub_unfalsifiable` | "the rubric is the always-pass placeholder, so it can never fail" |
| `oracle_stale` / `nop_stale` / `trials_stale` | "the Oracle/Nop/Trials run is older than the current task files, so its reward describes different code" |
| `gate_checksum_mismatch` | "the runs were produced against different versions of the task" |
| `*_recorded_no_reward` | "that run crashed and harbor stored no reward — `reward.txt` looks fine but nothing was recorded" |
| `*_reward_keys_noncanonical` | "the run recorded its rubric result under the old key name (`rubric_pass` instead of `rubric_passed`), so anything reading the canonical name sees no verdict — the judge graded fine, the key is wrong. Rename it in `tests/verifier.py`" |
| `nop_gate_unsatisfied` | "nop's gate did not hold — an f2p test passed on the empty submission, a p2p test failed, or the counts were unreadable. **Not** a statement about nop's `reward`, which is 0.0 whenever any f2p fails and so cannot show this either way" |
| `gate_f2p_inert` | "some f2p tests pass even with no fix, so they can't detect the bug" |
| `gate_p2p_mislabeled` | "some p2p tests fail without a fix — they're really f2p" |
| `gate_f2p_inertness` | "the *result* of asking whether any f2p test passes on an empty submission — the line that says the question was answered, so a clean run isn't read as an unasked one. It reports **OPEN** while `Nop/` doesn't exist yet (during authoring it always does), **OK** once nop shows no f2p passing, and **FAIL** only when nop's `reward.json` gives no way to tell either way. Per-test `f2p::<name>` keys are **optional**: `f2p_passed == 0` out of `f2p_total` already proves no f2p passed, and the keys only matter when some f2p *did* pass, to name which" |
| `agent_unsealed` / `agent_seal_absent` | "the agent phase isn't sealed, so during the trial the agent can just fetch or install the answer — whatever reward it gets proves nothing. Set `[agent] network_mode = \"no-network\"`" |
| `toml_task_missing` / `toml_task_name_missing` / `toml_task_name_mismatch` | "`task.toml` needs a `[task]` table with `name = \"scale-ai/<task_id>\"`, where `<task_id>` is exactly `[metadata] task_id`" |
| `toml_metadata_missing` / `toml_metadata_<key>_missing` | "`[metadata]` must set `task_id`, `title` and `repository_name`, all non-empty" |
| `toml_repository_name_format` / `toml_repository_name_mismatch` | "`repository_name` must be `<owner>/<repo>` and name the same repo as `repo_url`" |
| `toml_identity_ok` | "the `[task]` name and the `[metadata]` identity keys are present and agree" |
| `agent_seal_nonstandard` | "the agent phase is sealed, but not the plain `no-network` both reference tasks use — worth confirming the allowance is actually needed" |
| `env_harness_intact` | "the Dockerfile deletes or masks something harbor itself needs (`curl`, `wget`, `git`, `bash`, `node`, `npm`) — the agent CLI is installed *into* this image, so the trial won't score badly, it will die at startup with `curl: command not found`" **(blocking)** |
| `env_no_fetcher` | "this base ships no way to download the agent CLI and the Dockerfile never installs one — missing and deleted fail identically" **(blocking)** |
| `env_no_bash` | "an apk base with no `apk add bash` — harbor runs every phase under real bash, and busybox ash is not bash" **(blocking)** |
| `env_buildkit_heredoc` | "`COPY <<EOF` *creates* a file from the inline text, which only a modern BuildKit understands — on any other builder `COPY` reads `<<EOF` as a filename and the build dies before the first layer. The file was never mislocated; it never existed" **(blocking)** |
| `env_heredoc_unterminated` | "a heredoc that never closes, or several in one instruction — can't be converted safely, so rewrite it by hand" **(blocking)** |
| `env_syntax_directive` | "`# syntax=docker/dockerfile:1.4` fetches a parser from Docker Hub before instruction one, against a floating tag — a build-time network dependency in a task whose whole point is reproducibility" **(blocking)** |
| `env_copy_source_missing` / `env_copy_escapes_context` | "a `COPY`/`ADD` source that doesn't resolve under `environment/` — `not found in build context`" **(blocking)** |
| `env_npm_registry_blackhole` | "the npm registry is pointed at localhost, and something here actually installs from it — so that install can never resolve" **(blocking)** |
| `env_hosts_build_write` | "a `RUN` writes `/etc/hosts`, which does nothing on either builder and behaves *differently* on each: under BuildKit the write fails and aborts the rest of the `&&` chain, elsewhere it runs and deletes curl. Same file, two images, and a local probe passes on one of them" **(blocking)** |
| `env_nonroot_build` | "the build switches to a non-root user (`su postgres …`), and on this daemon `/` is `drwxr-x---` — so nothing non-root can even load libc. The build dies at that line with `libc.so.6: cannot open shared object file: Permission denied`, which reads like a corrupt base image and sends you hunting in the wrong place. Add `chmod a+rx /` to the *same* `RUN`" **(blocking, auto-fixable)** |
| `env_nonroot_verify` | "the same thing, but in a script the Dockerfile *writes* (a `harbor_pg_start`-style starter). Those lines are just text at build time, so the build passes and it dies later, on the first `test.sh` — where it looks like a broken test rather than a broken image. The script needs its own `chmod a+rx /` as root, because the build-time one doesn't ship" **(blocking, auto-fixable)** |
| `env_user_directive` | "a `USER <non-root>` stanza, which is the one version of this that can't be fixed inside the image: anything you chmod before it has already reverted, and after it there's no root left to redo it. Drop the directive and run as root" **(blocking; no auto-fix)** |
| `nonroot_privilege_drop` | "add `chmod a+rx /` at each place the image drops privileges — in the same `RUN` for build-time ones, inside the generated script for run-time ones. It's additive and does nothing on a normal daemon" *(mechanical; `auto --apply` fixes it)* |
| `nonroot_manual` | "the same defect in a shape the fixer won't edit blind — an exec-form `RUN [\"su\", …]`, a drop in `CMD`/`ENTRYPOINT`, a script built some other way, or a `USER` stanza. Still must be fixed, by hand" **(blocking)** |
| `heredoc_to_run` | "rewrite the heredoc in place as `RUN printf '%s\n' … > dest` — mechanical, byte-identical on both builders, adds no file" |
| `heredoc_manual` | "the same defect, but this shape was declined on purpose rather than guessed at (an unquoted tag, a `RUN` heredoc, several in one instruction) — still must be fixed, just by hand" **(blocking)** |
| `verifier_no_reward_json` | "the run wrote no `reward.json` at all, so nothing about it can be audited per-test — the verifier has to write it (the `verifier_reward_block.py` snippet in `template/tests/`)" |
| `gate_reward_json_unparseable` | "there's a `reward.json` but it isn't valid JSON, so nothing can be read out of it" |
| `trial_not_hard_enough` | "the model solved it inside the time budget" |
| `trial_model_mismatch` | "the trial didn't run on the agreed model" |
| `trial_model_unrecorded` | "the trial neither requested nor reported a model, so which model earned that reward can't be established from the run" |
| `trial_timeout_unauditable` | "the trial ran out of clock *before* the 90 minutes the difficulty clause is written against, because the agent budget was set lower — so 'the model didn't solve it' means 'the model wasn't given 90 minutes', and there's no reward to audit. Raise `[agent] timeout_sec` and re-run" |
| `trial_90min_clause` | "how long the trial actually ran couldn't be worked out from what it recorded, so the 90-minute difficulty clause can't be applied either way. **OPEN, not a failure** — it needs a trajectory with timing in it" |
| `unused_assets` | "an image isn't referenced anywhere — but it may still be the visual source" |
| `asset_not_in_instruction` | "the evidence files cite the image, but `instruction.md` never sends the agent to it — so it isn't dead, it's undirected. `COPY assets/` ships it either way, and if it's an *after* render it's the answer" |
| `junk` / `debris` / `empty_noncanon` | "build leftovers / editor debris / empty files are in the bundle" (`junk` covers `__pycache__`, `.pyc`, `.DS_Store`, `node_modules`, `__MACOSX`) |
| `hardcoded_proxy` | "the task names the litellm proxy directly — the endpoint is injected at run time, so it can't be written into the bundle" |
| `stray_files` | "files that aren't part of the expected layout" |
| `b_poster_*_does` | "one of the screenshots isn't a valid image file" |
| `s_*` (scope) | "the f2p tests cover N distinct behaviours — can a solver tell what each one is from the instruction or the screenshots? (this is about whether they can *find* the bug, not whether the tests are fair — that's `tests_overfit_*`)" |
| `behavioural_rescore` | "the rubric still needs checking against the golden fix" |
| `rubric_stub_only` / `rubfmt_rubrics_stub_only` | "the rubric is a placeholder that can't fail anything, but it still reports as *passed* — so delete the rubric layer instead of stubbing it" **(blocking)** |
| `rubfmt_mode` | "the rubric layer is in neither of the two valid shapes" **(blocking)** |
| `rubfmt_judge_backend` | "the judge can only grade after the run, by hand — so in practice the rubric never gets graded at all. It needs the in-band API backend" **(blocking; one file copy, which also fixes `rubfmt_judge_rubric_json`. Auto when the shipped judge is the stock stub; the agent handles it when the judge was adapted)** |
| `rubfmt_judge_rubric_json` | "`verifier.py` reads a `rubric.json` the judge never writes, so its count of failed criteria is always zero whatever the verdict" **(blocking; closed by the same judge fix)** |
| `rubfmt_verifier_network_mode` | "the verifier phase is sealed, so it can't install what the tests need — the test fails, and a correct fix scores 0. On a rubric task the judge also can't reach the model. It has to be `public`, on every task" **(blocking, auto-fixable; the agent phase stays sealed)** |
| `rubfmt_verifier_env` | "`task.toml` doesn't pass the judge its endpoint and key, so it skips grading. These are `${VAR}` references, not secrets" **(blocking, auto-fixable)** |
| `rubfmt_judge_absent` | "there's a judge but no rubric for it to grade" **(blocking)** |
| `rubfmt_judge_present` | "there's a rubric but no judge, so it's never graded" **(blocking)** |
| `rubfmt_config_rubric_file` | "`config.json` points at a rubric file that isn't there (or is missing the pointer)" **(blocking)** |
| `rubfmt_verifier_reward_json` / `…_keys` | "`reward.json` isn't the shape harbor accepts, so the run records no reward" **(blocking)** |
| `rubric_key_rename` | "the verifier writes the old key name `rubric_pass`, so the rubric result is recorded where nothing reads it — the judge graded fine, the key is wrong" *(mechanical; `auto --apply` fixes it)* |
| `rubfmt_verifier_gate_value` | "a submission that fails the rubric still gets half credit, so the rubric can't actually reject anything — it should score 0" **(blocking)** |
| `rubfmt_verifier_reward_domain` | "a half-finished fix scores 0.5, but the reward is pass/fail only. A partial fix is a fail, so it should score 0 — the f2p counts already show how close it got" **(blocking; the agent repairs it — the report names the exact lines)** |
| `verifier_partial_credit` | "there's a 0.5 somewhere in the verifier — probably half credit or a rubric cap, but it's a keyword match, so read the surrounding lines before treating it as real" *(candidate, not a blocker)* |
| `rubfmt_criterion_*` | "a rubric criterion can't be judged from the diff alone (it leans on the prompt, the screenshots, or a file the fix never touches)" **(blocking)** |
| `a_archive_*_tar_gz` / `a_deliverable_folder_*` | "the packaging isn't assembled yet — only applies when you're about to submit" |


The auto-generated ones (`a_…`, `b_…`, `d_…`, `f_…`, `h_…`, `i_…`, `r_…`, `s_…`) are slugs cut from their
own message text — always reword those; never echo the slug.

If an id is not listed here, read its message and evidence in the report and say that in your own
words. A missing glossary entry is never a reason to fall back to the raw id.
