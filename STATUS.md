# Status

> **Volatile working state.** Agents read this at the start of a session. Keep it
> short — it's a handoff note, not a log. Durable decisions belong in
> `docs/decisions/`; scratch belongs in `notes/` (git-ignored).

_Last updated: 2026-11-24_

## Current state
<!-- Where things stand right now, in a sentence or two. -->
Release **v0.4.0** (pending tag): ERA5 stores derive a surface geopotential
consistent with their model levels, `metbazarr repair` brings built stores up to
it, and the validator refuses validation inputs whose levels lie below the
surface ([decision 0009](docs/decisions/0009-era5-consistent-surface-geopotential.md));
v0.3.1 added read retries. Since v0.2.0: the `glide` format 2.0 writer and validator, sources
`um_global` (Met Office UM, NAME's archive) and `era5_arco` (ERA5 from ARCO;
`era5_ecmwf` reserved), `metbazarr build` / `validate`, provenance, synthetic
tests. Generic material only: project recipes and jobs live with their project
([decision 0008](docs/decisions/0008-project-inputs-live-with-projects.md));
GLIDE's are in GLIDE's `validation/met-inputs/`. Where to start:
[README](README.md), [docs/adding-a-source.md](docs/adding-a-source.md),
[docs/sources/](docs/sources/). Scope:
[decision 0001](docs/decisions/0001-scope-and-boundary.md); task list:
[docs/roadmap.md](docs/roadmap.md).

**GLIDE B14 UM validation inputs (format 2.0)**, built with GLIDE's recipes (now in GLIDE `validation/met-inputs/um/`): four case-library stores built 2026-11-19
from v0.2.0 (commit e7b561d) with `--validation-input`, LOTUS build jobs
4094162 (EUR-Jan), 4094164 (EUR-Jul), 4094166 (NAM-Jan), 4094168 (NAM-Jul),
1.7–2.1 h each on one CPU, under 3 GB peak; validator PASS with full scan,
period variables friction_velocity and surface_sensible_heat_flux (time:
mean, 10800 s); no values needed filling. In
`/work/scratch-pw5/mattrigby/met-bazarr/`, with sha256 lists (58,760 files
each) in `checksums/<store name>.sha256` (jobs 4094163, 4094165, 4094167,
4094169):

| Store | Size | sha256 of its list |
| --- | --- | --- |
| `EUR_20181222-20190115_UMG-Mk10.zarr` | 19 GB | `7cb16fab0f78072a1d4386e49415d9e815fa84509d8c886dd45c63da67fad52e` |
| `EUR_20190621-20190715_UMG-Mk10.zarr` | 19 GB | `2bed3639c8a2c75f447056ed822407a97d52c04b406b030251d3e1db0d494a96` |
| `NAM_20181222-20190115_UMG-Mk10.zarr` | 16 GB | `172f32e1f817d6ce88749a6f442b3f929b963ea47a1b8245bacb0749527a58d6` |
| `NAM_20190621-20190715_UMG-Mk10.zarr` | 17 GB | `af80073bb913cb7bdf58bca23872a7437ad225a2555cc9a4a199bca2daf9aa96` |

**Superseded, not validation inputs:** the v0.1.0 stores (format 1.0, u*
unlabelled; jobs 3037857–3037860), renamed `SUPERSEDED-v0.1.0_<store name>`
with their checksum lists; the 2026-11-17 trial store
`TRIAL-d4e9b63_EUR_20181222-20190115_UMG-Mk10.zarr`. Don't copy them.
Scratch files are deleted 28 days after last access.

## Next actions
<!-- The concrete next steps, most important first. -->
- [ ] **M9** — one interface for sources (`build.py` is UM-shaped; ERA5 is a
      special case). Needed before MERRA-2.
- [ ] **MERRA-2** — collaborators; start from `docs/adding-a-source.md`, whose
      MERRA-2 notes need checking against the file specification.
- [ ] **GLIDE builds from v0.2.0** (recipes and jobs in GLIDE): Matt copies
      the four UM stores above and `checksums/` to `$GLIDE_DATA/um-mk10/` on
      Isambard, checks them with the sha256 lists, and GLIDE's reader test runs
      there; the ERA5 validation stores are built on Isambard.
- [ ] **M2** remainder: ERA5 pressure levels and the level cap; **M2b**
      ECMWF-direct ERA5 (waits for MARS access).
- [ ] **M3** — which ERA5 ensemble (EDA) variables the CDS offers as ensemble
      members, then the column extraction for GLIDE's seven standard cases.

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
