# Project Hygiene

A Claude Code skill that keeps a software project healthy from the first commit
onward — covering both **where files live on disk** and **how the code inside
them is written**. It scaffolds new projects with a sound layout, cleans up
existing ones with risk-aware moves, scans for exposed secrets, and applies
code-level habits (single responsibility, DRY, named constants, graceful
failure, centralized auth) as part of normal review.

## What it does

- **New projects** — proposes and creates a layout (application vs library) before
  any code is written, so structure never forms ad hoc.
- **Existing projects** — analyzes structure, classifies findings by risk
  (reversibility and blast radius), executes the safe fixes, and asks before the
  destructive ones.
- **Secret tripwire** — flags secret-shaped files that aren't gitignored *and*
  secret-shaped strings hardcoded into source/config. Narrow by design; not a
  replacement for a dedicated scanner like gitleaks.
- **Code-level habits** — applied continuously while writing or editing code, not
  only when structure is explicitly raised.

## Layout

```
SKILL.md                       # the skill: when to use, workflow, code habits
references/conventions.md      # deep reference: layout, naming, config, secrets, tests, CI
scripts/analyze_structure.py   # read-only structural + secret analyzer
```

## Using the analyzer

Read-only — it flags candidates, never moves or deletes anything.

```bash
python scripts/analyze_structure.py <project_root>          # human-readable report
python scripts/analyze_structure.py <project_root> --json   # machine-readable
python scripts/analyze_structure.py --selftest              # internal self-checks
```

The secret checks are a narrow tripwire (dedicated secret files plus a few
high-signal hardcoded key shapes), not a full scanner. **A clean run is not proof
a repo is secret-free** — run gitleaks for exhaustive coverage.

## Auto-trigger at project start (optional)

A `SessionStart` hook can nudge Claude to run this skill the moment you open a
fresh/greenfield directory, so the layout is right before the first file lands.
It stays silent in any established repo (manifest, `src/` dir, or `.git`
present). Example hook lives in `~/.claude/hooks/new-project-nudge.py`.

## A note on judgment

These conventions aren't arbitrary style preferences — each one prevents a
specific recurring failure: secrets leaking, imports breaking, contributors
guessing wrong, code that's correct but unreadable six months later. When a
project doesn't fit cleanly (a tiny script, an early prototype), say so rather
than mechanically applying every rule.
