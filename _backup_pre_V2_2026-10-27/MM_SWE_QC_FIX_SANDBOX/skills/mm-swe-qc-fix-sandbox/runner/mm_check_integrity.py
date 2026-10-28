#!/usr/bin/env python3
"""Task-integrity gate for MM SWE tasks — runs before `harbor check` spends a run.

`check_files()` in mm_run.sh only confirms the required files EXIST; it says nothing
about whether they agree with each other. This catches the class of error where every
file is present but they disagree: task.toml claims one base_commit while the Dockerfile
pins another, files_edited names a file the golden patch never touches, the golden patch
quietly also edits the test harness, or the bug screenshot path drifts across
evidence_bundle.json / ASSET_MANIFEST.json / instruction.md.

Deliberately NOT here: an "every f2p/p2p id appears literally in tests/test.patch" check
used to live here and was removed. It doesn't hold in general — p2p ids are pre-existing
tests test.patch normally never touches, and f2p ids can *also* be pre-existing tests that
were already failing on base_commit and simply start passing once the fix is applied,
never appearing in test.patch either. Confirming an id actually names a test that exists
after test.patch is applied needs the real test file content, which means a repo
checkout — out of scope for this no-checkout gate (see below). That's what oracle running
the actual f2p/p2p selection against the real test file is for.

Pure stdlib, no docker, no network, no repo checkout — every check is a string/set
comparison across files already shipped in the task dir, so this runs in well under a
second. task.toml is NOT a full TOML parse (this sandbox's python3 has no tomllib/tomli):
each field is pulled with the same kind of targeted regex mm_run.sh itself already uses
for task_id and base_commit. Good enough for the handful of scalar/array-of-string keys
this needs; do not use load_toml_fields() as a general TOML parser.

Deliberately NOT here (see the skill's design discussion): patch-applies-cleanly, JSON/TOML
syntax validity, script syntax checks, upstream GitHub verification. Those either surface
for free the moment oracle runs, or need a real checkout/network — out of scope for a
free pre-flight gate. This is metadata cross-checks only.

Usage:
  mm_check_integrity.py <task-dir>
Exit code: 0 if every check passes, 1 if any fails.
"""
from __future__ import annotations
import json
import re
import shlex
import sys
from pathlib import Path

FAIL = []   # (check_id, message) accumulated as we go
PASS = []   # check_id only


def ok(check_id, detail=""):
    PASS.append(check_id)
    print(f"PASS {check_id}" + (f" — {detail}" if detail else ""))


def bad(check_id, detail):
    FAIL.append((check_id, detail))
    print(f"FAIL {check_id} — {detail}")


# --------------------------------------------------------------- task.toml (regex, not a parser)
def load_toml_scalar(text, key):
    """key = "value"  or  key = 'value'  — TOML allows either quote style."""
    m = re.search(rf'^[ \t]*{re.escape(key)}[ \t]*=[ \t]*(?:"([^"]*)"|\'([^\']*)\')', text, re.M)
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else m.group(2)


def load_toml_str_array(text, key):
    """key = [ "a", 'b', ... ] — possibly spanning multiple lines. String elements only,
    either quote style, mixed or not. re.findall gives '' (not None) for the alternation
    branch that didn't match a given element, so pick whichever side is non-empty —
    correct as long as no element is itself the empty string, which none of this script's
    fields (paths, f2p/p2p ids, URLs) legitimately are."""
    m = re.search(rf'^[ \t]*{re.escape(key)}[ \t]*=[ \t]*\[(.*?)\]', text, re.M | re.S)
    if not m:
        return None
    return [dq or sq for dq, sq in re.findall(r'"([^"]*)"|\'([^\']*)\'', m.group(1))]


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
        ok("no-path-escapes", "no absolute or '..' paths in files_edited/patches/manifest")


def main():
    if len(sys.argv) != 2:
        print("usage: mm_check_integrity.py <task-dir>", file=sys.stderr)
        return 2
    task_dir = Path(sys.argv[1])

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

    # 7. the bug-screenshot path agrees across evidence_bundle.json, ASSET_MANIFEST.json,
    #    and instruction.md.
    manifest_path = task_dir / "environment/assets/ASSET_MANIFEST.json"
    evidence_path = task_dir / "evidence_bundle.json"
    manifest_ok = True
    if manifest_path.is_file() and evidence_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        manifest_by_file = {e.get("file"): e for e in manifest if isinstance(e, dict)}
        for ev in evidence:
            if not isinstance(ev, dict):
                continue
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
            if local_path and local_path not in instruction_text:
                bad("asset-path-consistent",
                    f"{local_path!r} (evidence_bundle/ASSET_MANIFEST) not referenced in instruction.md")
                manifest_ok = False
        if manifest_ok:
            ok("asset-path-consistent")
    else:
        bad("asset-path-consistent", "evidence_bundle.json or ASSET_MANIFEST.json missing")
        manifest_ok = False

    # 8. every file ASSET_MANIFEST.json declares actually exists on disk.
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        missing_assets = []
        for entry in manifest:
            if not isinstance(entry, dict):
                continue
            fname = entry.get("file")
            if fname and not (task_dir / "environment/assets" / fname).is_file():
                missing_assets.append(fname)
        if missing_assets:
            bad("asset-files-exist", f"declared in ASSET_MANIFEST but not on disk: {missing_assets}")
        else:
            ok("asset-files-exist")
    else:
        bad("asset-files-exist", "ASSET_MANIFEST.json missing")

    # 9. no absolute paths or '..' traversal anywhere the above collected paths from.
    manifest_files = []
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_files = [e.get("file", "") for e in manifest if isinstance(e, dict) and e.get("file")]
    check_no_path_escapes({
        "files_edited": files_edited,
        "fix.patch paths": sorted(fix_paths),
        "test.patch paths": sorted(test_paths),
        "ASSET_MANIFEST file names": manifest_files,
    })

    print(f"\nintegrity: {'pass' if not FAIL else 'fail'}  ({len(PASS)} passed, {len(FAIL)} failed)")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
