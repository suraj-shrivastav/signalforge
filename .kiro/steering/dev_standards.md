# SignalForge Development Standards

**Applies to:** all code, config and docs in the SignalForge monorepo.
**Rule of thumb:** small, typed, tested, replaceable, reviewable.

---

## 1. Code Hygiene

- **Python:** ruff (lint + format), type hints everywhere, mypy or pyright in strict mode for `core/`.
- **TypeScript:** `strict` mode, eslint, prettier.
- **Pre-commit hooks** run the same checks as CI. Nothing merges on red CI.
- Small, single-purpose functions. Meaningful names. No dead or commented-out code. No magic numbers (use constants or config).
- **Comments explain why, not what,** and stay short. Docstrings only on public interfaces.
- **Layering is enforced:** stages depend on protocols, never on concrete providers, and never import another module's internals.
- **No hard dependencies:** every external service (LLM, search, source, publisher) sits behind an interface. SDK imports live only inside their plugin.
- Config comes from env vars or YAML. **No secrets in the repo.** Keep `.env.example` current.
- New dependencies are minimal, justified in the PR, and pinned in a lockfile.

## 2. Error Handling

- Use a **typed error hierarchy**, split into retryable and permanent errors.
- No bare `except`. Never swallow errors.
- Add context when wrapping errors. Log once, at the boundary.
- Every external call has a **timeout and bounded retries with backoff**.
- Failures end in a visible `failed` state with a reason. Never a silent skip.
- The API returns one consistent error shape.

## 3. Validation

- **Pydantic at every boundary:** API input, LLM output (validate, then retry), plugin output, config.
- Fetched web content is **untrusted:** sanitized, passed to models as delimited data, and never allowed to choose tools or trigger actions.

## 4. Testing

- **pytest.** Unit tests for deterministic logic; contract tests for every plugin against its Protocol.
- Golden files for artifact schemas and prompts.
- **No network and no real LLM calls in tests.**
- Every bug fix ships with a regression test.
- Critical paths must be covered: state machine, idempotency, span check, budgets.
- Keep a small labeled eval set for LLM stages.
- Frontend: light tests (vitest); Playwright only for the triage and review flows.

## 5. Feature Flags

- Config-based, **default off**, used for new stages, plugins or risky behavior.
- Each flag has an owner and a removal date, and is deleted once stable.
- Flags are not a substitute for configuration.

## 6. Data and Operations

- Schema changes only via **Alembic migrations**, backward-compatible (expand, then contract).
- Structured logs with correlation IDs. No secrets in logs.
- Every LLM call is logged with model, tokens, cost and latency.
- Architecture-changing decisions get a short ADR in `docs/adr/` (see its README for the bar and the numbering), and the PRD is updated in the same PR. The PRD stays the source of truth for current architecture; ADRs record changes to it.

## 7. Git Workflow

- **Never commit or push directly to `main`.** Branch protection is on.
- Every change goes through a **pull request**, merged by **squash**, with the branch deleted after merge.
- **Plan, then implement:** write a short plan (issue or draft PR) before any non-trivial change.
- Branch names: `feat/…`, `fix/…`, `chore/…`, `docs/…`.
- Commits follow **Conventional Commits** (`feat:`, `fix:`, `chore:`, …), imperative mood, small and focused.

### Git identity

This repo is **personal**, not work. Every commit must be authored by:

```text
suraj-shrivastav <suraj.shrivastavvv@gmail.com>
```

A second work account (`suraj-neuralarc`) is the global default, so **never assume the ambient identity is correct.** It is routed here by a conditional include in `~/.gitconfig`:

```gitconfig
[includeIf "gitdir:~/personal/"]
    path = ~/.gitconfig-personal
```

`origin` uses the `github.com-personal` SSH host alias, which maps to the personal key. Do not rewrite it to plain `github.com`.

**Before the first commit in any session, verify — do not set:**

```bash
git config user.name && git config user.email
```

If that does not print the personal identity, stop and report it. Do not run `git config` to fix it; the include or the SSH alias is misconfigured and that needs a human decision. Never add `user.name`/`user.email` to this repo's `.git/config` as a workaround — it masks the real problem and silently breaks if the repo moves.

### Bootstrap exception

The repository's first commit lands on `main`, because a base branch must exist before any PR can target it. That is the single documented exception. Once `main` is pushed and protected, the no-direct-commits rule applies without exception.

## 8. Pull Request Size

- **A PR must be ≤ 400 changed lines** (additions + deletions, tests included; lockfiles and generated files excluded).
- If a PR is larger, the description must explain why and why it cannot be split. Otherwise, break it up or stack PRs.
- Scope work to fit this limit *before* writing code, not after.

> Full PR description template and pre-merge checklist: `pull_requests.md` in this folder.

## 9. Attribution

**No AI or Claude attribution anywhere:** no co-author trailers, no "generated with" lines, and no tool mentions in commit messages, PR titles or PR descriptions.

## 10. Definition of Done

A change is done when it is merged to `main` via a PR that meets the size limit, passes CI, includes tests where needed, has a complete description, and leaves docs accurate.
