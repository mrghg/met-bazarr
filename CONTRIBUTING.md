# Contributing

Thanks for contributing. This is the human front door — the agent equivalent is
[AGENTS.md](AGENTS.md), and both point into the same [docs/](docs/), so there's
one source of truth.

## Getting set up

```bash
uv sync                      # create the env + install everything
uv run pre-commit install    # install git hooks (once per clone)
```

Details: [docs/setup.md](docs/setup.md).

## Making a change

1. **Branch** off `main` — don't commit directly to it.
2. Keep each branch/PR to **one concern** so it's easy to review and revert.
3. Follow the coding conventions in [docs/conventions.md](docs/conventions.md).
4. **All pre-commit hooks must pass** (ruff lint + format, gitleaks). Run them
   any time with `uv run pre-commit run --all-files`.
5. Open a pull request describing what changed and why.

## Security & secrets

Never commit credentials — gitleaks runs on every commit and will block them.
Put secrets in `.env` (git-ignored). See the full policy in
[docs/security.md](docs/security.md).

## Recording decisions

Significant, hard-to-reverse decisions get a short record in
[docs/decisions/](docs/decisions/) — copy the template and add an index row.

## Questions

Open an issue. For anything about *how the project works*, check
[docs/architecture.md](docs/architecture.md) first.
