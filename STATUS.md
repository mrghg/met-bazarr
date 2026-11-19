# Status

> **Volatile working state.** Agents read this at the start of a session. Keep it
> short — it's a handoff note, not a log. Durable decisions belong in
> `docs/decisions/`; scratch belongs in `notes/` (git-ignored).

_Last updated: 2026-11-19_

## Current state
<!-- Where things stand right now, in a sentence or two. -->
M0 and M1 minimum are on `main` (PR #1 merged, release v0.1.0): the `glide`
format writer and validator, the UM source, recipes, `metbazarr build` /
`validate`, provenance attributes (decision 0002). GLIDE format 2.0 (time
labels on means and accumulations, [decision 0005](docs/decisions/0005-glide-format-2-time-labels.md))
is for release v0.2.0.
Scope: [decision 0001](docs/decisions/0001-scope-and-boundary.md); task list:
[docs/roadmap.md](docs/roadmap.md).

**GLIDE task B14 (UM Mk10 → `glide` format 2.0).** Brief: GLIDE
`dev/agent/briefs/B14-um-met-conversion.md` (PR #23). Stage 1 assessment in
`notes/B14-stage1-assessment.md` (git-ignored). Conversion choices agreed by
Matt: [decision 0003](docs/decisions/0003-um-to-glide-conversion.md);
GLIDE format 1.0 fill rule (GLIDE `e3df2e3`) and u* correction:
[decision 0004](docs/decisions/0004-missing-values-and-ustar-note.md).
**Superseded, not validation inputs** (format 1.0, u* unlabelled; decision
0005): four case-library stores built 2026-11-18 from v0.1.0 (commit 436ede9) with
`--validation-input`, LOTUS jobs 3037857–3037860, 2.5–2.7 h each on one CPU,
under 3 GB peak; validator PASS with full scan; no values needed filling. In
`/work/scratch-pw5/mattrigby/met-bazarr/`:
`EUR_20181222-20190115_UMG-Mk10.zarr` (19 GB), `EUR_20190621-20190715_UMG-Mk10.zarr`
(19 GB), `NAM_20181222-20190115_UMG-Mk10.zarr` (16 GB),
`NAM_20190621-20190715_UMG-Mk10.zarr` (17 GB); sha256 lists in `checksums/`.
The 2026-11-17 trial store (untagged d4e9b63, not a validation input) is
superseded: `TRIAL-d4e9b63_EUR_20181222-20190115_UMG-Mk10.zarr`.
Scratch files are deleted 28 days after last access.

## Next actions
<!-- The concrete next steps, most important first. -->
- [ ] **B14**: rebuild the four case-library stores from **v0.2.0** with
      `--validation-input` (format 2.0: the heat flux and u* labelled as 3-h
      means); Matt copies them to `$GLIDE_DATA/um-mk10/` on Isambard and checks
      them with the sha256 lists; GLIDE's reader test runs there (no torch or
      GLIDE on JASMIN). Do not copy the v0.1.0 stores.
- [ ] **M0/M1** remainder: anything in the roadmap beyond the B14 minimum.
- [ ] **ERA5 (M2, M5; decision 0006)**: source `era5_arco` and 16 recipes
      done (model levels; values bit-identical to GLIDE's downloader). **Matt
      to confirm u\* from the surface stresses** (median 1.9x ERA5's `zust`
      over land; decision 0006) before validation stores are built from a
      tag with `scripts/isambard/build_era5.sh`. Still to do: pressure levels
      and the level cap (M2); ECMWF-direct ERA5 (M2b, waits for MARS access).
- [ ] **M3** — check which ERA5 ensemble (EDA) variables the CDS offers as
      ensemble members, then the column extraction for GLIDE's seven standard
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
