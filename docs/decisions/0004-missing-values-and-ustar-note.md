# 0004 — Missing source values (GLIDE format 1.0 fill rule); u* note in 0003 corrected

- **Date:** 2026-11-18
- **Status:** Accepted (follows GLIDE PR #23 at `e3df2e3`, which Matt agreed)

## Context

GLIDE's format 1.0 page (`docs/met_schema.md` at `e3df2e3`) added a rule for
isolated missing values in a source archive, after a missing value was found
in ARCO's ERA5 heat flux. A store may hold no non-finite values, so a missing
source value must be filled by the rule, fetched from the original archive, or
stop the conversion. The rule: a non-finite value in a time-varying variable
whose cell (and level) is finite at the timesteps immediately before and
after; at most 10 per variable per store; filled with the mean of those two
values; each one listed in the store attribute `glide_filled_values` and the
fill noted in `processing`. The geopotentials are never filled.

met-bazarr was built against `8f4aa99`, before the rule. Its UM reader stopped
at any missing value.

## Decision

- The `glide` format module implements format 1.0 as at `e3df2e3`.
  - `fill_isolated_missing` applies the rule to a finished store. If any
    non-finite value falls outside the rule, it lists every case, raises
    `FillError` and writes nothing.
  - The validator checks `glide_filled_values` whenever it is present:
    - it is a JSON list with the prescribed keys;
    - no variable is filled that may not be, and none at the first or last
      time;
    - each variable has no more than 10 entries, with no duplicates;
    - the stored values at the times before, at and after each entry equal
      the listed ones, and the filled value is their mean;
    - `processing` notes the fill.
- `metbazarr build --step finish` runs the fill after checking that every time
  was written, then validates.
- The UM reader turns missing data (the field's MDI) into NaN. It allows at
  most 10 missing values in one source field, the most the rule could ever
  fill, and stops on more. It allows none in the orography. A time counts as
  not yet written only when its surface pressure is missing everywhere.
- Filling happens on the stored (converted) values, not on the source fields.
  A missing u or v source value therefore produces up to four filled values
  (two neighbouring points and two theta levels). A missing T or q on theta
  level 1, or a missing stress, also produces a filled `friction_velocity`.

No missing value has been seen in `UMG_Mk10PT` so far. The EUR-Jan trial (193
times) had none.

**Correction to 0003, Consequences.** 0003 says GLIDE floors u* at
1e-3 m s⁻¹ only in the Obukhov length. That is wrong. GLIDE clamps u* to at
least 1e-3 m s⁻¹ as soon as it interpolates it to each particle
(`src/lpdm/turbulence/hanna.py`, ~line 959 on `main`). So the stored zeros
(about 0.3% of points) are safe, and the conversion does not change.

## Consequences

- The reader stops only for gaps the rule could not fill anyway. Isolated gaps
  are filled and recorded.
- A store filled by the rule records it, so GLIDE's validation can see exactly
  which values were made up.

## Alternatives considered

- **Fill while converting each time:** the rule needs the neighbouring times,
  which a single time's job does not have.
- **Fill the source fields before converting:** this would match the rule's
  wording less directly. The rule lists filled values in the store's
  variables and at the store's coordinates.
