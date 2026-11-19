# 0006 — ERA5 from ARCO to GLIDE format 2.0; ECMWF-direct ERA5 kept separate

- **Date:** 2026-11-19
- **Status:** Accepted (agreed with Matt Rigby, who asked for GLIDE's ERA5
  processing to move here, and confirmed u\* from the stresses on
  2026-11-19)

## Context

GLIDE downloaded ERA5 itself, from the Analysis-Ready, Cloud-Optimised (ARCO)
copy on Google Cloud (GLIDE `scripts/download_sample_cube.py`). Decision 0018 in
GLIDE moves meteorology preparation here (task M2). GLIDE decision 0020 (format
2.0) also changes two things for ERA5: means and accumulations carry time
labels, and validation inputs derive u\* from the surface stresses, as NAME and
FLEXPART do, instead of using ERA5's `zust`.

ERA5 will also be taken directly from ECMWF (MARS, or the CDS) once Matt has MARS
access, which is how FLEXPART's flex_extract gets it. The two routes must never
be confused.

## Decision

- **Two sources, two names.** `era5_arco` (this decision) reads ARCO anonymously;
  `era5_ecmwf` is reserved for ECMWF-direct ERA5 (task M2b) and refuses to run
  until implemented. Stores are named `<DOMAIN>_<start>-<end>_ERA5-ARCO.zarr`
  and `..._ERA5-ECMWF.zarr`, and say which in `source_dataset`.
- **Conversion** (`sources/era5_arco.py`), model levels only:
  - u, v, omega, T, q and geopotential from the model-level store;
    boundary-layer height, surface pressure, surface geopotential and the heat
    flux from the surface store; all **unchanged**, cropped to the ERA5 grid
    points inside the domain box, keeping ARCO's conventions as GLIDE's own
    downloader did (latitude north to south, `hybrid` levels, surface
    geopotential with a time dimension, longitude in 0..360 unless the box
    crosses 0 E);
  - heat flux: ERA5's hourly accumulation (J m-2), labelled `time: sum`, 3600 s,
    with `glide_flux_accumulation_seconds = 3600`;
  - **u\* = sqrt(|tau|/rho)**, tau the hourly accumulated stresses `ewss` and
    `nsss` divided by 3600 s, rho from surface pressure and T, q on the lowest
    model level at the timestamp; labelled `time: mean`, 3600 s. Not `zust`.
- **Builds** use the same create / fill / finish steps as the UM build
  (`build_era5.py`; `build.py` hands ERA5 recipes to it), so the fill rule and
  validation are shared. The stores are opened without dask: graphs over
  ARCO's 1900-2050 time axis cost more than the reads. Variables are read in
  parallel threads; several fill processes run at once on disjoint times
  (`scripts/isambard/build_era5.sh`).
- **Validator:** a lowest model level up to 500 m below the surface
  geopotential is a warning, not an error. ARCO's ERA5 has this over high
  ground (up to 125 m in 3.4% of NAM columns, 80 m in 2.1% of EUR columns);
  GLIDE excludes sub-surface levels. A unit mistake puts it thousands of metres
  below, and still fails.
- **Recipes** (`recipes/era5-arco/`): the 13 windows of GLIDE's validation plan
  §4 (four case-library blocks, ETEX-1/2, CAPTEX-1 to 7, ANATEX, OKC80 over the
  full NAM box), EUROPE December 2023 and January 2024 for GLIDE task A01, and a
  test day. Output goes to `$METBAZARR_OUT`.

## Evidence (19 Nov 2026, Isambard AI)

- **Equivalence with GLIDE's downloader:** every copied variable is
  bit-identical to GLIDE's existing stores, with the same coordinates, on NAM
  (6 h, 14 Oct 1983) and EUR (24 h, 8 Jan 2019, a box crossing 0 E)
  (`scripts/check_era5_equivalence.py`).
- **u\* from the stresses against `zust`** (NAM, 6 h):

  | | u\* from stresses | `zust` | ratio, median (5–95%) |
  |---|---|---|---|
  | sea | 0.269 | 0.269 | 1.00 (0.94–1.06) |
  | land above 100 m | 0.395 | 0.205 | 1.88 (1.08–7.17) |
  | mountains above 1,500 m | 0.487 | 0.137 | 3.62 (1.28–14.7) |

  Over the sea the two agree, which checks the formula. Over land, ERA5's
  surface stresses include the drag of sub-grid orography (turbulent
  orographic form drag), which `zust` does not. This **raises GLIDE's u\* over
  land by a median factor of about 1.9**, and more over mountains, relative to
  GLIDE's earlier ERA5 input. Matt confirmed the stresses on 2026-11-19, for
  the reasons in GLIDE decision 0020: one definition of u\* on ERA5 and the UM
  (whose meteorology has only the stresses), and the hill drag belongs in
  grid-cell turbulence. GLIDE revisits the choice after v1, against the tracer
  experiments and radon.
- **Speed:** about 12 s per hour of data and 2 GB per fill process; 8
  processes built 24 EUR hours in 2.5 minutes.

## Consequences

- GLIDE's task B1 can adopt these stores; GLIDE's own downloader is retired
  there.
- Not yet: pressure-level stores, and fetching only the levels below a height
  (roadmap M2). Neither is needed for the validation; GLIDE's existing
  pressure-level cubes serve task A01.
