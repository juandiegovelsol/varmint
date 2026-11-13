---
description: QC and fix an MM SWE task in the sandbox (no API key), then reproduce the gate
---

QC and repair the task the CB names. No API key is needed for any of this.

**Nothing is changed or run without the CB's explicit go-ahead.** The tool enforces this itself —
writes need `--apply`, docker runs need `--run` — so never pass either flag until the CB has said
yes to that specific step. Do not add them "to save a round trip".

1. Locate the task folder (usually `/home/sandbox/Tasks`, or the folder holding `Tasks/`). Both layouts work:
   flat `Tasks/task.toml` and nested `Tasks/<task-name>/task.toml` (any name). If `Tasks/` holds
   several tasks, the skill stops and names them - pass the one you mean.

2. `python3 ~/.claude/skills/mm-swe-qc-fix-sandbox/fix.py qc "<path>"` — **one command, the whole
   picture.** It runs the five checks *and* the live repair plan, joined: every finding, plus a
   `PROPOSED FIXES` section that is the authoritative preview of what `--apply` would touch, plus
   the `MODIFIED:` / `GATE:` decision. There is no second command to run before you can report.

   Then **write the audit up yourself, in the chat, in your own words.** Do not paste the raw
   report and call it a day: it is dense, uses ids and tier labels, and is built to be parsed as
   much as read. The CB wants a colleague's assessment, not a tool dump.

   For each finding that matters, tell them three things:
   - **what is wrong**, in plain language, naming the file;
   - **why it matters** — the consequence for the task, not the rule it violates. "harbor will
     record no reward at all, so the run looks scored but stores nothing" beats "non-numeric
     reward.json values";
   - **what you propose to do**, and whether it is mechanical or needs their judgment.

   Lead with the worst thing. Group the rest so it can be skimmed. Say explicitly what is **fine** —
   a list of only problems reads as if the whole task is broken. And state what was **not checked**
   (`GATE: not reproduced`, `TRIAL: n/a`) rather than letting silence imply it passed.

   Keep the raw output for when they ask, or when a specific detail (a sha, an exact key) is the
   evidence. One short quoted block is fine; the whole 40-line report is not.

   **Say it in words, not in ids.** `instr_solvable_without_image`, `reward_json_nonnumeric` and
   `s_fix_patch_spans_2` exist so `--approve <id>` can name a fix — they are not English. Translate
   every one using the glossary beside this skill:

       ~/.claude/skills/mm-swe-qc-fix-sandbox/FINDINGS_GLOSSARY.md

   Add the id in parentheses only when the CB will need to type it.

   **If any `env_*` or `heredoc_*` finding is present, lead with it.** Those are group E — the
   `environment/Dockerfile` has stopped being able to host the harness — and they are BLOCKING.
   Explain the consequence, not the rule: harbor installs the agent CLI *into* the image (`curl` on
   glibc bases, `npm install -g @anthropic-ai/claude-code` on apk ones), so the trial does not score
   badly, it **dies at startup** — `exit 127: curl: command not found` — and nothing cheaper catches
   it first, because oracle and nop install no agent and still score 1.0/0.0 while `harbor check`
   reads the bundle rather than the built image. Name what was removed, or which instruction only
   builds on a modern BuildKit. `heredoc_to_run` is mechanical; `heredoc_manual` means the shape was
   declined on purpose and is yours to rewrite. Un-stripping deleted binaries is offered as `ask`
   unless `[agent] network_mode = "no-network"` already seals the agent phase — if it is not sealed,
   that fragment is the only egress control the task has, so seal the phase first and say why.

   Once group E is clean, the optional dynamic confirmation is — like any docker run, **only with
   the CB's go-ahead**, since it builds the image:

       bash ~/.claude/skills/mm-swe-qc-fix-sandbox/checks/qc_env_probe.sh "<path>/Tasks"

   It asks the built image directly (`command -v` per harness binary, the npm registry, `/etc/hosts`,
   a writable `$HOME`, the `harbor_base` tag), so it catches what reading the Dockerfile cannot: a
   private base, a multi-stage `COPY`, a non-root `USER`. Keyless, no model call. **A green probe is
   not a clearance** — report it as "the harness runs on this builder", never as "group E passed". It
   prints its own portability caveat whenever the Dockerfile writes `/etc/hosts`, and the static
   finding stays authoritative.

3. **Settle test fitness — the audit cannot.** The report always carries
   `overfit_not_settled_statically`. That is not a formality: `check_O` reads test source only,
   while the rubric defines overfit against precedent in the REPOSITORY and against the posters,
   and nothing static reaches UNDERFIT at all (nop proves the empty diff fails, which says nothing
   about a plausible wrong fix). Follow
   `~/.claude/skills/mm-swe-qc-fix-sandbox/TEST_FITNESS.md`:

       python3 ~/.claude/skills/mm-swe-qc-fix-sandbox/fitness_digest.py "<path>" --out /tmp/digest.md

   then open BOTH posters yourself and judge in the container. Report a band —
   `[Fail - Overfit Tests]` / `[Non-Fail - Slightly Overfit]` / `[5]` — plus what you did NOT test.
   Never report "the tests are fair" without saying which alternatives you actually ran: that
   sentence is the one this whole check exists to stop being guessed at.

   **The `tests_overfit_*` findings block, and they run on a three-step workflow.** (1) Report each
   one in plain words — what the test pins, and which alternative implementation it would reject.
   (2) **Ask the CB whether to inspect it, and wait.** Do not investigate unasked and do not rule
   unasked: settling one means opening the posters and often building a container, so authorising
   that is theirs. Do not ask them to adjudicate it either — that is the analysis they have you
   for. (3) If they say yes, investigate: build the digest, open the posters, read the test *body*
   rather than the diff, check the "the golden fix introduces this" claim against the base tree,
   and run the alternative in the container.

   Then rule. What the evidence shows to be a **false positive you clear yourself**, quoting the
   evidence — the ruling is recorded and replays on later audits, so it holds for every run and the
   CB never types a flag. What it shows to be **real is a defect to fix**, not to clear.
   Inconclusive: say so and go back to the CB. Never clear one you have not inspected.

   Apply the outcome with `fix.py` directly, or by re-running the check with the flag appended —
   the runner forwards it:

       python3 ~/.claude/skills/mm-swe-qc-fix-sandbox/fix.py qc "<path>" --gate-tier bundle \
           --adjudicated <id>=cleared:"what you checked and why it is fair"

   Skip the deep procedure only when the CB asks you to, and say so when you skip.

4. **Judge whether the task needs its images, and warn either way.** The audit raises
   `instr_solvable_without_image` with the evidence it gathered and a *lean* — it deliberately
   does not decide. You do:

   Read `instruction.md` **with the image assets set aside** and answer one question: could a
   competent engineer locate *and* fix this defect from the prose alone? Then tell the CB, as a
   **warning — never a blocker**, whichever way it lands:

   - **Prose alone is enough** → warn that the poster is decorative: an MM SWE task that never
     needs the image does not exercise perception and is easier than its `task_type` claims.
   - **Prose alone is not enough** → that is the intended shape. Say so, and name what the image
     has to supply (the mode, the variant, the visual symptom) so the CB can confirm the poster
     genuinely supplies it. If it does not, the task is unsolvable — that *is* a #15 concern.

   Quote the specific phrase that decided it (`"the display mode shown in the attached
   screenshot"`), not just the verdict. Never let this stop the flow or change your recommendation
   about applying fixes.

5. **Ask once, for the whole golden-format repair.** The CB is not a harbor expert — they cannot
   judge these fixes better than you can, and asking them item by item just converts your context
   into their round trips. So put **one** question: may I bring this task up to the golden format?
   List what that covers, in words, and say plainly that it includes edits you will make yourself.

   Then run what they approved:
   - `fix.py auto "<path>" --apply` — apply the AUTO fixes (no docker).
   - `fix.py auto "<path>" --run` — reproduce the gate (oracle 1.0; nop with every f2p
     failing and every p2p passing).
   - `fix.py auto "<path>" --apply --run` — both.
   - `fix.py apply "<path>" --approve <id>,<id>` — only the fixes they named. Naming an id is
     itself the approval, so this needs no `--apply`.

   **Two things still get their own `AskUserQuestion`**, because they destroy content or turn on
   task knowledge you do not have — never because of permission:
   - **a deletion** — an unreferenced asset or a stray file. An unreferenced image may still be the
     task's visual source, and removing it invalidates the trial. One question each, never bundled.
   - **the rubric mode, either direction** — A→B deletes `rubrics.json` and `judge.py`; B→A is
     authoring what the task grades. Give them the evidence and your lean, and let them pick. Once
     they have, the *wiring* for that mode is yours and needs no second question.

6. **Then do the `AGENT REPAIRS` yourself — do not go back and ask again.** `--apply` prints a list
   of blockers no script may write (the `0.5` reward ladder, a judge with no API backend, the
   verifier reward block). Each names the exact sites, the `RUBRIC_MODES.md` section documenting the
   repair, and the command that proves it:

       [agent] [B] verifier_reward_domain: tests/verifier.py can emit a reward outside {0, 1}
                 → line 126: tests_passed = 0.5
                 read:   RUBRIC_MODES.md §2 (and §2c for the contract)
                 prove:  python3 checks/qc_rubric_format.py <Tasks> | grep reward_domain

   Read the playbook section before editing — it says what must **not** change, which is the part
   that stops a repair from quietly altering what the task grades. Then run the `prove:` command and
   **show the `[OK ]`**. A repair you did not verify is reported as unproven, never as done.

   **Finish by re-running `fix.py qc "<path>"`.** That is what shows the blockers actually cleared,
   and it is the only evidence worth reporting: the audit comes back with no blocking defects, and
   the verdict line says so.

   If instead you see a line naming blocking defects — `N blocking defect(s) must be fixed first:
   …` — then blockers remain. Say so and name them. Never report the task as fixed without a clean
   audit behind it.

7. **After fixing, ask whether to run oracle and nop — and only when it is warranted.** A docker
   run costs real time, so never ask for one reflexively. `apply` and `auto --apply` print the
   answer; do not infer it:

       MODIFIED: yes — 2 fix(es) applied: judge_drift, rubrics_shape
       GATE: MUST be re-reproduced — the bundle was modified, so the previous
             rewards describe files that no longer exist

   - **Something was modified** → ask, and say *why*: you changed the bundle, so the existing
     oracle/nop rewards describe files that no longer exist. Offer
     `fix.py verify "<path>" --run` and mention it is keyless and bounded by `$MM_RUN_TIMEOUT`.
   - **Nothing was modified and the gate is current** → **do not ask.** Say plainly that no re-run
     is needed because nothing changed, and stop. Asking anyway wastes their time.
   - **Nothing was modified but the gate is unproven** — never reproduced, or the last run predates
     the bundle — → still ask, and be precise that this is not because of anything you did: the
     gate was never established for these files. "We changed nothing" is evidence that nothing got
     worse, not evidence that the gate holds.

8. Exit codes: **6** nothing applied, nothing happened · **4** the gate broke · **5** applied but the gate
   is unproven. Report 4 and 5 as failures, never as success. **6** means you have not done
   anything yet — say so plainly rather than implying the task was fixed.

9. If a class-C fix was applied, tell the CB the trial must be re-run and let them run it. This
   skill never runs the trial.

10. **If the task has a real rubric**, the gate run leaves a judge request under
   `<ROOT>/Oracle/<task-folder>__xxx/verifier/judge`. Grade it yourself — read `criteria_payload.json`
   against `source.txt` (which IS the golden fix, because oracle applies `solution/fix.patch`) —
   and report each criterion pass/fail.

   Any criterion the **golden fix** fails would fail every correct submission: report it as a
   Major "Incorrect Criterion" and say which criterion and why. Write nothing; there is no
   `rescore` step and no verdict file to produce. An always-pass stub needs none of this.

Pre-trial is the normal case: `fix.py qc` is fully useful with only `Tasks/` present. Findings that
need artifacts which do not exist yet are reported as `OPEN [needs …]`, never as failures, and they
never affect the exit code.
