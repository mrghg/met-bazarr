# Setup

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — the only
  hard requirement; it manages Python itself.

## First-time setup

```bash
# 1. Create the virtual environment and install everything (incl. dev tools).
uv sync

# 2. Install the git pre-commit hooks (once per clone).
uv run pre-commit install
```

`uv sync` reads `pyproject.toml` + `uv.lock` and creates `.venv/`. Commit
`uv.lock` so everyone gets identical, reproducible environments.

## Everyday use

```bash
uv add xarray                 # add a runtime dependency
uv add --dev pytest           # add a dev-only dependency
uv run python scripts/foo.py  # run inside the environment
uv run ruff check --fix .     # lint + autofix
uv run ruff format .          # format
```

You rarely need to "activate" the venv — prefix commands with `uv run`. If you
prefer activation: `source .venv/bin/activate`.

## Python version

Pinned in `.python-version` and constrained by `requires-python` in
`pyproject.toml`. uv installs the right interpreter automatically.

## Secrets

Copy `.env.example` to `.env` and fill in local credentials. `.env` is
git-ignored; gitleaks will block commits that contain secrets.

## Adding testing (optional)

Not wired in by default. To enable pytest:

```bash
uv add --dev pytest
mkdir tests
```

Then uncomment the `[tool.pytest.ini_options]` block in `pyproject.toml` and run
`uv run pytest`.
