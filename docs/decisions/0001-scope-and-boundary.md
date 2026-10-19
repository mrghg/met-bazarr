# 0001 — Scope: data preparation, not physics

- **Date:** 2026-10-19
- **Status:** Proposed

## Context

GLIDE (a GPU Lagrangian particle dispersion model) reads meteorology as Zarr
stores, and so does GATES (a footprint emulator). Each meteorological centre
has its own download client and file format: `cdsapi` or earthkit for ECMWF,
`iris` for the Met Office, others for NOAA. Carrying those clients in a model
would bloat it with dependencies it does not need at run time. FLEXPART keeps
its preparation tool, flex_extract, separate for the same reason. GLIDE records
the same decision from its side in its `dev/decisions/0018-met-bazarr.md`.

## Decision

met-bazarr prepares meteorology; the models keep their physics. It is built for
GLIDE first. GATES's meteorology processing (currently
[extract_UM_met](https://github.com/elenafillo/extract_UM_met)) may also be
incorporated; that is still to be discussed with the team and the GATES
maintainer.

- **In scope:** download by wrapping the providers' existing clients;
  subsetting; optional regridding; renaming; units and sign conventions;
  turning accumulated fields into rates where a format asks for it; an
  ensemble-member dimension; chunking and compression; provenance; and a
  writer and validator for each output format.
- **Out of scope:** anything a model's physics depends on. For GLIDE this
  includes resampling onto its terrain-following levels, the
  vertical-velocity conversion, the model-level pressure reconstruction, its
  own cache for its vertical grid, and combining sources during a run. These
  sit under GLIDE's physics freeze and audit.
- **Named formats:** `glide` to begin with, and `gates` if GATES's processing
  is incorporated. Each model's own documentation is the authoritative
  definition of its format (for GLIDE, `docs/met_schema.md`); met-bazarr
  records which version it implements.
- **Provenance in every store:** met-bazarr version and commit, source dataset
  and access route, format and version, compression settings.
- **Lossless by default.** Lossy compression is opt-in and recorded.
- **The models do not import met-bazarr.** They read its stores.

## Consequences

- The models stay light. If GATES joins, both models get identical inputs from
  one tested conversion, which would matter when GATES is trained on GLIDE
  footprints.
- A change to a model's input contract becomes a change to a met-bazarr
  format, so the two repositories must coordinate: a format version, and a
  note in both.
- GLIDE's validation pins a met-bazarr release, so met-bazarr needs proper
  releases with DOIs early (roadmap task M6).

## Alternatives considered

- **Keep preparation inside each model:** bloated dependencies, and
  duplicated code if more than one model uses it.
- **Also move model-specific transforms here:** part of GLIDE's frozen physics
  would then live outside its freeze and audit.
- **Arbitrary user-defined formats from the start:** a large framework that
  neither model needs yet.
