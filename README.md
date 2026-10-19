# metbazarr

A marketplace for compressed zarr stores for atmospheric models, created from meteorological fields.

## Quick start

```bash
uv sync                       # create the env + install everything
uv run pre-commit install     # install git hooks (once per clone)
```

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
