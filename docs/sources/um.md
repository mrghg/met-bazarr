# Source `um_global`: Met Office global UM analyses (NAME's met archive)

The Met Office global Unified Model fields that NAME runs on, as partitioned PP
files in NAME's met archive (series `UMG_Mk10PT`: 59 levels, every 3 hours,
0.140625° × 0.09375°). Code: `src/metbazarr/sources/um.py` and
`src/metbazarr/build.py`. Decisions: [0003](../decisions/0003-um-to-glide-conversion.md)
(conversion), [0004](../decisions/0004-missing-values-and-ustar-note.md),
[0005](../decisions/0005-glide-format-2-time-labels.md) (time labels),
[0007](../decisions/0007-um-surface-stress-form-drag.md) (stresses and hill drag).

## How it converts (glide format 2.0)

- Target grid: the scalar points and theta levels. u and v are averaged from
  their two neighbouring C-grid points, then interpolated linearly in height
  from rho to theta levels.
- Geopotential from the level definition `z = a + b × orography`
  (time-invariant); GLIDE rebuilds pressure hydrostatically (within 0.75 hPa of
  the UM's own).
- u\* = sqrt(|τ|/ρ) from the 3-hour mean surface stresses; the heat flux is
  negated to positive-down. Both are labelled `time: mean`, 10800 s.
- No interpolation in time; the store keeps the 3-hourly step.

## Recipe

```yaml
source:
  type: um_global
  series: UMG_Mk10PT
  met_dir: /gws/ssde/j25a/name/met_archive/Global/UMG_Mk10PT
  file_pattern: "MO{time:%Y%m%d%H%M}.UMG_Mk10_I_L59PT{part}.pp"
  topography: /gws/ssde/j25a/name/data/UMTopogData/TopogUMG_Mk10_PT{part}.pp
```

Example: [`examples/recipes/um-day.yaml`](../../examples/recipes/um-day.yaml).

## Needs

- `uv sync --extra um` (`iris`, which needs the `udunits2` C library), and
  `mo_pack` for the WGDOS-packed files. `mo_pack` is on conda-forge only, so on
  JASMIN build the environment on JASMIN's `jaspy` Python, which has it:

  ```bash
  JP=/apps/jasmin/jaspy/miniforge_envs/jaspy3.12/mf3-25.3.0-3/envs/jasml3.12-mf3-25.3.0-3-v20261105/bin/python
  uv venv --python "$JP" --system-site-packages .venv-jaspy
  UV_PROJECT_ENVIRONMENT=.venv-jaspy uv sync --python "$JP" --extra um
  ```

  `--python` matters: without it `uv sync` follows `.python-version` and
  replaces the environment with one that cannot see `mo_pack`.
- Read access to NAME's met archive on JASMIN (the `gws_name` group).
- About 12–17 s and under 3 GB per 3-hourly time, on one CPU.

Met Office data, and anything derived from it, never goes into the repository,
a test or an issue. The tests use synthetic PP files.
