# Roadmap and task list

_Written 2026-10-19. What met-bazarr needs to do, for whom, and in what order.
Current state and the next few actions are in [STATUS.md](../STATUS.md); the
boundary with the models is in
[decision 0001](decisions/0001-scope-and-boundary.md)._

**Contents**

1. [Who needs what](#1-who-needs-what)
2. [Principles](#2-principles)
3. [Tasks](#3-tasks)
4. [Order](#4-order)
5. [Later](#5-later)

---

## 1. Who needs what

met-bazarr is built for GLIDE first. GATES may become a second user; that is
still to be discussed with the team and the GATES maintainer.

- **GLIDE**, the GPU Lagrangian particle dispersion model
  ([mrghg/glide](https://github.com/mrghg/glide)). Its input contract is
  [`docs/met_schema.md`](https://github.com/mrghg/glide/blob/main/docs/met_schema.md)
  in the GLIDE repository, which is the authoritative definition of the
  `glide` format. GLIDE's development plan
  ([`dev/roadmap.md`](https://github.com/mrghg/glide/blob/main/dev/roadmap.md))
  depends on met-bazarr at three points:
  - **Task B1:** GLIDE switches to met-bazarr stores. It needs `glide`-format
    stores of ERA5 for its reference configuration, on both pressure and model
    levels, whose values are identical to those of the cubes GLIDE's own
    download script makes today.
  - **Task A8a, the validation tolerances:** columns of the ERA5 ensemble (the
    EDA, 10 members) for six standard cases.
  - **Task A8b, the pre-registration:** every validation input store made with
    a released, citable met-bazarr version, which the pre-registration pins.
    This includes ERA5 for three historical tracer experiments.
- **GATES (possible), the graph-neural-network footprint emulator**
  ([Fillola et al., 2026](https://doi.org/10.5194/gmd-19-1893-2026)). It reads
  one Zarr store per domain per year, `<DOMAIN>/<DOMAIN>_Met_<YYYY>.zarr`, with
  dimensions `time`, `levels`, `lat`, `lon` and CF standard names
  (`x_wind`, `y_wind`, `upward_air_velocity`, `air_temperature`,
  `air_pressure`, `atmosphere_boundary_layer_thickness`,
  `surface_air_pressure`); see `How_Tos/HOW_TO_DATA.md` in the GATES
  repository. Today these stores are made from Met Office UM files on JASMIN
  by [extract_UM_met](https://github.com/elenafillo/extract_UM_met), which uses
  `iris`. If GATES's processing is incorporated here, and GATES is trained on
  GLIDE footprints (GLIDE roadmap 5a), it would also need ERA5 in its format,
  so that the emulator sees the same meteorology GLIDE used.

---

## 2. Principles

These follow from [decision 0001](decisions/0001-scope-and-boundary.md).

- **Wrap the providers' clients; never write new ones.** `cdsapi` or earthkit
  for the Copernicus Climate Data Store, xarray on the ARCO ERA5 store in
  Google Cloud, `iris` for Met Office files, and NOAA's own tools later.
- **Preparation, not physics.** Download, subset, rename, convert units and
  signs, turn accumulated fields into rates where the format asks for it,
  chunk, compress, record provenance. Anything a model's physics depends on
  (GLIDE's vertical resampling, vertical-velocity conversion, model-level
  pressure reconstruction) stays in the model.
- **Named formats.** `glide` first, and `gates` if GATES's processing is
  incorporated. Each format has a written
  definition, a writer and a validator. Generalise when a third consumer
  exists.
- **Provenance in every store:** the met-bazarr version and commit, the
  source dataset and how it was accessed, the format and its version, and
  the compression settings. GLIDE copies these into each run's metadata.
- **Lossless by default.** Bit-rounding or any other lossy compression is
  opt-in, recorded in the store, and only switched on for a model once that
  model has shown the effect on its results is negligible.
- **Tests without downloads.** Conversions are tested on small synthetic
  inputs that mimic each source. Real downloads need credentials and run on
  a human's account.
- **No data in git.** Stores, source files and credentials stay out of the
  repository. Met Office data is licensed and restricted.

---

## 3. Tasks

Each task names who needs it. IDs are stable; reorder by editing §4.

### M0 — Foundations

**Needed by:** everything.

- A recipe file (YAML) that describes one store: source, domain, period,
  levels, variables, output format, chunking and compression.
- A command-line entry point, `metbazarr build <recipe>` and
  `metbazarr validate --format <name> <store>`.
- A format registry: each format is a module with its variable table, a
  writer and a validator.
- The provenance attributes (decision 0002, to be written with this task),
  written by every writer and checked by every validator.
- Lossless zstd compression and chunking set by the recipe.
- Tests on synthetic data; CI running them.

**Acceptance.** A synthetic recipe builds a store that its own validator
accepts; provenance is present and correct; the test suite runs in CI with no
network access.

### M1 — The `glide` format

**Needed by:** GLIDE task B1.

- Implement GLIDE's `docs/met_schema.md`: variable names, dimensions, units,
  sign conventions, the vertical-coordinate tag (`glide_vertical_coordinate`
  = `pressure_level` or `model_level`), and the surface and orography fields.
- The validator checks everything that page prescribes, including the
  sign of the sensible heat flux and the units of accumulated fields.
- Record which GLIDE commit of `met_schema.md` the format implements. When
  that page changes, the format version changes.

**Acceptance.** Synthetic stores pass the validator; deliberately broken
ones (wrong sign, geopotential height instead of geopotential, untagged
model levels) fail it with a clear message.

### M2 — ERA5 from the ARCO store

**Needed by:** GLIDE task B1, and M5.

- Port GLIDE's current downloader (`scripts/download_sample_cube.py` in the
  GLIDE repository) into a met-bazarr source: pressure levels and model
  levels from the ARCO ERA5 store in Google Cloud, merged with the surface
  fields.
- For model levels, an option to fetch only the levels below a given height,
  because most of the 137 levels are above any LPDM domain top.
- Write the `glide` format through M1.

**Acceptance.** For GLIDE's reference configuration (EUROPE domain; the
period in GLIDE's `configs/example_multisite_january.yaml`), the store's
values are identical to those of the cube GLIDE's current script produces,
on both pressure and model levels. GLIDE's task B1 repeats this check through
its own reader.

### M3 — ERA5 ensemble (EDA) from the CDS

**Needed by:** GLIDE task A8a (columns); later, ensemble stores for
transport uncertainty (GLIDE roadmap 3a, 3e).

- A source using `cdsapi` (or earthkit) for the "ensemble members" product
  type: 10 members, 3-hourly, about 0.5°. Members become a `member`
  dimension.
- A column mode: extract single grid columns at given points and dates, for
  GLIDE's six standard cases. Variables, from GLIDE's Tier 1 tolerance rule:
  - single levels: surface pressure, 2 m temperature, 2 m dewpoint, surface
    sensible heat flux, eastward and northward surface stress, friction
    velocity, boundary-layer height, surface geopotential;
  - pressure levels: temperature, specific humidity, u, v, geopotential.
- First check which of these the CDS offers as ensemble members (friction
  velocity, boundary-layer height and the stresses are the least certain)
  and record the answer here.
- Accumulated fields in the ensemble cover 3 hours; record that in the store.

**Acceptance.** A column store for one synthetic case passes the `glide`
validator plus a `member` dimension; the list of available variables is
recorded; a real download for the six cases is run by the human.

### M4 — The `gates` format (possible)

**Needed by:** GATES, and GLIDE roadmap 5a (training GATES on GLIDE
footprints), if GATES's processing is incorporated. To be agreed with the
team and the GATES maintainer before any work starts.

- Write down the format from GATES's loader and existing stores: one store
  per domain per year, dimensions `time`, `levels`, `lat`, `lon`, the CF
  names above, duplicates removed, consolidated metadata.
- A writer and a validator, as for `glide`.
- First source: ERA5 through M2, so that GATES can be trained on the same
  meteorology GLIDE uses. Decide how ERA5's levels map onto GATES's `levels`
  (GATES today indexes UM model levels such as 3, 9, 15, 21, 30, 42, 51).

**Acceptance.** GATES's `load_meteorology()` opens an ERA5 store written by
met-bazarr without changes; the level mapping is recorded in a decision.

### M5 — ERA5 for the tracer experiments

**Needed by:** GLIDE tasks A11 and A8b.

- Recipes for ETEX (Europe, 23–27 October and 14–18 November 1994), CAPTEX
  (eastern North America, 18 September to 30 October 1983) and ANATEX (North
  America, 5 January to 29 March 1987), on model levels, in the `glide`
  format. Domains as in GLIDE's `data/tracer-experiments.md`.
- The ARCO store covers these years, so M2's source is enough.
- Estimate each store's size before building; ANATEX is the largest.

**Acceptance.** Three recipes and their size estimates; the stores built by
the human and listed in GLIDE's data inventory.

### M6 — First release

**Needed by:** GLIDE task A8b (the pre-registration pins it) and the GLIDE v1
release.

- Version numbering, a changelog, a tagged release, and a Zenodo DOI from the
  existing `CITATION.cff`.
- The provenance attributes show the released version, not a development
  one.

**Acceptance.** A tagged release with a DOI; a store built from it records
that version.

### M7 — Lossy compression option

**Needed by:** GLIDE task B1 (which tests it), and storage at satellite scale.

- Bit-rounding that keeps a set number of mantissa bits per variable (for
  example with numcodecs' `BitRound`), before lossless compression.
- Off by default; the setting is recorded in the store.

**Acceptance.** Round-trip tests showing the expected precision; storage
before and after on GLIDE's reference store. Whether GLIDE uses it is GLIDE's
decision.

### M8 — Met Office UM meteorology (possible)

**Needed by:** GATES, if its processing is incorporated; later GLIDE roadmap
3c (UKV nested inside the global model). The GATES part is to be agreed with
the team and the GATES maintainer before any work starts.

- A source using `iris` for Met Office files.
- For GATES: bring in, or wrap, the existing
  [extract_UM_met](https://github.com/elenafillo/extract_UM_met) code, which
  reads UM `.pp` files on JASMIN, rather than rewriting it.
- For GLIDE: the `glide` format from UKV and the global UM, for nesting.

**Acceptance.** For one domain and year, a store that matches the existing
GATES store for the same period, variable by variable.

---

## 4. Order

GLIDE's critical path sets the order. M3's column extraction is small and can
run in parallel with M1 and M2.

| Order | Task | Why now |
| --- | --- | --- |
| 1 | M0 | Everything depends on it |
| 2 | M1, M2 | GLIDE task B1 |
| 3 | M3 (columns) | GLIDE task A8a; small |
| 4 | M5 | GLIDE validation runs |
| 5 | M6 | Must exist before GLIDE's pre-registration |
| 6 | M7 | Tested by GLIDE B1; not on the critical path |
| 7 | M4 | GATES with ERA5, if agreed |
| 8 | M8 | GATES's UM pipeline, if agreed; GLIDE's UKV nesting later |

If GATES's processing is incorporated and GATES needs ERA5 soon, M4 can move
up; it depends only on M0 and M2.

---

## 5. Later

- NOAA sources (GFS, HRRR) for both formats.
- Ensemble stores for transport uncertainty (whole fields, not columns).
- Output from machine-learning weather models (GLIDE roadmap 5d).
- A format for learned, highly compressed meteorology (GLIDE roadmap 3d),
  once that research produces something to store.
