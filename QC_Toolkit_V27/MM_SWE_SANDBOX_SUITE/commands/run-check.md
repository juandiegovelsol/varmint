---
description: Run harbor check on an MM SWE task (task-quality rubric)
---

Run `harbor check` for the MM SWE task the user names.

1. Locate the task dir (the folder containing `task.toml`: `/home/sandbox/Tasks` in the flat layout, or
   `/home/sandbox/Tasks/<task-name>/` in the nested one - any folder name. Passing
   `/home/sandbox/Tasks` works for both when it holds a single task).
2. Run: `MM_VIA=run-check bash ~/.claude/skills/mmswe-runner/mm_run.sh "<task-dir>" check`

   **`MM_VIA=run-check` is required and is not decoration.** `check` refuses to run without it
   (exit 8), because this command is the only path that reads the findings back to the CB and asks
   before a credentialed run is spent — and a bare shell invocation is indistinguishable from this
   one otherwise. If you see the "runs through Claude Code chat" message, you dropped the variable;
   add it rather than reaching for `MM_ALLOW_DIRECT`, which exists for CI, not for you.
3. The runner verifies the required task files exist first and refuses to spend a run on an
   incomplete task. If that fires, list the missing files rather than passing
   `--no-file-check` — the missing file is usually the real problem.
4. Output lands in `<ROOT>/Check/`. Report each check's PASS/FAIL from `check_report.json`.

Note this grades **the task** (is it well-built?), which is different from the task's own
`tests/rubrics.json`, which grades **a submission**. Don't conflate them.

## The QC gate runs first

`check` runs the MM SWE QC audit before spending the credentialed run — a third pre-flight
alongside the existing file-name and metadata gates, for the same reason: anything decidable
locally is decided before you pay for a model opinion.

**Every finding is printed, in full, always.** The gate uses `--gate-tier bundle`, which separates
what is *shown* from what is *blocked on*: the audit renders at the phase actually on disk, so a
stale Oracle, a broken oracle/nop gate or an inert f2p test appears as a full finding — while only
bundle-tier FAILs can stop the run. A line states the split:

    GATE SCOPE: blocking on bundle-tier FAILs only (1 blocking, 5 shown-but-not-blocking).
      not blocking: gate_checksum_mismatch, oracle_recorded_no_reward, …

**You MUST report every issue to the CB. Never ask whether they want to see them, never summarise
only the blockers, and never withhold the non-blocking ones.** They are looking at their own task;
a defect you saw and did not mention is worse than no audit. Group them so it can be skimmed —
blocking first, then shown-but-not-blocking, then candidates and advisories — but show them all.

### Say it in words, not in ids

The ids (`instr_solvable_without_image`, `reward_json_nonnumeric`, `s_fix_patch_spans_2`) exist so
`--approve <id>` can name a fix and so the JSON can be parsed. **They are not English.** Never
paste one at a CB as though it explained itself. Say what is wrong, in a sentence they could repeat
to a colleague, and put the id in parentheses only if they will need to type it.

Use the glossary shipped with the QC skill — it maps every id to a plain sentence:

    ~/.claude/skills/mm-swe-qc-fix-sandbox/FINDINGS_GLOSSARY.md

Read it when you report. A few for orientation: `instr_solvable_without_image` → "Can this be fixed
without looking at the screenshots?" · `reward_json_nonnumeric` → "`verifier.py` writes values
harbor can't read, so runs record no reward at all" · `oracle_stale` → "the Oracle run is older
than the current task files" · `instr_lint_vague` → "a general phrase stands alone where the defect
should be named — an unspecific symptom". The auto-generated ids (`b_…`, `d_…`, `f_…`, `h_…`,
`i_…`, `r_…`, `s_…`) are slugs cut from their own message text — always reword those.

### Always report the two instruction reads together

Two advisory reads of `instruction.md` are reported **every time, side by side, under "Worth your
eye"**. Neither can block, and neither may be dropped:

1. **Could this be fixed without the screenshots?** (`instr_solvable_without_image`, box 6). Always
   a candidate. Give its lean and the reason in a sentence.
2. **The instruction wording scan** (group L, box 3: the Lean Instruction Playbook check for leaks,
   cause words, unspecific symptoms, bare time windows or regions, a vague "… is correct" truth
   sentence that never says *what* is correct, and the missing "images are correct" and "what
   correct looks like" sentences; plus, from the model read, a graded defect the text never
   describes, a sentence or caption vouching for one, hints at the fix, clues the image should
   keep, and a problem described as the wrong kind). Report **every** `instr_lint_*` hit in
   plain words, quoting
   the phrase the audit flagged and saying what to use instead. When it finds nothing, the audit
   prints `instruction wording scan: clean` on the EVIDENCE & IMAGE line. Say so in one line, e.g.
   "Wording scan: clean, no leaks or vague symptom phrases." **A clean scan is still reported.**
   Leaving it out reads the same as never having run it.

Say who did the instruction read. The first evidence line of each finding from it, and the pinned
`instruction read (…): clean` line, names it: `claude-sonnet-5` (a model read) or `static phrase
scan` (no model was reachable). If it fell back, say so in one line, and say what that leaves
unchecked, e.g. "Instruction read used the phrase scan; the model wasn't reachable, so undescribed
defects, clue leaks, hints at the fix and misdescription weren't checked." A model finding carries a
suggested rewrite; pass it on. For a clue leak, name which clue it gives away (which instance, the
trigger, the size, the timing, the error text, or an expected result that should point to a
reference image). **Lead with an undescribed graded defect**: it is the one most likely to sink the
task, because agents fix what the text describes and read the rest as intended. Say what the test
checks in plain words, and pair it with any sentence or caption that vouches for it.

The scan reads text only, so don't present a hit as a verdict on the images. A `cause_word` hit on a
word that names the *element* (the thing that looks wrong) is expected and fine; say so rather than
telling the CB to cut it.

### Worked example

Bad — a list of labels:

    QC found: judge_drift (FAIL), reward_json_nonnumeric (FAIL), oracle_stale,
    nop_stale, gate_checksum_mismatch, instr_solvable_without_image (CAND)

Good — the same audit, said out loud:

    Two things block the check run:

    - `tests/verifier.py` writes values harbor can't parse, so every run records
      no reward at all — reward.txt says 1.0 but harbor stored nothing. This is
      why your three runs came back empty.
    - `tests/judge.py` has been edited away from the template, which changes
      grading semantics invisibly. One command fixes it.

    Shown but not blocking a check run:

    - All three runs predate your current task files, and Trials was produced
      against a different version again — so none of those rewards describe the
      code as it stands. You'll want to re-run oracle and nop.

    Worth your eye:

    - Can this be fixed without the screenshots? The instruction never names
      forced-colors mode; it says "the display mode shown in the attached
      screenshot". So the image is load-bearing — which is correct for an MM SWE
      task. Just confirm the poster really shows it.
    - Instruction wording scan: one unspecific symptom. "Something does not
      render correctly in the frame centre" uses a generic phrase where the
      defect should be named; give one plain word for what's wrong (empty,
      spiky, missing) without naming the cause. It also links the upstream
      issue URL, which points the agent at the fix; cut it. And "the labels
      overlap only when the window is narrower than 600 pixels" gives away the
      trigger the screenshot should keep; "the labels overlap, as the
      screenshot shows" says the same without it.
      (On a clean scan: "Wording scan: clean, no leaks or vague symptom phrases.")

    Clean: bundle files, golden-fix scope, test identifiers, task_type, evidence chain.

### Fixing blockers costs no check run

Re-auditing is free — `fix.py` calls no runner — so a repair never has to be paid for with a
credentialed run. If the CB asks you to fix the issues:

1. `/qc-fix-sandbox` — apply the mechanical fixes and do the agent repairs.
2. `python3 ~/.claude/skills/mm-swe-qc-fix-sandbox/fix.py qc "<path>"` — confirm the audit comes
   back with no blocking defects.
3. Then run check, if they still want it.

When you report, say which of the three happened — "blockers fixed, audit clean", "check ran with
the blockers overridden", or "clean from the start". They are different outcomes and the CB needs to
know which one they have.

**Exit 7 means "QC found bundle FAILs and nobody could be asked."** You are not a terminal, so the
script refuses to guess. When you see it:

1. Report the whole audit in your own words — worst first, what each means, what you propose.
2. Ask with `AskUserQuestion` whether to **fix the blockers first** (preferred — it is free, where
   spending the run is not) or to spend the check run anyway.
3. Only if they choose to proceed unfixed, re-run with `--no-qc`, and tell them plainly that the
   blockers were overridden rather than fixed.

**Exit 9 means "no blockers, but a finding is waiting on YOU."** This is not a failure and it is not
a variant of exit 7. The audit found no bundle-tier FAILs, but one or more findings are `PENDING`:
the script gathered the evidence and stopped, because deciding them needs a READ it cannot perform.
Until one of them is ruled on, the audit records no QC pass — so no run is spent, and `oracle`/`nop`
stay blocked too. **You rule on the matcher/collision family directly — the overfit family runs on
its own workflow.** Settling a `tests_overfit_*` finding needs the posters, the repository and often
a container, so the CB decides whether that dig happens; once it has, the verdict is yours.

### Report → ask to inspect → rule. In that order.

The checkpoint comes **before** the investigation, and the verdict comes **after** it. Both of the
obvious shortcuts are wrong: listing ids and falling silent leaves the CB holding a finding with no
question attached, and asking "is this pinning deliberate?" hands them the analysis they have you
for.

**1. Report.** Say in plain words what each test pins and which other *correct* implementation it
would reject. Never paste an id as though it explained itself — use `FINDINGS_GLOSSARY.md`.

**2. Ask whether to inspect, and wait.** Use `AskUserQuestion`. These findings are read off test
source alone, so each is a question, not a verdict — and chasing one properly means opening the
posters and often building a container. That is the CB's call to authorise. **Do not investigate
unasked, and do not rule unasked.**

**3. If they say yes, inspect** — `skills/mm-swe-qc-fix-sandbox/TEST_FITNESS.md`:

   - **Read the test body, not the diff** — the diff hides the helpers. Is the symbol imported and
     asserted *by name*, or discovered by behaviour (a probe over exports, a composition check)? A
     behavioural probe pins no name, whatever the finding's token list says.
   - **Check the "the golden fix introduces this" claim** by grepping the base tree. TEST_FITNESS.md
     calls getting this backwards *the single most common false finding*.
   - **Open the posters.** A poster shows one correct rendering, not the space of them — apply the
     FORCED-or-one-of-many test.
   - **Measure where the read runs out.** Build the alternative implementation, run the affected
     test (~2s). This is the only step that proves anything.

**Then rule, yourself.** What the evidence shows to be a **false positive you clear**, quoting the
evidence as the reason — no second round of approval needed, that is what step 2 authorised. The
ruling is recorded and replayed on every later audit, so the gate stays green and **the CB never
types `--adjudicated`**. What the evidence shows to be **real is a defect to fix**, not to clear —
report it as such. **Inconclusive: say so and go back to the CB**; never clear to close the loop.

Report what you ruled and on what evidence, and say what you did *not* test — "the read settles the
name, I did not run the measurement" is honest; "the tests are fine" is not.

If the answer is that the tests should change instead, that is not an adjudication at all — fix the
test and the finding goes away on its own.

Rule on the rest (matcher, collision, parametrization) yourself, as below.

For everything else: Do not report this as "clean", and do not hand it
back to the CB as a question — the decision is a code read, which is your job, not theirs.

1. Open the file and line the finding cites (`tests/verifier.py`, usually the identifier matching).
2. Decide whether the collision it proposes is actually possible **for this verifier's matcher**.
3. Re-run with the ruling appended — **you** run this, never the CB. The runner forwards
   `--adjudicated` into the audit, so it is one command and spends nothing extra: the gate
   re-audits for free and proceeds if it comes back clean.

       MM_VIA=run-check bash ~/.claude/skills/mmswe-runner/mm_run.sh "<task-dir>" check \
           --adjudicated <id>=cleared:"why"

   The flag spelling:

       --adjudicated <id>=cleared:"exact-match on k, so a substring cannot collide"
       --adjudicated <id>=confirmed:"matches with endswith(), so `test_a` also matches `x_test_a`"

   Applying it against `fix.py` directly works too and is equally free:

       python3 ~/.claude/skills/mm-swe-qc-fix-sandbox/fix.py qc "<task>" --gate-tier bundle \
           --adjudicated <id>=cleared:"why"

**You only rule once.** The verdict is recorded and replayed by every later audit, so a bare
`/run-check` afterwards stays clean and `oracle`/`nop` stay unblocked — you do not re-type the flag.
Each replayed ruling is reprinted with its reason, marked `(replayed from an earlier ruling)`, and
**you must still report it**: a verdict the CB decided last week is still a verdict your report is
claiming. A ruling lapses on its own if `tests/` or `solution/` changes, since it was a judgment
about that code; editing `instruction.md` or the posters does not disturb it. To correct a verdict,
pass `--adjudicated` for the same id again — the new ruling wins.

`cleared` drops the finding to OK and the audit then records the QC pass; `confirmed` promotes it to
a FAIL, which is a real blocker to fix (and after the fix, the pass records itself). A reason is
mandatory — the script rejects a bare verdict — and it is quoted back in the report, so write one a
reviewer could check.

**Do not clear a finding to make the gate go green.** `cleared` is what writes the QC pass, so a
reflexive clear is indistinguishable from an audit that never happened, and that is precisely the
failure `PENDING` exists to prevent. Clear only what you have read and can justify from the code in
front of you. **If the matching logic is not clearly collision-proof, `confirmed` is the correct
ruling** — a false blocker costs one fix, a false clear ships a task whose tests can be gamed. If
you genuinely cannot tell after reading, say so and ask the CB rather than guessing in either
direction.

Report the ruling either way: which findings you cleared, which you confirmed, and on what evidence.
"QC clean" with no mention that you adjudicated something is a misleading report.

**"NO QC pass could be recorded" is not a clean result either — and it should not happen.** The audit
found nothing blocking but could not write its record. Where records live is resolved automatically
and falls back when the first location will not hold one, so this no longer fires for the reason it
used to; reaching it now means an internal fault in the audit itself. The check run proceeds, so you
will get a real verdict, but **`oracle` and `nop` will refuse afterwards and that gate has no bypass
flag.** Do not report the run as clean and move on: say the pass was not recorded, that the fix is to
re-run `/run-check` (free), and that it is a bug worth reporting. Left unsaid, this is the one failure
that looks like success right up until the CB tries the controls and cannot get past them.

**Never hand the CB infrastructure to repair.** Do not tell them to clear, chmod, empty or check
`/tmp` or any other directory, and do not name one. Where the record lives is not their concern and
never their mistake — they build tasks, they do not administer the box. The only action you may offer
is re-running the audit.

### Never name the QC records, and never let the CB write one

The audit's two records are internal artifacts with exactly one writer each, and the CB is neither:

- the **QC pass** record is written only by `fix.py`, and only after an audit that actually came back
  without blockers — including on the adjudication path, where your `--adjudicated` ruling is applied
  first and the record follows from the result.
- the **trial** record is written only by the runner, and only on a trial that scored exactly 0.

**Do not name either file, its path, or the directory it lives in, and never suggest — or offer, or
hint, or agree — that the CB create, copy, `touch` or edit one by hand.** A hand-made record is
indistinguishable from an earned one: it would unblock `oracle` and `nop` for a bundle nothing
audited, which is the exact failure these gates exist to prevent. The CB has no reason to know the
filenames, and knowing them only makes that mistake reachable.

So report the *state* and the *one action*, never the artifact and never a directory:

    Bad:  the audit couldn't write <the path the runner printed> — create it yourself to
          unblock oracle
    Bad:  QC passed but <that file> is missing, so oracle and nop won't run
    Bad:  the audit passed but couldn't record it — /tmp looks unwritable, clear it and retry
    Good: the audit passed but the pass didn't record, which shouldn't happen. Re-run
          /run-check — it's free — and flag it if it repeats. oracle and nop stay blocked
          until a pass is on record.

The only supported way to get a pass on record is an audit that earns it: fix the blockers (free) and
re-run `/run-check`. If the CB asks how to bypass the gate, where the record lives, or what they
should go fix, say the record is internal, only a clean audit produces one, and there is nothing on
their side to repair — then point them back at the re-run.

Never pass `--no-qc` pre-emptively. Exit 2 is still the older gates (missing files / inconsistent
metadata) and is not a "spend it anyway" question — those genuinely cannot produce a useful verdict.
Run with a terminal attached and the script asks directly instead.
