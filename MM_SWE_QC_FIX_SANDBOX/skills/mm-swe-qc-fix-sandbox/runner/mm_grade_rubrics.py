#!/usr/bin/env python3
"""RETIRED — do not use.

Host-side rubric grader that called the anonymizer directly (the legacy "api" judge
backend). MM SWE uses the SUB-AGENT backend instead: tests/judge.py writes a judge request,
a judge sub-agent writes verdict.json, and `mm_run.sh <task> rescore` folds it in. That path
needs no API key and no network from the verifier, so this file is obsolete.
"""
import sys
sys.stderr.write(__doc__)
sys.exit(0)
