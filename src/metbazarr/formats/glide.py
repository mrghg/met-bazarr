"""The ``glide`` format: GLIDE's meteorology input contract.

The authoritative definition is ``docs/met_schema.md`` in the GLIDE repository
(https://github.com/mrghg/glide). This module implements **format version 1.0**
as it stood at GLIDE commit :data:`GLIDE_SCHEMA_COMMIT`. When that page changes,
this module's version changes with it.

What lives here:

- the variable table (names, dimensions, accepted units);
- the store attributes (format tag and provenance);
- encoding and chunking for writing;
- :func:`validate`, which checks a store against everything the page
  prescribes, plus plausibility checks that catch the silent mistakes the page
  warns about (geopotential height for geopotential, heat flux with the wrong
  sign, untagged model levels).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import xarray as xr

FORMAT_NAME = "glide"
FORMAT_VERSION = "1.0"
#: GLIDE commit whose ``docs/met_schema.md`` defines format 1.0 (branch
#: ``docs/met-schema-v1``, PR #23).
GLIDE_SCHEMA_COMMIT = "8f4aa9957a209e43ea1be6fd0222f0ab1a358863"

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

#: Store attributes every met-bazarr ``glide`` store carries (format 1.0,
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
    """Check a store against ``glide`` format 1.0.

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
            info(f"{time.size} times, every {int(steps[0])} s, {time[0]} to {time[-1]}")
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

    if report.errors:
        return report

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
