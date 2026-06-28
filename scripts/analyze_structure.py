#!/usr/bin/env python3
"""
Scans a project directory and reports structural smells: files that violate
common senior-engineer conventions around layout, naming, config/secret
separation, test placement, and docs placement.

This script is deliberately conservative — it flags candidates for a human
(or Claude) to review, it never moves or deletes anything itself. Read-only.

The secret checks are a narrow tripwire (dedicated secret files plus a few
high-signal hardcoded key shapes), not a substitute for a real scanner like
gitleaks. A clean run is not proof a repo is secret-free.

Usage:
    python analyze_structure.py <project_root>
    python analyze_structure.py <project_root> --json   # machine-readable output
    python analyze_structure.py --selftest              # run internal self-checks
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Directories we never want to walk into — either huge, generated, or vendored.
SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", "__pycache__",
    "dist", "build", ".next", ".cache", "target", "vendor",
    ".idea", ".vscode", "coverage", ".pytest_cache", ".mypy_cache",
    "site-packages", ".tox", "egg-info",
}

# File extensions that count as "source code" for placement checks.
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rb", ".java",
    ".c", ".cpp", ".cs", ".rs", ".php", ".swift", ".kt",
}

TEST_NAME_PATTERNS = [
    re.compile(r"^test_.*"), re.compile(r".*_test\..*"),
    re.compile(r".*\.test\..*"), re.compile(r".*\.spec\..*"),
]

SECRET_FILENAME_PATTERNS = [
    re.compile(r"^\.env$"), re.compile(r"^\.env\..*"),
    re.compile(r".*secret.*", re.IGNORECASE),
    re.compile(r".*credentials.*", re.IGNORECASE),
    re.compile(r".*\.pem$"), re.compile(r".*\.key$"),
    re.compile(r".*service[-_]?account.*\.json$", re.IGNORECASE),
]

CONFIG_EXTENSIONS = {".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf"}

# High-signal patterns for secrets pasted directly into source — the common,
# highest-severity failure mode (especially with AI-written code) that a
# filename-only check misses entirely. Deliberately narrow to keep false
# positives low; this is a tripwire, not a replacement for a real scanner.
SECRET_CONTENT_PATTERNS = [
    ("AWS access key id", re.compile(r"(?:AKIA|ASIA)[A-Z2-7]{16}")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----")),
    ("PGP private key block", re.compile(r"-----BEGIN PGP PRIVATE KEY BLOCK-----")),
    ("Slack token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("hardcoded credential assignment", re.compile(
        r"""(?i)(?:api[_-]?key|secret|passwd|password|token|access[_-]?key)\s*[:=]\s*['"][^'"\n]{8,}['"]""")),
]

# Values that look like a secret's shape but are obviously not real — skip these
# so .env.example placeholders and doc snippets don't generate noise.
PLACEHOLDER_RE = re.compile(
    r"(?i)(example|placeholder|your[_-]?|changeme|xxx+|<[^>]+>|\$\{|\{\{|dummy|sample|redacted|\.\.\.|fake|test[_-]?key)")

NAMING_STYLES = {
    "snake_case": re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$"),
    "kebab-case": re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$"),
    "camelCase": re.compile(r"^[a-z][a-zA-Z0-9]*$"),
    "PascalCase": re.compile(r"^[A-Z][a-zA-Z0-9]*$"),
}


def classify_naming(stem):
    """Return which naming style a filename stem matches, or None."""
    for style, pattern in NAMING_STYLES.items():
        if pattern.match(stem):
            return style
    return None


def walk_project(root: Path):
    """Yield (path, is_dir) for everything under root, skipping noisy dirs."""
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def find_root_clutter(root: Path, all_paths):
    """Flag source files sitting loose in the project root instead of a package/src dir."""
    issues = []
    root_files = [p for p in root.iterdir() if p.is_file()]
    code_at_root = [p for p in root_files if p.suffix in CODE_EXTENSIONS]
    # A handful of root-level entrypoints (main.py, app.py, manage.py, setup.py)
    # is normal and expected — only flag when there's a real pile-up.
    entrypoint_names = {"main", "app", "manage", "setup", "wsgi", "asgi", "conftest"}
    non_entrypoint_code = [p for p in code_at_root if p.stem.lower() not in entrypoint_names]
    if len(non_entrypoint_code) > 3:
        issues.append({
            "type": "root_clutter",
            "severity": "medium",
            "detail": f"{len(non_entrypoint_code)} source files sit directly in the project root "
                      f"instead of a package/src/lib directory: "
                      f"{', '.join(p.name for p in non_entrypoint_code[:6])}"
                      f"{'...' if len(non_entrypoint_code) > 6 else ''}",
        })
    return issues


def find_misplaced_tests(root: Path, all_paths):
    """Flag test files that live next to source instead of in a tests/ tree, or vice versa missing mirror."""
    issues = []
    has_tests_dir = any(p.is_dir() and p.name in ("tests", "test", "__tests__", "spec") for p in all_paths)
    test_files_outside = []
    for p in all_paths:
        if not p.is_file():
            continue
        if any(pat.match(p.name) for pat in TEST_NAME_PATTERNS):
            if not any(parent.name in ("tests", "test", "__tests__", "spec") for parent in p.parents):
                test_files_outside.append(p)
    if test_files_outside and has_tests_dir:
        issues.append({
            "type": "scattered_tests",
            "severity": "low",
            "detail": f"A tests/ directory exists, but {len(test_files_outside)} test file(s) live "
                      f"outside it: {', '.join(str(p.relative_to(root)) for p in test_files_outside[:5])}"
                      f"{'...' if len(test_files_outside) > 5 else ''}. Consolidating keeps test "
                      f"discovery and CI config simple.",
        })
    elif test_files_outside and not has_tests_dir:
        issues.append({
            "type": "no_test_directory",
            "severity": "low",
            "detail": f"Found {len(test_files_outside)} test file(s) but no dedicated tests/ directory. "
                      f"Co-locating tests next to source (common in JS/Go) is fine if consistent — "
                      f"flagging in case a centralized tests/ tree is preferred instead.",
        })
    return issues


def load_gitignore(root: Path):
    """Read .gitignore into a list of (non-comment, non-blank) pattern lines."""
    path = root / ".gitignore"
    if not path.exists():
        return []
    return [
        line.strip() for line in path.read_text(errors="ignore").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _glob_to_regex(pat: str) -> str:
    """Translate a gitignore glob to a regex body, with git's `*`/`?` semantics:
    they do NOT cross `/`. `**` does. fnmatch can't express this (its `*` crosses
    `/`, and it's case-insensitive on Windows) — both are secret-hiding bugs in a
    tripwire, so we compile our own instead."""
    out, i, n = [], 0, len(pat)
    while i < n:
        c = pat[i]
        if c == "*":
            if i + 1 < n and pat[i + 1] == "*":
                out.append(".*"); i += 2; continue
            out.append("[^/]*"); i += 1; continue
        if c == "?":
            out.append("[^/]"); i += 1; continue
        if c == "[":  # char class — pass through, find the close
            j = i + 1
            if j < n and pat[j] in "!^": j += 1
            if j < n and pat[j] == "]": j += 1
            while j < n and pat[j] != "]": j += 1
            if j >= n:
                out.append(r"\["); i += 1; continue
            inner = pat[i + 1:j]
            if inner.startswith("!"): inner = "^" + inner[1:]
            out.append("[" + inner + "]"); i = j + 1; continue
        out.append(re.escape(c)); i += 1
    return "".join(out)


def matches_gitignore(rel_path: str, patterns):
    """Best-effort gitignore match for a path relative to the repo root.

    Handles the cases that actually decide secret exposure: basename globs
    (`*.key`), anchored paths (`/dist/`), `**`, negation (`!keep.env`), and
    git's case-sensitive, `/`-respecting `*`. Last matching pattern wins, like
    git.

    ponytail: own glob→regex, no nested-.gitignore support and no dir-only
    enforcement for trailing-slash patterns (no filesystem read here). If exact
    parity with git matters, shell out to `git check-ignore` instead.
    """
    rel = rel_path.replace("\\", "/")
    name = rel.rsplit("/", 1)[-1]
    ignored = False
    for pat in patterns:
        neg = pat.startswith("!")
        if neg:
            pat = pat[1:]
        anchored = pat.startswith("/")
        pat = pat.strip("/")
        if not pat:
            continue
        body = _glob_to_regex(pat)
        if "/" in pat or anchored:
            # Match the path itself or anything beneath it (dir pattern).
            hit = re.fullmatch(body, rel) or re.fullmatch(body + "/.*", rel)
        else:
            # Unanchored pattern matches any path component (file or dir),
            # which also covers everything beneath a matched directory.
            hit = re.fullmatch(body, name) or any(re.fullmatch(body, part) for part in rel.split("/"))
        if hit:
            ignored = not neg
    return ignored


def find_secrets_at_risk(root: Path, all_paths):
    """Flag secret-looking files that are not covered by .gitignore."""
    issues = []
    patterns = load_gitignore(root)
    for p in all_paths:
        if not p.is_file():
            continue
        if any(pat.match(p.name) for pat in SECRET_FILENAME_PATTERNS):
            rel = str(p.relative_to(root))
            if not matches_gitignore(rel, patterns):
                issues.append({
                    "type": "unignored_secret",
                    "severity": "high",
                    "detail": f"'{rel}' looks like it may contain secrets/credentials "
                              f"and doesn't appear to be covered by .gitignore. Verify it isn't tracked "
                              f"in git history (a past commit doesn't get cleaned by .gitignore alone). "
                              f"A pre-commit secret scanner (e.g. gitleaks) catches this class of issue "
                              f"even when a secret gets pasted directly into source rather than left in "
                              f"a dedicated file.",
                })
    return issues


def find_hardcoded_secrets(root: Path, all_paths):
    """Flag source/config files containing text that matches a real secret shape.

    Catches the high-severity case `find_secrets_at_risk` can't see: a key
    pasted straight into code rather than left in a dedicated file. Narrow by
    design — flags candidates for a human to confirm, never auto-acts.
    """
    issues = []
    scannable = CODE_EXTENSIONS | CONFIG_EXTENSIONS
    for p in all_paths:
        if not p.is_file() or p.suffix not in scannable:
            continue
        lower = p.name.lower()
        if "example" in lower or "sample" in lower or "template" in lower:
            continue
        try:
            if p.stat().st_size > 1_000_000:  # skip huge/generated files
                continue
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        found = []
        for label, pat in SECRET_CONTENT_PATTERNS:
            m = pat.search(text)
            if m and not PLACEHOLDER_RE.search(m.group(0)):
                found.append(label)
        if found:
            issues.append({
                "type": "hardcoded_secret",
                "severity": "high",
                "detail": f"'{p.relative_to(root)}' contains text matching {', '.join(sorted(set(found)))}. "
                          f"Confirm it isn't a real credential; if it is, rotate it immediately — gitignore "
                          f"does not scrub a secret already committed to history. Run a dedicated scanner "
                          f"(e.g. gitleaks) for exhaustive coverage; this check is a narrow tripwire.",
            })
    return issues


def find_config_sprawl(root: Path, all_paths):
    """Flag config files scattered across multiple directories instead of a config/ home or root."""
    issues = []
    config_dirs_seen = set()
    config_files = []
    for p in all_paths:
        if p.is_file() and p.suffix in CONFIG_EXTENSIONS:
            config_files.append(p)
            config_dirs_seen.add(p.parent)
    # More than a couple distinct directories holding config = sprawl worth a look.
    non_root_dirs = {d for d in config_dirs_seen if d != root}
    if len(non_root_dirs) > 2:
        issues.append({
            "type": "config_sprawl",
            "severity": "low",
            "detail": f"Config files ({len(config_files)} total) are spread across "
                      f"{len(non_root_dirs)} different directories. Consider a single config/ "
                      f"directory or co-locating with the module that owns each setting.",
        })
    return issues


def find_naming_inconsistency(root: Path, all_paths):
    """Flag directories where files mix naming conventions (snake_case vs kebab-case vs camelCase)."""
    issues = []
    by_dir = {}
    for p in all_paths:
        if not p.is_file() or p.suffix not in CODE_EXTENSIONS:
            continue
        by_dir.setdefault(p.parent, []).append(p)

    for directory, files in by_dir.items():
        if len(files) < 4:
            continue
        styles_found = set()
        for f in files:
            style = classify_naming(f.stem)
            if style:
                styles_found.add(style)
        # camelCase and PascalCase often coexist intentionally (e.g. components vs hooks),
        # so only flag when snake_case mixes with either dash or camel style — that's the
        # combination senior engineers actually consider sloppy.
        if "snake_case" in styles_found and ("kebab-case" in styles_found or "camelCase" in styles_found):
            issues.append({
                "type": "naming_inconsistency",
                "severity": "low",
                "detail": f"'{directory.relative_to(root)}' mixes naming conventions "
                          f"({', '.join(sorted(styles_found))}) across {len(files)} files. "
                          f"Pick one convention per language/directory and stick to it.",
            })
    return issues


def find_missing_standard_files(root: Path):
    """Flag absence of conventional project-level files that aid onboarding and tooling."""
    issues = []
    expected = {
        "README.md": "high",
        ".gitignore": "high",
    }
    for filename, severity in expected.items():
        if not (root / filename).exists():
            issues.append({
                "type": "missing_standard_file",
                "severity": severity,
                "detail": f"No {filename} found at project root.",
            })
    return issues


def analyze(root: Path):
    all_paths = list(walk_project(root))
    issues = []
    issues += find_missing_standard_files(root)
    issues += find_root_clutter(root, all_paths)
    issues += find_misplaced_tests(root, all_paths)
    issues += find_secrets_at_risk(root, all_paths)
    issues += find_hardcoded_secrets(root, all_paths)
    issues += find_config_sprawl(root, all_paths)
    issues += find_naming_inconsistency(root, all_paths)

    severity_order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: severity_order.get(i["severity"], 3))
    return issues


def _selftest():
    """Self-check for the non-trivial logic: the gitignore matcher and the
    secret content scanner. Run with `--selftest`. No framework, stdlib only."""
    import tempfile

    # gitignore matcher
    pats = ["/dist/", "*.key", ".env", "config/local.yaml", "!keep.key"]
    assert matches_gitignore(".env", pats)
    assert matches_gitignore("sub/app.key", pats)            # basename glob, nested
    assert matches_gitignore("dist/bundle.js", pats)         # anchored dir
    assert matches_gitignore("config/local.yaml", pats)      # path pattern
    assert not matches_gitignore("config/prod.yaml", pats)   # sibling not ignored
    assert not matches_gitignore("src/app.py", pats)
    assert not matches_gitignore("keep.key", pats)           # negation re-includes
    # `*` must not cross `/` (Bug A): git would track this, so must NOT match.
    assert not matches_gitignore("config/sub/database.yaml", ["config/*.yaml"])
    assert matches_gitignore("config/database.yaml", ["config/*.yaml"])
    # case-sensitive like git (Bug B): different case must NOT match.
    assert not matches_gitignore("secret.env", ["Secret.env"])

    # secret content scanner over a throwaway tree
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "leak.py").write_text('aws_key = "AKIA' + "B" * 16 + '"\n')
        (root / "ok.py").write_text('api_key = "your-api-key-here"\n')      # placeholder
        (root / "config.example.yaml").write_text('token = "AKIA' + "C" * 16 + '"\n')  # skipped by name
        paths = list(walk_project(root))
        sec = find_hardcoded_secrets(root, paths)
        flagged = {Path(i["detail"].split("'")[1]).name for i in sec}
        assert "leak.py" in flagged, flagged
        assert "ok.py" not in flagged, "placeholder must not flag"
        assert "config.example.yaml" not in flagged, "example file must be skipped"

        # private-key header variants embedded in source must trip the tripwire
        (root / "pgp.py").write_text("KEY = '''-----BEGIN PGP PRIVATE KEY BLOCK-----'''\n")
        (root / "enc.py").write_text("KEY = '''-----BEGIN ENCRYPTED PRIVATE KEY-----'''\n")
        paths = list(walk_project(root))
        flagged = {Path(i["detail"].split("'")[1]).name for i in find_hardcoded_secrets(root, paths)}
        assert "pgp.py" in flagged, flagged
        assert "enc.py" in flagged, flagged

        # unignored-secret detection honors the gitignore matcher
        (root / ".gitignore").write_text("*.key\n")
        (root / "creds.pem").write_text("x")     # not ignored -> flag
        (root / "secret.key").write_text("x")    # *.key ignored -> no flag
        paths = list(walk_project(root))
        names = " ".join(i["detail"] for i in find_secrets_at_risk(root, paths))
        assert "creds.pem" in names, names
        assert "secret.key" not in names, names

    print("selftest passed")


def main():
    parser = argparse.ArgumentParser(description="Analyze a project's file structure for organizational smells.")
    parser.add_argument("project_root", nargs="?", help="Path to the project directory to analyze")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON instead of text")
    parser.add_argument("--selftest", action="store_true", help="Run internal self-checks and exit")
    args = parser.parse_args()

    if args.selftest:
        _selftest()
        return
    if not args.project_root:
        parser.error("project_root is required (or pass --selftest)")

    root = Path(args.project_root).resolve()
    if not root.is_dir():
        print(f"Error: '{root}' is not a directory", file=sys.stderr)
        sys.exit(1)

    issues = analyze(root)

    if args.json:
        print(json.dumps({"project_root": str(root), "issue_count": len(issues), "issues": issues}, indent=2))
        return

    if not issues:
        print(f"No structural issues found in {root}. Looks clean.")
        return

    print(f"Found {len(issues)} structural issue(s) in {root}:\n")
    for i, issue in enumerate(issues, 1):
        print(f"{i}. [{issue['severity'].upper()}] {issue['type']}")
        print(f"   {issue['detail']}\n")


if __name__ == "__main__":
    main()
