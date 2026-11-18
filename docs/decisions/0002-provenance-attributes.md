# 0002 — Provenance attributes, and how a store is built

- **Date:** 2026-11-17
- **Status:** Proposed

## Context

Roadmap task M0 asks for provenance in every store, written by every writer
and checked by every validator. GLIDE's format 1.0 (`docs/met_schema.md` in
GLIDE, decision 0019 there) has since named the attributes it wants. The first
real store (GLIDE task B14, Met Office UM) is being built now, so the names
and the build steps need fixing before stores are handed to anyone.

## Decision

- **Attributes.** A `glide` store carries the attributes GLIDE's format 1.0
  lists: `glide_format`, `glide_format_version`,
  `glide_vertical_coordinate`, the heat-flux attribute that fits its units
  (`glide_flux_averaging_seconds` or `glide_flux_accumulation_seconds`),
  `source_dataset`, `source_access`, `producer` (`"met-bazarr"`),
  `producer_version`, `producer_commit`, `processing`, `compression` and
  `domain`. It also records `glide_format_definition` (the GLIDE commit whose
  `met_schema.md` the writer implements), `recipe` and `domain_box`. Further
  formats will reuse the format-independent names.
- **`producer_commit`** is the git commit of the checkout, with `-dirty`
  appended if tracked files have uncommitted changes. The validator's
  `--validation-input` rule refuses `-dirty` and `unknown`.
- **`processing`** lists every step, numbered, in the order applied: what each
  stored variable comes from, every derivation with its formula, every
  interpolation with its target and method, unit and sign changes, cropping.
- **Build in three steps:** `create` (coordinates, attributes, time-invariant
  fields; time-varying arrays declared with a NaN fill value), `fill` (one or
  more times; one time per chunk, so separate processes can fill disjoint
  ranges), `finish` (every time written, then the validator). `fill` refuses a
  store whose `producer_commit` differs from the running code, so one store is
  never written by two versions of the converter.
- **Zarr v3**, consolidated metadata, Blosc zstd (level 5 by default) with
  byte shuffle on float32. Chunks as GLIDE recommends: one time, 128 x 128
  horizontally, levels whole up to 48 and in 24s beyond.

## Consequences

- A store states, without its recipe, what it is, where it came from, which
  code made it and how. GLIDE copies these into each run's metadata (GLIDE
  task B1).
- Recreating a store is the only way to change the code that fills it. That
  is deliberate for validation inputs and a small cost in development (the
  `--allow-commit-mismatch` flag exists for that).

## Alternatives considered

- **One attribute holding a JSON blob:** harder to read with `ncdump`-style
  tools, and GLIDE's format names the attributes individually.
- **Writing a whole store in one process:** simpler, but a window of the
  four GLIDE domains would have no way to resume or split across jobs.
