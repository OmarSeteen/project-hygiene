# Project Hygiene: Conventions Reference

This is the detailed reference behind the project-hygiene skill. SKILL.md covers
the workflow; this file covers the conventions in depth. Read the section relevant to the
current task rather than the whole file.

## Table of contents
1. Folder layout
2. Naming conventions
3. Config & environment separation
4. Secrets handling
5. Test placement
6. Docs placement
7. Monorepo vs single-repo
8. CI/CD placement

---

## 1. Folder layout

A folder structure should make it obvious where new code goes, without asking anyone. If two
reasonable people would put a new file in different places, the structure has a gap. This
traces back to Parnas's 1972 argument that systems should be decomposed around the design
decisions most likely to change, with each module hiding one such decision from the rest,
rather than around the steps of a flowchart. Applied to file layout: group by what's likely
to change together, a feature, a domain concept, not by what happens to run in sequence. A
structure built around "this is where database code goes" survives a change to the database.
One built around "this runs second" survives almost nothing.

Common shapes, by project type:

**Single application (web app, CLI tool, service):**
```
project/
├── src/ or <package_name>/    # actual source, never loose in root
├── tests/                     # mirrors src/ structure
├── docs/
├── scripts/                   # one-off or maintenance scripts, not part of the app
├── config/                    # non-secret configuration
├── .env.example                # template, never the real .env
├── README.md
└── <manifest file>             # package.json, pyproject.toml, go.mod, etc.
```

**Library/package meant to be imported by others:**
```
project/
├── <package_name>/            # importable code, kept lean, no app-specific code
├── tests/
├── examples/                  # runnable usage examples
├── docs/
└── <manifest file>
```

**`src/` vs flat layout (Python specifically, though the logic generalizes):** putting the
package inside `src/<package_name>/` instead of directly at the project root changes what
your tests exercise. With a flat layout, Python adds the current working directory to the
import path, so running tests from the project root can import the local working copy of
your code even where it has bugs that the packaged version wouldn't have once installed.
The `src/` layout forces tests to import the installed package, which catches "works on my
machine, breaks for users" bugs before they ship. This matters most for libraries and
packages meant to be installed by others. For a script or app that's never pip-installed,
the distinction matters less, and a flat layout works fine.

A handful of files at the project root is normal: a main entrypoint (`main.py`, `app.py`,
`index.js`), the manifest file, README, `.gitignore`, CI config. The smell is unrelated
modules, business logic, helper functions, data access, piling up at the root instead of
inside a package directory. That's what `analyze_structure.py`'s `root_clutter` check looks
for; it allowlists common entrypoint names so it doesn't flag those.

**Depth tradeoff:** flat is easier to navigate, deep is easier to scale. For a project under
roughly 20 source files, one or two levels of nesting is enough; resist building a deep
hierarchy for a future size the project hasn't reached. Add more structure once a directory
holds more than 10 to 15 files that don't obviously belong together, not before. This is the
YAGNI principle (You Aren't Gonna Need It) applied to structure instead of features: a
`services/`, `interfaces/`, `adapters/` layering the project might need at ten times its
current size costs real navigability now, for a need that may never materialize or may
materialize differently than guessed. Add structure when the current size demands it, not
when it's merely possible that it might.

---

## 2. Naming conventions

What matters more than which style you pick is consistency within a directory and within a
language ecosystem. Mixing `snake_case` and `camelCase` files in the same JS directory is a
sign two contributors touched the project without a shared convention.

Ecosystem defaults, what the tooling and other engineers will expect:
- **Python**: `snake_case` for files and modules, `PascalCase` for classes inside them.
- **JavaScript/TypeScript**: the split that matters is filename vs the name exported from
  the file, and the two don't need to match in casing. Community consensus (not an official
  Next.js or React mandate, neither takes a documented stance on user file naming) leans
  toward `kebab-case` filenames across the board, `user-profile.tsx`, `format-date.ts`,
  partly because kebab-case avoids case-sensitivity bugs when code moves between
  case-sensitive (Linux/CI) and case-insensitive (Mac/Windows) filesystems. Inside
  the file, the exported component stays `PascalCase` (`export default function
  UserProfile()`), hooks and utility functions are `camelCase`, and hook files start with
  `use` (`use-auth.ts` exporting `useAuth`). Some codebases keep `PascalCase` filenames for
  components matching the export name; both approaches work, the failure mode is mixing
  them inconsistently within one project.
- **Go**: a subtlety worth knowing. The "no underscores, short lowercase names" rule applies
  to package names, the identifier after `package` in the source, for example `package
  httputil`, not to filenames. Go filenames aren't identifiers, and underscores in them are
  normal and common in the standard library itself (`routing_index.go`). Pick one filename
  convention, underscored or concatenated, and stay consistent within a project; it isn't a
  hard rule the way package naming is.
- **General config/docs**: `kebab-case` (`api-reference.md`) or `UPPERCASE` for files meant
  to stand out (`README.md`, `LICENSE`, `CHANGELOG.md`).

When advising on naming, name the convention the ecosystem already expects rather than
inventing a new one. A project that follows its language's idioms is easier for any future
contributor, human or AI, to navigate cold.

---

## 3. Config & environment separation

Three things that should never live in the same file:
1. **Code** (logic)
2. **Configuration** (values that change per environment: timeouts, feature flags, URLs)
3. **Secrets** (values that grant access: API keys, passwords, tokens)

Practical pattern:
- Non-secret config lives in versioned files (`config/settings.yaml`, `config.py`) or
  environment variables loaded at startup.
- Secrets live in environment variables, loaded from a `.env` file that is never committed.
- A `.env.example`, with placeholder values and no real secrets, is committed, so the next
  person knows what variables to set.
- Config that differs by environment (dev/staging/prod) is either separate files
  (`config/dev.yaml`, `config/prod.yaml`) or a single file with environment-keyed sections.
  Pick one pattern and use it everywhere; don't mix per module.

If config files show up in more than two or three different directories (`config_sprawl` in
the analysis script), that's usually a sign config was added file by file instead of
designed once.

---

## 4. Secrets handling

This is the highest-severity category because the failure mode is irreversible: a leaked
key in git history stays leaked even after the file is deleted. Rotating the credential is
the only real fix.

Checklist when reviewing or scaffolding a project:
- [ ] `.gitignore` includes `.env`, `*.key`, `*.pem`, and any credential-shaped filenames
      before the first commit, not after.
- [ ] No secret-looking file is tracked in git. `git log --all --full-history -- <path>`
      shows whether a now-gitignored file was ever committed in the past; gitignore doesn't
      retroactively scrub history.
- [ ] Secrets are read from environment variables or a secrets manager, never hardcoded as
      string literals in source, even temporarily during development. Temporary hardcodes
      are exactly what gets committed by accident.
- [ ] CI/CD pipelines pull secrets from the platform's secret store (GitHub Actions secrets,
      GitLab CI variables), never from a checked-in file.
- [ ] For anything beyond a quick personal script, a pre-commit secret-scanning hook is
      worth the few minutes it takes to set up. `.gitignore` only stops new files from being
      tracked; it does nothing for a secret pasted directly into a source file. Gitleaks is
      a common free choice: a single binary that works as a pre-commit hook and as a CI
      step. AI coding assistants writing code on someone's behalf increase the rate at
      which secrets get hardcoded and committed by accident, since the assistant has no way
      to know which constants are sensitive unless told. Scanning isn't only for larger
      teams.

If a secret was already committed, rotating the credential matters more than scrubbing
history. Say this plainly if it comes up. Cleaning history with `git filter-repo` is good
practice but doesn't undo exposure if the repo was ever public or cloned, and a scanner will
keep flagging the old commit even after rotation, since the string is still sitting in git
history.

---

## 5. Test placement

Two valid patterns; pick one and apply it consistently.

**Mirrored tree** (common in Python, Java, larger JS projects):
```
src/auth/login.py        →  tests/auth/test_login.py
src/billing/invoice.py   →  tests/billing/test_invoice.py
```
Keeps shipped code and test code clearly separated, and makes it easy to exclude tests/ from
packaging. The tradeoff: jumping between a file and its test means jumping directories.

**Co-located** (common in modern JS/TS, Go):
```
src/auth/login.ts
src/auth/login.test.ts
```
The test sits next to what it tests, which makes it hard to forget to update. The tradeoff:
test code ships alongside source unless explicitly filtered by the build.

The analysis script flags two situations, not which pattern was chosen: tests scattered
outside an existing `tests/` directory (inconsistent use of the mirrored pattern), and test
files with no test directory at all, which is fine for co-located but worth a second look.

---

## 6. Docs placement

- `README.md` at the project root is the front door. It should answer "what is this, how do
  I run it" in under a minute of reading, not become the full documentation.
- `docs/` holds everything beyond the README: architecture notes, API references, decision
  records. A README that's grown past roughly 150 lines is usually a sign content belongs in
  `docs/` instead.
- `CHANGELOG.md` matters for any project with external consumers, a published package, an
  API, anyone with users who aren't the author. Even a manually maintained one beats none.
- Inline code comments and docs/ are complementary, not redundant. Comments explain why a
  specific piece of code does something non-obvious; docs/ explains how the system fits
  together as a whole. If a README needs to explain individual functions, that content
  belongs in a docstring or comment instead.

---

## 7. Monorepo vs single-repo

This is a judgment call, not a default. Don't recommend a monorepo just because a project
has multiple pieces.

**Single-repo per project** fits when:
- Components are deployed and versioned together
- The team, or solo developer, working on it is small
- There's no need to share code across genuinely separate products

**Monorepo** fits when:
- Multiple deployable services or packages share substantial code (shared types, shared
  utils)
- Atomic commits across packages that change together matter
- Tooling for it already exists. Adopting a monorepo without workspace tooling just means a
  folder full of unrelated projects, which is worse than separate repos. In the JS/TS
  ecosystem, many monorepos need no dedicated orchestrator at all, `pnpm` and `bun`
  workspaces handle linking and scripts natively; reach for a build-orchestration layer only
  once task graphs and caching across packages actually hurt. When you do, Turborepo and Nx
  are the two established choices (Moonrepo is a newer Rust-based contender). Lerna's role
  has narrowed to npm package versioning and publishing, and it runs on Nx under the hood for
  everything else; reach for it only if publishing multiple npm packages is the actual job,
  not as a general monorepo tool. Python and Go each have their own native multi-package
  workspace support that doesn't need a separate tool layered on top.

If asked which to use for a specific situation, the deciding question is: if these pieces
version and deploy independently, why are they versioned together? If there's a good answer
(a shared library, coordinated releases), monorepo earns its complexity. If not, separate
repos are simpler, and simplicity is the right default.

---

## 8. CI/CD placement

- GitHub Actions: `.github/workflows/*.yml`. This location is enforced by the platform, not
  a convention choice.
- GitLab CI: `.gitlab-ci.yml` at root, similarly enforced.
- Generic or self-hosted (Jenkins, CircleCI without native repo integration): a `ci/` or
  `.ci/` directory keeps pipeline config out of the root, with the platform-specific entry
  file pointing into it.
- Keep pipeline logic, build steps, deploy steps, in versioned scripts the pipeline calls
  into (`scripts/deploy.sh`), rather than writing complex logic directly in YAML. YAML is
  hard to test and debug locally; a shell or Python script can be run and debugged outside
  CI.
