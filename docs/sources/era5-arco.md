# Source `era5_arco`: ERA5 from the ARCO copy on Google Cloud

ECMWF's ERA5 reanalysis, read anonymously from Google's Analysis-Ready,
Cloud-Optimised (ARCO) Zarr stores. Code: `src/metbazarr/sources/era5_arco.py`
and `src/metbazarr/build_era5.py`. Decision: [0006](../decisions/0006-era5-arco-to-glide.md).

ERA5 taken directly from ECMWF (MARS or the Copernicus Climate Data Store) is a
**separate source**, `era5_ecmwf`, reserved and not yet implemented, so stores
from the two routes are never confused (`_ERA5-ARCO` against `_ERA5-ECMWF`).

## What it reads

- **Model-level store:** u, v, omega, T, q and geopotential on ERA5's 137
  hybrid levels, hourly, 0.25°.
- **Surface store** (the unified pressure-level/surface store, used for its
  surface fields): boundary-layer height, surface pressure, surface
  geopotential, and the hourly accumulated sensible heat flux and surface
  stresses.

## How it converts (glide format 2.0)

- Every field except u\* is copied unchanged, cropped to the ERA5 grid points
  inside the domain box; the result is bit-identical to GLIDE's own downloader.
- The heat flux stays ERA5's accumulation over the hour ending at the
  timestamp, labelled `time: sum`, 3600 s.
- u\* is derived from the surface stresses, as GLIDE requires for validation
  inputs: u\* = sqrt(|τ|/ρ), with τ the hourly mean stress and ρ from the
  lowest model level. Labelled `time: mean`, 3600 s.
- Pressure levels and a level cap are not implemented yet (roadmap M2).

## Recipe

```yaml
source:
  type: era5_arco
  model_level_store: gs://...   # optional; ARCO's by default
  surface_store: gs://...       # optional; ARCO's by default
  anonymous: true               # optional
```

The period is in whole hours. Example: [`examples/recipes/era5-arco-day.yaml`](../../examples/recipes/era5-arco-day.yaml).

## Needs, and how fast

- `uv sync --extra arco` (`gcsfs`); no account.
- About 12 s and 2 GB per hour of data per process, on one GH200 node, because
  each read fetches whole-globe source chunks. Fill disjoint time ranges with
  several processes at once (`metbazarr build <recipe> --step fill --times A:B`).
- Known quirks of the ARCO copy: one missing heat-flux value (2018-12-28 21:00,
  59.0° N, 35.0° E; filled by the format's rule), and model-level geopotentials
  up to ~125 m below the surface geopotential over high ground (a validator
  warning).
- **Small negative humidities** are ERA5's own (its numerics, mostly in very dry
  air): a few per million values, down to about −3×10⁻⁵ kg/kg. They are kept
  unchanged; the validator warns down to −10⁻⁴ and fails below.
- **Requests can stall or crawl.** Each Google Cloud request times out after
  `request_timeout_s` (default 120 s) and is retried by gcsfs. Without this, three
  of eight fill processes once stalled until their job's time limit. Under heavy
  load (two jobs of 8 processes), single requests still outlasted the timeout and
  gcsfs's retries, failing 7 of 16 stores (20 Nov 2026), so a time that fails on
  a timeout or connection error is read again after a pause: `read_attempts`
  (default 5), `retry_backoff_s` (default 60 s, doubling). Other errors, and
  missing or unreadable files, are not retried. Fewer processes also help. To
  resume a build, fill only what is missing:
  `metbazarr build <recipe> --step fill --missing-only`.
