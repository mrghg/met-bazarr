# 0003 — Met Office UM (NAME's UMG_Mk10PT) to GLIDE format 1.0

- **Date:** 2026-11-17
- **Status:** Accepted (agreed with Matt Rigby at the GLIDE task B14 stop,
  2026-11-17)

## Context

GLIDE's second reference comparison runs GLIDE on the meteorology NAME uses:
the Met Office global Unified Model fields in NAME's met archive on JASMIN,
series `UMG_Mk10PT` (GLIDE `dev/agent/briefs/B14-um-met-conversion.md`).
GLIDE's validation is pre-registered, so every conversion choice that can
change results has to be agreed before the validation inputs are made.

Assessment of the files (8 January 2019, summarised from the stage-1 report):

- ENDGame Arakawa C grid, 2,560 x 1,920 scalar points (0.140625° x
  0.09375°); u offset half a cell west, v half a cell south.
- 59 levels, heights `z = a + b * orography` (PP vertical code 65; a and b in
  every header). u and v on rho levels (10 m to 29.1 km), T, q, w and the UM's
  pressure on theta levels (20 m to 30.1 km); theta level k lies between rho
  levels k and k+1.
- Every 3 h; 00/06/12/18Z are analyses, 03/09/15/21Z are 3-hour forecasts.
  The sensible heat flux and surface stresses are means over the 3 h ending at
  the timestamp; everything else is instantaneous.
- Fields are WGDOS-packed: u, v, T, pressure, boundary-layer depth and heat
  flux at 2^-3, w and the surface stresses at 2^-10, q at 2^-24.
- 14 partitions overlapping by one row or column, with identical values in the
  overlaps. EUR lies in partition 2; NAM in partitions 5 and 9. Orography is
  in separate topography files.

## Decision

1. **Vertical route A.** The theta levels are written as GLIDE model levels
   (`glide_vertical_coordinate = "model_level"`, coordinate `model_level` =
   1..59), with `geopotential = 9.80665 * (a + b * orography)` (no time
   dimension) and `geopotential_at_surface = 9.80665 * orography`. GLIDE
   rebuilds pressure from these with its own hydrostatic integration; the UM's
   pressure is not stored. No change to GLIDE's reader. Using GLIDE's g makes
   GLIDE's heights above ground exactly the UM's.
2. **Target grid:** the scalar (cell-centre) points and the theta levels.
   T (STASH 16/4), q (0/10), w (0/150, geometric, m s-1), surface pressure
   (0/409) and boundary-layer depth (0/25) are stored unchanged.
3. **Winds:** u (0/2) and v (0/3) are each the mean of the two neighbouring
   u (v) points onto the scalar point, then interpolated linearly in height
   (`z = a + b * orography` at the scalar point) from rho levels k and k+1 to
   theta level k. Theta level 59 (above rho level 59) takes the rho-59 value.
4. **Friction velocity:** `sqrt(|tau| / rho)`, with the stresses 3/219 and
   3/220 destaggered as u and v, and `rho = ps / (287.05 T (1 + 0.6077 q))`
   from T and q on theta level 1 at the timestamp.
5. **Sensible heat flux:** STASH 3/217 negated (UM positive up, GLIDE
   positive down), stored at the end of its averaging interval with
   `glide_flux_averaging_seconds = 10800`.
6. **Domain:** the scalar points covering the box with one point on or beyond
   each edge. EUR: 429 x 499 points (31.921875–72.046875° N,
   30.0234375° W–40.0078125° E). NAM: 386 x 464 (21.984375–58.078125° N,
   120.0234375–54.9140625° W). All 59 levels; no interpolation in time.
7. **Lossless:** float32, Blosc zstd, no scale/offset or bit-rounding.
   "Lossless" is relative to the WGDOS-packed archive, which is itself
   quantised; `source_dataset` says so.

## Consequences

- Measured on 8 January 2019 (EUR): GLIDE's rebuilt pressure is within
  0.75 hPa of the UM's pressure everywhere, and within 0.06% below 3 km.
  The geopotential is hydrostatically consistent with the UM's pressure to
  0.997–1.003 (layer ratio) below 15 km.
- The heat flux and stresses are 3-h means used by GLIDE as if they were
  values at their end time, i.e. about 1.5 h late. Whether that matters is
  for GLIDE.
- Friction velocity is exactly 0 at about 0.3% of points, where both
  stress components round to 0 in the packing (|tau| < ~5e-4 Pa). GLIDE floors
  u* at 1e-3 m s-1 in the Obukhov length but not everywhere it uses u*.
- One EUR day is ~1.2 GB; each 24-day EUR window ~29 GB, NAM ~25 GB.
- The same method serves the other UMG series if their structure matches; a
  different series needs its files checked and this record extended.

## Alternatives considered

- **Route B, a height-based vertical mode in GLIDE's reader:** not needed,
  given how closely the rebuilt pressure matches; it would have taken a new
  format version and GLIDE work before its physics freeze.
- **Rho levels as the target:** would interpolate T, q and w instead of u and
  v, and lose the exact match of the theta-level pressure.
- **1.5 m temperature (STASH 3/236) for the density in u*:** no humidity at
  1.5 m, and theta level 1 (13–20 m above the ground) is what GLIDE's lowest
  level sees.
