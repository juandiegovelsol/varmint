# Test fitness — are the tests fair, and do they discriminate?

Two questions, opposite ends of one axis:

- **overfit** — a test penalises an implementation that correctly does what was asked
- **underfit** — a test passes an implementation that does NOT do what was asked

Neither is decidable from the test source alone, and this document exists because QC tried that and
got it wrong. The scoring rubric defines overfit in terms of the REPOSITORY:

> A **valid** implementation solves the prompt's explicit requirements while not actively clashing
> with the repo's implicit expectations (design patterns, naming conventions).
> A **plausible** implementation is a valid implementation that also has **any precedent in the
> repo** — if a pre-existing function handles something by doing XYZ, an implementation that also
> does XYZ is plausible. Where the repo had no opportunity to set a precedent, general practice
> stands in.

"Precedent in the repo" is not computable from a diff. It is read off the codebase. So this
procedure runs with the codebase open, not with a scanner.

    [Fail - Overfit Tests]      a test penalises a PLAUSIBLE implementation, or is pinned to the
                                golden (exact names, bytes, layout, an asserted source/CSS string)
                                without cause
    [Non-Fail - Slightly Overfit]  a test penalises a VALID implementation that is not plausible
    [5]                         no test penalises a valid implementation

## The three references — all of them, every time

A test can only be too narrow or too loose RELATIVE TO WHAT WAS ASKED. Judging it against the
golden alone tells you whether the tests match one implementation, which is a different question.

| reference | supplies | where |
|---|---|---|
| `instruction.md` | what is asked, in words | the bundle |
| the posters | what is asked, visually | `environment/assets/` — **open them** |
| the repo | what a plausible implementation looks like | the container, at `/app` |

**The posters are not optional.** On a `visual_essentiality = required` task the image carries
requirements the text deliberately omits — band counts, edges, status wording, layout.

**But "the poster shows this value" is NOT enough to call an assertion fair.** A poster shows ONE
correct rendering, not the space of correct renderings. The question is:

> Is the asserted value FORCED by the requirement, or is it one of many values that satisfy it?

- **FORCED → fair.** A caption reading `avg kept 89%` is computed from the fixture's own samples;
  every correct implementation that averages them gets 89%. There is no other right answer, so
  pinning it pins the requirement.
- **ONE OF MANY → OVERFIT, even though the poster shows it.** If the reported defect is "the border
  is misaligned" and the reference renders it at 10px, then 8px and 12px also fix the defect.
  `spacing === 10px` penalizes a valid, plausible implementation: the test has pinned a CHOICE the
  golden made, not a requirement the task stated.

The distinction is whether the instruction or image establishes the value as *the requirement*, or
merely *displays* one implementation of it. Read what is ASKED. "The borders have no visible edges"
asks for visibility, and any spacing achieving it is correct. "Present the reading as the reference
shows it" makes the reference's layout the requirement, and then its counts and edges ARE the spec.

**This is runnable, and it is the cheapest experiment here.** Change the implementation to a
DIFFERENT value that still satisfies the stated requirement, then run the test:

- still passes → the assertion tolerates the alternative; fair
- fails → the assertion is pinned to the golden's choice; **OVERFIT**

Do this for every exact numeric, colour, spacing or string literal whose value is not visibly
computed from the fixture data. Two seconds, and it turns the hardest judgment in the rubric into
a measurement.

## Setting up (once per task)

The image is the same one oracle and nop use, so the build is amortised, not spent twice.

    docker rm -f qcfit 2>/dev/null                     # idempotent: a stale one blocks the name
    docker build -t qcfit <task>/environment/          # ~3 min cold, ~1s warm
    docker run -d --name qcfit qcfit sleep 7200
    docker cp <task>/tests/test.patch qcfit:/tmp/
    docker exec qcfit sh -c 'cd /app && git apply /tmp/test.patch'

`/app` is the repo at `base_commit` with the defect patches applied — exactly what the agent sees.
After `git apply` it also holds the graded tests. Two suites, run differently (check `tests/test.sh`
for the task's own invocation):

    docker exec qcfit sh -c 'cd /app && npx vitest run test/unit/<file> -t "<test name>"'
    docker exec qcfit sh -c 'cd /app/apps/gittensory-ui && npx vitest run <path> -t "<test name>"'

One test runs in about **2 seconds**. That is the whole point: where judgment runs out, you measure
instead of arguing.

## Procedure

Read `instruction.md` and open BOTH posters first. Everything after depends on knowing what was
asked, and half of it is only in the image.

Then, per graded test:

**1. What does this test actually assert?** Read the body in `/app`, not the diff — the diff hides
the helpers. Note that a test may assert without `expect`: `getByText`/`findBy*` throw on miss, and
an explicit `throw new Error(...)` is an assertion. A test that appears to assert nothing usually
does; confirm before believing it.

**2. Is what it asserts ASKED for?** Check the instruction text, then the posters. If neither asks
for it, that is not overfit — it is an **unasked instrument**, and it generates invalid fails: the
agent is scored on a requirement it was never given. Report it as such.

**3. Would a PLAUSIBLE implementation satisfy it?** This is the overfit question, and it is answered
against the repo:
  - grep for how the codebase already does this thing. A different-but-conventional approach is the
    one to test against — an experienced contributor follows the repo's patterns.
  - if the assertion pins something an alternative would legitimately vary (a helper name, an
    internal shape, a class, a byte-exact string, DOM structure) → likely overfit.
  - if it pins an exact value, apply the FORCED-or-one-of-many test above. Visible in the poster is
    NOT sufficient: ask whether a plausible implementation could produce a different value and
    still satisfy what was asked. If it could, the assertion is overfit however faithfully it
    matches the reference.
  - **verify claims about what the golden "introduces" before relying on them.** A symbol appearing
    on the added side of `fix.patch` may well predate it; `grep` for it in the base tree. Getting
    this backwards is the single most common false finding.

**4. Where step 3 is not conclusive, measure.** Edit `/app` into the alternative implementation and
run the affected test. Two seconds, and the failure message names the assertion. This is the only
step that PROVES anything; everything above is judgment.

**5. Underfit, the other direction.** For each test ask what a wrong implementation would have to
get right to pass it. Then make that wrong implementation in `/app` and run it — the canonical three:
  - **literal writeback** — return exactly the values the test observes, with none of the behaviour;
  - **the shallow fix `difficulty_explanation` predicts** — the metadata usually names what a lazy
    attempt does; make that exact attempt (this also checks whether the metadata's claim is true);
  - **the partial fix** — repair one of the N affected surfaces and leave the rest.

A wrong implementation that PASSES is a finding: the suite cannot tell it from a real fix.

## Reporting

Report per test, with the reference that decided it:

    FAIR      <test>  — asserts "avg kept 89%"; computed from the fixture samples, so every
                        correct implementation produces it (forced, not a choice)
    OVERFIT   <test>  — asserts the helper name `foo`; the repo's own pattern names it per-module
    UNASKED   <test>  — asserts X; neither instruction.md nor either poster asks for it
    UNDERFIT  <test>  — the literal-writeback probe passed it

State what you did NOT test. "These three wrong implementations all failed" is honest; "the tests
are tight" is not — you tested what you wrote and nothing else.

## Harness-level fallback

When a verdict needs the real scoring path rather than a single test — a whole alternative fix, or a
probe scored end to end — the runners take a patch and give a reward:

    fix.py variant <task> --patch v.diff --label <l> --run    # expects 1.0
    fix.py probe   <task> --patch p.diff --label <l> --run    # expects 0.0

They copy the task, swap `solution/fix.patch`, rewrite `files_edited` to match, mint an isolated QC
pass, and run the oracle. About 60s each versus 2s for a single test, so reach for them when the
question is genuinely about the whole suite. `variant` scoring < 1.0 is reported as UNRESOLVED, never
as overfit: an incorrect variant failing a test indicts nothing, and only you can tell which it was.

## Teardown

    docker rm -f qcfit
