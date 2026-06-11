# CLAUDE.md — Agent Behavior Contract

> This file governs how Claude (and other AI coding agents) interact with this repository. It extends `AGENTS.md` with agent-specific behavioral rules. Read `AGENTS.md` first, then this file.

---

## 1. Issue-First Rule (Scoped)

**An issue is required before writing code for:**
- New features (any net-new capability)
- BREAKING changes (API, DB schema, observable behavior)
- Security-sensitive work (auth, crypto, rate-limiting, secrets)
- Anything >150 LOC

**An issue is NOT required for:**
- Unit / integration tests (the PR description is enough)
- Bug fixes ≤50 LOC where the diff is self-explanatory
- Refactors ≤50 LOC with no behavior change
- Documentation, comments, README updates
- Chores: dependency bumps, config tweaks, lint fixes
- CI-only changes
- Test fixtures

**Even when an issue is required, the body can be short.** A 3-sentence web-UI issue is enough — Problem / Solution / Verification, one line each. The full mandatory-sections template (Problem Statement, Root Cause, Proposed Solution, Alternatives Considered, Verification Plan, Semantic Classification) is reserved for:
- Features that gate a release tag
- BREAKING changes
- Architectural decisions (new service, new dependency, new pattern)

For everything else, the PR description carries the context. Title + 2 paragraphs + verification checklist.

### When to use the full template
If a stakeholder might ask "why did we build this?" 6 months later and the answer needs to be searchable, use the full template. Otherwise short form.

### Rationale
Solo-founder phase prioritizes velocity. Audit trail still matters for big decisions. Relaxing the rule scope captures both. Re-tighten when a second contributor joins.

### Issue Template (Mandatory Sections)

Every issue created by an agent must include **all** of the following:

```markdown
## Problem Statement
[What is broken or missing? For bugs: concrete reproduction steps. For features: the user story.]

## Root Cause / Motivation
[Why does this happen? Or why is this feature needed? Link to code if relevant.]

## Proposed Solution
[The approach, files to modify, and any architectural decisions.]

## Alternatives Considered
[What else was evaluated and why this approach was chosen.]

## Verification Plan
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual QA steps: [describe]
- [ ] Typecheck clean: `npx tsc --noEmit`

## Semantic Classification
- **Type**: `bug` | `feature` | `refactor` | `perf` | `security` | `tech-debt`
- **Breaking**: `BREAKING` | `NON_BREAKING` | `FIX` | `DOCS_ONLY`
- **Scope**: `api` | `web` | `shared` | `services` | `infra`
```

### Why This Matters

- Issues are searchable documentation. PRs disappear after merge; issues persist.
- Forces the agent to think before coding, reducing revert rate.
- Enables project tracking, changelog generation, and release notes.
- Makes reviews faster because the context is already documented.

---

## 2. PR Description Standard

Every PR must have a body that answers **what**, **why**, and **how to verify**.

### PR Template (Mandatory)

```markdown
## What
[One-paragraph summary.]

## Changes
- **File/path.ts** — [what changed and why]
- **File/path.ts** — [what changed and why]

## Why
[The motivation, trade-offs, and any architectural decisions.]

## Verification
- [ ] `pnpm typecheck` — clean
- [ ] `pnpm --filter @ai-video-editor/api test` — N passing
- [ ] `pnpm --filter @ai-video-editor/web test` — N passing
- [ ] `.venv/Scripts/python -m pytest tests/` — N passing
- [ ] Manual QA: [steps]

## Regression Risks
[What could break and how it's guarded against.]

## Linked Issues
Closes #<issue-number>
```

### Prohibited

- PRs with empty bodies or only a title
- PRs that say "see commit messages" or "self-explanatory"
- PRs that skip the verification checklist

---

## 3. Semantic Classification (Never Skip)

Every issue and PR must be classified. This enables automated changelog generation and release management.

| Label | Meaning | Example |
|---|---|---|
| `bug` | Something is broken | "Autosave infinite loop when offline" |
| `feature` | New capability | "Add keyboard shortcuts for undo/redo" |
| `refactor` | Internal restructuring, no behavior change | "Extract autosave logic into hook" |
| `perf` | Performance improvement | "Debounce save calls to reduce API load" |
| `security` | Vulnerability or hardening | "Add rate limiting to upload endpoint" |
| `tech-debt` | Deferred cleanup | "Migrate remaining forms to react-hook-form" |

| Breaking Tag | Meaning |
|---|---|
| `BREAKING` | Changes public API, DB schema, or observable behavior |
| `NON_BREAKING` | Purely additive; existing code continues to work |
| `FIX` | Corrects behavior to match documented/intended behavior |
| `DOCS_ONLY` | Documentation, comments, or README changes only |

---

## 4. Testing Discipline

### Before Any Commit

1. Run `pnpm typecheck` — must be clean
2. Run `pnpm --filter @ai-video-editor/api test` — must pass
3. Run `pnpm --filter @ai-video-editor/web test` — must pass (if web changed)
4. Run Python tests if Python code changed

### Coverage Ratchet (Do Not Lower)

| Metric | Floor | Current |
|---|---|---|
| Statements | 70% | 86.79% |
| Branches | 55% | 76.67% |
| Functions | 60% | — |
| Lines | 70% | — |

If a PR drops coverage, the PR description must explain why and how it will be recovered.

---

## 5. Commit Message Format

Follow Conventional Commits with issue reference:

```
<type>(<scope>): <description>

[optional body explaining why]

Closes #<issue-number>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`

---

## 6. Minimal Changes Principle

This codebase is fragile. Prefer:
- Small PRs over large ones
- Refactoring one file at a time
- Adding tests before changing behavior
- Copy-paste over premature abstraction

---

## 7. Cross-Reference

- `AGENTS.md` — General project orientation and conventions
- `CONTRIBUTING.md` — Human contributor guide
- `docs/ARCHITECTURE.md` — System design decisions
- `docs/TESTING.md` — Testing patterns and how-to
