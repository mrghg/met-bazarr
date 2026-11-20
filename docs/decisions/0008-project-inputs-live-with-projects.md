# 0008 — Project-specific recipes and jobs live with the project; stores carry their recipe

- **Date:** 2026-11-20
- **Status:** Accepted (Matt Rigby)

## Context

met-bazarr had grown recipes, job scripts and checks for one project: GLIDE's
validation inputs (`recipes/era5-arco/`, `recipes/um/`, `scripts/isambard/`,
`scripts/lotus/`, `scripts/check_era5_equivalence.py`,
`scripts/check_um_store.py`), with site paths, allocation sizes and GLIDE task
numbers in the setup guide. Collaborators wanting to add a new source (MERRA-2)
could not easily tell the generic tool from one project's use of it, or find
the format they were writing.

## Decision

- **met-bazarr stays generic:** the sources, the formats, the build steps, the
  validator, one small example recipe per source (`examples/recipes/`), and a
  page per source (`docs/sources/`). The README says where each format is
  defined, and `docs/adding-a-source.md` says how to add a source.
- **A project's recipes, job scripts and checks live with that project.**
  GLIDE's are in the GLIDE repository, `validation/met-inputs/`, next to the
  validation plan that defines them, and run met-bazarr from a checkout at a
  pinned tag.
- **Every store carries its full recipe** in the attribute `recipe_text`, as
  well as the recipe's file name, so a store says exactly how it was built
  wherever its recipe is kept.

## Consequences

- A project pins a met-bazarr release and keeps its recipes; a recipe must
  still load after the project moves to a newer release (`--step plan`).
- Stores built before v0.3.0 carry only the recipe's file name; their recipes
  are in GLIDE's history (`validation/met-inputs/`) and in met-bazarr up to
  v0.2.0.
- Managing many such processing jobs (which stores exist, from which recipe
  and release, where, with which checksums) is not solved by this; it is a
  roadmap item (a catalogue of stores and recipes).

## Alternatives considered

- **A separate folder in met-bazarr** (`deployments/glide-validation/`): keeps
  everything in one place, but the generic repository would still grow with
  every project.
- **A new repository for processing jobs:** clean, but one more repository
  before it is clear what a catalogue of jobs should look like.
