# Status

> **Volatile working state.** Agents read this at the start of a session. Keep it
> short — it's a handoff note, not a log. Durable decisions belong in
> `docs/decisions/`; scratch belongs in `notes/` (git-ignored).

_Last updated: 2026-11-17_

## Current state
<!-- Where things stand right now, in a sentence or two. -->
M0 and M1 minimum are in place on branch `b14-um-glide` (draft PR #1): the
`glide` format writer and validator, the UM source, recipes, `metbazarr build` /
`validate`, provenance attributes (decision 0002) and 41 synthetic tests.
Scope: [decision 0001](docs/decisions/0001-scope-and-boundary.md); task list:
[docs/roadmap.md](docs/roadmap.md).

**GLIDE task B14 (UM Mk10 → `glide` format 1.0).** Brief: GLIDE
`dev/agent/briefs/B14-um-met-conversion.md` (PR #23). Stage 1 assessment in
`notes/B14-stage1-assessment.md` (git-ignored). Conversion choices agreed by
Matt: [decision 0003](docs/decisions/0003-um-to-glide-conversion.md).
Trial EUR-Jan store built 2026-11-17 (LOTUS job 2607290, untagged commit
d4e9b63, **not a validation input**):
`/work/scratch-pw5/mattrigby/met-bazarr/EUR_20181222-20190115_UMG-Mk10.zarr`, 193 times,
28 GB, 1 h 36 min on one CPU, 2.8 GB peak; validator PASS with full scan;
`scripts/check_um_store.py` at two times: native fields bit-identical, winds
within their source values, GLIDE pressure rebuild within 0.57 hPa of the UM's.
Scratch files are deleted 28 days after last access.

## Next actions
<!-- The concrete next steps, most important first. -->
- [ ] **B14**: review and merge PR #1; tag a release; build the four
      case-library windows with `--validation-input` from the tag; move them
      to Isambard, where GLIDE's reader opens them (GLIDE side; no torch or
      GLIDE on JASMIN).
- [ ] **M0/M1** remainder: anything in the roadmap beyond the B14 minimum.
- [ ] **M2** — ERA5 from the ARCO store, ported from GLIDE's
      `scripts/download_sample_cube.py`; values identical to GLIDE's current
      cubes on pressure and model levels.
- [ ] **M3** — check which ERA5 ensemble (EDA) variables the CDS offers as
      ensemble members, then the column extraction for GLIDE's six standard
      cases.

## Open questions / blockers
<!-- Anything undecided or waiting on someone. -->
- Whether GATES's meteorology processing
  ([extract_UM_met](https://github.com/elenafillo/extract_UM_met)) moves here:
  to be discussed with the team and the GATES maintainer. Tasks M4 and M8
  wait on this.
- If it does, how should ERA5's levels map onto GATES's `levels` dimension
  (task M4)? To be decided.
- Where do real downloads run? Credentials stay with the human, and on
  Isambard AI downloads must not run on the login node. To be decided.
