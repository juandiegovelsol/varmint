FROM node:22-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone repo, pin to base commit, strip .git (anti-cheat: agent cannot inspect
# fix PR or future history). Re-init a single immutable commit tagged harbor_base
# so the verifier can reset test files; git apply still works without upstream history.
#
# base_commit verification: PR #8737's own reported baseRefOid
# (51d47b77e852e646091ff5cb7675264fd9aa234e) was cross-checked against the merge
# commit's own parents. `gh api repos/facebook/lexical/commits/9c1cbf8caae14505c5fb1c371fed66f49d28bf9f
# --jq '.parents'` (9c1cbf8c = PR #8737's merge commit) returns exactly ONE parent,
# 51d47b77e852e646091ff5cb7675264fd9aa234e -- an exact match with the PR's own
# reported baseRefOid (NOT the stale-base hazard seen on several sibling lexical-mm
# tasks this session). `gh api repos/facebook/lexical/compare/51d47b77e...9c1cbf8ca`
# confirms ahead_by=1, behind_by=0. Clean single-parent merge.
RUN git clone https://github.com/facebook/lexical /app \
 && git -C /app checkout 51d47b77e852e646091ff5cb7675264fd9aa234e \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install repo dependencies (avoids network waits at verify time).
#
# base_commit is 2026-06-28, well after this repo's npm->pnpm migration (PR #8035,
# merged 2025-12-21) -- so pnpm is required, NOT npm ci. Pin pnpm to the major this
# exact base_commit's root package.json declares ("packageManager": "pnpm@10.34.1")
# explicitly via npm rather than trusting a bare `corepack enable`: this repo's own
# sibling lexical-mm tasks confirmed corepack's bundled 'last known good' pnpm
# resolution drifts as the node:22-bookworm base image is rebuilt over time and can
# refuse this repo's pnpm-lock.yaml (lockfileVersion '9.0') under --frozen-lockfile.
#
# The fix lives in packages/lexical/src/{LexicalSelection.ts,index.ts,
# nodes/LexicalTextNode.ts}, packages/lexical-rich-text/src/index.ts and
# packages/lexical-extension/src/DecoratorTextExtension.ts. Its own new test,
# packages/lexical-extension/src/__tests__/unit/DecoratorTextExtension.test.ts,
# imports from '@lexical/extension' (buildEditorFromExtensions/DecoratorTextExtension/
# DecoratorTextNode) and '@lexical/rich-text' (RichTextExtension), so
# `--filter '!@lexical/devtools' --filter '!lexical-playground'` (the broad filter
# confirmed sufficient for sibling task facebook__lexical-8713-mm, which also touches
# packages/lexical-extension) is used here too, rather than a narrower single-package
# filter that could miss a transitive dep -- confirmed sufficient by actually running
# the new test file in-container against this exact base_commit checkout before
# finalizing this Dockerfile.
RUN npm install -g pnpm@10 \
 && pnpm install --frozen-lockfile --filter '!@lexical/devtools' --filter '!lexical-playground'

# Visual evidence readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are NOT baked in -- the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
