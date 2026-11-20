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

## Tests

```bash
uv sync --extra um            # iris, for the UM tests (needs udunits2)
uv run pytest
```

The tests use small synthetic inputs only: never real (or licensed) data. The
UM tests write synthetic PP files, which need iris but not `mo_pack`; they are
skipped if iris is missing.

## Optional extras, by source

| Extra | For | Notes |
| --- | --- | --- |
| `arco` | ERA5 from the ARCO stores on Google Cloud | `gcsfs`; anonymous access, no account needed. See [sources/era5-arco.md](sources/era5-arco.md). |
| `um` | Met Office UM PP files | `iris`, which needs the `udunits2` C library; WGDOS-packed files also need `mo_pack`, which is on conda-forge only. See [sources/um.md](sources/um.md). |

```bash
uv sync --extra arco
```

Large builds belong on compute nodes, not login nodes. Recipes and job scripts
for a particular project (for example GLIDE's validation inputs) live with that
project, not here: see [decision 0008](decisions/0008-project-inputs-live-with-projects.md).
