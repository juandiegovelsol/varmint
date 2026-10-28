Write the justification and the contributor feedback for this task-hardening job. Print
them in the chat only — do not create, edit, move or delete any file, and do not run
anything that changes the sandbox. Reading files is fine. Everything you need is below —
do not look for an external guidelines document.

CONTEXT
This is a multimodal SWE benchmark task. Each task is one real merged PR: the agent gets
a GitHub issue text plus a screenshot ("the poster") and must produce the code fix. It is
scored by behavioral tests. My job as reviewer was to take a delivered task and raise its
difficulty without breaking the gate: the golden fix must still score oracle = 1.0, the
untouched base must still score nop = 0.0, and a live model trial must now FAIL (< 1.0).

The five hardening levers, by name:
- localization — strip hand-holding from instruction.md (files-to-change lists, named
  CSS property / API / function, step-by-step recipes, corrected-output previews) and
  scrub repo traces (name, URLs, org, issue/PR links) so the agent must find the code
  itself.
- tests — add discriminating fail-to-pass cases, tighten loose assertions, add
  pass-to-pass regression guards. Tests must be behavioral and implementation-agnostic.
- scope — broaden the fix to the cross-file / multi-symptom version so a one-line change
  is no longer enough.
- visual reliance — make the poster genuinely necessary; raise visual_essentiality to
  match.
- anti-cheat — close leaks and scoring holes (tests reset from harbor_base, no source
  string shortcuts, nothing in the agent-visible surface leaking the fix).

INPUTS, in this order
1. There is no copy of the pre-hardening bundle on disk. The "before" side comes from
   this conversation: scroll back over the whole session and list every edit made to the
   task — the original text of each line you changed in instruction.md, the original
   metadata values, every test added or retuned, every file deleted. Work from what the
   session actually shows, not from memory of what you intended. If a change was
   discussed but never applied, it does not go in the write-up.
2. Read the current bundle to confirm the "after" side: instruction.md, task.toml,
   tests/config.json, tests/test.patch, tests/test.sh, tests/verifier.py,
   solution/fix.patch. The bundle is the task folder /home/sandbox/Tasks/<task_id>/
   (the single folder inside Tasks/); every path above is relative to it.
3. Read the run artifacts for the real numbers. They sit beside Tasks/, never inside it,
   and each run dir is named <task_id>__<random>:
   - the oracle run's verifier/reward.txt and the nop run's verifier/reward.txt
     (/home/sandbox/Oracle/<task_id>__*/verifier/, /home/sandbox/Nop/<task_id>__*/verifier/)
   - the check report (/home/sandbox/Check/check_report.json) — each check's outcome, and
     which ones flipped fail -> pass compared to the check run from earlier in this session
   - the trial result (/home/sandbox/Trials/<task_id>__*/verifier/: reward.txt,
     reward.json, and reward_detail.json for the per-f2p/p2p breakdown if present)
   - the analyze result (/home/sandbox/Analyze/analysis.json) — the reward_hacking and
     task_specification outcomes
   Use the numbers from the runs, never numbers you expect the runs to produce.
4. Read the poster in the bundle's environment/assets/ and confirm the facts you claim
   are "only in the image" are actually visible there.

WHAT TO FOCUS ON
Content changes carry the write-up. Those are the ones that change what the agent must
reason about or what the scoring can discriminate: the hint you removed from
instruction.md and what the agent must now derive from the poster instead, the assertion
a new test makes and the wrong fix it now rejects, the symptom you broadened the fix to
cover, the metadata field that was dishonest about the difficulty. Spend the words there.
Structural and plumbing changes are secondary: file layout, renames, deleted stray files,
wiring between test.sh and verifier.py, reward output formats, bookkeeping fields kept in
sync. Compress all of those into one short clause at most, or drop them if they did not
affect what the agent has to do or how the run is scored. Never let a plumbing detail take
more room than a content change.

OUTPUT — print two snippets in the chat, each in its own fenced code block, each a single
continuous paragraph on ONE line with no line breaks inside it, so it can be copied and
pasted into a form field. Plain text only: no markdown, no bullet lists, no headings
inside the snippet. Put a short label line above each block (Justification / Feedback).
Say nothing else except a one-line note under the blocks if something still needs fixing
before submission (an off-schema metadata value, a latent bug, an inconsistency you found
but did not change) — omit that note entirely if there is nothing.

Keep both snippets SHORT. Hard caps: the justification is at most 6 sentences and 160
words; the feedback is at most 5 sentences and 130 words. Being under the cap is better
than hitting it. Cut adjectives, background and restatement before you cut a concrete
fact — if you are over, drop a plumbing detail, never a content change.

Snippet 1, the justification. Name the levers you applied. For each content change: quote
the exact text or line removed or added, before -> after, and say in engineering terms
what a shallow, partial, or recipe-following attempt could get away with before that it
can no longer get away with now. Close with one sentence of gate numbers: oracle, nop,
which check flags flipped, the trial reward with its f2p/p2p split, and the analyzer
verdicts.

Snippet 2, the feedback for the previous contributor. One clause on what was already
sound. Then the main gap, tied to the specific rule it breaks (from the lever list above)
and to the concrete artifact that caught it — a failed check flag, a trial that passed, a
metadata field that contradicts the instruction. Then one habit worth carrying forward,
phrased as something checkable. Smaller items only if they matter, one clause each.

RULES
- Every claim points at something concrete: a quoted hint removed, a named test with the
  assertion it makes, a named file, a specific reward number. "It looked too easy" and
  "I made it harder" are rejected submissions.
- Plain, simple language. No hedging, no filler.
- Do not invent changes. Only write up edits this session actually made. If you cannot
  point to where a change happened, leave it out.

REFERENCE — the length and level of detail expected, from a different task; do not reuse
its content, and note that each of these is one unbroken line in the real output:

  Justification: Hardened on localization and visual reliance. instruction.md no longer
  names the reproduction case ("a left-oriented axis for a linear scale whose domain spans
  0 to 12, with a minimum tick step of 3") and no longer previews the corrected output
  ("every rendered tick step should be at least 3 (e.g., 0, 3, 6, 9, 12)"); only the
  symptom, the minStep value of 3 and the log/time exclusion remain. The orientation,
  domain, scale kind and buggy step of 2 now exist only in bug.png, so an agent that skips
  the poster cannot reconstruct the case at all, where before it could write the fix and
  its own check from the text; visual_essentiality was raised from "helpful" and
  difficulty_explanation rewritten to name those facts. The rubric verdict test.sh
  computed is now actually passed to verifier.py. Re-validated: oracle 1.0, nop 0.0,
  check "Behavior In Task Description" fail -> pass, trial 0.0 with 0/3 f2p and 7/7 p2p,
  analyzer clean on both flags.

  Feedback: The harness was solid, so the gap was the prompt: instruction.md gave the full
  repro case in text and then showed the fixed output as "0, 3, 6, 9, 12", which the rules
  exclude as a corrected-output preview, leaving the poster with nothing to contribute.
  The check caught it directly, failing "Behavior In Task Description" because the blanket
  rule stated in the text would push an agent to enforce minStep on log and time scales
  too, the opposite of what three p2p tests require. Worth carrying forward: put the repro
  values in the poster, keep only the symptom and the scope boundaries in the text, and
  check those boundaries against the p2p list. Minor: the rubric verdict never reached
  verifier.py.
