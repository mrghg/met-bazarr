# Decision records

One file per significant decision, dated and numbered, **immutable once
written**. If a decision is later reversed, add a *new* record that supersedes
the old one (and note it here) rather than editing history.

Copy [`0000-template.md`](0000-template.md) to start a new record:
`NNNN-short-title.md`.

## Index

<!-- One line per decision, newest last. Keep this current. -->
| # | Date | Decision | Status |
|---|------|----------|--------|
| 0000 | — | _Template — not a real decision_ | — |
| [0001](0001-scope-and-boundary.md) | 2026-10-19 | Scope: data preparation, not physics | Proposed |
| [0002](0002-provenance-attributes.md) | 2026-11-17 | Provenance attributes, and how a store is built | Proposed |
| [0003](0003-um-to-glide-conversion.md) | 2026-11-17 | Met Office UM (UMG_Mk10PT) to GLIDE format 1.0 | Accepted (u* note corrected by 0004; lag remark superseded by 0005) |
| [0004](0004-missing-values-and-ustar-note.md) | 2026-11-18 | Missing source values: GLIDE format 1.0 fill rule; u* note in 0003 corrected | Accepted |
| [0005](0005-glide-format-2-time-labels.md) | 2026-11-19 | GLIDE format 2.0: means and accumulations labelled per variable | Accepted |
| [0006](0006-era5-arco-to-glide.md) | 2026-11-19 | ERA5 from ARCO to GLIDE format 2.0; ECMWF-direct ERA5 kept separate | Accepted |
