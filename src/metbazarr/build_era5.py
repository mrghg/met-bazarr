"""Build a ``glide`` store from ERA5 on ARCO, in the same three steps as the UM
build (:mod:`metbazarr.build`): ``create`` the store, ``fill`` ranges of times
(separate processes may fill disjoint ranges), ``finish`` (shared with the UM
build: every time written, the format's fill rule, validation).

Recipe ``source`` keys::

    source:
      type: era5_arco
      model_level_store: gs://...   # optional; ARCO's by default
      surface_store: gs://...       # optional; ARCO's by default
      anonymous: true               # optional
      request_timeout_s: 120        # optional; seconds before a request is retried
      read_attempts: 5              # optional; tries at reading one time
      retry_backoff_s: 60           # optional; pause before a retry, doubling

The period must be whole hours (ERA5 is hourly).
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import dask.array as da
import numpy as np
import xarray as xr
import zarr

from metbazarr.formats import glide
from metbazarr.provenance import producer_commit, producer_version
from metbazarr.recipe import Recipe
from metbazarr.sources import era5_arco as arco

INTERVAL_HOURS = 1
LEVEL = arco.LEVEL
DIMS_3D = (glide.TIME, LEVEL, glide.LAT, glide.LON)
DIMS_2D = (glide.TIME, glide.LAT, glide.LON)
#: Variables labelled as period variables (format 2.0), and how.
PERIODS = {
    "surface_sensible_heat_flux": "sum",
    "friction_velocity": "mean",
}


@dataclass
class Plan:
    source: arco.ArcoSource
    crop: arco.Crop
    levels: np.ndarray
    times: list[datetime]


def source_from(recipe: Recipe) -> arco.ArcoSource:
    src = recipe.source
    return arco.ArcoSource(
        model_level_store=src.get("model_level_store", arco.MODEL_LEVEL_STORE),
        surface_store=src.get("surface_store", arco.SURFACE_STORE),
        anonymous=bool(src.get("anonymous", True)),
        request_timeout_s=float(src.get("request_timeout_s", 120.0)),
        read_attempts=int(src.get("read_attempts", 5)),
        retry_backoff_s=float(src.get("retry_backoff_s", 60.0)),
    )


def plan(recipe: Recipe) -> Plan:
    source = source_from(recipe)
    lat, lon, levels = source.grid()
    crop = arco.crop_for_box(lat, lon, recipe.domain)
    return Plan(source, crop, levels, recipe.times(INTERVAL_HOURS))


def describe(p: Plan, recipe: Recipe) -> str:
    return (
        f"{recipe.domain.name}: {p.crop.ny} x {p.crop.nx} ERA5 points, lat "
        f"{p.crop.latitudes[0]}..{p.crop.latitudes[-1]}, lon {p.crop.longitudes[0]}.."
        f"{p.crop.longitudes[-1]}; {p.levels.size} levels; {len(p.times)} times "
        f"{p.times[0]} .. {p.times[-1]}; output {recipe.output}"
    )


def _encoding(recipe: Recipe, nz: int, ny: int, nx: int) -> dict:
    ty, tx, lev = min(recipe.tile, ny), min(recipe.tile, nx), glide.level_chunk(nz)
    compressors = (
        zarr.codecs.BloscCodec(
            cname=recipe.codec, clevel=recipe.level, shuffle="shuffle"
        ),
    )
    enc = {}
    for name in glide.REQUIRED:
        three_d = name in glide.THREE_D or name == glide.GEOPOTENTIAL
        enc[name] = {
            "chunks": (1, lev, ty, tx) if three_d else (1, ty, tx),
            "compressors": compressors,
            "dtype": "float32",
            "_FillValue": np.float32(np.nan),
        }
    return enc


def create(recipe: Recipe, *, overwrite: bool = False) -> Path:
    """Create the store: coordinates, attributes, empty arrays (NaN)."""
    p = plan(recipe)
    out = recipe.output
    if out.exists() and not overwrite:
        raise FileExistsError(f"{out} exists; pass overwrite to replace it")
    t0 = _time.time()
    nt, nz, ny, nx = len(p.times), p.levels.size, p.crop.ny, p.crop.nx
    print(f"[create] {describe(p, recipe)}")

    coords = {
        glide.TIME: (
            glide.TIME,
            np.array([np.datetime64(t, "ns") for t in p.times]),
            {"standard_name": "time"},
        ),
        LEVEL: (
            LEVEL,
            p.levels,
            {"long_name": "ERA5 model (hybrid) level number", "positive": "down"},
        ),
        glide.LAT: (
            glide.LAT,
            p.crop.latitudes.astype(np.float32),
            {"units": "degrees_north", "standard_name": "latitude"},
        ),
        glide.LON: (
            glide.LON,
            p.crop.longitudes.astype(np.float32),
            {"units": "degrees_east", "standard_name": "longitude"},
        ),
    }
    data_vars = {}
    for name in glide.REQUIRED:
        three_d = name in glide.THREE_D or name == glide.GEOPOTENTIAL
        shape, dims, chunks = (
            ((nt, nz, ny, nx), DIMS_3D, (1, nz, ny, nx))
            if three_d
            else ((nt, ny, nx), DIMS_2D, (1, ny, nx))
        )
        data_vars[name] = (
            dims,
            da.full(shape, np.nan, dtype=np.float32, chunks=chunks),
        )
    ds = xr.Dataset(data_vars, coords=coords)
    units = p.source.units()
    for name in glide.REQUIRED:
        ds[name].attrs["units"] = units[name]
    for name, kind in PERIODS.items():
        ds[name].attrs.update(glide.period_attrs(kind, arco.ACCUMULATION_SECONDS))

    ds.attrs = glide.store_attrs(
        vertical_coordinate="model_level",
        source_dataset=p.source.source_dataset(nz),
        source_access=p.source.source_access(),
        producer_version=producer_version(),
        producer_commit=producer_commit(),
        processing=" | ".join(f"({k}) {s}" for k, s in enumerate(arco.PROCESSING, 1)),
        compression=(
            f"lossless: Blosc {recipe.codec} level {recipe.level} with byte shuffle on "
            "float32 (Zarr v3); no scale/offset, no bit-rounding"
        ),
        domain=recipe.domain.name,
        flux_accumulation_seconds=arco.ACCUMULATION_SECONDS,
    )
    ds.attrs["recipe"] = Path(recipe.path).name
    # The full recipe, so the store says exactly how it was built wherever the
    # recipe file is kept (decision 0008).
    ds.attrs["recipe_text"] = Path(recipe.path).read_text()
    ds.attrs["domain_box"] = (
        f"lon {recipe.domain.lon_min}..{recipe.domain.lon_max}, "
        f"lat {recipe.domain.lat_min}..{recipe.domain.lat_max}"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    ds.to_zarr(
        out,
        mode="w" if overwrite else "w-",
        compute=False,
        consolidated=True,
        zarr_format=3,
        encoding=_encoding(recipe, nz, ny, nx),
    )
    print(f"[create] wrote {out} ({_time.time() - t0:.0f} s)")
    return out


def fill(
    recipe: Recipe,
    indices: range | None = None,
    *,
    allow_commit_mismatch: bool = False,
) -> None:
    """Read and write the times ``indices`` (all if None) into the store."""
    p = plan(recipe)
    ds = xr.open_zarr(recipe.output, consolidated=True)
    commit = producer_commit()
    if ds.attrs.get("producer_commit") != commit and not allow_commit_mismatch:
        raise RuntimeError(
            f"store was created by commit {ds.attrs.get('producer_commit')}, this code "
            f"is {commit}: recreate the store, or fill with the code that created it"
        )
    want = np.array([np.datetime64(t, "ns") for t in p.times])
    if not np.array_equal(ds[glide.TIME].values, want):
        raise RuntimeError("store times differ from the recipe's period")
    if not (
        np.array_equal(ds[glide.LAT].values, p.crop.latitudes.astype(np.float32))
        and np.array_equal(ds[glide.LON].values, p.crop.longitudes.astype(np.float32))
        and np.array_equal(ds[LEVEL].values, p.levels)
    ):
        raise RuntimeError("store grid differs from the recipe's domain")
    indices = range(len(p.times)) if indices is None else indices
    for i in indices:
        t0 = _time.time()
        when = p.times[i]
        fields = p.source.read_time_retrying(when, p.crop)
        out = xr.Dataset(
            {
                name: (DIMS_3D if arr.ndim == 3 else DIMS_2D, arr[None])
                for name, arr in fields.items()
            }
        )
        out.to_zarr(recipe.output, region={glide.TIME: slice(i, i + 1)}, mode="r+")
        print(
            f"[fill] {i:4d} {when:%Y-%m-%d %H:%M} written ({_time.time() - t0:.1f} s)",
            flush=True,
        )
