# reference/ — known-good files, verbatim

`template/` holds **fragments to merge**. This folder holds **whole files, exactly as they ship in
a task that works**. When a repair is authoring rather than wiring and you are unsure what the
result should look like, read the file here.

## `judge.py`

The API-backend rubric judge. Copy it whole into `tests/judge.py`; it is task-agnostic and needs
no edits.

Provenance, which is the reason to trust it:

- **byte-identical in both reference tasks** — `recharts__recharts-7445-mm` (TypeScript/recharts)
  and `IvarK__AntimatterDimensionsSourceCode-2877-mm` (JavaScript). Same sha256. Two unrelated
  repos, one file, no task-specific patterns to strip.
- **verified grading in-band in a live oracle run**: `[judge] graded via API
  model=anthropic/claude-opus-4-5-20251101` → `verdict=pass`, 4/4 criteria, with `verdict.json`
  and `summary.json` written inside the run.
- **verified degrading correctly**: pointed at a dead endpoint it retried, gave up, wrote the
  sub-agent request (`PROMPT.md`, `source.txt`, `criteria_payload.json`), printed nothing, and let
  the verifier score on tests alone. It never failed the run.

It satisfies `rubfmt_judge_backend` because it defines `call_eval_api` — the check greps for that
name, so keep it if you adapt the file.

Using it also requires the `task.toml` side, which IS auto-fixable:

```toml
[verifier]
network_mode = "public"

[verifier.env]
EVAL_API_KEY  = "${OPENAI_API_KEY}"
EVAL_BASE_URL = "${OPENAI_API_BASE}"
EVAL_MODEL    = "${EVAL_MODEL:-anthropic/claude-opus-4-5-20251101}"
```

    python3 fix.py apply <Tasks> --approve verifier_network_mode --approve verifier_env --apply

See `../RUBRIC_MODES.md` §2b for what each requirement is for, and
`../template/tests/judge_api_block.py` for the API block alone if you are adding it to a judge you
already have rather than replacing the file.
