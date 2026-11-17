# task108 recording / validation kit

Scratch tooling used to harden actualbudget__actual-7999-mm (not part of the bundle).

- `inject.py` / `inject_lib.py` / `mkbug.py` - author the 5 injected defects (`mkbug.py <repo> 01..05`).
- `altfix.py` - independent alternative fix used to prove the tests are implementation-agnostic (25/25).
- `vt.sh`, `matrix.sh`, `junit.py` - run the two test files with the repo's vitest and list failing tests.
- `pw_common.js`, `pw_seed.js`, `pw_capture.js` - headless Chromium reshoot: seed the budget through `window.$send`,
  then `node pw_capture.js buggy|fixed` against the desktop-client vite dev server (`--mode=browser`, port 3001).
- `fix_on_base.patch` - full fix relative to the clean base commit (upstream PR + single-ring donut).
- `explanation.txt` - source of task.toml `difficulty_explanation`.
- `altfix2.py` - on top of altfix.py: sentinel id for synthesized rows (proves tests don't require an empty id).
