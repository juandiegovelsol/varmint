#!/usr/bin/env python3
"""Build the FACT digest the test-fitness check reads instead of exploring for itself.

WHY THIS EXISTS. Judging overfit needs three references - what the instruction asks, what the
posters ask, and what a plausible implementation looks like in this repo. An agent handed only the
bundle spends most of its budget rediscovering mechanical facts: which lines are the test body,
which symbols the golden actually introduced, which tests share a fixture. On the reference task
that exploration was roughly 90% of a 199k-token audit, and the two real findings came from the
other 10%.

Everything here is a FACT with a checkable source. It contains no verdicts, and that is the whole
design: the check it replaced (`check_O`) inferred semantics from token patterns - "the golden
INTRODUCES computeCalibration" because the name appeared on the added side of the diff - and was
wrong four times on one task. A symbol's presence in the base tree is not an inference. It is
looked up, and the answer is printed with a line number.

Read the posters yourself and paste their facts into the slot; images are the half of the
specification the text deliberately omits, and nothing mechanical can supply them.

    python3 fitness_digest.py <task-dir> [--out digest.md]
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "checks"))
from qc_structure import (  # the base-fetch machinery, already proven by the identifier check
    _raw_url, _http_get, collect_test_source, parse_toml, load_json, _ident_leaf, read)

_TEST_DECL = re.compile(
    r"\b(?:x|f)?(?:it|test|specify)(?:\.(?:only|skip|each))?\s*\(\s*(['\"`])(.+?)\1", re.S)
_IMPORT = re.compile(r"^\s*import\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]", re.M)
_ASSERT_ANY = re.compile(r"\bexpect\s*\(|\bgetBy\w+\s*\(|\bfindBy\w+\s*\(|\bqueryBy\w+\s*\(|"
                         r"\bthrow\s+new\s+\w*Error|\bassert\w*\s*\(")
_LITERAL = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)(?![\w.])")
_CALL = re.compile(r"\b([a-z][A-Za-z0-9_]*)\s*\(")


def _fetch_base(repo, sha, path, notes):
    url = _raw_url(repo, sha, path)
    if not url:
        return None
    import time
    body, _ = _http_get(url, time.monotonic() + 30, notes, path)
    return body or None


def _test_bodies(src):
    """{test name: body text} - each body runs to the next declaration at the same indent."""
    out, marks = {}, [(m.start(), m.group(2)) for m in _TEST_DECL.finditer(src)]
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(src)
        out[name] = src[pos:end]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--out")
    a = ap.parse_args()
    # Flat Tasks/task.toml, nested Tasks/<any-name>/task.toml, or the task dir itself.
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "checks"))
    from qc_layout import find_task_dir, AmbiguousLayout
    try:
        t = find_task_dir(a.task) or a.task
    except AmbiguousLayout as exc:
        sys.exit(f"error: {exc}")
    conf, _ = load_json(os.path.join(t, "tests/config.json"))
    md = (parse_toml(os.path.join(t, "task.toml")) or {}).get("metadata") or {}
    repo, sha = (md.get("repo_url") or "").strip(), (md.get("base_commit") or "").strip()
    golden = read(os.path.join(t, "solution/fix.patch")) or ""
    src = collect_test_source(t, conf, include_context=True)
    notes = []
    # the pre-existing test files, so bodies of PRE-EXISTING tests resolve too
    for tf in conf.get("test_files") or []:
        if not os.path.exists(os.path.join(t, tf)):
            b = _fetch_base(repo, sha, tf, notes)
            if b:
                src += "\n" + b
    bodies = _test_bodies(src)

    # --- which symbols the golden ACTUALLY introduces, verified against the base tree ----------
    edited = re.findall(r"^diff --git a/\S+ b/(\S+)$", golden, re.M)
    base_src = {}
    for f in edited:
        base_src[f] = _fetch_base(repo, sha, f, notes) or ""
    base_all = "\n".join(base_src.values())
    added = "\n".join(l[1:] for l in golden.splitlines()
                      if l.startswith("+") and not l.startswith("+++"))
    # Only names the golden DECLARES. An earlier version collected every `word(` on the added
    # side, which swept in `return`, `push`, `filter`, `some`, `round`, `toFixed` and any local
    # called `card` - then "resolved" them by finding the word somewhere in a base file, which is
    # not evidence of anything. A declaration is a fact; an appearance is not.
    # THE SET THAT MATTERS IS WHAT THE TESTS DEPEND ON, not what the golden declares. Built the
    # other way round, `computeCalibration` never appears - the golden edits its body rather than
    # redeclaring it - and the agent gets no answer to the exact question that produced four false
    # "the golden introduces this" findings on this task.
    #
    # AND EVERY IMPORT IS RESOLVED TO ITS OWN MODULE. Checking a name against only the golden's
    # edited files marks `describe`, `expect`, `render` and every helper from an unedited file as
    # INTRODUCED, which is false and is the same mistake in a new place: absent from the files I
    # happened to fetch is not absent from the repo.
    DECLS = (r"(?:export\s+)?(?:async\s+)?function\s+%s\b",
             r"(?:export\s+)?(?:const|let|var)\s+%s\s*[:=]",
             r"(?:export\s+)?(?:class|interface|type|enum)\s+%s\b")

    def _declared_in(body, name):
        for pat in DECLS:
            m = re.search(pat % re.escape(name), body or "")
            if m:
                return (body[:m.start()].count("\n") + 1)
        return None

    def _resolve(importer, mod):
        """Candidate repo paths for a relative import from `importer`."""
        base = os.path.dirname(importer)
        p = os.path.normpath(os.path.join(base, mod)).replace(os.sep, "/")
        return [p + e for e in (".ts", ".tsx", ".js", "/index.ts", "/index.tsx", "")]

    symbols, seen = [], set()
    per_file = {}
    for tf in conf.get("test_files") or []:
        body = read(os.path.join(t, tf))
        if body is None:
            body = _fetch_base(repo, sha, tf, notes) or ""
        per_file[tf] = body
    for tf, body in per_file.items():
        for names, mod in _IMPORT.findall(body):
            imported = [n.strip().split(" as ")[0].strip() for n in names.split(",") if n.strip()]
            imported = [n.replace("type ", "").strip() for n in imported]
            if not mod.startswith("."):
                for n in imported:
                    if n not in seen:
                        seen.add(n)
                        symbols.append((n, "THIRD-PARTY", "imported from `%s`" % mod))
                continue
            target, tbody = None, None
            for capath in _resolve(tf, mod):
                b = base_src.get(capath)
                if b is None:
                    b = _fetch_base(repo, sha, capath, [])
                if b:
                    target, tbody = capath, b
                    break
            for n in imported:
                if n in seen:
                    continue
                seen.add(n)
                if tbody is None:
                    symbols.append((n, "UNRESOLVED", "could not fetch `%s` at %s" % (mod, sha[:7])))
                    continue
                ln = _declared_in(tbody, n)
                symbols.append((n, "PRE-EXISTS", "%s:%d (base)" % (target, ln)) if ln
                               else (n, "INTRODUCED", "not declared in %s at base" % target))
    # plus anything the golden DECLARES that the tests also reference by name
    for pat in DECLS:
        for c in re.findall(pat.replace(r"%s", r"([A-Za-z_]\w*)"), added):
            if len(c) > 2 and c not in seen and re.search(r"\b%s\b" % re.escape(c), src):
                seen.add(c)
                where = next((f for f, b in base_src.items() if _declared_in(b, c)), None)
                symbols.append((c, "PRE-EXISTS", "%s (base)" % where) if where
                               else (c, "INTRODUCED", "declared only on the golden's added side"))
    symbols.sort()

    L = []
    w = L.append
    w("# Test-fitness digest — %s" % md.get("task_id", "?"))
    w("")
    w("Facts only. No verdict here is implied; every line is looked up and sourced.")
    w("")
    w("## 1. What is asked, in words")
    w("")
    w("```")
    w((read(os.path.join(t, "instruction.md")) or "").strip())
    w("```")
    w("")
    w("## 2. What is asked, visually — YOU MUST FILL THIS IN")
    w("")
    for p in sorted(os.listdir(os.path.join(t, "environment/assets"))):
        if p.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            w("- `%s/environment/assets/%s`" % (t, p))
    w("")
    w("> Open them and record what they specify: counts, edges, exact wording, layout, which")
    w("> values are visible. On a `visual_essentiality = required` task the image carries")
    w("> requirements the text omits, and an assertion on a poster-visible value is FAIR however")
    w("> literal it looks. Nothing mechanical can supply this section.")
    w("")
    w("## 3. Symbols on the golden's added side, checked against the base tree")
    w("")
    w("`INTRODUCED` means the golden brought it into existence, so a test pinning it may be")
    w("pinning the golden. `PRE-EXISTS` means the golden only modified it — a test referencing it")
    w("is referencing the repo, not the fix. Verify before treating any name as golden-only.")
    w("")
    w("| symbol | status | source |")
    w("|---|---|---|")
    for c, st, wh in symbols:
        w("| `%s` | %s | %s |" % (c, st, wh))
    w("")
    w("## 4. The graded tests")
    w("")
    for kind in ("f2p", "p2p"):
        w("### %s (%d)" % (kind, len(conf.get(kind) or [])))
        w("")
        for ident in conf.get(kind) or []:
            leaf = _ident_leaf(ident)
            body = bodies.get(leaf, "")
            asserts = len(_ASSERT_ANY.findall(body))
            lits = sorted(set(_LITERAL.findall(body)))[:12]
            calls = sorted({c for c in _CALL.findall(body) if len(c) > 3})[:10]
            w("**%s**" % leaf)
            w("")
            w("- assertions found: %d %s" % (asserts, "" if asserts else "  <-- none matched; read it, it may assert by other means"))
            w("- numeric literals: %s" % (", ".join("`%s`" % x for x in lits) or "none"))
            w("- calls: %s" % (", ".join("`%s`" % x for x in calls) or "none"))
            if body:
                w("")
                w("```")
                w(body.rstrip()[:1800])
                w("```")
            else:
                w("- BODY NOT RESOLVED — read it in the container")
            w("")
    w("## 5. Setup / fixture reuse")
    w("")
    w("Tests sharing one fixture with no override cannot, between them, distinguish a data-driven")
    w("implementation from one hardcoded to that fixture. Where several tests below call the same")
    w("setup with no argument, the suite's discrimination rests on the ones that DO override.")
    w("")
    # A fixture is a helper the TEST FILE declares - not a matcher, not a keyword. Scanning every
    # `word(` reported `async()`, `any()` and `arrayContaining()` as fixtures, which is noise.
    declared = set(re.findall(r"(?:function|const|let)\s+([a-z][A-Za-z0-9_]*)\s*[=(]", src))
    setups = {}
    for ident in (conf.get("f2p") or []) + (conf.get("p2p") or []):
        leaf = _ident_leaf(ident)
        b = bodies.get(leaf, "")
        for fn in declared:
            calls = re.findall(r"\b%s\s*\(([^)]{0,40})" % re.escape(fn), b)
            if not calls:
                continue
            # "no override" = every call in this test passes nothing
            setups.setdefault(fn, {})[leaf] = any(c.strip() for c in calls)
    any_row = False
    for fn, per_test in sorted(setups.items()):
        plain = sorted(n for n, overridden in per_test.items() if not overridden)
        if len(per_test) >= 3 and len(plain) >= 2:
            any_row = True
            w("- `%s()` used by %d test(s), **%d of them with no argument**: %s"
              % (fn, len(per_test), len(plain), ", ".join("`%s`" % n for n in plain[:8])))
    if not any_row:
        w("- no helper declared in the test source is shared by 3+ graded tests with 2+ of them "
          "passing no argument.")
    w("")
    if notes:
        w("## Fetch notes")
        w("")
        for n in notes:
            w("- %s" % n)
        w("")
    out = "\n".join(L)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(out)
        print("wrote %s (%d lines, ~%dk tokens)" % (a.out, len(L), len(out) // 4000))
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
