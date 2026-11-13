#!/usr/bin/env python3
"""Content digest of a Tasks/ bundle — what qc_check.md records, and what oracle/nop compare.

USES HARBOR'S OWN DIGEST, NOT A NEW ONE. harbor records `Packager.compute_content_hash` in
every run's lock.json, and mm_run.sh already recomputes it (task_digest_now) to refuse a trial
whose Oracle/Nop controls describe an older bundle. A second algorithm here would produce a
number that agrees with nothing: the marker could say "changed" while lock.json said "same".
So this shells out to harbor's own interpreter and asks harbor. The value written to
qc_check.md is therefore directly comparable with the one in any lock.json.

harbor cannot be imported from the system python3 (it ships under its own 3.12), which is why
this resolves the harbor interpreter from the `harbor` entry point's shebang — the same search
mm_run.sh's harbor_python() performs — instead of just importing it.

THE SUPPLEMENT EXISTS BECAUSE HARBOR'S DIGEST HAS A BLIND SPOT. Packager.collect_files takes
task.toml, instruction.md, README.md, and recursively environment/ tests/ solution/ steps/.
evidence_bundle.json sits at the task root and is in NONE of those, so harbor's digest does not
move when it is edited — verified: editing evidence_bundle.json leaves the hash identical,
editing environment/assets/ASSET_MANIFEST.json changes it. Since the evidence documents are
exactly what the integrity gate grades, a staleness check blind to half of them is not much of
a check, so everything harbor omits is hashed separately and reported separately.

Pure stdlib, no imports from this skill. Invoked two ways, and must keep working as both:
imported by fix.py to write the digest into qc_check.md, and run as a script by mm_run.sh to
compare the current bundle against that record before oracle/nop.

Usage:
  qc_digest.py <tasks-dir>                    print both digests
  qc_digest.py <tasks-dir> --compare <marker> compare against what a marker recorded
Exit codes (compare mode): 0 match, 3 mismatch, 4 nothing recorded / not computable.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

# What Packager.collect_files takes. Anything else in the bundle is harbor's blind spot and
# goes in the supplement. Keep in step with harbor: if collect_files grows a path, move it
# from the supplement to harbor's side by updating these two.
HARBOR_ROOT_FILES = ("task.toml", "instruction.md", "README.md")
HARBOR_DIRS = ("environment", "tests", "solution", "steps")

JUNK = re.compile(r"(^|/)(__pycache__(/|$)|\.git(/|$)|__MACOSX(/|$)|\.DS_Store$)|\.pyc$|~$")

# The marker lives at ONE path (/tmp/qc_check.md by default), not one per task, so it may
# well describe a different task than the one being compared. It records which, and that has
# to be checked first: without it, auditing task A and then running oracle on task B reports
# B as "CHANGED since the QC audit" when B was never audited at all — a false block with a
# message that sends someone hunting for an edit nobody made.
TASK_DIR_LINE = re.compile(r"^- task_dir:\s*`?(.+?)`?\s*$", re.M)
DIGEST_LINE = re.compile(r"^- digest:\s*(sha256:[0-9a-f]{64}|unavailable)\s*$", re.M)
EXTRA_LINE = re.compile(r"^- extra-digest:\s*(sha256:[0-9a-f]{64})\s*$", re.M)
FILE_LINE = re.compile(r"^([0-9a-f]{64})\s\s(.+)$", re.M)

HARBOR_SNIPPET = """
import sys
from pathlib import Path
from harbor.publisher.packager import Packager
print("sha256:" + Packager.compute_content_hash(Path(sys.argv[1]))[0])
"""


def harbor_python():
    """An interpreter that can import harbor, or None. Mirrors mm_run.sh's harbor_python()."""
    exe = shutil.which("harbor")
    if not exe:
        return None
    exe = os.path.realpath(exe)
    try:
        with open(exe, "rb") as fh:
            first = fh.readline(512).decode("utf-8", "replace").strip()
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    parts = first[2:].split()
    if not parts:
        return None
    # `#!/usr/bin/env python3` names env, not the interpreter env would resolve.
    interp = parts[1] if os.path.basename(parts[0]) == "env" and len(parts) > 1 else parts[0]
    if not os.path.isfile(interp) or not os.access(interp, os.X_OK):
        return None
    try:
        subprocess.run([interp, "-c", "import harbor.publisher.packager"],
                       check=True, capture_output=True, timeout=60)
    except (subprocess.SubprocessError, OSError):
        return None
    return interp


def harbor_digest(tasks):
    """harbor's own content hash, or None when harbor cannot be reached.

    DECLINES rather than substituting a home-grown value: a digest that is not harbor's would
    disagree with every lock.json, and a comparison that reports a false mismatch would send
    someone re-running a `check` they did not need.
    """
    interp = harbor_python()
    if not interp:
        return None
    try:
        out = subprocess.run([interp, "-c", HARBOR_SNIPPET, tasks],
                             capture_output=True, timeout=300)
    except (subprocess.SubprocessError, OSError):
        return None
    value = out.stdout.decode("utf-8", "replace").strip()
    return value if re.fullmatch(r"sha256:[0-9a-f]{64}", value) else None


def extra_hashes(tasks):
    """{relpath: sha256} for every file harbor's collect_files does NOT cover."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(tasks):
        rel_dir = os.path.relpath(dirpath, tasks).replace("\\", "/")
        if rel_dir == ".":
            # Do not descend into what harbor already hashes.
            dirnames[:] = [d for d in dirnames if d not in HARBOR_DIRS]
        for name in filenames:
            rel = name if rel_dir == "." else f"{rel_dir}/{name}"
            if JUNK.search(rel) or (rel_dir == "." and name in HARBOR_ROOT_FILES):
                continue
            h = hashlib.sha256()
            try:
                with open(os.path.join(dirpath, name), "rb") as fh:
                    for chunk in iter(lambda: fh.read(65536), b""):
                        h.update(chunk)
            except OSError:
                out[rel] = "unreadable"
                continue
            out[rel] = h.hexdigest()
    return out


def combined(hashes):
    """One digest over a {path: hash} map, in harbor's own "<rel>\\0<hash>\\n" style so the
    two halves are at least built the same way. Covers the file SET as well as contents."""
    outer = hashlib.sha256()
    for rel in sorted(hashes):
        outer.update(f"{rel}\0{hashes[rel]}\n".encode("utf-8"))
    return "sha256:" + outer.hexdigest()


def marker_section(tasks):
    """The markdown block fix.py appends to qc_check.md."""
    hd = harbor_digest(tasks)
    extra = extra_hashes(tasks)
    lines = ["## Bundle digest", "",
             f"- digest: {hd or 'unavailable'}",
             f"- extra-digest: {combined(extra)}",
             f"- extra-files: {len(extra)}", ""]
    if hd:
        lines += ["`digest` is harbor's own `Packager.compute_content_hash` — the same value it",
                  "records in each run's lock.json, so it is comparable with any control run."]
    else:
        lines += ["`digest` is unavailable: harbor could not be reached to compute it. Only the",
                  "files below are covered, and a staleness comparison will say so."]
    lines += ["",
              "`extra-digest` covers what harbor's hash does NOT: evidence_bundle.json and",
              "anything else outside task.toml / instruction.md / README.md / environment/ /",
              "tests/ / solution/ / steps/.", "",
              "```"]
    lines += [f"{extra[rel]}  {rel}" for rel in sorted(extra)]
    lines += ["```", ""]
    return "\n".join(lines)


# ------------------------------------------------------- the per-file map, and what it is FOR
# harbor's digest is one number over task.toml + instruction.md + README.md + environment/ +
# tests/ + solution/ + steps/. You cannot subtract a directory from a hash, so that number can
# answer "did the bundle change?" and never "did anything the AGENT can see change?".
#
# The second question is the one a pseudo-trial turns on. An agent never sees tests/ -- test.patch
# is mounted at /tests/ and applied by the verifier, after the agent phase is over -- so editing
# the tests cannot change what the agent produced, and a recorded submission stays valid. Editing
# instruction.md or environment/ can, and does.
#
# STORE THE MAP, DERIVE THE DIGESTS. An earlier design recorded a single `digest-trusted` value
# plus the exclusion set it was computed under. The map subsumes both: any trusted digest is
# derivable from it at comparison time, under whatever exclusions the caller asks for, so
# changing the exclusion set later does not invalidate records already written.
#
# NOT A SECOND ALGORITHM. harbor's own combining step is sha256 over "<rel>\0<filehash>\n" per
# sorted file, which is exactly what combined() above does -- so combined(full_map) reproduces
# harbor's digest byte-for-byte, and a trusted digest is that same algorithm over a subset.
# That identity is what anchor() checks, and it is the whole basis for trusting a map at all.
HARBOR_MAP_SNIPPET = """
import json, sys
from pathlib import Path
from harbor.publisher.packager import Packager
d = Path(sys.argv[1]).resolve()
_, files = Packager.compute_content_hash(d)
print(json.dumps({f.relative_to(d).as_posix(): Packager.compute_file_hash(f) for f in files}))
"""

# What the agent cannot see, and may therefore change freely between a trial and a pseudo-trial.
# tests/ is verifier-only. solution/ is used by the oracle and by nobody else.
#
# task.toml IS ON THIS LIST BECAUSE IT IS COUPLED TO tests/, NOT BECAUSE IT IS UNIMPORTANT. Its
# f2p/p2p arrays must mirror tests/config.json -- mm_check_integrity.py enforces exactly that, in
# both directions -- so adding or removing a test in test.patch REQUIRES editing task.toml in the
# same breath. Pinning it therefore made the one edit this gate is built to permit impossible to
# perform, and blocked replays for a change that cannot touch a recorded submission: the agent
# never reads task.toml. What the agent actually reads or runs against stays pinned, and that is
# now exactly the remainder -- instruction.md, README.md and environment/.
#
# THE COST, STATED RATHER THAN BLOCKED: task.toml also carries [agent] and [environment] policy
# (network_mode, timeout_sec, resource limits). Edit those after a trial and this gate will not
# notice, even though they describe the conditions the recorded submission was produced under.
# The reward stays honest -- it is measured, and it is this submission against these tests -- but
# a trial record written from it describes a bundle whose run policy has moved. compare_trusted()
# says out loud when task.toml has changed for that reason; it does not refuse.
AGENT_BLIND = ("tests/", "solution/", "task.toml")


def harbor_map(tasks):
    """{relpath: sha256} for exactly the files harbor hashes, or None if harbor is unreachable.

    Uses harbor's OWN collect_files and compute_file_hash rather than walking the tree here: the
    file set is gitignore/pathspec-filtered by rules this module must not try to imitate, and a
    map built from a different set would recombine to a different digest -- which anchor() would
    then report as tampering.
    """
    interp = harbor_python()
    if not interp:
        return None
    try:
        out = subprocess.run([interp, "-c", HARBOR_MAP_SNIPPET, tasks],
                             capture_output=True, timeout=300)
        m = json.loads(out.stdout.decode("utf-8", "replace"))
    except (subprocess.SubprocessError, OSError, ValueError):
        return None
    return m if isinstance(m, dict) else None


def trusted_digest(fmap, blind=AGENT_BLIND):
    """Digest over the agent-VISIBLE half of a map. Same algorithm, fewer files."""
    return combined({k: v for k, v in fmap.items() if not k.startswith(tuple(blind))})


def anchor(fmap, recorded_digest):
    """Does this map recombine to the digest harbor recorded for that run?

    THE ONLY REASON A MAP CAN BE BELIEVED. A map is otherwise just a number we wrote; recombining
    it and matching it against a value harbor itself put in lock.json proves it describes the file
    set harbor actually packaged. A map that fails this is not evidence of anything and callers
    must refuse rather than fall back to it.
    """
    return bool(recorded_digest) and combined(fmap) == recorded_digest


def compare_trusted(map_then, map_now, blind=AGENT_BLIND):
    """(matched, lines). Did anything the agent can see change between two maps?

    Returns per-file detail, not a yes/no: a refusal that cannot name the file it tripped on
    sends someone hunting through a bundle for an edit they may not remember making.
    """
    a = {k: v for k, v in map_then.items() if not k.startswith(tuple(blind))}
    b = {k: v for k, v in map_now.items() if not k.startswith(tuple(blind))}
    # Ignored is not the same as unremarked. task.toml is blind because its f2p/p2p arrays have
    # to move with tests/, but the same file also carries the run policy this gate no longer
    # checks -- so a replay permitted over a CHANGED task.toml says so, and a reader who did not
    # expect that edit still learns of it. Nothing here refuses; see AGENT_BLIND.
    note = []
    if map_then.get("task.toml") != map_now.get("task.toml"):
        note = ["NOTE  task.toml changed since that trial and was not checked: its f2p/p2p must "
                "track tests/. If [agent]/[environment] policy moved too, the recorded "
                "submission was produced under the older policy."]
    if combined(a) == combined(b):
        return True, [f"agent-visible files unchanged ({len(a)} file(s)); "
                      f"{len(map_then) - len(a)} agent-blind file(s) ignored"] + note
    lines = []
    for k in sorted(set(a) & set(b)):
        if a[k] != b[k]:
            lines.append(f"CHANGED  {k}")
    lines += [f"ADDED    {k}" for k in sorted(set(b) - set(a))]
    lines += [f"REMOVED  {k}" for k in sorted(set(a) - set(b))]
    return False, lines + note


MANIFEST_NAME = "task_manifest.json"
MANIFEST_VERSION = 1


def lock_digest(run_dir):
    """The task digest a run's lock.json recorded: a sha256, "mixed", or None.

    MIRRORS mm_run.sh's control_digest(), including BOTH lock shapes -- the job-level lock.json
    carries a trials[] array, the per-trial one inside Tasks__*/ hangs `task` off the root. A job
    whose locks disagree is "mixed" and is not usable as an anchor: picking one would be choosing
    which bundle to believe.
    """
    seen = set()
    for dirpath, _, filenames in os.walk(run_dir):
        if "lock.json" not in filenames:
            continue
        try:
            with open(os.path.join(dirpath, "lock.json"), encoding="utf-8") as fh:
                lock = json.load(fh)
        except (OSError, ValueError):
            continue
        entries = lock.get("trials") or ([lock] if isinstance(lock.get("task"), dict) else [])
        for tr in entries:
            d = ((tr or {}).get("task") or {}).get("digest")
            if d:
                seen.add(d)
    if not seen:
        return None
    return seen.pop() if len(seen) == 1 else "mixed"


def write_manifest(tasks, run_dir):
    """Record the file map for the bundle a run just measured. (path, note).

    WRITES NOTHING UNLESS IT ANCHORS. The map is computed from the bundle on disk NOW, moments
    after the run; the anchor is what proves nothing moved in between. A map that does not
    recombine to the run's own recorded digest describes a bundle that is not the one harbor
    packaged, and recording it would hand a later gate a false baseline -- the exact failure the
    gate exists to prevent. Refusing costs a re-run; recording costs correctness.
    """
    fmap = harbor_map(tasks)
    if fmap is None:
        return None, "harbor could not be reached, so no file map was computed"
    rec = lock_digest(run_dir)
    if not rec:
        return None, "the run recorded no lock.json digest to anchor against"
    if rec == "mixed":
        return None, "the run's lock files disagree about which bundle it measured"
    if not anchor(fmap, rec):
        return None, ("the bundle on disk no longer matches what this run measured, so no "
                      "baseline was recorded (was the task edited while it ran?)")
    body = {"version": MANIFEST_VERSION,
            "task_dir": os.path.realpath(tasks),
            "lock_digest": rec,
            "computed": combined(fmap),
            "trusted": trusted_digest(fmap),
            "blind": list(AGENT_BLIND),
            "files": fmap}
    path = os.path.join(run_dir, MANIFEST_NAME)
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(body, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        return None, f"the baseline could not be written ({exc.__class__.__name__})"
    return path, f"baseline recorded ({len(fmap)} files, trusted {body['trusted'][:23]}…)"


def gate_trusted(tasks, run_dir):
    """May a submission from `run_dir` be replayed against the bundle now? (ok, lines).

    ok is None when the question cannot be answered at all, which is NOT a pass: every caller
    must treat None exactly as it treats False. The distinction exists only so the message can
    say "nothing to compare" rather than "something changed".
    """
    path = os.path.join(run_dir, MANIFEST_NAME)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None, ["this run recorded no baseline, so there is nothing to compare the bundle "
                      "against. Runs from before that was added cannot be replayed."]
    if doc.get("version") != MANIFEST_VERSION or not isinstance(doc.get("files"), dict):
        return None, ["this run's baseline was written by a different version and was ignored"]
    if os.path.realpath(doc.get("task_dir") or "") != os.path.realpath(tasks):
        return None, [f"this run's baseline covers {doc.get('task_dir')}, not this task"]
    then = doc["files"]
    if not anchor(then, doc.get("lock_digest")):
        return None, ["this run's baseline does not match the digest harbor recorded for it, "
                      "so it cannot be trusted as a description of that run"]
    now = harbor_map(tasks)
    if now is None:
        return None, ["harbor could not be reached, so the bundle could not be compared"]
    # UNION, NOT SUBSTITUTION, and that is the whole reason a policy fix here reaches anyone. The
    # recorded list describes what the checker ignored on the day the baseline was written; the
    # constant describes what it ignores now. A baseline written before task.toml joined the blind
    # set would otherwise re-impose the old pin on the trials that are already recorded -- which
    # is precisely the population being unblocked, since a pseudo-trial exists to avoid paying for
    # a fresh one. Unioning is safe in one direction only: AGENT_BLIND may grow, never shrink. To
    # take a path BACK out of it, bump MANIFEST_VERSION so old baselines are refused outright
    # rather than silently keeping a pin the current rule has dropped.
    blind = tuple(sorted(set(doc.get("blind") or ()) | set(AGENT_BLIND)))
    return compare_trusted(then, now, blind)


# ----------------------------------------------------------------- where records live
# ONE resolver, used by fix.py (which writes records) and mm_run.sh (which reads them), for the same
# reason the digest algorithm lives here rather than in both: two copies can disagree, and a reader
# looking in a different place than the writer wrote is indistinguishable from no audit at all.
#
# /tmp comes first, so nothing changes anywhere it works. The fallbacks exist to remove the one
# outcome a CB can do nothing about: a clean audit whose pass could not be recorded, which then
# blocks oracle and nop through a gate with no bypass flag. That state made the CB go and repair a
# directory to get their own controls to run, which is not their job and not their mistake.
#
# Every candidate is OUTSIDE the bundle, deliberately. A record written into the task folder would
# travel to a reviewer along with it, and /run-check-reviewers exists precisely because the CB's
# records must NOT travel -- a reviewer has to re-verify against what they were given.
RECORD_NAMES = {"check": "qc_check.md", "trial": "qc_trial.md",
                "adjudications": "qc_adjudications.json"}

# NOT OPTIONAL, and not bookkeeping: record_path() resolves an unregistered kind through
# `RECORD_NAMES.get(kind, RECORD_NAMES["check"])`, so a caller asking for "adjudications" before
# this entry existed would be handed qc_check.md and the ruling ledger would overwrite the QC pass
# marker. Any new record kind must land in this dict in the same change as its first caller.


def record_dirs():
    """Candidate directories, most-preferred first. Deterministic for a given environment."""
    out = ["/tmp"]
    tmpdir = (os.environ.get("TMPDIR") or "").rstrip("/")
    if tmpdir and tmpdir not in out:
        out.append(tmpdir)
    home = os.path.expanduser("~")
    if os.path.isabs(home):
        for d in (os.path.join(home, ".cache", "mm-swe"), home):
            if d not in out:
                out.append(d)
    return out


def record_path(kind="check"):
    """Absolute path of an audit record: the first candidate that can actually hold one.

    Deterministic, so a writer and a reader in the same environment agree without passing anything
    between them. It FAILS CLOSED in the case where they cannot: a reader that resolves to a
    directory holding no record gets "no audit pass is recorded yet" and sends the CB back to
    /run-check. It can never read a record describing a DIFFERENT bundle, because compare() checks
    task_dir and the digest before believing one -- so a fallback can cost a re-run, never a false
    pass.
    """
    name = RECORD_NAMES.get(kind, RECORD_NAMES["check"])
    for d in record_dirs():
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            continue
        if os.access(d, os.W_OK | os.X_OK):
            return os.path.join(d, name)
    # Nothing is writable. Hand back the primary anyway: the caller's write will fail and it
    # already degrades honestly, and inventing a path here would only move the failure.
    return os.path.join("/tmp", name)


# ------------------------------------------------- what an adjudication is a judgment ABOUT
# A ruling recorded by an agent or a CB has to expire when the thing it ruled on changes, or a
# `cleared` verdict outlives the test it vouched for. The whole-bundle digest above is the wrong
# key for that: every adjudicable finding (`tests_overfit_*`, `tests_ident_collision_*`) is a claim
# about a test body or about verifier.py's matcher, so a typo fix in instruction.md would expire
# every ruling and invite the reflexive re-clearing that PENDING exists to prevent.
#
# So the scope is narrowed to the code the claim is about, and NOT narrowed further to the single
# file a finding cites: a collision ruling depends on tests/verifier.py's matcher as much as on the
# test, and solution/ is what an overfit finding is measured against. Anything under those two
# trees invalidates; nothing outside them does.
ADJUDICATION_DIRS = ("tests", "solution")


def scope_hashes(tasks):
    """{relpath: sha256} for tests/ and solution/. Same walk and skips as extra_hashes()."""
    out = {}
    for sub in ADJUDICATION_DIRS:
        base = os.path.join(tasks, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not JUNK.search(d + "/")]
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, tasks).replace("\\", "/")
                if JUNK.search(rel):
                    continue
                h = hashlib.sha256()
                try:
                    with open(full, "rb") as fh:
                        for chunk in iter(lambda: fh.read(65536), b""):
                            h.update(chunk)
                except OSError:
                    # Deliberately a VALUE, not a skip: a file that stopped being readable is a
                    # change to the tree, and a ruling made when it was readable should expire.
                    out[rel] = "unreadable"
                    continue
                out[rel] = h.hexdigest()
    return out


def scope_digest(tasks):
    """One digest over tests/ + solution/, built with combined() so there is one hashing idiom."""
    return combined(scope_hashes(tasks))


# ------------------------------------------------------------- the ruling ledger
# WHY THIS EXISTS, given that qc_common calls adjudication "stateless by design". That rationale
# ("a fresh container per task, so an on-disk store would have a structurally zero hit rate") is
# right about the case it was written for and wrong about the one that broke: mm_run.sh's qc_gate()
# re-invokes `fix.py qc` with a FIXED argument list, in the same container, on the same bundle,
# seconds after an agent ruled. That is a 100% hit rate, and without a store the re-invocation
# recomputes the finding as PENDING and DELETES the pass the ruling earned - so a task with a
# correctly cleared finding could never satisfy the gate at all.
#
# WHAT THIS MAY AND MAY NOT DO. A ledger entry can only re-apply a verdict to a finding THIS run
# independently recomputed as PENDING; apply_adjudications ignores anything else. It cannot create
# a finding, cannot clear a FAIL, and cannot write a marker - update_qc_marker still removes the
# marker on any blocker. So the ledger is strictly WEAKER than the QC pass record, which is what
# makes it safe to keep beside it. Do not grow it into something that gates anything by itself.
LEDGER_VERSION = 1


def load_rulings(tasks, path=None, valid_verdicts=None):
    """Recorded rulings for `tasks`: ({fid: (verdict, reason)}, [notes]).

    FAILS CLOSED, LOUDLY. Every way of not trusting the file drops ALL of its rulings and appends a
    note saying so, because a silently ignored ledger is indistinguishable from one that was never
    written - and the caller prints these notes. `valid_verdicts` is passed in by the caller rather
    than imported, so qc_common stays the single source of the verdict vocabulary and this module
    keeps its "no imports from this skill" property.
    """
    path = path or record_path("adjudications")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return {}, []
    except (OSError, ValueError):
        return {}, ["a recorded ruling set could not be read, so no ruling was replayed"]
    if not isinstance(doc, dict) or doc.get("version") != LEDGER_VERSION:
        return {}, ["a recorded ruling set was written by a different version and was ignored"]

    recorded_dir = doc.get("task_dir")
    if not isinstance(recorded_dir, str) or \
            os.path.realpath(recorded_dir) != os.path.realpath(tasks):
        # Same guard compare() applies to the marker: one path holds one file, so it may well
        # describe another task, and another task's rulings say nothing about this one.
        return {}, []

    raw = doc.get("rulings")
    if not isinstance(raw, dict) or not raw:
        return {}, []

    now = scope_digest(tasks)
    if doc.get("scope_digest") != now:
        return {}, [f"{len(raw)} recorded ruling(s) EXPIRED: tests/ or solution/ changed since "
                    f"they were made, so they must be ruled on again"]

    out, bad = {}, []
    for fid, entry in raw.items():
        verdict_ = (entry or {}).get("verdict") if isinstance(entry, dict) else None
        reason = (entry or {}).get("reason") if isinstance(entry, dict) else None
        # A verdict this module does not recognise must never reach apply_adjudications, which
        # treats anything that is not `confirmed` as a clear. An unreadable entry silently
        # CLEARING a finding is the one failure mode this validation exists to prevent.
        if valid_verdicts is not None and verdict_ not in valid_verdicts:
            bad.append(fid); continue
        # Mirrors parse_adjudications: an unexplained verdict is not auditable, so it is not one.
        if not isinstance(reason, str) or not reason.strip():
            bad.append(fid); continue
        out[str(fid)] = (verdict_, reason.strip())
    notes = []
    if bad:
        notes.append(f"{len(bad)} recorded ruling(s) were malformed and were ignored: "
                     f"{', '.join(sorted(bad)[:4])}")
    return out, notes


def save_rulings(tasks, rulings, path=None):
    """Merge `rulings` ({fid: (verdict, reason)}) into the record. Returns the path, or None.

    NEVER RAISES INTO AN AUDIT. A ledger that cannot be written costs a re-typed flag; an audit
    that dies because /tmp is full costs the CB their run. Rebuilt from scratch whenever the
    existing file describes another task or another scope, so a stale entry cannot survive an edit
    by riding along in a merge.
    """
    if not rulings:
        return None
    path = path or record_path("adjudications")
    now = scope_digest(tasks)
    merged = {}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if isinstance(doc, dict) and doc.get("version") == LEDGER_VERSION \
                and doc.get("scope_digest") == now \
                and isinstance(doc.get("task_dir"), str) \
                and os.path.realpath(doc["task_dir"]) == os.path.realpath(tasks) \
                and isinstance(doc.get("rulings"), dict):
            merged = dict(doc["rulings"])
    except (OSError, ValueError):
        merged = {}
    stamp = _utcnow()
    for fid, (verdict_, reason) in rulings.items():
        merged[fid] = {"verdict": verdict_, "reason": reason, "recorded_at": stamp}
    body = {"version": LEDGER_VERSION,
            "task_dir": os.path.realpath(tasks),
            "scope_digest": now,
            "rulings": merged}
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(body, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        return None
    return path


def _utcnow():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_detail(marker):
    """The record's PATH, as a diagnostics-only suffix. Empty unless $MM_QC_MARKER_DEBUG.

    compare()'s lines are printed verbatim to the CB by mm_run.sh's check_digest(), so anything
    here is CB-facing. The marker is an INTERNAL artifact and its path must not appear there: a CB
    who learns the filename can create one by hand, and a hand-made record is indistinguishable
    from an earned one -- it would unblock oracle and nop on a bundle no audit has seen, which is
    the single failure this gate exists to prevent. The remedy is always /run-check, which the
    caller already prints; the path adds nothing a CB can safely act on.

    Same opt-in switch fix.py uses for its own write diagnostics, so the team can still tell a
    missing record from a malformed one.
    """
    return [f"(record path: {marker})"] if os.environ.get("MM_QC_MARKER_DEBUG") else []


def compare(tasks, marker):
    """(matched, lines). matched is None when there is nothing usable to compare against.

    Every line returned here reaches the CB. Describe the STATE of the audit, never the file --
    see _record_detail.
    """
    try:
        with open(marker, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None, ["no audit pass is recorded yet"] + _record_detail(marker)

    # Whose audit is this? A marker for another task records nothing about this one.
    t = TASK_DIR_LINE.search(text)
    if t and os.path.realpath(t.group(1)) != os.path.realpath(tasks):
        return None, [f"the recorded audit covers {t.group(1)}, not this task"] \
                     + _record_detail(marker)

    m, e = DIGEST_LINE.search(text), EXTRA_LINE.search(text)
    if not m and not e:
        return None, ["the recorded audit has no digest to compare"] + _record_detail(marker)

    recorded_files = {p: h for h, p in FILE_LINE.findall(text)}
    problems, checked, unchecked = [], [], []

    recorded_harbor = m.group(1) if m else None
    if recorded_harbor and recorded_harbor != "unavailable":
        now_harbor = harbor_digest(tasks)
        if now_harbor is None:
            # NOT a problem: being unable to compute the digest is not evidence the bundle
            # changed. There is no bypass flag on this gate, so a blocking verdict here would
            # ground oracle and nop on any box where harbor cannot be reached — over a check
            # that is an addition to the existing controls, not a replacement for them. Same
            # reasoning mm_run.sh already applies to its own trial-time digest comparison.
            unchecked.append("NOT CHECKED  harbor's half — harbor could not be reached now")
        elif now_harbor != recorded_harbor:
            problems.append("CHANGED  one or more of task.toml / instruction.md / README.md / "
                            "environment/ / tests/ / solution/ / steps/")
        else:
            checked.append("harbor digest")

    if e:
        now_extra = extra_hashes(tasks)
        if combined(now_extra) != e.group(1):
            for p in sorted(set(now_extra) & set(recorded_files)):
                if now_extra[p] != recorded_files[p]:
                    problems.append(f"CHANGED  {p}")
            for p in sorted(set(now_extra) - set(recorded_files)):
                problems.append(f"ADDED    {p}")
            for p in sorted(set(recorded_files) - set(now_extra)):
                problems.append(f"REMOVED  {p}")
        else:
            checked.append("evidence/root files")

    if problems:
        return False, problems + unchecked
    if not checked:
        return None, unchecked or ["nothing in the recorded audit could be compared"]
    # Matched on everything that COULD be compared. Any half that could not is carried in the
    # output so the caller can say so rather than implying a full match.
    return True, [f"bundle matches the audited digest ({', '.join(checked)})"] + unchecked


def main():
    argv = sys.argv[1:]
    positional = [a for a in argv if not a.startswith("-")]
    # Before the positional check: asking where records live needs no bundle. mm_run.sh calls this
    # so it resolves the same path fix.py will write to, rather than keeping its own copy.
    if "--record-path" in argv:
        idx = argv.index("--record-path")
        kind = argv[idx + 1] if idx + 1 < len(argv) and not argv[idx + 1].startswith("-") else "check"
        if kind not in RECORD_NAMES:
            print(f"--record-path takes {' or '.join(sorted(RECORD_NAMES))}", file=sys.stderr)
            return 2
        print(record_path(kind))
        return 0
    if not positional:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    tasks = positional[0]
    if not os.path.isdir(tasks):
        print(f"not a directory: {tasks}", file=sys.stderr)
        return 2

    if "--map" in argv:
        m = harbor_map(tasks)
        if m is None:
            print("harbor could not be reached", file=sys.stderr); return 4
        print(json.dumps(m, indent=2, sort_keys=True)); return 0

    if "--trusted" in argv:
        m = harbor_map(tasks)
        if m is None:
            print("harbor could not be reached", file=sys.stderr); return 4
        print(trusted_digest(m)); return 0

    if "--write-manifest" in argv:
        i = argv.index("--write-manifest")
        if i + 1 >= len(argv):
            print("--write-manifest needs a run dir", file=sys.stderr); return 2
        path, note = write_manifest(tasks, argv[i + 1])
        print(note)
        return 0 if path else 4

    if "--gate-trusted" in argv:
        i = argv.index("--gate-trusted")
        if i + 1 >= len(argv):
            print("--gate-trusted needs a run dir", file=sys.stderr); return 2
        ok, lines = gate_trusted(tasks, argv[i + 1])
        for line in lines:
            print(line)
        return 0 if ok else (3 if ok is False else 4)

    if "--section" in argv:
        # The digest block on its own, for a caller composing a record file around it
        # (mm_run.sh writes qc_trial.md this way). Emitting the SAME block the QC marker
        # uses is what lets --compare read either file without knowing which it is.
        print(marker_section(tasks))
        return 0

    if "--compare" in argv:
        idx = argv.index("--compare")
        if idx + 1 >= len(argv):
            print("--compare needs a marker path", file=sys.stderr)
            return 2
        matched, lines = compare(tasks, argv[idx + 1])
        for line in lines:
            print(line)
        return 0 if matched else (4 if matched is None else 3)

    print(f"digest:       {harbor_digest(tasks) or 'unavailable'}")
    print(f"extra-digest: {combined(extra_hashes(tasks))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
