# Adding a source

How to turn a new archive (MERRA-2, a regional model, another reanalysis) into
stores in an existing format. The examples are for the `glide` format, the only
one so far.

## 1. Read the format first

A store in the `glide` format is defined by **GLIDE's
[`docs/met_schema.md`](https://github.com/mrghg/glide/blob/main/docs/met_schema.md)**,
format version 2.0. It is the contract: exact variable names, dimensions,
units, sign conventions, one grid for every field, provenance attributes, what
a timestamp means, the domain and extent rules, and the extra rules for
validation inputs. Its section "Preparing meteorology from a non-ERA5 source"
lists the gaps other archives usually have. `src/metbazarr/formats/glide.py`
implements and validates it; `metbazarr validate <store>` checks any store,
however it was made.

## 2. Answer these questions about the archive before writing code

Write the answers down (a short note, then a decision record for the choices
that affect results):

- **Grid.** Horizontal spacing and origin; whether fields sit at different
  points (staggered); longitudes 0..360 or −180..180.
- **Levels.** Pressure, hybrid sigma-pressure, height-based? Which fields are
  on which levels? Is there 3-D geopotential, or must it be derived (and from
  what)? Does the top reach 20 km above the ground?
- **Fields**, against the format's required set: winds, vertical velocity
  (omega or geometric w), temperature, specific humidity, geopotential,
  boundary-layer height, surface pressure, surface geopotential, friction
  velocity (from the surface stresses for validation inputs), sensible heat
  flux (sign and units).
- **Time.** The interval of each field, and whether each value is a snapshot
  or a mean or accumulation; if a mean, over which interval and **where the
  timestamp sits** (start, middle or end). The format requires a period to end
  at the timestamp and to equal the store's time step.
- **Missing values,** packing and precision at source.
- **Access:** client library, credentials, licence, and where it can run.

## 3. Write the source module

Add `src/metbazarr/sources/<name>.py`. Keep the numerics as plain functions on
arrays, so they can be tested on synthetic data, and the file handling in a
small class. A source must give the build:

- the **grid** of the store for a recipe's domain box (the points covering the
  box, with one point on or beyond each edge);
- the **times** for the recipe's period, at the source's own interval (no
  interpolation in time);
- the **time-invariant fields**, if any (for example geopotential on a
  height-based grid);
- **`read_time(i)`**: every required variable at time `i`, on the store's
  grid, in the format's units and sign conventions, as float32;
- the **variable attributes**: units, and `cell_methods` with
  `glide_period_seconds` on every mean or accumulation
  (`formats.glide.period_attrs`);
- the **provenance strings**: `source_dataset`, `source_access`, and one line
  per processing step for `processing`.

The build steps (`metbazarr build <recipe> --step create|fill|finish`) do the
rest: chunking, compression, store attributes, the fill rule for isolated
missing values, and validation. Two sources exist to copy from:
[`era5_arco`](sources/era5-arco.md) (cloud Zarr, the simpler one) and
[`um_global`](sources/um.md) (partitioned files, a staggered grid, height-based
levels). Register the new `source.type` in `build.py`.

## 4. Recipe keys

A recipe is a YAML file (`src/metbazarr/recipe.py`): `format`, `output`,
`domain` (name and box), `period` (start and end, both included), `source`
(`type` plus the source's own keys), and optional `compression` and `chunks`.
Add an example to `examples/recipes/`. Recipes for a particular project's
stores live with that project, not here ([decision 0008](decisions/0008-project-inputs-live-with-projects.md)).

## 5. Tests and checks

- Tests on **synthetic data only** (`tests/synthetic_<name>.py`), shaped like the
  real archive: same variable names, units, dimension order, grid conventions.
  Never real or licensed data. Check every value against an independent
  calculation, and run the store through `validate`.
- Optional dependencies go in an extra (`uv add --optional <name> <pkg>`), and
  tests that need them skip cleanly without them.
- Before using real stores: build one day, validate it, and compare a few
  points against the source archive.

## 6. Record it

A page in `docs/sources/<name>.md` (what it reads, how it converts, recipe
keys, needs, speed, known quirks) and a decision record for the conversion
choices.

## Notes for MERRA-2

Points to check against the MERRA-2 file specification before writing code;
they are where the format's rules will bite:

- The time-averaged collections (e.g. `tavg1_2d_flx`, with the heat flux and
  u\*) are believed to be stamped at the **middle** of each hour, where the
  format needs the period to end at the timestamp.
- The 3-D fields are believed to be 3-hourly and the surface fluxes hourly, but
  a store has one time step and a mean's period must equal it.
- Its 72 model levels are hybrid sigma-pressure; check whether a 3-D height or
  geopotential is provided or must be derived from the layer pressure
  thicknesses.
