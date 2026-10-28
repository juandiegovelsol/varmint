---
name: talk-test-suite-conftest-drift
description: The talk test suite fails at fixture setup due to organiser/organizer field drift
metadata: 
  node_type: memory
  type: project
  originSessionId: 38d96b65-b076-440b-81e8-a8c81abbf3ff
  modified: 2026-08-16T15:51:37.701Z
---

`app/tests/talk/conftest.py` creates `Team.objects.create(organiser=..., can_change_organiser_settings=...)`, but the imported `Team` (`eventyay.base.models.organizer.Team`) uses `organizer=` / `can_change_organizer_settings`. So any test using the `organiser`/`event` fixtures dies at setup with `TypeError: Team() got unexpected keyword arguments`.

**Why:** pretix ("organizer") vs pretalx ("organiser") merge artifact. It is pre-existing, not caused by product-code edits.

**How to apply:** Don't assume your change broke `tests/talk/...` if it errors in fixture setup — verify with `git status`. For a quick regression test of talk-area code, add a self-contained test that builds its own objects with the correct `organizer=` spelling (see [[local-postgres-for-tests]]). Example: `app/tests/test_review_scoring_fix.py`.
