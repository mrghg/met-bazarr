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
uv sync --extra um            # iris, for the UM tests
uv run pytest
```

The tests use small synthetic inputs only: never real (or licensed) data. The
UM tests write synthetic PP files, which need iris but not `mo_pack`; they are
skipped if iris is missing.

## Met Office UM on JASMIN

Reading the Met Office's WGDOS-packed PP files needs `iris` **and** `mo_pack`.
`mo_pack` is published on conda-forge only, so `uv` cannot install it. On
JASMIN, build a second environment on JASMIN's `jaspy` Python, which has
`mo_pack`, and let `uv` install everything else into it:

```bash
JP=/apps/jasmin/jaspy/miniforge_envs/jaspy3.12/mf3-25.3.0-3/envs/jasml3.12-mf3-25.3.0-3-v20261105/bin/python
uv venv --python "$JP" --system-site-packages .venv-jaspy
UV_PROJECT_ENVIRONMENT=.venv-jaspy uv sync --python "$JP" --extra um
.venv-jaspy/bin/metbazarr --help
```

`--python` matters: without it `uv sync` follows `.python-version` and
replaces the environment with one that cannot see `mo_pack`. Reading the NAME
met archive needs membership of the `gws_name` group.

Build a store from a recipe (`recipes/`), interactively or as a LOTUS2 job:

```bash
.venv-jaspy/bin/metbazarr build recipes/um/EUR-day-20190108.yaml --step plan
.venv-jaspy/bin/metbazarr build recipes/um/EUR-day-20190108.yaml
sbatch --account=<account> scripts/lotus/build_store.sbatch recipes/um/EUR-Jan.yaml
.venv-jaspy/bin/python scripts/check_um_store.py recipes/um/EUR-day-20190108.yaml --times 0 4
```

UM stores are named `<DOMAIN>_<start YYYYMMDD>-<end YYYYMMDD>_UMG-Mk10.zarr`,
where the dates are those of the first and last times in the store, e.g.
`EUR_20181222-20190115_UMG-Mk10.zarr`.

Met Office data, and anything derived from it, never goes into the
repository, a test or an issue.
