# 0007 — The UM surface stresses include sub-grid orographic form drag

- **Date:** 2026-11-19
- **Status:** Accepted (a record of evidence; no change to the conversion)

## Context

GLIDE derives u\* from the surface stresses for every meteorology source (GLIDE
decision 0020; here, decisions 0003 and 0006). Over land, ERA5's stresses
include the drag of hills too small for its grid (its turbulent orographic form
drag scheme), which makes u\* from them about 1.9 times ERA5's own `zust`
(decision 0006). One of GLIDE's reasons for using the stresses is that ERA5 and
the UM then give the same kind of u\*. That holds only if the UM stresses
(STASH 3/219, 3/220), from which decision 0003 derives u\*, also include that
drag.

## Findings

**From the model's documentation** (researched for GLIDE task B14):

- Both case-library windows (Dec 2018 – Jan 2019, Jun – Jul 2019) come from the
  operational global UM running Global Atmosphere 6.1 with land surface GL8.1.
  GA6.1 was operational from July 2014 (Walters et al. 2017,
  doi:10.5194/gmd-10-1487-2017). GL8.1 was paired with GA6.1 until December
  2019, then with GA7.2 (Willett et al. 2026, GMD 19, 1473, Sect. 1), which
  is after our windows. NAME's documentation places the UMG_Mk10 series from
  mid-2017 to May 2022.
- In GA6.1 (Walters et al. 2017, Sect. 2.6), the drag of the smallest sub-grid
  hills is represented by **increasing the surface roughness length**
  (effective roughness, Wood & Mason 1993). The larger scales, where buoyancy
  matters (flow blocking and mountain waves), go to a separate drag scheme
  (Lott & Miller 1997). A distributed form-drag scheme (Wood et al. 2001)
  replaced the effective roughness only in GA8/GL9 (Willett et al. 2026,
  Sect. 3.1.4), which is later than our meteorology.
- So the turbulent form drag enters through the roughness length used in the
  surface exchange, and the surface stress the boundary-layer scheme
  computes, which 3/219 and 3/220 report, should include it. The blocking and
  gravity-wave drag (STASH section 6) is **not** in 3/219 and 3/220, as ERA5's
  gravity-wave stresses are kept apart from `ewss` and `nsss`.
- In the Mk10 PP files, the only section-3 fields are 3/026, 3/217, 3/219,
  3/220, 3/236, 3/319, 3/321 and 3/462. There is no separate form-drag
  stress. 3/026, "roughness length after boundary layer", reaches metres over
  mountains, far above vegetation roughness, which fits an effective roughness
  that includes orography.
- No source states in so many words that 3/219 and 3/220 include it, and the UM
  boundary-layer documentation (UMDP 24) was not available to confirm. NAME's
  documentation does not address it.

**Measured** (Isambard AI, 8 Jan 2019, EUR, every 3 h; medians by terrain
class of each store's own orography):

| u\* (m s-1) | UM, from its stresses (v0.1.0 trial store) | ERA5, from its stresses (`era5_arco`) | ERA5 `zust` |
|---|---|---|---|
| sea (orography < 1 m) | 0.30 | 0.31 | 0.31 |
| land 100–1,500 m | 0.31 | 0.42 | 0.18 |
| mountains > 1,500 m | 0.32 | 0.69 | 0.07 |

- The UM's u\* over mountains is more than four times `zust`, which is close to
  a local-roughness-only u\*: the UM stresses **do include orographic drag**.
- But less of it than ERA5's: the UM's u\* is about 0.75 times ERA5's
  stress-based u\* over land, and about 0.46 times over mountains. The two
  models represent the drag differently (effective roughness against ERA5's
  form-drag scheme).
- One day, compared by class across different grids (0.25° against about
  0.14° by 0.09°), with 3-h means against hourly means: the pattern, not
  precise ratios.

## Decision

- No change to the conversion: u\* from 3/219 and 3/220 (decision 0003) is the
  right input for GLIDE's choice of u\* from the stresses.
- For GLIDE: both meteorologies include sub-grid hill drag in u\*, so the
  definitions match in kind, and the UM's values are much closer to ERA5's
  stress-based u\* than to `zust`. GLIDE on the two meteorologies will still see
  different u\* over hilly land, a real difference between the two models'
  drag schemes, to be noted in GLIDE's comparison of the meteorologies (GLIDE
  decision 0020).

## Possible further check

Over mountains, compare u\* from the UM stresses with a log-law u\* using the
vegetation-only roughness. If the stresses include form drag, the first should
be clearly larger. The comparison with `zust` above makes the same point
indirectly.
