---
inclusion: auto
name: pull_requests
description: PR description template, pre-merge checklist and commit conventions for SignalForge. Use when opening, writing, reviewing or merging a pull request, writing a PR description or title, or preparing a branch for review.
---

# SignalForge Pull Requests

Size limit and git workflow rules live in `dev_standards.md` (always active). This file is the mechanics.

## Description template

```markdown
## What
<what changed, in 1-3 lines>

## Why
<the problem or requirement; link to plan/issue>

## Approach
<key design choices; alternatives considered if relevant>

## Testing
<what was tested and how; commands or evidence>

## Risks / Rollback
<what could break; how to revert or disable (flag, migration notes)>

## Screenshots (UI changes only)

## Size note (only if > 400 lines)
<why this could not be split>
```

## Before merge

- [ ] Self-review done (read your own diff)
- [ ] CI green (lint, types, tests)
- [ ] Tests added or updated
- [ ] Docs/PRD/ADR updated if behavior or decisions changed
- [ ] No secrets, debug code or unrelated changes
- [ ] All comments resolved

## Merge

Squash merge, delete the branch. Never push to `main`.

## Attribution

No AI or tool attribution in the title, description, or commit messages. No co-author trailers.
