# metbazarr

A marketplace for compressed zarr stores for atmospheric models, created from meteorological fields.

![met-bazarr: three stacked meteorological fields, continuous on the left, crack
along a regular grid and separate into small, compressed chunks on the
right.](docs/img/feature.png)

## Quick start

```bash
uv sync                       # create the env + install everything
uv run pre-commit install     # install git hooks (once per clone)
```

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

`src/metbazarr/` (reusable code) · `scripts/` (analysis entry points) ·
`notebooks/` (exploration) · `data/` (git-ignored) · `docs/` (project + agent
docs). Full map: [docs/architecture.md](docs/architecture.md).

## Contributing, citing, licensing

- **Contributing:** see [CONTRIBUTING.md](CONTRIBUTING.md) (the human front door;
  agents use [AGENTS.md](AGENTS.md)).
- **Citing:** citation metadata is in [CITATION.cff](CITATION.cff) — GitHub shows
  a "Cite this repository" button from it.
- **License:** [Apache-2.0](LICENSE).
