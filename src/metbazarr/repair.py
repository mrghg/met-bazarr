"""Repairs to stores already built, recorded in the store (decision 0009).

A repair recomputes a variable from fields already in the store, with no
download, so a store built by an earlier release can meet a rule that release
did not apply. Each repair is recorded in the store's ``glide_repairs``
attribute (what, when, met-bazarr version and commit, and how much the values
changed) and appended to ``processing``. The validator holds a repair's commit
to the same rule as the producer's.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import xarray as xr
import zarr

from metbazarr.formats.glide import GRAVITY_M_S2
from metbazarr.provenance import producer_commit, producer_version, utc_now
from metbazarr.sources import era5_arco as arco

REPAIRS_ATTR = "glide_repairs"
ERA5_SURFACE_GEOPOTENTIAL = "era5-surface-geopotential"

_DESCRIPTION = (
    "geopotential_at_surface replaced by geopotential at hybrid 137 - alpha * "
    "287.0597 * T * (1 + 0.6078 q) at hybrid 137 (alpha = 1 - b/(1-b) ln(1/b), "
    "b = 0.997630), so the surface lies under the model levels (met-bazarr "
    "decision 0009)"
)


def repairs(path: str | Path) -> list[dict]:
    """The repairs recorded in a store."""
    group = zarr.open_group(str(path), mode="r")
    return json.loads(group.attrs.get(REPAIRS_ATTR, "[]"))


def repair_era5_surface_geopotential(
    path: str | Path, *, block: int = 24, dry_run: bool = False
) -> dict:
    """Derive a surface geopotential consistent with the model levels of an
    ERA5 store built before decision 0009, and write it in place.

    Refuses a store that is not ERA5 on model levels down to hybrid 137, or that
    has had this repair already. Returns the change in metres of height and the
    share of columns whose lowest level lay below the old surface.
    """
    path = Path(path)
    ds = xr.open_zarr(path)
    attrs = ds.attrs
    if not str(attrs.get("source_dataset", "")).startswith("ERA5"):
        raise ValueError(f"{path}: not an ERA5 store (source_dataset)")
    if (
        attrs.get("glide_vertical_coordinate") != "model_level"
        or "hybrid" not in ds.dims
    ):
        raise ValueError(f"{path}: not on ERA5 model (hybrid) levels")
    levels = ds["hybrid"].values
    lowest = int(np.argmax(levels))
    if int(levels[lowest]) != arco.LOWEST_LEVEL:
        raise ValueError(
            f"{path}: lowest level is {levels[lowest]}, not {arco.LOWEST_LEVEL}"
        )
    if any(r.get("repair") == ERA5_SURFACE_GEOPOTENTIAL for r in repairs(path)):
        raise ValueError(f"{path}: already repaired ({ERA5_SURFACE_GEOPOTENTIAL})")

    zs_dims = ds["geopotential_at_surface"].dims
    if zs_dims[0] != "time":
        raise ValueError(
            f"{path}: geopotential_at_surface has dims {zs_dims}, expected time first"
        )
    nt = ds.sizes["time"]
    max_change = 0.0
    samples: list[np.ndarray] = []
    below_before = []
    for start in range(0, nt, block):
        sl = slice(start, min(start + block, nt))
        sub = ds.isel(time=sl, hybrid=lowest)
        z1 = sub["geopotential"].values
        new = arco.surface_geopotential_from_lowest_level(
            z1, sub["temperature"].values, sub["specific_humidity"].values
        ).astype(np.float32)
        old = sub["geopotential_at_surface"].values.astype(np.float64)
        change = np.abs(new.astype(np.float64) - old) / GRAVITY_M_S2
        max_change = max(max_change, float(np.nanmax(change)))
        samples.append(change[0].ravel())
        below_before.append(float(np.mean(z1[0] < old[0])))
        if not dry_run:
            xr.Dataset({"geopotential_at_surface": (zs_dims, new)}).to_zarr(
                path, region={"time": sl}, mode="r+"
            )
    sample = np.concatenate(samples)
    result = {
        "repair": ERA5_SURFACE_GEOPOTENTIAL,
        "description": _DESCRIPTION,
        "date": utc_now(),
        "producer_version": producer_version(),
        "producer_commit": producer_commit(),
        "change_m": {
            "median": round(float(np.nanmedian(sample)), 2),
            "p99": round(float(np.nanpercentile(sample, 99)), 2),
            "max": round(max_change, 2),
        },
        "lowest_level_below_old_surface_fraction": round(
            float(np.mean(below_before)), 4
        ),
    }
    if not dry_run:
        group = zarr.open_group(str(path), mode="r+")
        entries = json.loads(group.attrs.get(REPAIRS_ATTR, "[]")) + [result]
        processing = str(group.attrs.get("processing", ""))
        step = processing.count(" | ") + 2 if processing else 1
        note = f"({step}) repair {ERA5_SURFACE_GEOPOTENTIAL}, met-bazarr {result['producer_version']}: {_DESCRIPTION}"
        group.attrs.update(
            {
                REPAIRS_ATTR: json.dumps(entries),
                "processing": f"{processing} | {note}" if processing else note,
            }
        )
        zarr.consolidate_metadata(str(path))
    return result
