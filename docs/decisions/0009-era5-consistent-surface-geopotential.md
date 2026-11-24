# 0009 — ERA5 stores carry a surface geopotential consistent with their model levels; built stores are repaired in place

- **Date:** 2026-11-24
- **Status:** Accepted (Matt Rigby, 2026-11-24, who chose the in-place repair
  over a rebuild)

## Context

GLIDE takes heights above ground on model levels as
(level geopotential − `geopotential_at_surface`) / g. ARCO's ERA5 supplies
the two from different stores: level geopotential from the model-level store,
surface geopotential from the single-level store. In steep terrain they do not
describe the same ground. GLIDE's task A01 (GLIDE PR #47) found that ERA5's
lowest model level, which the IFS places about 10 m above the surface, lies
*below* ARCO's surface geopotential in about 6% of land cells and 21–25% of
cells above 1,000 m (blocks EUR-Jan and NAM-Jan), by up to 111–136 m. The
likely cause is that ARCO regrids its model-level and single-level fields by
different routes. GLIDE's terrain-following grid is shifted by that offset in
those columns, so near-surface winds there come from the wrong height. FLEXPART,
on flex_extract's fields from MARS, does not see this. Our validator warned of
levels below the surface but treated them as normal, as they are on pressure
levels.

The UM stores are consistent by construction: their level and surface
geopotentials come from the same orography (decision 0003). Their lowest level
lies 12–20 m above the surface everywhere.

## Decision

- **The `era5_arco` source derives the surface geopotential from the lowest
  model level**, by the IFS's own hydrostatic relation for full level 137:

  z_s = z₁₃₇ − α R_d T_v,137, with α = 1 − b/(1 − b) · ln(1/b), b = 0.997630

  where b is the L137 coefficient at half level 136 (ECMWF, "L137 model level
  definitions"; a = 0 at both half levels around level 137 and b = 1 at the
  surface, so α does not depend on surface pressure), R_d = 287.0597 J kg⁻¹ K⁻¹
  and T_v = T (1 + 0.6078 q) at level 137. α = 0.0011859, so level 137 sits
  9.7 m above the ground at 280 K. ARCO's own surface geopotential is no longer
  read. A store whose lowest level is not 137 is refused.
- **The validator holds validation inputs to the rule** that on model levels
  the level and surface geopotentials describe the same ground: a lowest level
  more than 1 m below `geopotential_at_surface` is an error with
  `--validation-input` and a warning otherwise. (More than 500 m is an error in
  any case, as before: mixed units.) GLIDE's `docs/met_schema.md` states the
  rule.
- **Stores already built are repaired in place**, not rebuilt:
  `metbazarr repair <store> --fix era5-surface-geopotential` recomputes the
  variable from the store's own level-137 geopotential, temperature and
  humidity, with no download (about 30 s for a 24-day EUR window). It refuses
  anything that is not ERA5 on model levels down to 137, and a store already
  repaired. It records the repair in the store's `glide_repairs` attribute (what,
  when, met-bazarr version and commit, the change in metres: median, 99th
  percentile, maximum, and the share of columns that had their lowest level
  below the old surface) and appends it to `processing`. The validator holds a
  repair's commit to the producer's rule: validation inputs are repaired by a
  clean, tagged release. `--dry-run` reports the change and writes nothing.

## Consequences

- Validation stores built with v0.3.0 and repaired with the next release carry
  two producers: `producer_version` 0.3.0 and a `glide_repairs` entry. The
  pre-registration records both. The repair is a deterministic function of the
  store's own contents, so it adds no new input.
- The original ARCO surface geopotential is not kept in the store (the format
  holds exactly its required variables); it can be read again from ARCO, and the
  repair record gives the size of the change. On EUR-Jan (dry run, 24 Nov
  2026): median 0.36 m, 99th percentile 23.5 m, maximum 111 m; 2.3% of columns
  had their lowest level below the old surface.
- Over the sea and flat land nothing changes measurably; in steep terrain the
  surface moves to where ERA5's own model levels put it, as in FLEXPART.
- The ERA5-direct (`era5_ecmwf`) source, when written, gets its surface
  geopotential from the same archive as its levels and does not need this; the
  validator rule applies to it all the same.

## Alternatives considered

- *Rebuild every ERA5 store with the new release.* Clean single-producer
  provenance, but about 9 hours of jobs reading Google Cloud again, where reads
  have stalled before, for a change that depends only on fields already in each
  store.
- *Fix it in GLIDE's reader.* A product-specific constant inside GLIDE, which
  decision 0018 (GLIDE) moves out; the UM stores also declare model levels and
  would have needed excluding by name.
- *Keep ARCO's surface geopotential and record the inconsistency as a known
  limitation.* A GLIDE-only difference from FLEXPART in the mountain cases (JFJ)
  where Tier 2 is hardest to read, when the fix is one relation.
- *Keep ARCO's field alongside under another name.* The format holds exactly its
  required variables; the repair record carries the size of the change instead.
