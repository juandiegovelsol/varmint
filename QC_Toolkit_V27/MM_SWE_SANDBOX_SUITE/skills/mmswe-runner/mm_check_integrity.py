#!/usr/bin/env python3
"""Task-integrity gate for MM SWE tasks — runs before `harbor check` spends a run.

`check_files()` in mm_run.sh only confirms the required files EXIST; it says nothing
about whether they agree with each other. This catches the class of error where every
file is present but they disagree: task.toml claims one base_commit while the Dockerfile
pins another, files_edited names a file the golden patch never touches, the golden patch
quietly also edits the test harness, or the bug screenshot path drifts across
evidence_bundle.json / ASSET_MANIFEST.json / instruction.md. It also catches the evidence
errors that only show up when you start from what is ON DISK rather than from what the
documents claim: a poster sitting in environment/assets/ that neither document mentions
(COPY assets/ still ships it to the agent, so an undocumented `after.png` is an answer
leak), a poster instruction.md never tells the agent to look at, and a Dockerfile that
delivers a poster somewhere other than the container_path the documents promise.

Every asset check is driven from the DIRECTORY, not from the documents, and each reports
independently. Both properties are load-bearing: an earlier version folded the
instruction.md test into the evidence_bundle loop, where two `continue`s and the loop
itself made it unreachable for exactly the posters most likely to be wrong.

Check 6b guards the SHAPE of the two evidence documents before anything reads them, and
every check that reads them SKIPs when it fails. That ordering is the point. Both documents
are arrays of poster objects (see GOLDEN_FORMAT); a packager that emits an object wrapping
those arrays under a different key, or entries keyed `container_path` where the bundle wants
`local_path`, used to yield empty indices — and empty indices made checks 7, 8 and 12's
manifest arm PASS on a document they never read, check 10 print nothing at all, and check 9
report a correctly-documented poster as "absent from" both files. A gate that reports PASS
for a document it failed to parse is worse than one that has no such check. So: one FAIL
naming the shape problem, the golden format printed verbatim so the fix needs no other
reference, and an honest SKIP everywhere the answer is genuinely unknown.

Deliberately NOT here: an "every f2p/p2p id appears literally in tests/test.patch" check
used to live here and was removed. It doesn't hold in general — p2p ids are pre-existing
tests test.patch normally never touches, and f2p ids can *also* be pre-existing tests that
were already failing on base_commit and simply start passing once the fix is applied,
never appearing in test.patch either. Confirming an id actually names a test that exists
after test.patch is applied needs the real test file content, which means a repo
checkout — out of scope for this no-checkout gate (see below). That's what oracle running
the actual f2p/p2p selection against the real test file is for.

Pure stdlib, no docker, no repo checkout, NO NETWORK — every check is a string/set comparison
across files already shipped in the task dir, so this stays sub-second and works air-gapped.
task.toml is NOT a full TOML parse (this sandbox's python3 has no tomllib/tomli): each field
is pulled with the same kind of targeted regex mm_run.sh itself already uses for task_id and
base_commit. Good enough for the handful of scalar/array-of-string keys this needs; do not
use load_toml_fields() as a general TOML parser.

Whether an evidence_bundle URL serves the same bytes as the poster on disk is a human
judgement, not a gate: a poster is often DERIVED from what the URL serves — a still extracted
from a screen recording — so the two legitimately differ. What is checked instead ties each
poster to both documents, to instruction.md and to the Dockerfile's COPY, all read from disk.

Deliberately NOT here (see the skill's design discussion): patch-applies-cleanly, TOML/JSON
syntax validity, script syntax checks, and any upstream GitHub verification — no
repo/commit/branch existence probing. Those either surface for free the moment oracle runs,
or need a real checkout. The two evidence documents are the one exception, and only because
6b cannot do its job without parsing them: unparseable JSON there is reported as a shape
FAIL rather than left to raise a traceback out of the middle of the run.

This gate REPORTS; it never writes. Every other check here prints both sides of the
disagreement and stops — `files-edited-matches-fix-patch` could regenerate files_edited from
fix.patch mechanically and deliberately does not — so 6b prints the golden format and stops
too. Repair is the QC skill's job, and a gate that edits what it grades cannot be trusted to
grade it.

Usage:
  mm_check_integrity.py <task-dir>
Exit code: 0 if every check passes, 1 if any fails. SKIPs do not affect it.
"""
from __future__ import annotations
import fnmatch
import json
import os
import re
import shlex
import sys
import textwrap
from pathlib import Path, PurePosixPath

FAIL = []   # (check_id, message) accumulated as we go
PASS = []   # check_id only
SKIP = []   # (check_id, reason) — could not be decided; does NOT affect the exit code

ASSETS_REL = "environment/assets"
MANIFEST_NAME = "ASSET_MANIFEST.json"
# The image is built with the context set to Tasks/environment/, which is why
# `COPY assets/ ...` resolves.
ASSETS_CONTEXT_DIR = "assets"

# Required keys per poster entry. Attested by the three golden tasks, which agree exactly:
# manifest entries carry these three keys and nothing else, bundle entries these four.
# EXTRA keys are tolerated on purpose — a packager adding `bytes` or `source_url` has not
# broken anything, and a check that rejects unknown keys turns every schema addition into a
# false FAIL. `role` is likewise NOT validated against a fixed vocabulary: the goldens
# already use `before`, `bug_screenshot` and `bug_screenshot_override`, so an enum here
# would fail correct tasks. That the two documents AGREE on role is check 10's job.
MANIFEST_KEYS = ("file", "role", "container_path")
BUNDLE_KEYS = ("role", "local_path", "description")

# Part of the bundle shape, but its VALUE is optional. The poster's source URL is often
# unavailable (a capture made for the task has no upload link), and nothing downstream reads
# it: the agent sees the file at `local_path`. --fix always writes the key, in its golden
# position - the source link when one is found, else "" - so every entry has the same shape.
# An empty value, or a missing key, is never a finding.
OPTIONAL_FIELDS = {"manifest": (), "bundle": ("url",)}

# `description` is the one field nothing can derive: it has to come from looking at the
# poster. An agent CAN draft it from the image, and that draft is a genuinely useful
# starting point — but it is a machine's reading of a screenshot standing in for the task
# author's, in the field the agent will later be judged against. So a draft is marked, and a
# marked description fails this gate exactly like a blank one. The marker is what makes
# "this is only a draft" enforceable instead of advisory: the task cannot go green until a
# human has read the poster, corrected the text, and deleted the prefix.
DRAFT_PREFIX = "DRAFT:"

# Printed verbatim under a 6b failure. The point of a gate that only reports is that its
# message has to be sufficient on its own — a builder who sees this should not need to open
# a golden task to know what to write.
GOLDEN_FORMAT = """\
environment/assets/ASSET_MANIFEST.json — a JSON ARRAY, one object per poster:
  [
    {
      "file": "before.png",
      "role": "before",
      "container_path": "/app/.harbor_assets/before.png"
    }
  ]

evidence_bundle.json — a JSON ARRAY, one object per poster:
  [
    {
      "role": "before",
      "url": "https://github.com/user-attachments/assets/<id>",   (or "" when there is none)
      "local_path": "/app/.harbor_assets/before.png",
      "description": "What the poster shows, in enough detail to stand in for seeing it."
    }
  ]

Rules:
  * Both files are ARRAYS at the top level, never an object wrapping one.
  * A poster's manifest `container_path` and bundle `local_path` are the SAME absolute
    container path, and `role` agrees between the two documents.
  * Everything else in a wrapper object is DROPPED, not moved anywhere. Do NOT copy
    task_id / issue_url / pr_url / base_commit / source_files / link_evidence / provenance
    into task.toml to preserve them: task.toml has its own golden structure, already carries
    the task metadata it is meant to (task_id, base_commit, fix_commit, issue_number,
    pr_number, visual_essentiality), and adding fields to it that the goldens do not have is
    a new defect, not a rescue. The goldens have no home for the rest — it simply goes.
  * Extra keys on an entry are allowed; the keys above are the required minimum, except
    `url`, whose value is optional — the poster's source link if there is one, else "".
  * `description` must be written by a HUMAN who has looked at the poster. If it was
    drafted for you — by an agent reading the image, or from the issue text — prefix it
    with "DRAFT:" and this check keeps failing until you have verified it against the
    poster, corrected it, and removed the prefix. A draft is a starting point, never the
    finished field: it is a machine's reading of a screenshot standing in for the task
    author's, in the evidence the solving agent is judged against."""

# Reason attached to every check that cannot be decided once 6b has failed. Names the check
# by the id that is actually PRINTED, not by its number in this file's comments — a reader
# of the output has the id in front of them and has never seen "6b".
SHAPE_SKIP = ("evidence documents are not in the golden format "
              "— see the evidence-schema-shape FAIL above")

# Where each golden field may be sourced from in a non-conforming document, in order of
# preference. The key order here IS the output order, and it matches the goldens.
# `description` is special-cased below: it is the one field that cannot be derived from any
# other, so it is written blank for a human to fill in rather than invented.
FIELD_SOURCES = {
    "manifest": {"file": ("file",),
                 "role": ("role",),
                 "container_path": ("container_path",)},
    "bundle": {"role": ("role",),
               "url": ("url", "source_url"),
               "local_path": ("local_path", "container_path"),
               "description": ("description",)},
}


def wrapped_entries(doc):
    """(key, entries) for the ONE list-of-objects inside a wrapper object, else (None, None).

    Deliberately refuses when there is not exactly one candidate. This converts a document
    whose shape was inferred from a single packager's output, so it must decline anything
    ambiguous rather than guess which array holds the posters and silently rewrite the file
    around the wrong one.
    """
    if not isinstance(doc, dict):
        return None, None
    candidates = [(k, v) for k, v in doc.items()
                  if isinstance(v, list) and v and all(isinstance(e, dict) for e in v)]
    if len(candidates) != 1:
        return None, None
    return candidates[0]


def propose_golden(doc, kind):
    """(proposal, reason) — proposal is None when no safe conversion could be built.

    proposal is (entries, wrapper_key, dropped_top_level, dropped_per_entry).
    """
    key, entries = wrapped_entries(doc)
    if entries is None:
        return None, ("could not identify exactly one array of poster objects inside it")

    fields = FIELD_SOURCES[kind]
    out, missing = [], []
    for i, entry in enumerate(entries):
        new = {}
        for field, sources in fields.items():
            value = next((entry[s] for s in sources
                          if isinstance(entry.get(s), str) and entry[s].strip()), None)
            if value is not None:
                new[field] = value
            elif field == "description":
                new[field] = ""          # blank ON PURPOSE — only a human can write this
            elif field in OPTIONAL_FIELDS[kind]:
                new[field] = ""          # optional value: keep the key, blank when unknown
            else:
                missing.append(f"entry[{i}] has no usable {field!r} "
                               f"(looked for {', '.join(repr(s) for s in sources)})")
        out.append(new)
    if missing:
        return None, "; ".join(missing)

    consumed = {s for sources in fields.values() for s in sources}
    dropped_entry = sorted({k for e in entries for k in e} - consumed)
    dropped_top = sorted(k for k in doc if k != key)
    return (out, key, dropped_top, dropped_entry), None


def report_proposal(label, path, proposal, reason, apply_fix):
    """Print what a conversion would do (or why it cannot), and write it under --fix.

    Returns True if the file was written. The consent step is NOT a stdin prompt: this
    script is driven by an agent through a shell, so there is never a human at a terminal to
    type an answer, and a blocking read() would hang the run. The dry run is what the user
    reads in chat; --fix is what the agent passes once they have said yes.
    """
    print(f"\n     --- {label} ---")
    if proposal is None:
        print(f"     cannot convert automatically: {reason}")
        print("     rewrite it by hand against the format above.")
        return False

    entries, wrapper_key, dropped_top, dropped_entry = proposal
    print(f"     posters found under the {wrapper_key!r} key: {len(entries)}")
    if dropped_top:
        print(f"     top-level keys that would be REMOVED: {', '.join(dropped_top)}")
    if dropped_entry:
        print(f"     per-entry keys that would be REMOVED: {', '.join(dropped_entry)}")
    # `"description" in e`, not .get(...) — the manifest has no description field at all, and
    # .get("description", "") returns "" for every one of its entries, which made this warn
    # about a blank field the document is not supposed to have.
    blank = [i for i, e in enumerate(entries)
             if "description" in e and not e["description"].strip()]
    if blank:
        print(f"     'description' would be written EMPTY for entry {blank} — it cannot be "
              f"derived from any other field, so it is left blank rather than invented.")
        print(f"     A human must open the poster and write it. If something drafts it for "
              f"you from the image, prefix that text with {DRAFT_PREFIX!r} — this check goes "
              f"on failing until a human has verified it and removed the prefix.")
    print("     proposed contents:")
    print(textwrap.indent(json.dumps(entries, indent=2), "       "))

    if not apply_fix:
        print("     (dry run — nothing written. re-run with --fix to apply.)")
        return False
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    print(f"     WROTE {path}")
    return True


def ok(check_id, detail=""):
    PASS.append(check_id)
    print(f"PASS {check_id}" + (f" — {detail}" if detail else ""))


def bad(check_id, detail):
    FAIL.append((check_id, detail))
    print(f"FAIL {check_id} — {detail}")


def skip(check_id, detail):
    """Undecidable, not failed. Originally for where the network did not answer: a builder
    with no egress must not be able to block a check run the task itself is fine for.

    Check 6b uses it for a second, different reason — the task's OWN defect made a check
    undecidable — which is only safe because 6b always FAILs in the same breath, so the
    exit code is already 1 and the SKIPs cost nothing. See the shape_bad comment in main().
    A SKIP must never be the only thing standing between a broken task and a pass; if you
    add one for a reason that does not come with its own FAIL, it belongs as a FAIL instead."""
    SKIP.append((check_id, detail))
    print(f"SKIP {check_id} — {detail}")


# --------------------------------------------------------------- task.toml (regex, not a parser)
def load_toml_scalar(text, key):
    """key = "value"  or  key = 'value'  — TOML allows either quote style."""
    m = re.search(rf'^[ \t]*{re.escape(key)}[ \t]*=[ \t]*(?:"([^"]*)"|\'([^\']*)\')', text, re.M)
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else m.group(2)


_TOML_ESC = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r",
             '"': '"', "\\": "\\", "/": "/"}


def _toml_unescape(s):
    r"""A TOML basic string's escapes, resolved. \u/\U are left as written: they do not occur in
    the fields this script reads, and an unresolved sequence is a visible non-match rather than a
    silent wrong character."""
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(_TOML_ESC.get(s[i + 1], s[i:i + 2])); i += 2
        else:
            out.append(s[i]); i += 1
    return "".join(out)


def load_toml_str_array(text, key):
    r"""key = [ "a", 'b', ... ] - possibly spanning multiple lines. String elements only,
    either quote style, mixed or not.

    A SCANNER, NOT A REGEX. The two regexes this replaces were each wrong in a way that only
    showed up on real ids. `\[(.*?)\]` is non-greedy, so the array ended at the FIRST `]` in the
    file - and a pytest id like `test_x[1-2]`, or any prose test name containing a bracket, puts
    one inside the first element and silently truncated the list. `"([^"]*)"` then treated the `"`
    of an escaped `\"` as a terminator, so an id like `renders with scope=\"col\"` came back as a
    fragment plus an empty string - the exact case the old docstring assumed away when it said no
    element is legitimately empty. Together they turned a correct bundle into an
    `f2p-matches-config-json` failure that no edit to the bundle could clear.

    Depth and quoting have to be tracked together: strings are consumed whole, so a bracket
    inside one cannot close the array, and escapes are resolved so the result compares equal to
    the same id read out of config.json by the JSON parser.
    """
    m = re.search(rf'^[ \t]*{re.escape(key)}[ \t]*=[ \t]*\[', text, re.M)
    if not m:
        return None
    items, i, depth, n = [], m.end(), 1, len(text)
    while i < n:
        c = text[i]
        if c in '"\'':
            esc, j, buf = (c == '"'), i + 1, []
            while j < n:
                d = text[j]
                if esc and d == "\\" and j + 1 < n:
                    buf.append(text[j:j + 2]); j += 2; continue
                if d == c:
                    break
                buf.append(d); j += 1
            if j >= n:
                return None                      # unterminated string: refuse, do not guess
            items.append(_toml_unescape("".join(buf)) if esc else "".join(buf))
            i = j + 1
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return items
        i += 1
    return None                                  # unterminated array


# --------------------------------------------------------------- patch parsing
def diff_git_paths(patch_text):
    """Every path a patch 'touches' — one path per file, not per diff header. Ordinary
    add/modify/delete hunks name the same path as both a/ and b/, so either one is fine.
    A git RENAME is different: its 'diff --git a/old b/new' header names two DIFFERENT
    paths for what is conceptually one file. Naively adding both would demand the task
    author declare files_edited=[old, new] for a plain rename, which is wrong — from the
    author's point of view they edited (renamed) one file, so only the new path counts.
    Rename detection: the 'diff --git' line is immediately followed (mode-line noise
    aside) by 'rename from <old>' / 'rename to <new>' before the next 'diff --git'."""
    lines = patch_text.splitlines()
    paths = set()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("diff --git "):
            i += 1
            continue
        try:
            fields = shlex.split(line)
        except ValueError:
            i += 1
            continue
        header_paths = {field[2:] for field in fields[2:] if field.startswith(("a/", "b/"))}

        rename_to = None
        j = i + 1
        while j < len(lines) and not lines[j].startswith("diff --git "):
            if lines[j].startswith("rename to "):
                rename_to = lines[j][len("rename to "):].strip()
            j += 1

        if rename_to is not None:
            paths.add(rename_to)   # rename: one logical file, keep only the new path
        else:
            paths |= header_paths  # ordinary add/modify/delete: both sides are fine to keep

        i += 1
    return paths


# --------------------------------------------------------------- Dockerfile comments
def strip_comment_lines(text):
    """Drop every line whose first non-whitespace character is '#'. Dockerfile comment
    syntax is whole-line only, so this is enough to stop a commented-out clone/checkout
    line (or an unrelated remark mentioning a URL/sha) from satisfying a presence check
    that's only supposed to match real instructions."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


# --------------------------------------------------------------- evidence posters
def asset_files(task_dir):
    """Every file under environment/assets/, relative to it, ASSET_MANIFEST.json aside.

    Starts from the DIRECTORY, not from either document — that is the whole point. Checks
    #7 and #8 walk the manifest and can only find posters the documents already know about.
    """
    adir = task_dir / ASSETS_REL
    if not adir.is_dir():
        return None
    return sorted(
        str(p.relative_to(adir)).replace("\\", "/")
        for p in adir.rglob("*")
        if p.is_file() and p.name != MANIFEST_NAME
    )


def dockerfile_copies(dockerfile_text):
    """[(sources, dest)] for every COPY/ADD, with `\\` continuations joined and relative
    destinations resolved against the WORKDIR in force at that point.

    Returns (copies, unparsed) where unparsed holds COPY/ADD remainders that mention
    assets/ but could not be tokenised — reported rather than silently passed over.
    """
    lines, buffer = [], ""
    for raw in strip_comment_lines(dockerfile_text).splitlines():
        stripped = raw.strip()
        if not stripped and not buffer:
            continue
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        lines.append(buffer + stripped)
        buffer = ""
    if buffer.strip():
        lines.append(buffer.strip())

    copies, unparsed, workdir = [], [], "/"
    for line in lines:
        parts = line.split(None, 1)
        if not parts:
            continue
        keyword, remainder = parts[0].upper(), (parts[1] if len(parts) > 1 else "")

        if keyword == "WORKDIR":
            candidate = remainder.strip().strip('"').strip("'")
            if candidate:
                workdir = candidate if candidate.startswith("/") else f"{workdir.rstrip('/')}/{candidate}"
            continue
        if keyword not in ("COPY", "ADD"):
            continue

        remainder = remainder.strip()
        # Flags (--chown=, --from=, ...) come first in BOTH forms, so they are peeled off before
        # deciding shell vs JSON form - `COPY --chown=1:1 ["assets/", "/x"]` is JSON form too,
        # and splitting it on whitespace made it ship nothing from assets/ as far as every check
        # here could tell.
        parsed = _split_copy(remainder)
        tokens = parsed[1] if parsed else []

        tokens = [t for t in tokens if not t.startswith("--")]   # --chown=, --from=, ...
        if len(tokens) < 2:
            if ASSETS_CONTEXT_DIR in remainder:
                unparsed.append(remainder)
            continue

        sources, dest = tokens[:-1], tokens[-1]
        if not dest.startswith("/"):
            trailing = "/" if dest.endswith("/") else ""
            dest = f"{workdir.rstrip('/')}/{dest.strip('/')}" + trailing
        copies.append((sources, dest))
    return copies, unparsed


def shipped_assets(copies, on_disk):
    """{asset filename: absolute container path} that the Dockerfile actually delivers.

    Returns (mapping, missing_sources, whole_dir) — missing_sources are COPY sources under
    assets/ that match nothing on disk, whole_dir is True if any COPY takes the directory
    itself (in which case Docker ships its entire contents, documented or not).
    """
    mapping, missing_sources, whole_dir = {}, [], False

    for sources, dest in copies:
        for src in sources:
            norm = src.replace("\\", "/").strip()
            while norm.startswith("./"):
                norm = norm[2:]
            if norm.rstrip("/") != ASSETS_CONTEXT_DIR and not norm.startswith(ASSETS_CONTEXT_DIR + "/"):
                continue                                    # this COPY is not about assets/
            inner = norm[len(ASSETS_CONTEXT_DIR):].lstrip("/")

            if inner == "":                                 # whole directory -> contents
                whole_dir = True
                for rel in on_disk:
                    mapping[rel] = f"{dest.rstrip('/')}/{rel}"
            elif any(ch in inner for ch in "*?["):
                matched = fnmatch.filter(on_disk, inner)
                if not matched:
                    missing_sources.append(src)
                for rel in matched:
                    mapping[rel] = f"{dest.rstrip('/')}/{PurePosixPath(rel).name}"
            elif inner in on_disk:
                if dest.endswith("/") or len(sources) > 1:
                    mapping[inner] = f"{dest.rstrip('/')}/{PurePosixPath(inner).name}"
                else:
                    mapping[inner] = dest                   # single file onto an exact path
            else:
                missing_sources.append(src)

    return mapping, missing_sources, whole_dir


# --------------------------------------------------------------- what assets/ may ship
# What may reach the container from assets/: images, plus non-image evidence the documents
# list. Never ASSET_MANIFEST.json - packaging metadata for the TASK, which names every poster's
# role and so tells the agent what each image is meant to show before it has looked. Extend
# this set (lower-case, with the dot) if a new image type is used.
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".tif", ".tiff", ".avif"}


def context_files(task_dir):
    """Every file in the build context (environment/), relative to it, '/'-separated."""
    ctx = task_dir / ASSETS_REL.rsplit("/", 1)[0]
    if not ctx.is_dir():
        return []
    return sorted(str(p.relative_to(ctx)).replace("\\", "/") for p in ctx.rglob("*") if p.is_file())


def shipped_from_assets(copies, ctx_files):
    """{assets/<file>: the COPY/ADD source that ships it} - every file under assets/ that lands
    in the image, documented or not. Unlike shipped_assets() this keeps ASSET_MANIFEST.json and
    also follows sources that take assets/ in from ABOVE (`COPY . /x`, `COPY * /x`), because
    Docker ships whatever a source resolves to, whatever the author meant by it."""
    out = {}
    for sources, _dest in copies:
        for src in sources:
            if "://" in src:                               # ADD <url>: not from the context
                continue
            norm = src.replace("\\", "/").strip()
            while norm.startswith("./"):
                norm = norm[2:]
            norm = norm.rstrip("/")
            if norm in ("", "."):
                hits = ctx_files                           # the whole context
            elif any(ch in norm for ch in "*?["):
                hits = [f for f in ctx_files
                        if fnmatch.fnmatch(f, norm)
                        or any(fnmatch.fnmatch(str(parent), norm)
                               for parent in PurePosixPath(f).parents if str(parent) != ".")]
            else:
                hits = [f for f in ctx_files if f == norm or f.startswith(norm + "/")]
            for f in hits:
                if f.startswith(ASSETS_CONTEXT_DIR + "/"):
                    out.setdefault(f, src)
    return out


def dockerfile_instructions(text):
    """[(first_line, last_line, logical_text)] (0-based, inclusive) for every instruction, with
    `\\` continuations joined and comment lines dropped - the joining dockerfile_copies() does,
    but keeping WHERE each instruction sits so a fix can replace exactly its lines."""
    out, start, buf = [], None, ""
    lines = text.splitlines()
    for i, raw in enumerate(lines):
        s = raw.strip()
        if s.startswith("#") or (start is None and not s):
            continue
        if start is None:
            start = i
        if s.endswith("\\"):
            buf += s[:-1] + " "
            continue
        out.append((start, i, (buf + s).strip()))
        start, buf = None, ""
    if start is not None:
        out.append((start, len(lines) - 1, buf.strip()))
    return out


def _split_copy(remainder):
    """(flags, tokens, json_form) for a COPY/ADD remainder, or None if it cannot be tokenised."""
    rem, flags = remainder.strip(), []
    while rem.startswith("--"):
        flag, _, rem = rem.partition(" ")
        flags.append(flag)
        rem = rem.lstrip()
    if rem.startswith("["):
        try:
            tokens = json.loads(rem)
        except json.JSONDecodeError:
            return None
        return (flags, tokens, True) if all(isinstance(t, str) for t in tokens) else None
    try:
        return flags, shlex.split(rem), False
    except ValueError:
        return None


def propose_images_only_copy(dockerfile_text, task_dir, documented):
    """The assets-images-only auto-fix: (new_text, changes, declined).

    Every COPY/ADD source that ships ASSET_MANIFEST.json (or an undocumented non-image file) out
    of assets/ is rewritten to image GLOBS - `assets/*.png`, `assets/*.jpg`, ... one per image
    extension actually present in what that source shipped, case kept, because a glob matching
    nothing can fail the build - plus each non-image file the documents list as evidence, by
    name, so documented evidence keeps landing where they promise. Destination unchanged except
    for the trailing `/` Docker requires for several sources or a glob. Other sources on the
    line, and every other line of the Dockerfile, are left byte-for-byte alone.

    `documented` is the set of poster names the evidence documents list, or None when they are
    unreadable - then every non-image file except the manifest is kept, since nothing can say
    which of them are evidence.

    DECLINES, rather than guesses, when a rewrite cannot be shown equivalent: a source that takes
    assets/ in from above (`COPY . /x` ships the whole context, and narrowing it changes what
    else lands), a file in a subfolder of assets/ (a glob would flatten its path), a line that
    cannot be tokenised, and a multi-stage `--from=` copy (its sources are not this context).

    changes:  [(line_no, before, after_or_None, dropped_files)]   after None = line removed
    declined: [(line_no, before, reason)]
    """
    ctx = context_files(task_dir)
    lines = dockerfile_text.splitlines()
    changes, declined, edits = [], [], []

    def offending(f):
        name, image = PurePosixPath(f).name, PurePosixPath(f).suffix.lower() in IMAGE_EXTS
        return name == MANIFEST_NAME or (not image and documented is not None
                                         and name not in documented)

    for start, end, text in dockerfile_instructions(dockerfile_text):
        keyword, _, remainder = text.partition(" ")
        if keyword.upper() not in ("COPY", "ADD"):
            continue
        parsed = _split_copy(remainder)
        if parsed is None or len(parsed[1]) < 2:
            if MANIFEST_NAME in remainder or ASSETS_CONTEXT_DIR in remainder:
                declined.append((start + 1, text, "this COPY/ADD cannot be parsed - edit it by hand"))
            continue
        flags, tokens, json_form = parsed
        sources, dest = tokens[:-1], tokens[-1]
        new_sources, dropped, touched, why_not = [], [], False, None
        for src in sources:
            shipped = sorted(shipped_from_assets([([src], dest)], ctx))
            bad_files = [f for f in shipped if offending(f)]
            if not bad_files:
                new_sources.append(src)
                continue
            touched = True
            if any(f.startswith("--from") for f in flags):
                why_not = "a multi-stage --from= copy - its sources are not this build context"
                break
            norm = src.replace("\\", "/").strip()
            while norm.startswith("./"):
                norm = norm[2:]
            if norm.rstrip("/") != ASSETS_CONTEXT_DIR and not norm.startswith(ASSETS_CONTEXT_DIR + "/"):
                why_not = (f"source {src!r} ships the whole build context, not just "
                           f"{ASSETS_CONTEXT_DIR}/ - narrowing it changes what else lands; "
                           f"split it by hand")
                break
            keep = [f for f in shipped if f not in bad_files]
            images = [f for f in keep if PurePosixPath(f).suffix.lower() in IMAGE_EXTS]
            evidence = [f for f in keep if f not in images]
            nested = [f for f in keep if f.count("/") > 1]
            if nested:
                why_not = (f"{nested[0]} is in a subfolder of {ASSETS_CONTEXT_DIR}/ - an image glob "
                           f"would flatten its path; rewrite this line by hand")
                break
            new_sources += [f"{ASSETS_CONTEXT_DIR}/*{suf}"
                            for suf in sorted({PurePosixPath(f).suffix for f in images})]
            new_sources += evidence
            dropped += bad_files
        if not touched:
            continue
        if why_not:
            declined.append((start + 1, text, why_not))
            continue
        seen = set()
        new_sources = [s for s in new_sources if not (s in seen or seen.add(s))]
        if not new_sources:
            after = None                                   # it shipped nothing worth keeping
        else:
            out_dest = dest if dest.endswith("/") else dest + "/"
            args = new_sources + [out_dest]
            body = (json.dumps(args) if json_form or any(any(c.isspace() for c in a) for a in args)
                    else " ".join(args))
            indent = lines[start][:len(lines[start]) - len(lines[start].lstrip())]
            after = indent + " ".join([keyword] + flags + [body])
        changes.append((start + 1, text, after, dropped))
        edits.append((start, end, after))

    for start, end, after in sorted(edits, reverse=True):
        lines[start:end + 1] = [] if after is None else [after]
    new_text = "\n".join(lines) + ("\n" if dockerfile_text.endswith("\n") else "")
    return new_text, changes, declined


def report_images_only_fix(dockerfile_path, dockerfile_text, task_dir, documented, apply_fix):
    """Print the assets-images-only fix as a dry run, and write it under --fix. True if written."""
    new_text, changes, declined = propose_images_only_copy(dockerfile_text, task_dir, documented)
    print("\n     --- auto-fix: environment/Dockerfile ---")
    for line_no, before, after, dropped in changes:
        print(f"     line {line_no}:")
        print(f"       - {before}")
        print(f"       + {after}" if after else "       + (instruction removed - it shipped nothing else)")
        print(f"       no longer shipped: {', '.join(dropped)}")
    for line_no, before, reason in declined:
        print(f"     line {line_no}: NOT rewritten - {reason}")
        print(f"       {before}")
    if not changes:
        print("     nothing can be rewritten automatically - edit the Dockerfile by hand.")
        return False
    if not apply_fix:
        print("     (dry run — nothing written. re-run with --fix to apply.)")
        return False
    dockerfile_path.write_text(new_text, encoding="utf-8")
    print(f"     WROTE {dockerfile_path}")
    if declined:
        print("     the line(s) marked NOT rewritten still need a hand edit.")
    print("     re-run this check — the verdict below describes the Dockerfile as it was BEFORE\n"
          "     the rewrite, so it is already out of date. The image changed, so oracle/nop/trial\n"
          "     runs must be re-done against it.")
    return True


# --------------------------------------------------------------- evidence document shape
def evidence_doc(path, required, label):
    """(entries, problems, state) for one evidence document.

    state is "ok" (a conforming array of poster objects), "bad" (present but unparseable or
    the wrong shape) or "absent" (no such file — left alone, because checks 7 and 8 already
    report a missing document and this must not turn their FAIL into a SKIP).

    On "bad" the entries list comes back EMPTY even where some entries were fine. That is
    deliberate: a half-read document is exactly what produced the vacuous passes this check
    exists to stop, so callers get nothing to accidentally succeed against.
    """
    if not path.is_file():
        return [], [], "absent"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], [f"{label} is not valid JSON: {exc}"], "bad"
    except OSError as exc:
        return [], [f"{label} could not be read: {exc}"], "bad"

    if not isinstance(doc, list):
        if isinstance(doc, dict):
            # The common packager defect: the array is nested under some key of a wrapper
            # object. Name the keys found — that is usually enough to spot which one it is.
            found = f"a JSON object with top-level keys {sorted(doc)}"
        else:
            found = f"a JSON {type(doc).__name__}"
        return [], [f"{label} is {found}, expected an array of poster objects"], "bad"

    problems = []
    for i, entry in enumerate(doc):
        if not isinstance(entry, dict):
            problems.append(f"{label}[{i}] is a {type(entry).__name__}, expected an object")
            continue
        for key in required:
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                if key == "description" and value.strip().upper().startswith(DRAFT_PREFIX):
                    problems.append(
                        f"{label}[{i}] has a DRAFT {key!r} — it was drafted from the poster "
                        f"and has NOT been checked by a human. Open the image, correct the "
                        f"text, and delete the {DRAFT_PREFIX!r} prefix.")
                continue
            # A key present-but-blank and a key absent are different situations with
            # different next steps — and --fix deliberately produces the first, writing an
            # empty `description` for a human to fill in. Saying "has no 'description'" over
            # a file that visibly contains one would send them looking for the wrong thing.
            if key in entry:
                problems.append(f"{label}[{i}] has an empty {key!r} — it must be written")
            else:
                problems.append(
                    f"{label}[{i}] has no {key!r} (keys present: {sorted(entry)})")
    if problems:
        return [], problems, "bad"
    return doc, [], "ok"


# --------------------------------------------------------------- path safety
def unsafe_path(p):
    return p.startswith("/") or ".." in Path(p).parts


def check_no_path_escapes(label_to_paths):
    any_bad = False
    for label, paths in label_to_paths.items():
        offenders = [p for p in paths if unsafe_path(p)]
        if offenders:
            bad("no-path-escapes", f"{label} contains absolute/'..' paths: {offenders}")
            any_bad = True
    if not any_bad:
        # Names the sources actually inspected rather than a fixed list: when 6b has failed,
        # the manifest arm is dropped and this line must not claim to have covered it.
        ok("no-path-escapes", f"no absolute or '..' paths in {', '.join(label_to_paths)}")


def main():
    argv = sys.argv[1:]
    # Every check is offline, so `--offline` / MM_INTEGRITY_OFFLINE are no-ops. They stay ACCEPTED
    # rather than rejected: the filter below drops them with every other `-` argument, so a caller
    # or shell alias that passes either one keeps working instead of failing on usage.
    #
    # --fix is the ONE flag that does something, and it is opt-in for a reason: mm_run.sh calls
    # this script as a gate and never passes it, so the pipeline keeps getting today's read-only
    # behaviour. Consent happens in chat off the back of the dry run, not at a prompt here.
    apply_fix = "--fix" in argv
    positional = [a for a in argv if not a.startswith("-")]
    if len(positional) != 1:
        print("usage: mm_check_integrity.py <task-dir> [--fix]", file=sys.stderr)
        return 2
    task_dir = Path(positional[0])

    toml_text = (task_dir / "task.toml").read_text(encoding="utf-8", errors="replace")
    dockerfile_text = (task_dir / "environment/Dockerfile").read_text(encoding="utf-8", errors="replace")
    fix_patch_text = (task_dir / "solution/fix.patch").read_text(encoding="utf-8", errors="replace")
    test_patch_text = (task_dir / "tests/test.patch").read_text(encoding="utf-8", errors="replace")
    config_json = json.loads((task_dir / "tests/config.json").read_text(encoding="utf-8"))
    instruction_text = (task_dir / "instruction.md").read_text(encoding="utf-8", errors="replace")

    base_commit = load_toml_scalar(toml_text, "base_commit") or ""
    repo_url = load_toml_scalar(toml_text, "repo_url") or ""
    repository_name = load_toml_scalar(toml_text, "repository_name") or ""
    files_edited = load_toml_str_array(toml_text, "files_edited") or []
    toml_f2p = load_toml_str_array(toml_text, "f2p") or []
    toml_p2p = load_toml_str_array(toml_text, "p2p") or []

    fix_paths = diff_git_paths(fix_patch_text)
    test_paths = diff_git_paths(test_patch_text)

    # 1. base_commit (task.toml) vs the sha the Dockerfile pins. Presence-based, not
    #    syntax-based: earlier drafts required the exact 'git -C /app checkout <sha>' shape
    #    and broke on 'cd /app && git checkout <sha>', a different WORKDIR, etc. — the
    #    directory and clone/checkout style are not part of what we're verifying, so don't
    #    encode them. Instead: does *any* 'checkout <hex-sha>' or 'reset --hard <hex-sha>'
    #    appear on a REAL (non-comment) line, and does it match base_commit (either may be
    #    a short prefix of the other)? Comments are stripped first so a sha merely mentioned
    #    in a Dockerfile remark ("# do not checkout <sha>") can't satisfy this by accident.
    dockerfile_code = strip_comment_lines(dockerfile_text)
    docker_shas = re.findall(r'(?:checkout|reset\s+--hard)\s+["\']?([0-9a-fA-F]{6,40})\b', dockerfile_code)
    match = base_commit and any(
        base_commit.lower() == sha.lower()
        or base_commit.lower().startswith(sha.lower())
        or sha.lower().startswith(base_commit.lower())
        for sha in docker_shas
    )
    if not base_commit:
        bad("base-commit-matches-dockerfile", "task.toml has no base_commit")
    elif not docker_shas:
        bad("base-commit-matches-dockerfile", "no 'checkout <commit-hash>' found anywhere in the Dockerfile")
    elif match:
        ok("base-commit-matches-dockerfile", f"{base_commit} checked out in Dockerfile")
    else:
        bad("base-commit-matches-dockerfile",
            f"task.toml base_commit={base_commit} matches none of the Dockerfile's checkout targets {docker_shas}")

    # 2. files_edited (task.toml) == paths touched by solution/fix.patch, both directions.
    fe_set = set(files_edited)
    if fe_set == fix_paths:
        ok("files-edited-matches-fix-patch", f"{sorted(fe_set)}")
    else:
        missing_from_patch = fe_set - fix_paths
        missing_from_toml = fix_paths - fe_set
        detail = []
        if missing_from_patch:
            detail.append(f"declared but not touched by fix.patch: {sorted(missing_from_patch)}")
        if missing_from_toml:
            detail.append(f"touched by fix.patch but not declared: {sorted(missing_from_toml)}")
        bad("files-edited-matches-fix-patch", "; ".join(detail))

    # 3. fix.patch and test.patch must not touch the same path.
    overlap = fix_paths & test_paths
    if overlap:
        bad("fix-and-test-patch-disjoint", f"both patches touch: {sorted(overlap)}")
    else:
        ok("fix-and-test-patch-disjoint")

    # 4. test.patch must not touch anything declared in files_edited (a second, independent
    #    check from #3: this compares against the DECLARED set, not fix.patch's actual set,
    #    so it still catches an overlap even if #2 already found files_edited/fix.patch disagree).
    overlap2 = fe_set & test_paths
    if overlap2:
        bad("test-patch-does-not-touch-source", f"test.patch touches declared source file(s): {sorted(overlap2)}")
    else:
        ok("test-patch-does-not-touch-source")

    # 5. f2p/p2p sets agree between task.toml and tests/config.json, both directions, and
    #    neither list overlaps itself (verifier.py already enforces the overlap rule at
    #    container run time; checking it here just surfaces the same problem for free).
    cfg_f2p = list(config_json.get("f2p") or [])
    cfg_p2p = list(config_json.get("p2p") or [])
    if set(toml_f2p) != set(cfg_f2p):
        bad("f2p-matches-config-json", f"task.toml={sorted(toml_f2p)} != config.json={sorted(cfg_f2p)}")
    else:
        ok("f2p-matches-config-json", f"{sorted(toml_f2p)}")
    if set(toml_p2p) != set(cfg_p2p):
        bad("p2p-matches-config-json", f"task.toml={sorted(toml_p2p)} != config.json={sorted(cfg_p2p)}")
    else:
        ok("p2p-matches-config-json", f"{sorted(toml_p2p)}")
    id_overlap = set(toml_f2p) & set(toml_p2p)
    if id_overlap:
        bad("f2p-p2p-disjoint", f"declared as both f2p and p2p: {sorted(id_overlap)}")
    else:
        ok("f2p-p2p-disjoint")

    # 6. repo_url is actually the repo the Dockerfile clones. Presence-based, like #1: the
    #    clone command's syntax and destination directory are not part of what we're
    #    verifying, so don't hardcode them — just confirm repo_url's host+path appears
    #    in the Dockerfile (tolerating a trailing slash or ".git" either side), on a REAL
    #    line (comments stripped, same reasoning as #1), case-insensitively (GitHub repo
    #    paths are not case-sensitive, so IvarK/Foo and ivark/foo are the same repo).
    norm_repo_url = repo_url.rstrip("/").removesuffix(".git")
    if not repo_url:
        bad("repo-url-matches-dockerfile", "task.toml has no repo_url")
    elif norm_repo_url and (
        norm_repo_url.lower() in dockerfile_code.lower()
        or f"{norm_repo_url}.git".lower() in dockerfile_code.lower()
    ):
        ok("repo-url-matches-dockerfile", repo_url)
        if repository_name and not norm_repo_url.endswith(repository_name):
            bad("repository-name-matches-repo-url",
                f"repository_name={repository_name} is not the path of repo_url={repo_url}")
        elif repository_name:
            ok("repository-name-matches-repo-url", repository_name)
    else:
        bad("repo-url-matches-dockerfile", f"task.toml repo_url={repo_url} does not appear anywhere in the Dockerfile")

    # 6b. both evidence documents are in the golden format, BEFORE anything reads them.
    #     Everything from here to #12 either indexes these documents or compares against
    #     them, so this runs first and every dependent SKIPs on failure rather than passing
    #     against an index that silently came out empty.
    manifest_path = task_dir / "environment/assets/ASSET_MANIFEST.json"
    evidence_path = task_dir / "evidence_bundle.json"
    manifest_entries, man_problems, man_state = evidence_doc(
        manifest_path, MANIFEST_KEYS, MANIFEST_NAME)
    bundle_entries, bundle_problems, bundle_state = evidence_doc(
        evidence_path, BUNDLE_KEYS, "evidence_bundle.json")

    # shape_bad is derived from the problems THEMSELVES, not from the states, so that the one
    # property the SKIPs below depend on cannot be broken by a later edit: a check may only
    # be skipped for a bad shape when there is at least one problem to report, and every
    # problem is reported as a FAIL immediately below. No SKIP without an accompanying FAIL,
    # therefore no path where skipping softens the exit code. (`state == "bad"` currently
    # implies a non-empty problem list, but nothing structural forced that to stay true.)
    shape_problems = man_problems + bundle_problems
    shape_bad = bool(shape_problems)

    if shape_bad:
        for problem in shape_problems:
            bad("evidence-schema-shape", problem)
        # The format goes to stdout with the findings, not to stderr: mm_run.sh already sends
        # this script's whole output to stderr, and splitting the fix instructions away from
        # the FAIL that motivates them helps nobody.
        print("\n     the golden format both documents must follow:\n")
        print(textwrap.indent(GOLDEN_FORMAT, "       "))

        # Offer a conversion for the shape problems that ARE mechanically convertible: a
        # wrapper object around the poster array. Nothing is written without --fix, and the
        # only field that cannot be derived is left blank rather than invented.
        wrote = False
        for label, path, kind, state in ((MANIFEST_NAME, manifest_path, "manifest", man_state),
                                         ("evidence_bundle.json", evidence_path, "bundle",
                                          bundle_state)):
            if state != "bad":
                continue
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue                    # unparseable: no conversion to offer
            if isinstance(doc, list):
                continue                    # already an array; the fault is in the entries
            proposal, reason = propose_golden(doc, kind)
            wrote |= report_proposal(label, path, proposal, reason, apply_fix)
        if wrote:
            print("\n     files rewritten. WRITE THE EMPTY 'description' FIELD(S), then re-run\n"
                  "     this check — the verdict below describes the files as they were BEFORE\n"
                  "     the rewrite, so it is already out of date.")
        print()
    elif "absent" in (man_state, bundle_state):
        missing = [n for n, s in ((MANIFEST_NAME, man_state),
                                  ("evidence_bundle.json", bundle_state)) if s == "absent"]
        skip("evidence-schema-shape", f"not present: {', '.join(missing)} "
                                      f"(reported by asset-path-consistent/asset-files-exist)")
    else:
        ok("evidence-schema-shape",
           f"{len(manifest_entries)} manifest / {len(bundle_entries)} bundle entries")

    # 6c. no two entries in one document name the same poster. Every index from #7 on is a
    #     dict keyed on the poster's name — `file` for the manifest, the basename of
    #     `local_path` for the bundle — so a repeated key silently discards all but the last
    #     entry, and each downstream check then reports on the survivor as though it were the
    #     only claim the document made. Two entries for one poster that DISAGREE about role
    #     or description otherwise pass this whole gate clean, with the losing entry never
    #     mentioned; a task can ship an evidence_bundle that contradicts itself about what
    #     the agent is looking at and be told it is fine.
    #
    #     Cross-entry, which is why it is not part of 6b: that validates one entry at a time
    #     and both halves of a contradictory pair are individually well-formed. Runs only
    #     once 6b passes, because before that the entry lists are deliberately empty.
    if shape_bad:
        skip("asset-entries-unique", SHAPE_SKIP)
    else:
        dup_problems = []
        for label, entries, key_of in (
                (MANIFEST_NAME, manifest_entries,
                 lambda e: e.get("file")),
                ("evidence_bundle.json", bundle_entries,
                 lambda e: PurePosixPath(e["local_path"]).name if e.get("local_path") else None)):
            groups = {}
            for i, entry in enumerate(entries):
                name = key_of(entry)
                if name:
                    groups.setdefault(name, []).append((i, entry))
            for name, group in sorted(groups.items()):
                if len(group) < 2:
                    continue
                # Distinguish a harmless repeat from a contradiction: the second is the one
                # that makes a downstream PASS actively wrong rather than merely redundant.
                distinct = {json.dumps(e, sort_keys=True) for _, e in group}
                kind = ("identical duplicate entries" if len(distinct) == 1 else
                        "entries that DISAGREE — every one but the last is silently discarded")
                dup_problems.append(
                    f"{label}: {name!r} is claimed by {len(group)} {kind} "
                    f"(at {', '.join(f'[{i}]' for i, _ in group)})")
        if dup_problems:
            for problem in dup_problems:
                bad("asset-entries-unique", problem)
        elif manifest_entries or bundle_entries:
            ok("asset-entries-unique", "every entry names a distinct poster")
        else:
            skip("asset-entries-unique", "no poster entries to compare")

    # 7. the bug-screenshot path agrees across evidence_bundle.json and ASSET_MANIFEST.json.
    #    Document-vs-document only — whether instruction.md actually points the agent at each
    #    poster is #9b, driven from what is on disk. That test used to live in this loop, where
    #    it was reachable only for a poster already present in BOTH documents with agreeing
    #    paths: the two `continue`s below skipped it, and an asset missing from either document
    #    was never tested against instruction.md at all.
    manifest_ok = True
    if shape_bad:
        skip("asset-path-consistent", SHAPE_SKIP)
        manifest_ok = False
    elif manifest_path.is_file() and evidence_path.is_file():
        manifest_by_file = {e.get("file"): e for e in manifest_entries}
        for ev in bundle_entries:
            local_path = ev.get("local_path", "")
            fname = Path(local_path).name if local_path else None
            entry = manifest_by_file.get(fname)
            if entry is None:
                bad("asset-path-consistent",
                    f"evidence_bundle local_path={local_path!r} has no matching ASSET_MANIFEST 'file'={fname!r}")
                manifest_ok = False
                continue
            if entry.get("container_path") != local_path:
                bad("asset-path-consistent",
                    f"evidence_bundle local_path={local_path!r} != ASSET_MANIFEST container_path={entry.get('container_path')!r}")
                manifest_ok = False
                continue
        if manifest_ok:
            ok("asset-path-consistent")
    else:
        bad("asset-path-consistent", "evidence_bundle.json or ASSET_MANIFEST.json missing")
        manifest_ok = False

    # 8. every file ASSET_MANIFEST.json declares actually exists on disk.
    if shape_bad:
        skip("asset-files-exist", SHAPE_SKIP)
    elif manifest_path.is_file():
        missing_assets = []
        for entry in manifest_entries:
            fname = entry.get("file")
            if fname and not (task_dir / "environment/assets" / fname).is_file():
                missing_assets.append(fname)
        if missing_assets:
            bad("asset-files-exist", f"declared in ASSET_MANIFEST but not on disk: {missing_assets}")
        else:
            ok("asset-files-exist")
    else:
        bad("asset-files-exist", "ASSET_MANIFEST.json missing")

    # 9-12. the same evidence chain read from the OTHER end: start at the files in
    #    environment/assets/ and at the Dockerfile, not at the two documents. #7 and #8
    #    iterate manifest/bundle entries, so a poster no document mentions is invisible to
    #    them — and `COPY assets/` ships it anyway.
    #    Both indices are built from the entries 6b already parsed and validated — the
    #    documents are NOT re-read here. Three separate re-parses of the same two files used
    #    to live in this function, each with its own idea of what an entry looked like, which
    #    is how the shape assumption came to be wrong in some of them and not others.
    on_disk = asset_files(task_dir)
    manifest_by_name = {e.get("file"): e for e in manifest_entries if e.get("file")}
    bundle_by_name = {PurePosixPath(e["local_path"]).name: e
                      for e in bundle_entries if e.get("local_path")}

    if shape_bad:
        skip("asset-documented-both-files", SHAPE_SKIP)
    elif on_disk is None:
        bad("asset-documented-both-files", f"{ASSETS_REL}/ is missing")
    elif not on_disk:
        bad("asset-documented-both-files", f"{ASSETS_REL}/ holds no poster files")
    else:
        undocumented = []
        for name in on_disk:
            missing_from = [doc for doc, index in (("ASSET_MANIFEST.json", manifest_by_name),
                                                   ("evidence_bundle.json", bundle_by_name))
                            if name not in index]
            if missing_from:
                undocumented.append(f"{name} (absent from {' and '.join(missing_from)})")
        orphaned = sorted(n for n in bundle_by_name if n not in set(on_disk))
        if undocumented:
            bad("asset-documented-both-files",
                f"in {ASSETS_REL}/ but undocumented: {undocumented} — COPY assets/ ships "
                f"these to the agent regardless, so an undocumented 'after' poster leaks the fix")
        if orphaned:
            bad("asset-documented-both-files",
                f"evidence_bundle.json cites files not in {ASSETS_REL}/: {orphaned}")
        if not undocumented and not orphaned:
            ok("asset-documented-both-files", f"{len(on_disk)} poster(s) in both documents")

    # 9b. instruction.md actually points the agent at every poster on disk. Driven from the
    #     DIRECTORY for the same reason #9 is: keyed off the documents, this test only ever
    #     reached posters the documents already agreed about, so the one case that matters most
    #     — a poster in NEITHER document — was the one case never checked. An asset the
    #     instruction never mentions is either dead weight the agent must ignore or, if it is an
    #     'after' render, the answer; `COPY assets/` ships it either way.
    #
    #     A match on the bare filename counts, not just on the full container path: the
    #     instruction may legitimately spell it relatively or name the file in prose, and this
    #     check should not manufacture a FAIL out of a spelling difference. #7 and #11 are what
    #     hold the container path itself to one value.
    #
    #     Deliberately NOT skipped when 6b fails, unlike #7-#11: the question it asks is
    #     "is every file in assets/ mentioned in instruction.md", and both sides of that come
    #     from disk. The documents only ever contribute `promised` as an extra spelling to
    #     look for, so an unreadable document costs this check one candidate string, not its
    #     ability to answer.
    if on_disk:
        unreferenced = []
        for rel in on_disk:
            name = PurePosixPath(rel).name
            promised = (manifest_by_name.get(rel, {}).get("container_path")
                        or manifest_by_name.get(name, {}).get("container_path")
                        or bundle_by_name.get(name, {}).get("local_path"))
            spellings = [s for s in (promised, rel, name) if s]
            if not any(s in instruction_text for s in spellings):
                unreferenced.append(f"{rel} (documents promise {promised!r})" if promised else rel)
        if unreferenced:
            bad("asset-referenced-in-instruction",
                f"in {ASSETS_REL}/ but never mentioned in instruction.md: {unreferenced} — the "
                f"agent is shipped evidence the task statement never tells it to look at")
        else:
            ok("asset-referenced-in-instruction", f"{len(on_disk)} poster(s) cited in instruction.md")
    elif on_disk is None:
        skip("asset-referenced-in-instruction", f"{ASSETS_REL}/ is missing")
    else:
        skip("asset-referenced-in-instruction", f"{ASSETS_REL}/ holds no poster files")

    # 10. role/description completeness. #7 already compares container paths, so this only
    #     covers what it does not look at. 6b guarantees both keys are present and non-empty
    #     once it passes, so what is left here is whether the two documents AGREE on role.
    #
    #     The final branch is a SKIP, not silence. When both indices were empty this check
    #     used to print nothing at all — no PASS, no FAIL, no SKIP — so a reader had to
    #     notice an absent line to know it had not run.
    if shape_bad:
        skip("asset-role-agrees", SHAPE_SKIP)
    else:
        role_problems = []
        for name in sorted(set(manifest_by_name) & set(bundle_by_name)):
            m_role, b_role = manifest_by_name[name].get("role"), bundle_by_name[name].get("role")
            if m_role != b_role:
                role_problems.append(f"{name}: manifest role={m_role!r} != evidence_bundle role={b_role!r}")
            elif not m_role:
                role_problems.append(f"{name}: neither document gives a 'role'")
            if not (bundle_by_name[name].get("description") or "").strip():
                role_problems.append(f"{name}: evidence_bundle entry has no 'description'")
        if role_problems:
            for problem in role_problems:
                bad("asset-role-agrees", problem)
        elif manifest_by_name and bundle_by_name:
            ok("asset-role-agrees")
        else:
            skip("asset-role-agrees", "no poster is documented in both files (see #9)")

    # 11. the Dockerfile really delivers each poster to the container_path the documents
    #     promise. #7 only checks the two documents against each other, so both can agree
    #     on a path nothing ever copies to.
    if on_disk is not None:
        copies, unparsed = dockerfile_copies(dockerfile_text)
        shipped, missing_sources, whole_dir = shipped_assets(copies, on_disk)
        ship_problems = [f"COPY/ADD mentions assets/ but cannot be parsed: {r!r}" for r in unparsed]
        ship_problems += [f"COPY source {s!r} matches nothing in {ASSETS_REL}/" for s in missing_sources]

        if not shipped:
            # Decidable from the Dockerfile and the directory alone, which is why it is
            # reported even when 6b failed: "nothing ships the posters" is true whatever the
            # documents turn out to say once they are readable.
            ship_problems.append(
                f"no COPY/ADD instruction ships {ASSETS_REL}/, so the agent sees no evidence at all")

        if shape_bad:
            # The Dockerfile half above still stands and is reported. The promised-path
            # comparison is the half that cannot be made, so it is skipped rather than run
            # against an empty `promised` and passed off as "0 poster(s) land where the
            # documents say" — which is what this check printed before 6b existed.
            for problem in ship_problems:
                bad("asset-shipped-to-container", problem)
            if not ship_problems:
                skip("asset-shipped-to-container",
                     f"{SHAPE_SKIP} — COPY/ADD ships {len(shipped)} file(s), but the promised "
                     f"container paths cannot be read to compare against")
        else:
            promised = {}
            for name, entry in manifest_by_name.items():
                if entry.get("container_path"):
                    promised[name] = entry["container_path"]
            for name, entry in bundle_by_name.items():
                promised.setdefault(name, entry.get("local_path"))

            for name in sorted(promised):
                want, got = promised[name], shipped.get(name)
                if not want:
                    continue                   # #7 already reports a missing container_path
                if got is None:
                    ship_problems.append(f"{name}: documents promise {want}, no COPY/ADD delivers it")
                elif os.path.normpath(got) != os.path.normpath(want):
                    ship_problems.append(f"{name}: documents promise {want}, Dockerfile delivers to {got}")

            if ship_problems:
                for problem in ship_problems:
                    bad("asset-shipped-to-container", problem)
            else:
                ok("asset-shipped-to-container",
                   f"{len(promised)} poster(s) land where the documents say"
                   + (" (whole assets/ dir copied)" if whole_dir else ""))
    else:
        # Without the directory there is nothing to compare a COPY against — but say so.
        # This branch used to be absent entirely, so a task with no environment/assets/ got
        # 17 lines where every other task got 18, and the missing one was the check that
        # decides whether the agent is shipped any evidence at all. #9 reports the missing
        # directory; this only has to avoid pretending it had an opinion.
        skip("asset-shipped-to-container", f"{ASSETS_REL}/ is missing")

    # 11b. ASSET_MANIFEST.json never reaches the container. It is packaging metadata naming every
    #      poster's role - what each image is meant to show - so shipping it tells the agent
    #      the answer to the perception step before it has looked. A whole-directory
    #      `COPY assets/` (or `COPY .`) ships it silently. Beyond the manifest, assets/ may
    #      carry only images plus non-image EVIDENCE the documents list (an audit log, a text
    #      dump); an undocumented non-image file is shipped with nothing explaining it. Decided
    #      from the Dockerfile and the directory; when 6b failed the documents cannot say what
    #      is evidence, so only the manifest half is judged and the PASS line says so.
    if on_disk is not None:
        copies, _unparsed = dockerfile_copies(dockerfile_text)
        documented = set(manifest_by_name) | set(bundle_by_name)
        problems_11b = []
        for f, src in sorted(shipped_from_assets(copies, context_files(task_dir)).items()):
            name = PurePosixPath(f).name
            if name == MANIFEST_NAME:
                problems_11b.append(
                    f"the Dockerfile ships {f} into the container (via COPY/ADD source {src!r}) "
                    f"- it lists every poster's role, telling the agent what each image shows "
                    f"before it has looked")
            elif (PurePosixPath(f).suffix.lower() not in IMAGE_EXTS and not shape_bad
                  and name not in documented):
                problems_11b.append(
                    f"the Dockerfile ships {f} (via COPY/ADD source {src!r}), which is neither an "
                    f"image nor evidence listed in the documents")
        if problems_11b:
            for problem in problems_11b:
                bad("assets-images-only", problem)
            # Auto-fix: rewrite the offending source(s) to image globs (+ listed evidence by
            # name). Dry run unless --fix, like the evidence-schema-shape conversion above.
            report_images_only_fix(task_dir / "environment/Dockerfile", dockerfile_text, task_dir,
                                   None if shape_bad else documented, apply_fix)
            print()
        else:
            ok("assets-images-only",
               f"{MANIFEST_NAME} is not shipped"
               + (" (documents unreadable - other non-image files not judged, see 6b)"
                  if shape_bad else "; every other shipped file is an image or listed evidence"))
    else:
        skip("assets-images-only", f"{ASSETS_REL}/ is missing")

    # 12. no absolute paths or '..' traversal anywhere the above collected paths from. The
    #     patch/toml arms are independent of the evidence documents and always run; the
    #     manifest arm is dropped when 6b failed, and check_no_path_escapes names the sources
    #     it actually inspected so the PASS line cannot imply coverage it did not have.
    escape_sources = {
        "files_edited": files_edited,
        "fix.patch paths": sorted(fix_paths),
        "test.patch paths": sorted(test_paths),
    }
    if not shape_bad:
        escape_sources["ASSET_MANIFEST file names"] = [
            e["file"] for e in manifest_entries if e.get("file")]
    check_no_path_escapes(escape_sources)

    summary = f"({len(PASS)} passed, {len(FAIL)} failed"
    summary += f", {len(SKIP)} skipped)" if SKIP else ")"
    print(f"\nintegrity: {'pass' if not FAIL else 'fail'}  {summary}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
