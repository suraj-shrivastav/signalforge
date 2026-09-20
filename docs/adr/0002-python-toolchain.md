# ADR-0002: Python toolchain — uv, Python 3.13, ruff, mypy

**Status:** Accepted
**Date:** 2026-09-20
**Deciders:** suraj
**PRD impact:** none (§42 deployment and §44 decisions unchanged; this fills in tooling the PRD left open)

## Context

The repo held only documentation. Phase 1 of the build order (PRD §43) needs an
installable package, a lockfile, and CI that can go red before any pipeline code
lands. Three choices were unpinned: the dependency manager, the Python version,
and the type checker (`dev_standards.md` allows "mypy or pyright").

The system Python is 3.14. Phase 1 adds `psycopg`, `SQLAlchemy` and `pgvector`,
all of which ship compiled wheels; a too-new interpreter turns a routine install
into a source build.

## Decision

We use **uv** for dependency resolution, locking and task running, with the
interpreter pinned to **Python 3.13** via `.python-version` so uv provisions the
same version locally and in CI. **ruff** handles lint and format, **mypy** runs
in strict mode over `src` and `tests`. Pre-commit runs ruff and mypy on commit
and pytest on push, all as local `uv run` hooks so they share the versions in
`uv.lock` instead of a second set of pins that can drift from CI.

## Alternatives considered

| Option | Why not |
|---|---|
| Poetry | Slower resolution; a second Python-version mechanism to manage alongside uv-style pinning |
| pip + pip-tools + venv | Works, but hand-rolls what uv does in one tool, including interpreter provisioning |
| Python 3.14 (system) | Newest interpreter, thinnest wheel coverage for the Phase 1 database dependencies |
| pyright | Node runtime in a Python CI job; mypy is already implied by the committed `.mypy_cache` ignore |
| ruff-pre-commit mirror | Pins ruff twice, so pre-commit and CI can silently disagree |

## Consequences

Contributors need uv installed; it provisions Python itself, so that is the only
prerequisite. `uv sync --locked` in CI makes lockfile drift a build failure.
Strict mypy over `tests` as well as `src` means test helpers carry annotations —
deliberate, since the artifacts and protocols are the product's contract.

Exit cost is low. `pyproject.toml` is standard metadata, so moving to Poetry or
pip-tools is a lockfile regeneration. Dropping the 3.13 pin is a one-line change
once the database dependencies publish 3.14 wheels.

## Follow-ups

- [x] Update `.kiro/steering/tech.md` commands section
- [ ] Revisit the 3.13 pin when Phase 2 dependencies publish 3.14 wheels
- [ ] Decide the queue library (Procrastinate vs Arq) in its own ADR before Phase 1 closes
