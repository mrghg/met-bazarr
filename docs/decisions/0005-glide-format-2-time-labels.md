# 0005 — GLIDE format 2.0: means and accumulations labelled per variable

- **Date:** 2026-11-19
- **Status:** Accepted (follows GLIDE decision 0020, merged in GLIDE PR #27 at `b21f586`, which Matt agreed)

## Context

GLIDE interpolated every meteorology field linearly in time, treating each
stored value as a snapshot at its timestamp. The UM's heat flux and surface
stresses (so its u*) are means over the 3 h ending at the timestamp, and
ERA5's heat flux and stresses are accumulations over the hour ending at
theirs, so GLIDE used them 1.5 h and 0.5 h late. Decision 0003 recorded the
UM case and left it to GLIDE.

GLIDE decision 0020 settles it, with GLIDE format 2.0 (`docs/met_schema.md`,
"What a timestamp means"): a variable that is a mean or accumulation over the
period ending at its timestamp carries `cell_methods = "time: mean"` or
`"time: sum"` and `glide_period_seconds`; GLIDE holds it constant through each
window at its value at the window's end, as NAME does with the UM's means.
Validation inputs derive `friction_velocity` from the surface stresses, as NAME
and FLEXPART do.

## Decision

- **`formats/glide.py` implements format 2.0** (`FORMAT_VERSION = "2.0"`,
  `GLIDE_SCHEMA_COMMIT` = `b21f586`). `period_attrs()` gives a variable's
  labels. The validator checks that:
  - both labels come together, with a known method and a whole positive
    period;
  - the period equals the store's time step (GLIDE refuses any other);
  - time-invariant fields are never labelled;
  - the heat flux's labels agree with its units and the store-level flux
    attributes (`time: sum` with `glide_flux_accumulation_seconds`,
    `time: mean` with `glide_flux_averaging_seconds`), and a mean or
    accumulated heat flux is labelled;
  - for `--validation-input`, `friction_velocity` is labelled, since it is
    derived from mean stresses.
  A store declaring format 1.0 fails, so a 1.0 store cannot pass for a 2.0
  validation input.
- **UM source:** `surface_sensible_heat_flux` and `friction_velocity` are
  labelled `time: mean`, 10800 s. No values change.
- **Release `v0.2.0`.** The four case-library UM stores built from `v0.1.0`
  (format 1.0, unlabelled u*) are superseded and are not validation inputs;
  they are rebuilt from `v0.2.0`.

## Consequences

- With these labels, GLIDE and NAME treat the UM's surface forcing
  identically, and decision 0003's remark that GLIDE uses the fluxes about
  1.5 h late no longer applies.
- Any new source labels its means and accumulations the same way (the ERA5
  ARCO source, task M2, labels its heat flux `time: sum` and its u* from the
  stresses `time: mean`, 3600 s).

## Alternatives considered

- **Relabel the `v0.1.0` stores in place:** no values would change, but a
  validation input would then not be exactly what a tagged release wrote.
  Rebuilding takes about 2.5 h per store.
- **Keep accepting format 1.0 stores:** a 1.0 store's u* would be read as a
  snapshot, with the lag this decision removes.
