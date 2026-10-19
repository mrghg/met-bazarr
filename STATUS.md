# Status

> **Volatile working state.** Agents read this at the start of a session. Keep it
> short — it's a handoff note, not a log. Durable decisions belong in
> `docs/decisions/`; scratch belongs in `notes/` (git-ignored).

_Last updated: 2026-10-19_

## Current state
<!-- Where things stand right now, in a sentence or two. -->
Scaffold only: no package code yet. Scope and the boundary with the models are
proposed in [decision 0001](docs/decisions/0001-scope-and-boundary.md);
the task list, and who needs each task, is in [docs/roadmap.md](docs/roadmap.md).
GLIDE's development plan waits on this repository for its task B1 and its
pre-registration, so the GLIDE tasks come first.

## Next actions
<!-- The concrete next steps, most important first. -->
- [ ] **M0** — recipe format, `metbazarr build` / `validate`, format registry,
      provenance attributes (write decision 0002), synthetic tests, CI.
- [ ] **M1** — the `glide` format, from GLIDE's `docs/met_schema.md`.
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
