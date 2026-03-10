# Contributing to GraphRAG

Thank you for your interest in contributing! This document covers how to get
started, the development workflow, and what to expect from the review process.

## Getting started

1. Fork the repository and clone your fork
2. Copy `.env.example` to `.env` and fill in values
3. Copy `docker-compose.override.yml.example` to `docker-compose.override.yml`
4. Install dev dependencies:
   ```bash
   pip install -e ".[dev]"
   ```
5. Start the stack:
   ```bash
   docker compose up postgres   # just the DB is enough for most work
   ```

## Running tests

```bash
pytest
```

The test suite does not require a running database — DB-dependent tests are
integration tests and are skipped unless `POSTGRES_PASSWORD` is set and the
database is reachable.

## Code style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and
formatting.

```bash
ruff check src/ tests/
ruff format src/ tests/
```

Type annotations are checked with mypy:

```bash
mypy src/
```

CI enforces both on every pull request.

## Submitting changes

1. Create a branch from `main`: `git checkout -b feat/my-feature`
2. Make your changes, add tests where appropriate
3. Run the linter and tests locally before pushing
4. Open a pull request against `main` — fill in the PR template
5. A maintainer will review and merge or request changes

## Reporting bugs

Please use the [bug report issue template](.github/ISSUE_TEMPLATE/bug_report.md).
Include the output of `docker compose logs` and your environment details.

## Suggesting features

Open a [feature request](.github/ISSUE_TEMPLATE/feature_request.md) and
describe the use case before starting implementation work. This avoids effort
on changes that may not align with the project direction.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
Please be respectful and constructive in all interactions.
