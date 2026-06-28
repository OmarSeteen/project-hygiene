#!/usr/bin/env python3
"""SessionStart hook: nudge Claude to scaffold structure when cwd looks like a
fresh/greenfield project, so the project-hygiene skill runs at the very start
instead of after the layout already went sideways.

Stays SILENT for any established project (manifest, src dir, or .git present) so
it adds zero noise to day-to-day work. Reads the session cwd from the hook's
stdin JSON; never raises — a hook that crashes must not break session start.

Install: copy to ~/.claude/hooks/ and register under hooks.SessionStart (matcher
"startup") in ~/.claude/settings.json, e.g.:
    {"hooks": {"SessionStart": [{"matcher": "startup", "hooks": [
        {"type": "command", "command": "python \"~/.claude/hooks/new-project-nudge.py\""}
    ]}]}}
"""
import json
import sys
from pathlib import Path

# A project is "already set up" if any of these sit at the root.
MANIFESTS = {
    "package.json", "pyproject.toml", "setup.py", "setup.cfg", "go.mod",
    "cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts", "gemfile",
    "composer.json", "requirements.txt", "pipfile", "deno.json", "build.sbt",
    "mix.exs", "pubspec.yaml", "makefile", "cmakelists.txt",
}
SRC_DIRS = {"src", "app", "lib", "cmd", "internal", "pkg"}


def looks_greenfield(root: Path) -> bool:
    try:
        entries = list(root.iterdir())
    except OSError:
        return False
    names = {e.name.lower() for e in entries}
    if ".git" in names:               # version-controlled = not fresh
        return False
    if names & MANIFESTS:             # has a build manifest = set up
        return False
    if any(e.is_dir() and e.name.lower() in SRC_DIRS for e in entries):
        return False
    # Nothing that marks an initialized project. Empty or near-empty dirs and
    # loose-file piles both qualify as "scaffold me first".
    return True


def main():
    try:
        raw = sys.stdin.read()
        cwd = json.loads(raw).get("cwd") if raw.strip() else None
    except (ValueError, OSError):
        cwd = None
    root = Path(cwd) if cwd else Path.cwd()

    if not looks_greenfield(root):
        return  # silent: established project

    print(
        "New/greenfield project detected (no manifest, src dir, or .git in "
        f"'{root.name}'). Before writing code, use the project-hygiene "
        "skill to scaffold a sound layout up front: pick application-vs-library "
        "shape, create src/ or the package dir, tests/, .gitignore, and "
        ".env.example, and set the naming convention. Cheaper now than "
        "reorganizing later. Skip if this dir is intentionally not a project root."
    )


if __name__ == "__main__":
    main()
