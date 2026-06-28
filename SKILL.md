---
name: project-hygiene
description: Keeps a software project healthy from first commit onward, covering both where files live on disk and how individual files should be written. Covers folder layout, naming, config/secrets separation, test/docs placement, monorepo vs single-repo, CI placement, and code-level habits (single-responsibility files, DRY, named constants with rationale, why-focused comments, graceful failure handling, centralized authorization). Use when the user asks how to structure a project, asks to organize or clean up a repo, scaffolds a new project, or shares a file tree for feedback. Also consult proactively when noticing messy organization mid-task, such as loose files in root, ungitignored secrets, scattered tests, or mixed naming, or when writing/editing code and noticing magic numbers, missing why-comments, unguarded external calls, duplicated logic, or scattered auth checks. Flag these as part of normal code review judgment, not only when structure or quality is explicitly raised.
---

# Project Hygiene

Senior engineers treat project structure and code organization as design decisions, not
afterthoughts. A new contributor, or a future version of yourself six months later, should be
able to guess where something lives without asking. This skill is a guideline for both halves
of that goal: where files live on disk, and how the code inside them is written. It covers
analysis, risk-aware execution for existing projects, layout for new projects, and the
ongoing code-level habits that keep a project healthy as it grows.

## When to use this

- Explicit requests: "organize my repo," "how should I structure this project," "is this
  folder layout okay," "clean up this mess."
- New project scaffolding: when starting a project from scratch, set up the structure using
  these conventions from the start rather than letting it form ad hoc.
- Proactively, mid-task: if you're already working in a project and notice structural
  smells, loose files in root, tests scattered outside `tests/`, inconsistent naming, mention
  it. A one-line flag costs little and catches real problems.
- Proactively, for secrets: this needs a deliberate check, not passive noticing. Standard
  directory listings often skip dotfiles, so an `.env` sitting ungitignored next to the code
  you're editing can go unseen during normal browsing. Whenever a task touches environment
  variables, API keys, credentials, or config loading, or whenever you're touching a project
  for the first time in a session, check `cat .gitignore` (or note its absence) and look for
  `.env`/credential-shaped files with a command that shows hidden files, such as `ls -la`,
  rather than relying on having spotted it along the way. Secrets are the highest-severity,
  least-reversible category this skill covers.
- Continuously, while writing or editing code: the code-level habits in Step 5 (single
  responsibility, DRY, named constants with rationale, mutation-safe data structures,
  why-comments, graceful failure on external calls, centralized authorization, matching
  existing style) apply on every coding task in a project, not only when structure was
  explicitly asked about.

This skill is language-agnostic. The principles apply across Python, JS/TS, Go, or any
other stack; see `references/conventions.md` for ecosystem-specific naming and layout
defaults.

## Workflow

### Step 1: Analyze before proposing anything

Run the bundled analysis script against the project root before suggesting changes. It's
read-only, it never modifies anything, and it gives a concrete, evidence-based list of issues
instead of a vibes-based one:

```bash
python3 scripts/analyze_structure.py <project_root>
```

Use `--json` to process the output programmatically, for example to group issues before
presenting them. The script checks for missing standard files (README, .gitignore), source
files cluttering the root instead of living in a package directory, secrets-looking files
that aren't gitignored, secret-shaped strings hardcoded directly into source or config,
scattered test files, config sprawl across directories, and naming convention
inconsistencies within a directory.

The hardcoded-secret check is a deliberately narrow tripwire (AWS/Google/Slack key shapes,
private-key blocks, quoted `password=`/`api_key=` assignments), not a full scanner. A clean
run is not proof a repo is secret-free; for anything beyond a quick personal script,
recommend a dedicated pre-commit scanner such as gitleaks for exhaustive coverage. The
script's own self-checks run with `python3 scripts/analyze_structure.py --selftest`.

The script's checks aren't exhaustive. They catch the common, programmatically-detectable
smells. Use judgment on top of it for anything structural that requires reading the code,
such as whether a monorepo split makes sense, or whether a "utils" dump is several
distinct concerns that should be separate modules.

### Step 2: Classify each finding by risk before proposing

Not all fixes are equal. Sort what you found, from the script and from your own read of the
project, into two buckets:

**Low-risk: execute directly, then report what you did.**
- Creating new standard directories (`tests/`, `docs/`, `config/`) that don't exist yet
- Creating a missing `.gitignore` or `.env.example`
- Moving a file into a directory that already matches the project's existing convention,
  such as moving a stray `test_foo.py` into an existing `tests/` directory
- Renaming a file to match the naming convention already dominant in its directory
- Adding entries to an existing `.gitignore`
- Moving root-clutter source files into a package directory, but only after grepping the
  project for references to those filenames (`grep -rn "filename_without_ext"` or the
  language equivalent). Zero matches outside the file itself means the move is low-risk.
  Even one or two matches puts it in the higher-risk bucket below, since a missed import
  update is a silent break, not a loud one. Run this check even on files that look like
  obvious leftovers; those are exactly the files most likely to be quietly imported
  somewhere else.

**Higher-risk: always propose first and wait for explicit go-ahead.**
- Deleting any file, even one that looks redundant or unused
- Anything involving a file that looks like it holds real secrets. Don't move or show its
  contents; point out the risk and ask how the user wants to handle it. Rotating the
  credential matters more than relocating the file.
- Moving or renaming files in a way that could break imports or references across many
  files. If a move requires updating more than a couple of import statements elsewhere,
  surface the full list of affected files before touching anything.
- Restructuring that changes the public shape of a package: anything importable from
  outside the project, published packages, API contracts.
- Any change to git history (`git filter-repo`, history rewrites).
- Converting between monorepo and single-repo, or any change that affects how the project
  is deployed or versioned.

The dividing line is reversibility and blast radius. A file move within a project is trivial
to undo with git. A deleted file, an exposed secret, or a broken import across a dozen files
is not free to undo. When unsure which bucket something falls into, confirm first; the cost
of one extra confirmation is far lower than the cost of an unwanted destructive change.

### Step 3: Present the plan, then execute

For the low-risk bucket, state what you're about to do before doing it, then execute it. A
short list is enough; this is narrating intent, not asking permission. For the higher-risk
bucket, stop and wait for an explicit yes before touching anything. A reasonable structure
for the response:

```
Found N structural issues. I'll fix the straightforward ones:
- [low-risk item 1]
- [low-risk item 2]

These need your call first since they're harder to undo:
- [higher-risk item 1] (why it needs confirmation)
```

After executing the low-risk fixes, report what changed: paths moved, files created. Give
the user a clear record rather than only saying "done."

### Step 4: New project scaffolding

When setting up a project from scratch rather than fixing an existing one, there's nothing
to analyze yet. Go straight to proposing a layout based on the project type (application vs
library), language, and any stack details the user mentioned, using
`references/conventions.md` section 1 for the shape and sections 2 to 3 for naming and
config defaults. Create the structure directly; this is greenfield, so there's no existing
work to risk.

### Step 5: Code-level habits that keep a repo healthy day to day

Structure is where files live. Code organization is what's inside each file, and it
degrades just as easily without anyone deciding to let it. Apply these on every coding task
in a project, not only when the structural workflow above is explicitly invoked:

- **Single responsibility.** A filename should say what's inside without needing to open
  it. If a function does two unrelated things, split it. If a file accumulates unrelated
  responsibilities over time, split that too rather than let it grow into a grab-bag.
- **DRY, where the thing not being repeated is knowledge, not just text.** Two files
  containing the same literal block of code is the obvious case, but DRY also covers the
  same fact expressed twice in different forms: a validation rule enforced both in a form
  and in the API that receives it, a business rule re-derived in two places instead of
  computed once and reused. If that fact changes, one place should need editing, not several
  places that have to be remembered and kept in sync by hand.
- **Named constants with a reason, not just a value.** Magic numbers, paths, URLs, and
  pinned third-party asset references (a CDN URL, a version pin, a hash) belong in one
  config location with a comment explaining why that value was chosen, not just what it is.
  Scattering the same literal across multiple files means a future change requires hunting
  for every copy instead of editing one place.
- **In-place mutation isn't always tracked.** When a structure is persisted through an ORM
  or serialization layer (a JSON or dict-backed column is the classic case), the default
  type often tracks reassignment but silently drops in-place edits. Check whether the library
  ships a mutation-tracking variant, and verify with a quick test rather than assuming —
  per-field tracking on the same model has documented interference cases.
- **Comments explain why, not what.** State the edge case being handled, the order
  operations are tried and why that order matters, the failure mode being tolerated on
  purpose. A comment that restates the code adds noise, not information; skip it. If code
  isn't clear without a paragraph explaining what it's doing, refactor the code into
  something self-explanatory instead of writing a longer comment. Comments cover the why a
  reader can't get from reading the code at all, not a patch for code that's hard to read.
- **Fail gracefully on anything that touches the outside world.** Network calls,
  third-party APIs, optional integrations such as a notification or webhook. Wrap these so
  one failure doesn't abort the operation the user cares about; log or surface the failure,
  then let the primary flow continue. The core action a person is performing shouldn't be
  sacrificed because an auxiliary side effect failed.
- **Authorization checks live in one guarded layer**, not sprinkled across templates,
  views, and helpers. A query-level check or a decorator that every protected path routes
  through can be audited in one place. Logic duplicated across a dozen call sites will
  eventually be missed in one of them.
- **Match the surrounding code's existing style.** Naming patterns, comment density, idioms
  already in use, rather than introducing a new convention mid-project even if you'd write
  it differently. Consistency within a codebase beats any one style being objectively
  better.

A project that's organized on disk but full of undocumented magic numbers and scattered auth
checks isn't easy to work in. The two halves of this guideline work together.

## Reference material

`references/conventions.md` has the full depth behind each topic: folder layout patterns,
naming conventions per ecosystem, config and secret separation, test placement patterns,
docs placement, monorepo vs single-repo tradeoffs, and CI config conventions. Read the
relevant sections rather than the whole file, for example "what does a Python library layout
look like" or "should this be a monorepo."

## A note on judgment over rules

These conventions aren't arbitrary style preferences. Each one exists to prevent a specific,
recurring failure: secrets leaking, imports breaking, new contributors guessing wrong about
where things live, code that's correct but unreadable six months later. When a project's
situation doesn't fit cleanly, a tiny script that doesn't need a `tests/` directory, a
prototype where deep structure would be premature, say so rather than mechanically applying
every rule. The goal is a project that's easy to navigate, easy to read, and safe to work in,
not maximum compliance with a checklist.
