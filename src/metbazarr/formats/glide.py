"""The ``glide`` format: GLIDE's meteorology input contract.

The authoritative definition is ``docs/met_schema.md`` in the GLIDE repository
(https://github.com/mrghg/glide). This module implements **format version 2.0**
as it stood at GLIDE commit :data:`GLIDE_SCHEMA_COMMIT`. When that page changes,
this module's version changes with it.

What lives here:

- the variable table (names, dimensions, accepted units);
- the store attributes (format tag and provenance), and the per-variable
  time attributes that mark means and accumulations (:func:`period_attrs`);
- encoding and chunking for writing;
- :func:`fill_isolated_missing`, the page's fill rule for isolated missing
  source values (recorded in ``glide_filled_values``);
- :func:`validate`, which checks a store against everything the page
  prescribes, plus plausibility checks that catch the silent mistakes the page
  warns about (geopotential height for geopotential, heat flux with the wrong
  sign, untagged model levels).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import xarray as xr

FORMAT_NAME = "glide"
FORMAT_VERSION = "2.0"
#: GLIDE commit whose ``docs/met_schema.md`` defines format 2.0 (the merge of
#: GLIDE PR #27, decision 0020).
GLIDE_SCHEMA_COMMIT = "b21f58602ef8660e9aa20eb104cce3336f5ebf28"

# Physical constants, identical to GLIDE's (src/lpdm/met_reader.py,
# src/lpdm/vertical_grid.py), so derived fields are consistent with how GLIDE
# reads them.
GRAVITY_M_S2 = 9.80665
R_DRY_AIR_J_KG_K = 287.05
TV_COEFF = 0.6077

TIME = "time"
LAT = "latitude"
LON = "longitude"
#: Names GLIDE recognises for the vertical coordinate.
LEVEL_NAMES = ("level", "hybrid", "model_level")

THREE_D = (
    "u_component_of_wind",
    "v_component_of_wind",
    "vertical_velocity",
    "temperature",
    "specific_humidity",
)
SURFACE = (
    "boundary_layer_height",
    "surface_pressure",
    "friction_velocity",
    "surface_sensible_heat_flux",
)
GEOPOTENTIAL = "geopotential"
SURFACE_GEOPOTENTIAL = "geopotential_at_surface"
REQUIRED = (*THREE_D, GEOPOTENTIAL, *SURFACE, SURFACE_GEOPOTENTIAL)

#: Units written by met-bazarr: ERA5's CF strings, as the page recommends.
CANONICAL_UNITS = {
    "u_component_of_wind": "m s**-1",
    "v_component_of_wind": "m s**-1",
    "vertical_velocity": "m s**-1",
    "temperature": "K",
    "specific_humidity": "kg kg**-1",
    "geopotential": "m**2 s**-2",
    "boundary_layer_height": "m",
    "surface_pressure": "Pa",
    "friction_velocity": "m s**-1",
    "surface_sensible_heat_flux": "W m**-2",
    "geopotential_at_surface": "m**2 s**-2",
}

# Accepted unit strings after normalisation (lower case, no spaces). These are
# GLIDE's own sets; an empty string is never accepted (the page requires
# non-empty units even where GLIDE's reader tolerates them).
_VELOCITY = {"m/s", "m.s-1", "ms-1", "ms**-1", "m*s^-1", "m*s**-1"}
_OMEGA = {"pa/s", "pas-1", "pas**-1", "pa*s^-1", "pa*s**-1", "pa.s-1"}
_LENGTH = {"m", "meter", "metre", "meters", "metres"}
_PRESSURE = {"pa", "pascal", "pascals"}
_TEMPERATURE = {"k", "kelvin"}
_GEOPOTENTIAL = {
    "m**2s**-2",
    "m2/s2",
    "m^2s^-2",
    "m2s-2",
    "m2s**-2",
    "m^2/s^2",
    "m2/s^2",
}
_FLUX_RATE = {"w/m**2", "wm**-2", "wm-2", "w/m^2", "w/m2", "w*m**-2", "w*m^-2", "w.m-2"}
_FLUX_ACCUMULATED = {
    "j/m**2",
    "jm**-2",
    "jm-2",
    "j/m^2",
    "j/m2",
    "j*m**-2",
    "j*m^-2",
    "j.m-2",
}
_HUMIDITY = {"kg/kg", "kgkg-1", "kgkg**-1", "kg*kg-1", "kg*kg**-1", "1"}

ACCEPTED_UNITS = {
    "u_component_of_wind": _VELOCITY,
    "v_component_of_wind": _VELOCITY,
    "vertical_velocity": _VELOCITY | _OMEGA,
    "temperature": _TEMPERATURE,
    "specific_humidity": _HUMIDITY,
    "geopotential": _GEOPOTENTIAL,
    "boundary_layer_height": _LENGTH,
    "surface_pressure": _PRESSURE,
    "friction_velocity": _VELOCITY,
    "surface_sensible_heat_flux": _FLUX_RATE | _FLUX_ACCUMULATED,
    "geopotential_at_surface": _GEOPOTENTIAL,
}

#: Store attributes every met-bazarr ``glide`` store carries (format 1.0 onward,
#: "Provenance attributes"). The flux attributes depend on the flux units and
#: are checked separately.
PROVENANCE_ATTRS = (
    "glide_format",
    "glide_format_version",
    "glide_vertical_coordinate",
    "source_dataset",
    "source_access",
    "producer",
    "producer_version",
    "producer_commit",
    "processing",
    "compression",
    "domain",
)

#: Per-variable attributes marking a mean or accumulation over the period that
#: ends at each timestamp (format 2.0, "What a timestamp means"). A variable
#: with neither is a snapshot.
CELL_METHODS_ATTR = "cell_methods"
PERIOD_ATTR = "glide_period_seconds"
PERIOD_METHODS = {"mean": "time: mean", "sum": "time: sum"}


def period_attrs(kind: str, seconds: int) -> dict[str, object]:
    """Variable attributes for a mean (``kind="mean"``) or accumulation
    (``kind="sum"``) over the ``seconds`` ending at each timestamp."""
    if kind not in PERIOD_METHODS:
        raise ValueError(f"kind must be one of {sorted(PERIOD_METHODS)}, got {kind!r}")
    if int(seconds) <= 0:
        raise ValueError(f"period must be positive, got {seconds}")
    return {CELL_METHODS_ATTR: PERIOD_METHODS[kind], PERIOD_ATTR: int(seconds)}


# Plausible physical ranges, wide enough for any real atmosphere and narrow
# enough to catch a unit mistake (hPa for Pa, degrees C for K, height for
# geopotential).
PLAUSIBLE = {
    "u_component_of_wind": (-200.0, 200.0),
    "v_component_of_wind": (-200.0, 200.0),
    "temperature": (150.0, 350.0),
    "specific_humidity": (0.0, 0.05),
    "boundary_layer_height": (0.0, 10_000.0),
    "surface_pressure": (30_000.0, 110_000.0),
    "friction_velocity": (0.0, 10.0),
}


def normalise_units(units: str) -> str:
    """Normalise a unit string as GLIDE does: lower case, no spaces."""
    return units.strip().lower().replace(" ", "")


def level_chunk(n_levels: int) -> int:
    """GLIDE's chunk depth: whole when 48 levels or fewer, otherwise 24
    (``scripts/download_sample_cube.py``, ``_output_chunks``)."""
    return n_levels if n_levels <= 48 else 24


@dataclass
class ValidationReport:
    """What :func:`validate` found. A store passes when ``errors`` is empty."""

    path: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def format(self) -> str:
        lines = [f"glide {FORMAT_VERSION} validation of {self.path}"]
        lines += [f"  info:    {m}" for m in self.info]
        lines += [f"  WARNING: {m}" for m in self.warnings]
        lines += [f"  ERROR:   {m}" for m in self.errors]
        lines.append("  PASS" if self.ok else f"  FAIL ({len(self.errors)} errors)")
        return "\n".join(lines)


def _vertical_dim(ds: xr.Dataset) -> str | None:
    for name in LEVEL_NAMES:
        if name in ds.dims:
            return name
    return None


def _sample_times(n: int) -> list[int]:
    return sorted({0, n // 2, n - 1}) if n else []


def validate(
    path: str | Path,
    *,
    full_scan: bool = True,
    validation_input: bool = False,
) -> ValidationReport:
    """Check a store against ``glide`` format :data:`FORMAT_VERSION`.

    Args:
        path: The Zarr store.
        full_scan: Also read every value of every required variable to check
            that all are finite. Reads the whole store; turn off for a quick
            check of structure and a sample of times.
        validation_input: Apply the extra rules for GLIDE's validation inputs
            (lossless, clean release commit).

    Returns:
        A :class:`ValidationReport`.
    """
    report = ValidationReport(str(path))
    err, info = report.errors.append, report.info.append

    try:
        ds = xr.open_zarr(path, consolidated=True, decode_times=True)
    except Exception as exc:  # noqa: BLE001 - any failure to open is a failure
        err(f"cannot open as a Zarr store with consolidated metadata: {exc}")
        return report

    # --- attributes -------------------------------------------------------
    attrs = ds.attrs
    for name in PROVENANCE_ATTRS:
        if str(attrs.get(name, "")).strip() == "":
            err(f"missing or empty store attribute {name!r}")
    if attrs.get("glide_format") not in (None, FORMAT_NAME):
        err(f"glide_format is {attrs.get('glide_format')!r}, expected {FORMAT_NAME!r}")
    if attrs.get("glide_format_version") not in (None, FORMAT_VERSION):
        err(
            f"glide_format_version is {attrs.get('glide_format_version')!r}; "
            f"this validator implements {FORMAT_VERSION!r}"
        )
    vcoord = str(attrs.get("glide_vertical_coordinate", ""))
    if vcoord not in ("pressure_level", "model_level"):
        err(
            "glide_vertical_coordinate must be 'pressure_level' or 'model_level', "
            f"got {vcoord!r} (an untagged model-level store is refused by GLIDE)"
        )
    commit = str(attrs.get("producer_commit", ""))
    if validation_input and (commit.endswith("-dirty") or commit in ("", "unknown")):
        err(
            f"producer_commit is {commit!r}: validation inputs come from a clean, "
            "tagged release"
        )

    # --- coordinates ------------------------------------------------------
    for coord in (TIME, LAT, LON):
        if coord not in ds.coords:
            err(f"missing coordinate {coord!r}")
    lev = _vertical_dim(ds)
    if lev is None:
        err(f"no vertical coordinate; expected one of {LEVEL_NAMES}")
    if report.errors and any(c not in ds.coords for c in (TIME, LAT, LON)):
        return report

    time = ds[TIME].values
    step_s: int | None = None
    if not np.issubdtype(time.dtype, np.datetime64):
        err(f"time has dtype {time.dtype}, expected datetime64")
    elif time.size > 1:
        steps = np.diff(time).astype("timedelta64[s]").astype(np.int64)
        if np.any(steps <= 0):
            err("time is not strictly increasing")
        elif np.unique(steps).size != 1:
            err(
                f"time spacing is not uniform: steps of {sorted(set(steps.tolist()))} s"
            )
        else:
            step_s = int(steps[0])
            info(f"{time.size} times, every {step_s} s, {time[0]} to {time[-1]}")
    lat, lon = ds[LAT].values, ds[LON].values
    if lat.ndim != 1 or not (np.all(np.diff(lat) > 0) or np.all(np.diff(lat) < 0)):
        err("latitude must be 1-D and strictly monotonic")
    if np.nanmin(lat) < -90 or np.nanmax(lat) > 90:
        err("latitude outside -90..90")
    if lon.ndim != 1 or not np.all(np.diff(lon) > 0):
        err("longitude must be 1-D and strictly increasing")
    if not (
        (np.nanmin(lon) >= -180 and np.nanmax(lon) <= 180)
        or (np.nanmin(lon) >= 0 and np.nanmax(lon) <= 360)
    ):
        err("longitude must lie in -180..180 or 0..360")
    info(
        f"grid {lat.size} x {lon.size}: lat {lat.min():.6f}..{lat.max():.6f}, "
        f"lon {lon.min():.6f}..{lon.max():.6f}"
    )
    if lev is not None:
        levels = ds[lev].values
        if vcoord == "pressure_level":
            units = normalise_units(str(ds[lev].attrs.get("units", "")))
            if units not in {"pa", "hpa", "mbar", "millibar", ""}:
                err(f"pressure-level coordinate has units {units!r}")
            if np.all(np.diff(levels) == 1):
                err(
                    "pressure_level store whose vertical coordinate holds "
                    "consecutive integers: GLIDE refuses it"
                )
        info(f"{levels.size} levels on {lev!r} ({vcoord})")

    # --- variables --------------------------------------------------------
    present = set(ds.data_vars)
    for name in REQUIRED:
        if name not in present:
            err(f"missing required variable {name!r}")
    extra = sorted(present - set(REQUIRED))
    if extra:
        err(
            f"variables not in the format (a store holds exactly the required set): {extra}"
        )
    if report.errors:
        return report

    want_3d = (TIME, lev, LAT, LON)
    want_2d = (TIME, LAT, LON)
    for name in THREE_D:
        if ds[name].dims != want_3d:
            err(f"{name} has dims {ds[name].dims}, expected {want_3d}")
    if ds[GEOPOTENTIAL].dims not in (want_3d, (lev, LAT, LON)):
        err(f"geopotential has dims {ds[GEOPOTENTIAL].dims}")
    for name in SURFACE:
        if ds[name].dims != want_2d:
            err(f"{name} has dims {ds[name].dims}, expected {want_2d}")
    zs_dims = ds[SURFACE_GEOPOTENTIAL].dims
    if zs_dims not in ((LAT, LON), want_2d) and not (
        len(zs_dims) == 3 and zs_dims[1:] == (LAT, LON) and ds[zs_dims[0]].size == 1
    ):
        err(f"geopotential_at_surface has dims {zs_dims}")

    for name in REQUIRED:
        units = str(ds[name].attrs.get("units", ""))
        if units.strip() == "":
            err(f"{name} has no units attribute")
        elif normalise_units(units) not in ACCEPTED_UNITS[name]:
            err(f"{name} has unrecognised units {units!r}")
        enc = ds[name].encoding
        dtype = np.dtype(enc.get("dtype", ds[name].dtype))
        lossy = "scale_factor" in enc or "add_offset" in enc
        if dtype not in (np.float32, np.float64) and not (dtype == np.int16 and lossy):
            err(f"{name} is stored as {dtype}; expected float32, float64 or CF int16")
        if validation_input and (lossy or dtype == np.int16):
            err(f"{name} uses scale/offset encoding: validation inputs are lossless")
        for codec in enc.get("filters", None) or []:
            if (
                "bitround" in type(codec).__name__.lower()
                or "quantize" in str(codec).lower()
            ):
                err(f"{name} has a lossy filter {codec}")

    # --- heat-flux tagging ------------------------------------------------
    shf_units = normalise_units(
        str(ds["surface_sensible_heat_flux"].attrs.get("units", ""))
    )
    if shf_units in _FLUX_ACCUMULATED:
        if "glide_flux_accumulation_seconds" not in attrs:
            err(
                "accumulated (J m**-2) heat flux without glide_flux_accumulation_seconds"
            )
    elif shf_units in _FLUX_RATE:
        avg = attrs.get("glide_flux_averaging_seconds")
        if avg is None:
            err(
                "W m**-2 heat flux without glide_flux_averaging_seconds (0 if instantaneous)"
            )
        else:
            try:
                if int(avg) < 0:
                    raise ValueError
            except (TypeError, ValueError):
                err(
                    f"glide_flux_averaging_seconds is {avg!r}, expected a whole number >= 0"
                )

    # --- what each timestamp means (format 2.0) ----------------------------
    _check_periods(ds, attrs, step_s, shf_units, validation_input, report)

    if report.errors:
        return report

    # --- documented fills -------------------------------------------------
    _check_filled(ds, lev, report)

    # --- physical plausibility on a sample of times -----------------------
    _check_physics(ds, lev, vcoord, report)

    # --- every value finite ----------------------------------------------
    if full_scan:
        for name in REQUIRED:
            n_bad = int((~np.isfinite(ds[name].data)).sum())  # computes if dask
            if n_bad:
                err(f"{name} has {n_bad} non-finite values")
        info("full scan: every value of every required variable read")
    return report


def _check_periods(
    ds: xr.Dataset,
    attrs: dict,
    step_s: int | None,
    shf_units: str,
    validation_input: bool,
    report: ValidationReport,
) -> None:
    """Check the per-variable ``cell_methods`` / ``glide_period_seconds``.

    A period variable carries both; its method is one GLIDE knows; its period
    equals the store's time step (GLIDE refuses any other); time-invariant
    fields are never period variables. The heat flux's labels agree with the
    store-level flux attributes. In validation inputs, ``friction_velocity`` is
    a period variable, because it is derived from the mean surface stresses.
    """
    err, info = report.errors.append, report.info.append
    periods: dict[str, int] = {}
    for name in REQUIRED:
        va = ds[name].attrs
        has_cm, has_p = CELL_METHODS_ATTR in va, PERIOD_ATTR in va
        if not (has_cm or has_p):
            continue
        if has_cm != has_p:
            err(f"{name}: {CELL_METHODS_ATTR} and {PERIOD_ATTR} must come together")
            continue
        if TIME not in ds[name].dims:
            err(f"{name} has no time dimension, so it cannot be a period variable")
            continue
        method = str(va[CELL_METHODS_ATTR])
        if method not in PERIOD_METHODS.values():
            err(
                f"{name}: {CELL_METHODS_ATTR} is {method!r}, expected one of "
                f"{sorted(PERIOD_METHODS.values())}"
            )
        try:
            period = int(va[PERIOD_ATTR])
            if period <= 0 or float(va[PERIOD_ATTR]) != period:
                raise ValueError
        except (TypeError, ValueError):
            err(
                f"{name}: {PERIOD_ATTR} is {va[PERIOD_ATTR]!r}, "
                "expected a whole number > 0"
            )
            continue
        if step_s is not None and period != step_s:
            err(
                f"{name}: {PERIOD_ATTR} = {period} s differs from the store's time step "
                f"of {step_s} s (GLIDE refuses this)"
            )
        periods[name] = period

    shf = "surface_sensible_heat_flux"
    if shf_units in _FLUX_ACCUMULATED:
        acc = attrs.get("glide_flux_accumulation_seconds")
        if shf not in periods:
            err(f"{shf} is accumulated (J m**-2) but not labelled as a period variable")
        else:
            if ds[shf].attrs[CELL_METHODS_ATTR] != PERIOD_METHODS["sum"]:
                err(
                    f"{shf} is accumulated (J m**-2): "
                    f"{CELL_METHODS_ATTR} must be 'time: sum'"
                )
            if acc is not None and str(periods[shf]) != str(acc):
                err(
                    f"{shf}: {PERIOD_ATTR} = {periods[shf]} differs from "
                    f"glide_flux_accumulation_seconds = {acc}"
                )
    elif shf_units in _FLUX_RATE:
        avg = attrs.get("glide_flux_averaging_seconds")
        averaged = avg is not None and str(avg).strip() not in ("", "0")
        if averaged and shf not in periods:
            err(
                f"{shf} is a mean (glide_flux_averaging_seconds = {avg}) but not "
                "labelled as a period variable"
            )
        if shf in periods:
            if ds[shf].attrs[CELL_METHODS_ATTR] != PERIOD_METHODS["mean"]:
                err(
                    f"{shf} is a rate (W m**-2): "
                    f"{CELL_METHODS_ATTR} must be 'time: mean'"
                )
            if str(periods[shf]) != str(avg):
                err(
                    f"{shf}: {PERIOD_ATTR} = {periods[shf]} differs from "
                    f"glide_flux_averaging_seconds = {avg}"
                )

    if validation_input and "friction_velocity" not in periods:
        err(
            "friction_velocity is not a period variable: validation inputs derive it "
            "from the mean surface stresses (format 2.0)"
        )
    if periods:
        info(
            "period variables: "
            + ", ".join(
                f"{n} ({ds[n].attrs[CELL_METHODS_ATTR]}, {p} s)"
                for n, p in sorted(periods.items())
            )
        )


def _check_physics(
    ds: xr.Dataset, lev: str, vcoord: str, report: ValidationReport
) -> None:
    err, warn = report.errors.append, report.warnings.append
    times = _sample_times(ds.sizes[TIME])
    sample = ds.isel({TIME: times}).load()

    for name, (lo, hi) in PLAUSIBLE.items():
        vals = sample[name].values
        vmin, vmax = float(np.nanmin(vals)), float(np.nanmax(vals))
        if vmin < lo or vmax > hi:
            err(
                f"{name} spans {vmin:g}..{vmax:g}, outside the plausible {lo:g}..{hi:g}"
            )
    w_units = normalise_units(str(ds["vertical_velocity"].attrs.get("units", "")))
    if (
        w_units in _VELOCITY
        and float(np.nanmax(np.abs(sample["vertical_velocity"].values))) > 50
    ):
        err("vertical_velocity exceeds 50 m s**-1: omega stored with velocity units?")

    phi = sample[GEOPOTENTIAL]
    phi_s = sample[SURFACE_GEOPOTENTIAL]
    if TIME in phi_s.dims:
        phi_s = phi_s.isel({TIME: 0})
    phi_s = phi_s.squeeze(drop=True).values.astype(np.float64)
    ps = sample["surface_pressure"].isel({TIME: 0}).values.astype(np.float64)

    # Geopotential, not geopotential height: across the domain, ln(ps) falls
    # with surface geopotential at about 1/(R_d T). Stored as height in metres,
    # the slope would be about g = 9.8 times steeper. Only judged where terrain,
    # not weather, dominates the variation of surface pressure.
    corr = (
        np.corrcoef(phi_s.ravel(), np.log(ps).ravel())[0, 1]
        if np.ptp(phi_s) > 0 and np.ptp(ps) > 0
        else 0.0
    )
    if np.ptp(ps) > 5000.0 and corr < -0.8:
        slope = np.polyfit(phi_s.ravel(), np.log(ps).ravel(), 1)[0]
        scale_t = -1.0 / (R_DRY_AIR_J_KG_K * slope)  # implied mean temperature, K
        if not 150.0 < scale_t < 350.0:
            err(
                "surface pressure and geopotential_at_surface imply a column "
                f"temperature of {scale_t:.0f} K: geopotential_at_surface is probably "
                "not in m**2 s**-2 (geopotential height in metres gives ~30 K)"
            )
    else:
        warn(
            "terrain does not dominate surface pressure in this domain: "
            "geopotential-vs-height check skipped"
        )

    phi_0 = (phi.isel({TIME: 0}) if TIME in phi.dims else phi).values.astype(np.float64)
    order = np.argsort(phi_0.reshape(phi_0.shape[0], -1).mean(axis=1))
    stacked = phi_0[order]
    if np.any(np.diff(stacked, axis=0) <= 0):
        err("geopotential does not increase monotonically with level in every column")
    if vcoord == "model_level":
        gap = stacked[0] - phi_s
        if np.nanmin(gap) < -GRAVITY_M_S2:
            err(
                "lowest model level lies below geopotential_at_surface "
                f"(by up to {-np.nanmin(gap) / GRAVITY_M_S2:.0f} m): mixed units?"
            )
        # Top of the model must reach 20 km above the ground everywhere.
        top_agl = (stacked[-1] - phi_s) / GRAVITY_M_S2
        if np.nanmin(top_agl) < 20_000.0:
            report.warnings.append(
                f"top level is only {np.nanmin(top_agl):.0f} m above the ground "
                "somewhere: validation inputs keep levels to at least 20 km"
            )

    # Sign of the sensible heat flux. GLIDE wants positive downward. Upward
    # (daytime, convective) fluxes reach several hundred W m-2; downward
    # (stable) ones rarely exceed ~150. So in the right convention the largest
    # magnitudes are negative.
    shf = ds["surface_sensible_heat_flux"]
    shf_units = normalise_units(str(shf.attrs.get("units", "")))
    vals = sample["surface_sensible_heat_flux"].values.astype(np.float64)
    if shf_units in _FLUX_ACCUMULATED:
        acc = float(ds.attrs.get("glide_flux_accumulation_seconds", 3600))
        vals = vals / acc
    lo_q, hi_q = np.nanpercentile(vals, [0.5, 99.5])
    if hi_q > 100.0 and hi_q > 2.0 * abs(lo_q):
        err(
            f"surface_sensible_heat_flux 0.5/99.5 percentiles {lo_q:.0f}/{hi_q:.0f} "
            "W m**-2: large positive values suggest positive-UP; GLIDE wants "
            "positive-down (ECMWF convention)"
        )
    elif max(abs(lo_q), abs(hi_q)) < 100.0:
        warn("heat-flux magnitudes too small in the sampled times to check the sign")
    if float(np.nanmax(np.abs(vals))) > 2000.0:
        err("surface_sensible_heat_flux exceeds 2000 W m**-2 (GLIDE rejects this)")


# ---------------------------------------------------------------------------
# Isolated missing source values (format 1.0 onward, "Validation inputs")
# ---------------------------------------------------------------------------

FILLED_VALUES_ATTR = "glide_filled_values"
#: At most this many filled values per variable per store.
MAX_FILLED_PER_VARIABLE = 10
#: Never filled: a missing value here stops the conversion.
NEVER_FILLED = (GEOPOTENTIAL, SURFACE_GEOPOTENTIAL)
_FILL_KEYS = ("variable", "time", "latitude", "longitude", "before", "after", "filled")
FILL_PROCESSING = (
    "Isolated missing values filled by the GLIDE met format fill rule (format 1.0 onward): a single "
    "timestep with finite values at the same cell either side, at most "
    f"{MAX_FILLED_PER_VARIABLE} per variable, set to the mean of the values at the "
    f"timesteps before and after; each listed in {FILLED_VALUES_ATTR}."
)


class FillError(RuntimeError):
    """Missing values the fill rule does not allow to be filled."""


def _iso(t: np.datetime64) -> str:
    return np.datetime_as_string(t, unit="s") + "Z"


def _fill_mean(before: float, after: float) -> np.float32:
    return np.float32((np.float64(before) + np.float64(after)) / 2.0)


def _fill_key(entry: dict) -> tuple:
    return (
        entry["variable"],
        entry["time"],
        entry["latitude"],
        entry["longitude"],
        entry.get("level"),
    )


def _time_varying(ds: xr.Dataset) -> list[str]:
    return [n for n in REQUIRED if TIME in ds[n].dims and n not in NEVER_FILLED]


def fill_isolated_missing(path: str | Path) -> list[dict]:
    """Apply the format's fill rule to every non-finite value in a store.

    A non-finite value in a time-varying variable is filled when the same cell
    (and level) is finite at the timesteps immediately before and after it,
    and the variable has no more than :data:`MAX_FILLED_PER_VARIABLE` such
    values. It becomes the mean of those two values, and is listed in the store
    attribute ``glide_filled_values``; ``processing`` notes the fill.

    Anything else (a gap at the first or last time, a gap longer than one
    timestep, too many values, a missing value in the geopotential) raises
    :class:`FillError` listing every case, and nothing is written.

    Returns:
        The entries added to ``glide_filled_values`` (empty if nothing was
        missing).
    """
    import zarr

    ds = xr.open_zarr(path, consolidated=True)
    lev = _vertical_dim(ds)
    times = ds[TIME].values
    nt = times.size
    problems: list[str] = []
    for name in NEVER_FILLED:
        n_bad = int((~np.isfinite(ds[name].data)).sum())
        if n_bad:
            problems.append(f"{name}: {n_bad} non-finite values (never filled)")

    # variable -> time index -> (array for that time, [(cell index, entry)])
    plan: dict[str, dict[int, tuple[np.ndarray, list]]] = {}
    for name in _time_varying(ds):
        da = ds[name]
        other = tuple(range(1, da.ndim))
        per_time = np.asarray((~np.isfinite(da.data)).sum(axis=other))
        if hasattr(per_time, "compute"):
            per_time = per_time.compute()
        bad_times = np.flatnonzero(per_time)
        total = int(per_time.sum())
        if total == 0:
            continue
        if total > MAX_FILLED_PER_VARIABLE:
            problems.append(
                f"{name}: {total} non-finite values, more than the "
                f"{MAX_FILLED_PER_VARIABLE} the fill rule allows "
                f"(at {', '.join(_iso(times[t]) for t in bad_times[:5])}"
                f"{' ...' if bad_times.size > 5 else ''})"
            )
            continue
        for t in bad_times:
            t = int(t)
            here = da.isel({TIME: t}).values
            cells = np.argwhere(~np.isfinite(here))
            if t == 0 or t == nt - 1:
                problems.append(
                    f"{name}: {len(cells)} non-finite values at the "
                    f"{'first' if t == 0 else 'last'} time {_iso(times[t])}"
                )
                continue
            before_all = da.isel({TIME: t - 1}).values
            after_all = da.isel({TIME: t + 1}).values
            fills = []
            for cell in map(tuple, cells):
                before, after = before_all[cell], after_all[cell]
                where = _describe_cell(ds, da, lev, cell)
                if not (np.isfinite(before) and np.isfinite(after)):
                    problems.append(
                        f"{name} at {_iso(times[t])}, {where}: not finite at the "
                        "neighbouring timestep too (a gap longer than one timestep)"
                    )
                    continue
                filled = _fill_mean(before, after)
                entry = {"variable": name, "time": _iso(times[t])}
                entry.update(_cell_coords(ds, da, lev, cell))
                entry.update(
                    before=float(before), after=float(after), filled=float(filled)
                )
                fills.append((cell, entry))
            if fills:
                here = here.copy()
                for cell, entry in fills:
                    here[cell] = entry["filled"]
                plan.setdefault(name, {})[t] = (here, fills)

    if problems:
        raise FillError(
            "missing values the GLIDE format fill rule does not allow to be "
            "filled; fetch them from the original archive or report the case:\n  "
            + "\n  ".join(problems)
        )
    added = [
        e for per_t in plan.values() for _, fills in per_t.values() for _, e in fills
    ]
    if not added:
        return []

    for name, per_t in plan.items():
        dims = ds[name].dims
        for t, (arr, _) in per_t.items():
            xr.Dataset({name: (dims, arr[None])}).to_zarr(
                path, region={TIME: slice(t, t + 1)}, mode="r+"
            )

    group = zarr.open_group(str(path), mode="r+")
    previous = json.loads(group.attrs.get(FILLED_VALUES_ATTR, "[]"))
    merged = {_fill_key(e): e for e in previous}
    merged.update({_fill_key(e): e for e in added})
    entries = sorted(merged.values(), key=lambda e: (e["variable"], e["time"]))
    attrs = {FILLED_VALUES_ATTR: json.dumps(entries)}
    processing = str(group.attrs.get("processing", ""))
    if FILLED_VALUES_ATTR not in processing:
        step = processing.count(" | ") + 2 if processing else 1
        attrs["processing"] = (
            f"{processing} | ({step}) {FILL_PROCESSING}"
            if processing
            else f"({step}) {FILL_PROCESSING}"
        )
    group.attrs.update(attrs)
    zarr.consolidate_metadata(str(path))
    return added


def _cell_coords(ds: xr.Dataset, da: xr.DataArray, lev: str | None, cell) -> dict:
    """Coordinates of one cell of one time slice of ``da``."""
    pos = dict(zip(da.dims[1:], cell, strict=True))
    out = {
        "latitude": float(ds[LAT].values[pos[LAT]]),
        "longitude": float(ds[LON].values[pos[LON]]),
    }
    if lev is not None and lev in pos:
        level = ds[lev].values[pos[lev]]
        out["level"] = (
            int(level)
            if np.issubdtype(np.asarray(level).dtype, np.integer)
            else float(level)
        )
    return out


def _describe_cell(ds, da, lev, cell) -> str:
    c = _cell_coords(ds, da, lev, cell)
    where = f"{c['latitude']:.4f} N, {c['longitude']:.4f} E"
    return where + (f", level {c['level']}" if "level" in c else "")


def _check_filled(ds: xr.Dataset, lev: str, report: ValidationReport) -> None:
    """Check ``glide_filled_values`` against the rule and the stored values."""
    err = report.errors.append
    raw = ds.attrs.get(FILLED_VALUES_ATTR)
    if raw is None:
        return
    try:
        entries = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        err(f"{FILLED_VALUES_ATTR} is not valid JSON: {exc}")
        return
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        err(f"{FILLED_VALUES_ATTR} must be a JSON list of objects")
        return
    if not entries:
        err(
            f"{FILLED_VALUES_ATTR} is present but empty (omit it if nothing was filled)"
        )
        return
    if FILLED_VALUES_ATTR not in str(ds.attrs.get("processing", "")):
        err(f"processing does not note the fill listed in {FILLED_VALUES_ATTR}")

    times = ds[TIME].values
    lat, lon = ds[LAT].values, ds[LON].values
    fillable = _time_varying(ds)
    counts: dict[str, int] = {}
    seen: set = set()
    for k, e in enumerate(entries):
        tag = f"{FILLED_VALUES_ATTR}[{k}]"
        name = e.get("variable")
        if name not in fillable:
            err(f"{tag}: variable {name!r} may not be filled")
            continue
        three_d = lev in ds[name].dims
        keys = set(_FILL_KEYS) | ({"level"} if three_d else set())
        if set(e) != keys:
            err(f"{tag}: keys {sorted(e)}, expected {sorted(keys)}")
            continue
        key = _fill_key(e)
        if key in seen:
            err(f"{tag}: listed twice")
            continue
        seen.add(key)
        counts[name] = counts.get(name, 0) + 1
        try:
            t = int(np.flatnonzero(times == np.datetime64(e["time"].rstrip("Z")))[0])
            j = int(np.flatnonzero(np.isclose(lat, float(e["latitude"]), atol=1e-6))[0])
            i = int(
                np.flatnonzero(np.isclose(lon, float(e["longitude"]), atol=1e-6))[0]
            )
            pos = {LAT: j, LON: i}
            if three_d:
                pos[lev] = int(np.flatnonzero(ds[lev].values == e["level"])[0])
        except (AttributeError, IndexError, ValueError, TypeError):
            err(f"{tag}: time, latitude, longitude or level not in the store")
            continue
        if t == 0 or t == times.size - 1:
            err(f"{tag}: at the first or last time, which may not be filled")
            continue
        vals = (
            ds[name].isel({TIME: slice(t - 1, t + 2), **pos}).values.astype(np.float32)
        )
        before, filled, after = (
            np.float32(e[x]) for x in ("before", "filled", "after")
        )
        if not np.array_equal(
            vals, np.array([before, filled, after], dtype=np.float32)
        ):
            err(
                f"{tag}: stored values at the times before, at and after "
                f"{e['time']} differ from the attribute"
            )
        elif filled != _fill_mean(before, after):
            err(f"{tag}: filled value is not the mean of before and after")
    for name, n in counts.items():
        if n > MAX_FILLED_PER_VARIABLE:
            err(
                f"{name}: {n} filled values, more than the {MAX_FILLED_PER_VARIABLE} "
                "the fill rule allows"
            )
    report.info.append(
        f"{len(entries)} filled values ("
        + ", ".join(f"{n} {v}" for v, n in sorted(counts.items()))
        + ")"
    )


def store_attrs(
    *,
    vertical_coordinate: str,
    source_dataset: str,
    source_access: str,
    producer_version: str,
    producer_commit: str,
    processing: str,
    compression: str,
    domain: str,
    flux_averaging_seconds: int | None = None,
    flux_accumulation_seconds: int | None = None,
) -> dict[str, str]:
    """The store-level attributes for a ``glide`` store, as strings."""
    attrs = {
        "glide_format": FORMAT_NAME,
        "glide_format_version": FORMAT_VERSION,
        "glide_format_definition": (
            f"mrghg/glide docs/met_schema.md at commit {GLIDE_SCHEMA_COMMIT}"
        ),
        "glide_vertical_coordinate": vertical_coordinate,
        "source_dataset": source_dataset,
        "source_access": source_access,
        "producer": "met-bazarr",
        "producer_version": producer_version,
        "producer_commit": producer_commit,
        "processing": processing,
        "compression": compression,
        "domain": domain,
    }
    if flux_averaging_seconds is not None:
        attrs["glide_flux_averaging_seconds"] = str(int(flux_averaging_seconds))
    if flux_accumulation_seconds is not None:
        attrs["glide_flux_accumulation_seconds"] = str(int(flux_accumulation_seconds))
    return attrs
