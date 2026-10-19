# Conventions

## Formatting & linting

- **Ruff** is the single tool for both linting and formatting (config in
  `pyproject.toml` under `[tool.ruff]`). Run `ruff check --fix` then
  `ruff format` before committing; pre-commit enforces this.
- Line length is 88. Import sorting is handled by ruff's `I` rules.

## Python style

- Prefer clear, explicit code over clever one-liners — analysis code is read
  far more often than it's written.
- Add type hints to function signatures in `src/`; they're optional in
  throwaway scripts and notebooks.
- Write docstrings for public functions in `src/` (NumPy or Google style —
  pick one and keep it consistent).
- Use `pathlib.Path`, not `os.path`.
- Use f-strings for formatting.

## Scientific-computing specifics

- **Vectorise** with NumPy/pandas/xarray rather than Python loops over arrays.
- Prefer **xarray** for labelled N-dimensional data (netCDF), **pandas** for
  tabular data.
- Keep **units** explicit — in variable names, docstrings, or via a units
  library. Unit confusion is a leading source of scientific bugs.
- Set **random seeds** for anything stochastic so results reproduce.
- Don't hard-code paths to data — read them from config or `data/`.

## Notebooks

- Keep notebooks for exploration and narrative; move reusable logic into
  `src/metbazarr/` and import it.
- Clear heavy outputs before committing.

## Project layout rules

- Importable, tested logic → `src/metbazarr/`.
- Runnable analysis entry points → `scripts/`.
- Exploration → `notebooks/`.
- Raw/large data → `data/` (git-ignored).
