FROM node:22-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone repo, pin to base commit, inject the task's defects, strip .git (anti-cheat:
# the agent cannot inspect fix PR or future history). Re-init a single immutable
# commit tagged harbor_base so the verifier can reset test files; git apply still
# works without upstream history.
#
# base_commit verified via `gh api repos/facebook/lexical/commits/<merge_sha> --jq
# '.parents'` -- PR #7960's merge commit 174580dfbb2d1a54fa0b102e7938407d9c8aca34 has
# EXACTLY one parent (this repo rebase/squash-merges), 34cab58e2ce3997d829ac7b68413fa
# 0acf9c24dc. `gh api .../compare/34cab58e...174580d...` confirms ahead_by=1,
# behind_by=0, total_commits=1, with exactly the PR's one changed file -- no
# squash-merge-parent-mismatch drift here. Also confirmed 174580d is a real ancestor of
# current main (compare 174580d...main: ahead_by=621, behind_by=0) -- no post-merge
# branch-deletion risk.
#
# ---------------------------------------------------------------------------------
# DEFECT INJECTION (authoring detail; not visible to the agent)
# ---------------------------------------------------------------------------------
# The upstream regression this task is built on (a participant's caret/selection never
# reaching the other clients on its own) is ALREADY PRESENT at base_commit 34cab58e --
# it is what issue #7959 reports and what PR #7960 fixes, and nothing in environment/
# bugs/ touches the file that PR changed.
#
# Two further defects in the same visible feature are injected from environment/bugs/.
# Each is a good -> buggy patch of existing, known-good upstream code and each is a PURE
# DELETION, so the injected tree contains no added line, comment, marker or other
# artifact that could give a repair away and is byte-identical to upstream apart from
# the omissions:
#
#   01-remote-cursor-never-repositioned.patch
#       packages/lexical-yjs/src/SyncCursors.ts -- an already-visible remote cursor's
#       stored anchor/focus is never rewritten, so another participant's caret freezes
#       at the first place it appeared however far they then move. Exactly what the
#       supplied recording shows: measured frame by frame, each caret holds a single
#       position for 5.7s then 7.6s (left pane) and 4.6s then 4.9s (right pane), moving
#       only in short bursts that coincide with text being typed.
#
#   02-local-selection-not-reanchored.patch
#       packages/lexical-yjs/src/SyncEditorStates.ts -- when a remote change is applied,
#       the local editor no longer re-derives its OWN selection from the position it
#       published, so a participant's caret keeps a raw offset and drifts through the
#       text whenever somebody edits earlier content. Distinct from the other two
#       defects in direction (your own selection, not other people's) and in trigger (a
#       remote DOCUMENT change, not a presence broadcast).
#
#   03-structural-point-mapping.patch
#       packages/lexical-yjs/src/SyncCursors.ts -- a STRUCTURAL (element) point, the kind
#       a caret has on an empty line or at a paragraph boundary, is encoded the way a
#       text point is: against the PARENT's shared type at the element's own slot,
#       instead of against the element's own shared type at the accumulated content
#       offset of the child boundary. Unlike the other two this is not a deleted call or
#       branch -- the algorithm is REPLACED by a plausible wrong one, so the repair
#       requires deriving v1's content-unit layout (a text child occupies 1 + length
#       units, any other child 1) from the decode walk in Utils.ts rather than copying an
#       adjacent line. The v2 encoder sitting 30 lines below is a deliberate trap: it
#       counts children against the node's own type, which is correct for v2's layout and
#       wrong for v1's.
#
# The patches are inlined below as base64 (quote-safe, portable in a classic RUN) and are
# decoded, applied and deleted inside the SAME RUN layer, so they exist in no image layer's
# filesystem, are never copied into /app/.harbor_assets/, and the agent cannot read them.
# They are inlined rather than shipped as files on purpose. The canonical bundle layout
# admits only environment/Dockerfile and environment/assets/*, and environment/assets/ is
# walked recursively by the shipping integrity gate, which requires every file in it to be a
# documented poster referenced from instruction.md -- verified: a patch placed under
# environment/assets/bugs/ fails asset-documented-both-files and asset-referenced-in-
# instruction. A sidecar elsewhere under environment/ is reported as a stray file whose
# offered repair is to DELETE it, which would break this build with a missing COPY source.
# Inlining is the project's documented resolution for Dockerfile-auxiliary content. The full
# patch text is reproduced verbatim above and below so a reviewer never has to decode
# anything. The harbor_base commit is taken AFTER injection, so `git diff harbor_base` in a
# candidate container shows the candidate's own work and nothing else.
#
# A focus/blur defect was considered and deliberately REJECTED: the supplied recording
# never shows a collaborator caret disappearing (confirmed across 140 frames sampled at
# 10fps over the whole 14s clip), so nothing in the visual evidence establishes that a
# caret is meant to vanish when a participant stops working, and a persistent caret is
# equally consistent with a design that keeps showing a collaborator's last position.

# ----- 01-remote-cursor-never-repositioned (verbatim; this comment is not shipped into the image) -----
#   diff --git a/packages/lexical-yjs/src/SyncCursors.ts b/packages/lexical-yjs/src/SyncCursors.ts
#   index 31dc8dc0c..3712cb2c7 100644
#   --- a/packages/lexical-yjs/src/SyncCursors.ts
#   +++ b/packages/lexical-yjs/src/SyncCursors.ts
#   @@ -661,13 +661,6 @@ export function syncCursorPositions(
#                  focusKey,
#                  focusOffset,
#                );
#   -          } else {
#   -            const anchor = selection.anchor;
#   -            const focus = selection.focus;
#   -            anchor.key = anchorKey;
#   -            anchor.offset = anchorOffset;
#   -            focus.key = focusKey;
#   -            focus.offset = focusOffset;
#              }
#            }
#          }
#
# ----- 02-local-selection-not-reanchored (verbatim; this comment is not shipped into the image) -----
#   diff --git a/packages/lexical-yjs/src/SyncEditorStates.ts b/packages/lexical-yjs/src/SyncEditorStates.ts
#   index a797e830e..aaaa2ccd3 100644
#   --- a/packages/lexical-yjs/src/SyncEditorStates.ts
#   +++ b/packages/lexical-yjs/src/SyncEditorStates.ts
#   @@ -200,8 +200,6 @@ function $syncCursorFromYjs(
#            prevSelection,
#            $getSelection(),
#          );
#   -    } else {
#   -      $syncLocalCursorPosition(binding, provider);
#        }
#      }
#    }
#
# ----- 03-structural-point-mapping (verbatim; this comment is not shipped into the image) -----
#   diff --git a/packages/lexical-yjs/src/SyncCursors.ts b/packages/lexical-yjs/src/SyncCursors.ts
#   index 31dc8dc0c..d68ae6de5 100644
#   --- a/packages/lexical-yjs/src/SyncCursors.ts
#   +++ b/packages/lexical-yjs/src/SyncCursors.ts
#   @@ -96,20 +96,20 @@ function createRelativePosition(
#        collabNode instanceof CollabElementNode &&
#        point.type === 'element'
#      ) {
#   -    const parent = point.getNode();
#   -    invariant($isElementNode(parent), 'Element point must be an element node');
#   -    let accumulatedOffset = 0;
#   -    let i = 0;
#   -    let node = parent.getFirstChild();
#   -    while (node !== null && i++ < offset) {
#   -      if ($isTextNode(node)) {
#   -        accumulatedOffset += node.getTextContentSize() + 1;
#   -      } else {
#   -        accumulatedOffset++;
#   -      }
#   -      node = node.getNextSibling();
#   +    const parentCollabNode = collabNode._parent;
#   +
#   +    if (parentCollabNode === null) {
#   +      return null;
#   +    }
#   +
#   +    const currentOffset = collabNode.getOffset();
#   +
#   +    if (currentOffset === -1) {
#   +      return null;
#        }
#   -    offset = accumulatedOffset;
#   +
#   +    sharedType = parentCollabNode._xmlText;
#   +    offset = currentOffset + offset;
#      }
#    
#      return createRelativePositionFromTypeIndex(sharedType, offset);
#
RUN git clone https://github.com/facebook/lexical /app \
 && git -C /app checkout 34cab58e2ce3997d829ac7b68413fa0acf9c24dc \
 && echo 'ZGlmZiAtLWdpdCBhL3BhY2thZ2VzL2xleGljYWwteWpzL3NyYy9TeW5jQ3Vyc29ycy50cyBiL3BhY2thZ2VzL2xleGljYWwteWpzL3NyYy9TeW5jQ3Vyc29ycy50cwppbmRleCAzMWRjOGRjMGMuLjM3MTJjYjJjNyAxMDA2NDQKLS0tIGEvcGFja2FnZXMvbGV4aWNhbC15anMvc3JjL1N5bmNDdXJzb3JzLnRzCisrKyBiL3BhY2thZ2VzL2xleGljYWwteWpzL3NyYy9TeW5jQ3Vyc29ycy50cwpAQCAtNjYxLDEzICs2NjEsNiBAQCBleHBvcnQgZnVuY3Rpb24gc3luY0N1cnNvclBvc2l0aW9ucygKICAgICAgICAgICAgICAgZm9jdXNLZXksCiAgICAgICAgICAgICAgIGZvY3VzT2Zmc2V0LAogICAgICAgICAgICAgKTsKLSAgICAgICAgICB9IGVsc2UgewotICAgICAgICAgICAgY29uc3QgYW5jaG9yID0gc2VsZWN0aW9uLmFuY2hvcjsKLSAgICAgICAgICAgIGNvbnN0IGZvY3VzID0gc2VsZWN0aW9uLmZvY3VzOwotICAgICAgICAgICAgYW5jaG9yLmtleSA9IGFuY2hvcktleTsKLSAgICAgICAgICAgIGFuY2hvci5vZmZzZXQgPSBhbmNob3JPZmZzZXQ7Ci0gICAgICAgICAgICBmb2N1cy5rZXkgPSBmb2N1c0tleTsKLSAgICAgICAgICAgIGZvY3VzLm9mZnNldCA9IGZvY3VzT2Zmc2V0OwogICAgICAgICAgIH0KICAgICAgICAgfQogICAgICAgfQo=' | base64 -d > /tmp/hb1.patch \
 && echo 'ZGlmZiAtLWdpdCBhL3BhY2thZ2VzL2xleGljYWwteWpzL3NyYy9TeW5jRWRpdG9yU3RhdGVzLnRzIGIvcGFja2FnZXMvbGV4aWNhbC15anMvc3JjL1N5bmNFZGl0b3JTdGF0ZXMudHMKaW5kZXggYTc5N2U4MzBlLi5hYWFhMmNjZDMgMTAwNjQ0Ci0tLSBhL3BhY2thZ2VzL2xleGljYWwteWpzL3NyYy9TeW5jRWRpdG9yU3RhdGVzLnRzCisrKyBiL3BhY2thZ2VzL2xleGljYWwteWpzL3NyYy9TeW5jRWRpdG9yU3RhdGVzLnRzCkBAIC0yMDAsOCArMjAwLDYgQEAgZnVuY3Rpb24gJHN5bmNDdXJzb3JGcm9tWWpzKAogICAgICAgICBwcmV2U2VsZWN0aW9uLAogICAgICAgICAkZ2V0U2VsZWN0aW9uKCksCiAgICAgICApOwotICAgIH0gZWxzZSB7Ci0gICAgICAkc3luY0xvY2FsQ3Vyc29yUG9zaXRpb24oYmluZGluZywgcHJvdmlkZXIpOwogICAgIH0KICAgfQogfQo=' | base64 -d > /tmp/hb2.patch \
 && echo 'ZGlmZiAtLWdpdCBhL3BhY2thZ2VzL2xleGljYWwteWpzL3NyYy9TeW5jQ3Vyc29ycy50cyBiL3BhY2thZ2VzL2xleGljYWwteWpzL3NyYy9TeW5jQ3Vyc29ycy50cwppbmRleCAzMWRjOGRjMGMuLmQ2OGFlNmRlNSAxMDA2NDQKLS0tIGEvcGFja2FnZXMvbGV4aWNhbC15anMvc3JjL1N5bmNDdXJzb3JzLnRzCisrKyBiL3BhY2thZ2VzL2xleGljYWwteWpzL3NyYy9TeW5jQ3Vyc29ycy50cwpAQCAtOTYsMjAgKzk2LDIwIEBAIGZ1bmN0aW9uIGNyZWF0ZVJlbGF0aXZlUG9zaXRpb24oCiAgICAgY29sbGFiTm9kZSBpbnN0YW5jZW9mIENvbGxhYkVsZW1lbnROb2RlICYmCiAgICAgcG9pbnQudHlwZSA9PT0gJ2VsZW1lbnQnCiAgICkgewotICAgIGNvbnN0IHBhcmVudCA9IHBvaW50LmdldE5vZGUoKTsKLSAgICBpbnZhcmlhbnQoJGlzRWxlbWVudE5vZGUocGFyZW50KSwgJ0VsZW1lbnQgcG9pbnQgbXVzdCBiZSBhbiBlbGVtZW50IG5vZGUnKTsKLSAgICBsZXQgYWNjdW11bGF0ZWRPZmZzZXQgPSAwOwotICAgIGxldCBpID0gMDsKLSAgICBsZXQgbm9kZSA9IHBhcmVudC5nZXRGaXJzdENoaWxkKCk7Ci0gICAgd2hpbGUgKG5vZGUgIT09IG51bGwgJiYgaSsrIDwgb2Zmc2V0KSB7Ci0gICAgICBpZiAoJGlzVGV4dE5vZGUobm9kZSkpIHsKLSAgICAgICAgYWNjdW11bGF0ZWRPZmZzZXQgKz0gbm9kZS5nZXRUZXh0Q29udGVudFNpemUoKSArIDE7Ci0gICAgICB9IGVsc2UgewotICAgICAgICBhY2N1bXVsYXRlZE9mZnNldCsrOwotICAgICAgfQotICAgICAgbm9kZSA9IG5vZGUuZ2V0TmV4dFNpYmxpbmcoKTsKKyAgICBjb25zdCBwYXJlbnRDb2xsYWJOb2RlID0gY29sbGFiTm9kZS5fcGFyZW50OworCisgICAgaWYgKHBhcmVudENvbGxhYk5vZGUgPT09IG51bGwpIHsKKyAgICAgIHJldHVybiBudWxsOworICAgIH0KKworICAgIGNvbnN0IGN1cnJlbnRPZmZzZXQgPSBjb2xsYWJOb2RlLmdldE9mZnNldCgpOworCisgICAgaWYgKGN1cnJlbnRPZmZzZXQgPT09IC0xKSB7CisgICAgICByZXR1cm4gbnVsbDsKICAgICB9Ci0gICAgb2Zmc2V0ID0gYWNjdW11bGF0ZWRPZmZzZXQ7CisKKyAgICBzaGFyZWRUeXBlID0gcGFyZW50Q29sbGFiTm9kZS5feG1sVGV4dDsKKyAgICBvZmZzZXQgPSBjdXJyZW50T2Zmc2V0ICsgb2Zmc2V0OwogICB9CiAKICAgcmV0dXJuIGNyZWF0ZVJlbGF0aXZlUG9zaXRpb25Gcm9tVHlwZUluZGV4KHNoYXJlZFR5cGUsIG9mZnNldCk7Cg==' | base64 -d > /tmp/hb3.patch \
 && git -C /app apply /tmp/hb1.patch \
 && git -C /app apply /tmp/hb2.patch \
 && git -C /app apply /tmp/hb3.patch \
 && rm -f /tmp/hb1.patch /tmp/hb2.patch /tmp/hb3.patch \
 && rm -rf /app/.git \
 && git -C /app init -q \
 && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base \
 && git -C /app tag harbor_base

# Pre-install repo dependencies (avoids network waits at verify time).
#
# IMPORTANT REPO-WIDE HAZARD, specific to this task's vintage: unlike most other
# lexical-mm tasks banked this session (base commits from Dec 2025 or later, all
# pnpm-based), issue #7959's base commit (2025-10-30) predates this repo's OWN
# migration from npm to pnpm workspaces -- that migration landed in PR #8035
# "npm -> pnpm" (commit 95009d4f, merged 2025-12-21), almost two months after our base
# commit. At 34cab58e, there is NO pnpm-lock.yaml / pnpm-workspace.yaml at all -- only
# package-lock.json (npm lockfileVersion 2) and package.json's own
# `"workspaces": ["packages/*"]`. None of the banked pnpm advice for this repo (bare
# `corepack enable` resolving a too-new pnpm major, `--filter` package narrowing)
# applies here: this is a plain npm workspaces monorepo at this commit, full stop.
#
# npm workspaces has no per-package --filter equivalent -- a single `npm ci` resolves
# and hoists the ENTIRE lockfile-declared dependency graph in one pass regardless of
# which workspace a test imports from, so (unlike the pnpm-based lexical-mm tasks)
# there is no narrower install to select here even though the fix + the new test file
# only need the `lexical`, `@lexical/react`, `@lexical/yjs` and `yjs` packages plus
# React.
#
# HUSKY=0 skips the root "prepare": "husky install" lifecycle script (git-hooks setup;
# irrelevant in a throwaway container). Do NOT add --ignore-scripts globally: esbuild
# (a transitive vite/vitest dependency, hasInstallScript in package-lock.json) needs
# its own install script to select the correct platform binary; skipping it breaks
# vitest at run time.
RUN HUSKY=0 npm ci

# Visual evidence readable by the agent at /app/.harbor_assets/.
# tests/ and solution/ are NOT baked in -- the harness supplies them at verify time.
RUN mkdir -p /logs /app/.harbor_assets
COPY assets/ /app/.harbor_assets/

CMD ["bash"]
