# met-bazarr

A "marketplace" for compressed zarr stores for atmospheric models, created from meteorological fields.

![met-bazarr: three stacked meteorological fields, continuous on the left, crack
along a regular grid and separate into small, compressed chunks on the
right.](docs/img/feature.png)

met-bazarr reads a meteorological archive (a reanalysis, a forecast model's
analyses) and writes it as a chunked, compressed Zarr store in the input format
of a particular transport model. It wraps the providers' own clients for
download and reading; the physics stays in the model
([decision 0001](docs/decisions/0001-scope-and-boundary.md)).

## Formats

| Format | For | Defined by | Implemented |
| --- | --- | --- | --- |
| `glide` | [GLIDE](https://github.com/mrghg/glide), the GPU Lagrangian particle dispersion model | GLIDE's **[`docs/met_schema.md`](https://github.com/mrghg/glide/blob/main/docs/met_schema.md)**, the authoritative contract | version 2.0, in [`src/metbazarr/formats/glide.py`](src/metbazarr/formats/glide.py) (writer and validator) |

Start from the format's definition: it says exactly what a store must contain,
including what each timestamp means and the rules for validation inputs.

## Sources

| Source type | Archive | Page |
| --- | --- | --- |
| `era5_arco` | ERA5, from the ARCO copy on Google Cloud (anonymous) | [docs/sources/era5-arco.md](docs/sources/era5-arco.md) |
| `um_global` | Met Office global UM analyses in NAME's met archive (JASMIN) | [docs/sources/um.md](docs/sources/um.md) |
| `era5_ecmwf` | ERA5 directly from ECMWF (MARS/CDS) | reserved, not yet implemented |

**Adding a source** (for example MERRA-2): [docs/adding-a-source.md](docs/adding-a-source.md).

## Quick start

```bash
uv sync                       # create the env + install everything
uv run pre-commit install     # install git hooks (once per clone)
uv sync --extra arco          # for the ERA5 example below
```

A store is described by a **recipe**, a short YAML file: format, output path,
domain box, period, source. Build one day of ERA5 and check it:

```bash
export METBAZARR_OUT=$PWD/data
uv run metbazarr build examples/recipes/era5-arco-day.yaml --step plan   # what it resolves to
uv run metbazarr build examples/recipes/era5-arco-day.yaml               # create, fill, finish
uv run metbazarr validate data/EUR_20190108-20190108_ERA5-ARCO.zarr      # any store, however made
```

A day of ERA5 over Europe is a few GB and takes several minutes; run real
builds on a compute node. Each store records its full recipe, the met-bazarr
version and commit, and every processing step in its attributes.

**Repairs.** A store built by an earlier release can be brought up to a later
rule by recomputing a variable from its own fields, with no download; the repair
is recorded in the store (`glide_repairs`, `processing`):

```bash
.venv/bin/metbazarr repair <store> --fix era5-surface-geopotential --dry-run   # report the change
.venv/bin/metbazarr repair <store> --fix era5-surface-geopotential             # write it
```

`era5-surface-geopotential` gives ERA5 stores built before v0.4.0 a surface
geopotential consistent with their model levels
([decision 0009](docs/decisions/0009-era5-consistent-surface-geopotential.md)).

**Recipes for a project's own stores live with that project**, not here
([decision 0008](docs/decisions/0008-project-inputs-live-with-projects.md)):
GLIDE's validation inputs are in GLIDE's
[`validation/met-inputs/`](https://github.com/mrghg/glide/tree/main/validation/met-inputs).

## What a store looks like

![A meteorology Zarr store: a folder of small JSON metadata files and many chunk
files; each variable is a 4-D array of time, level, latitude and longitude, cut
into chunks of one hour, 24 levels and 128 by 128 grid points; each chunk is
compressed on its own, so a reader opens only the chunks it needs. met-bazarr
turns ERA5, Met Office UM and other archives into such stores for
GLIDE.](docs/img/zarr-store.svg)

A Zarr store keeps each meteorological field as an array cut into small,
separately compressed chunks, so a transport model can read one hour over one
region without opening the rest. The images are drawn by
[`scripts/draw_feature_image.py`](scripts/draw_feature_image.py) (the banner
above) and [`scripts/draw_zarr_schematic.py`](scripts/draw_zarr_schematic.py).

## Layout

`src/metbazarr/` (the package: `formats/`, `sources/`, build steps, CLI) ·
`examples/recipes/` (one example per source) · `tests/` (synthetic data only) ·
`scripts/` (helpers) · `docs/` (setup, sources, decisions, roadmap) · `data/`
(git-ignored). Full map: [docs/architecture.md](docs/architecture.md).

## Contributing, citing, licensing

- **Contributing:** see [CONTRIBUTING.md](CONTRIBUTING.md) (the human front door;
  agents use [AGENTS.md](AGENTS.md)).
- **Citing:** citation metadata is in [CITATION.cff](CITATION.cff) — GitHub shows
  a "Cite this repository" button from it.
- **License:** [Apache-2.0](LICENSE).
