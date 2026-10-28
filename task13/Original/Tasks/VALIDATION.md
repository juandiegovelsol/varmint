# Validation record — `IvarK__AntimatterDimensionsSourceCode-2613-mm`

All figures below are measured, not estimated. Runs were executed with
`harbor run` against `environment/Dockerfile`, agent and verifier both under
`network_mode = "no-network"`.

## Verifier discrimination matrix

The verifier was run against four deliberately different candidate states to
confirm it rewards a correct fix and only a correct fix:

| Candidate state                                     | Reward | Expected |
| --------------------------------------------------- | -----: | -------- |
| Base commit, untouched (nop)                         |  0.0   | 0.0 ✅   |
| `solution/fix.patch` applied (oracle)                |  1.0   | 1.0 ✅   |
| Corner hard-coded to a single colour (`#1a1a1a`)     |  0.5   | partial ✅ |
| Scrollbar block deleted from the stylesheet (gutted) |  0.0   | 0.0 ✅   |

The 0.5 row is what the second f2p test buys: a fix that hard-codes one theme's
background suppresses the white corner in the dark container but fails the
container-background match in the magenta and teal containers. Before that test
existed, both the hard-coded and gutted candidates scored 1.0.

Reward pipeline is unit tests → JUnit XML (`/logs/verifier/report.xml`) →
`tests/verifier.py` → `/logs/verifier/reward.txt`. There is no LLM judge, so
oracle and nop runs need no model credentials.

## Test classification

Sets in `task.toml` and `tests/config.json` are identical (verified as sets):

- f2p `scrollbar_corner::test_corner_not_white`
- f2p `scrollbar_corner_edge::test_corner_matches_container_background`
- p2p `scrollbar_chrome::test_custom_scrollbar_metrics_and_thumb_preserved`

All three assert observable output only — decoded screenshot pixels and
DOM-measured geometry (`offsetWidth - clientWidth`). None greps candidate source
for CSS text or keywords. The p2p derives the expected 16px scrollbar width from
the live root font-size rather than hard-coding it, so it does not break if the
`html { font-size: 62.5% }` base changes.

## Live model trials

Agent `claude-code`, model `anthropic/claude-opus-4-8`,
`--agent-timeout-multiplier 6`, web tools disallowed, no network.

| Run                     | Trials | Errors | Mean  | Rewards |
| ----------------------- | -----: | -----: | ----: | ------- |
| `Trials`  (`-k 1 -n 1`) |      1 |      0 | 1.000 | 1.0 ×1  |
| `Trials5` (`-k 5 -n 1`) |      5 |      0 | 1.000 | 1.0 ×5  |

The n=5 run was serial (`-n 1`) so that concurrent Xvfb + Chromium containers
could not starve CPU and produce timeout failures that would understate the mean.
Trials ran back-to-back, ~1m45s each; total cost $1.05, ~2.3k output tokens per
trial.

**Measured pass rate: 6/6 (100%).** The `< 1.0` difficulty gate is not
achievable for this task — see below.

### What the model did, every time

All six trials followed the same path: opened `/app/.harbor_assets/bug.png`
(exactly once each), identified the white square where the two scrollbars meet,
searched the stylesheets, observed that `::-webkit-scrollbar-corner` is styled
nowhere in the repo, and appended a corner rule setting `background: transparent`.

Two consequences worth recording:

1. **The tests are implementation-agnostic in practice, not just by design.**
   Every trial wrote `background: transparent`; the golden patch writes
   `-webkit-appearance: none; appearance: none`. Both score 1.0. The hardening
   did not create a golden-patch-shaped keyhole.
2. **Prompt hardening was not the limiting factor.** `instruction.md` carries no
   repository URL, no issue link, no file list, no named API, and no
   implementation recipe. The model still solved it in under two minutes from the
   screenshot alone.

## Why the `< 1.0` gate cannot be met here

No verifier change can make a *correct* fix fail. The verifier can only reject
candidates that are genuinely wrong on some input — which is exactly what the
0.5 and 0.0 rows above demonstrate it does. The model is not producing wrong
fixes, so the failure rate is a property of the problem, not of the tests.

The problem is a two-line CSS addition to a pseudo-element that no rule in the
repository targets, and the screenshot points directly at it. `difficulty =
"easy"` in `task.toml` is an accurate, now-measured label. This bundle is
correct and discriminating; it is not hard, and it should be used as an
easy-tier / calibration task rather than forced past a difficulty gate it was
never going to clear.

A theme-aware corner-matching requirement was investigated as a way to raise the
required precision and rejected for two independent reasons: (a) `background:
transparent` is *already* theme-adaptive — a transparent corner shows whatever
the container's themed background is, verified across dark, magenta, and teal
containers — so a theme-matching test passes on the model's existing fix; and
(b) all 13 theme stylesheets contain zero scrollbar rules and no
`::-webkit-scrollbar*` block anywhere sets a track background, so a per-theme
requirement would invent a feature the upstream PR never had, making
`fix_commit`, `pr_number`, and `files_edited` fiction.

## Known limitations, disclosed

- **`visual_essentiality = "required"` is not proven.** Every trial did open the
  screenshot, but the issue title — "horizontal + vertical scroll looks bad on
  chrome" — already names both scrollbars and the browser, which is most of the
  way to the corner. An ablation with the screenshot reference removed would
  settle it; it has not been run.
- **`CSS_FILE` is hardcoded** in `tests/scrollbar-corner-test.js`. A candidate
  that fixes the corner in a different stylesheet than
  `public/stylesheets/styles.css` would not be credited. Left as-is because
  `files_edited` pins the intended file.
- **`tests/.s`** is a 0-byte file referenced by nothing. It is not a synthetic
  test marker used by anything in this bundle, but it reads like one; recommend
  deleting it.
- **Headful Chromium under Xvfb is mandatory.** Headless Chrome 112+ uses overlay
  scrollbars regardless of `::-webkit-scrollbar` CSS, so the corner widget never
  renders and the bug is unobservable. `tests/test.sh` starts Xvfb on `:99` and
  polls for its X11 socket before launching the browser.
- **`pngjs@6.0.0` must stay baked into the image** (`/opt/test-deps`, via
  `TEST_DEPS_DIR`). The verifier phase has no network; any registry round-trip
  there fails with ECONNRESET and takes the whole run to reward 0.
