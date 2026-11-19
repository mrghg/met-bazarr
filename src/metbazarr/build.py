"""Build a ``glide`` store from a recipe, in three steps.

The steps below are for Met Office UM files. ERA5 recipes (source types
``era5_arco`` and ``era5_ecmwf``) are handed to :mod:`metbazarr.build_era5` by
:func:`plan`, :func:`create` and :func:`fill`; :func:`finish` is shared.


1. :func:`create` writes the store's coordinates, attributes and the
   time-invariant fields, and declares the time-varying arrays (unwritten
   chunks read as NaN).
2. :func:`fill` converts and writes a range of times. Each time is its own
   chunk, so separate processes (Slurm array tasks) can fill disjoint ranges
   of one store at once.
3. :func:`finish` checks that every time was written and validates the store.

The commit recorded at :func:`create` must match the code that fills, so a
store is never written by two versions of the converter.
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
from metbazarr.sources import um

LEVEL = "model_level"
DIMS_3D = (glide.TIME, LEVEL, glide.LAT, glide.LON)
DIMS_2D = (glide.TIME, glide.LAT, glide.LON)


@dataclass
class Plan:
    """What a recipe resolves to: files, grid, crop, partitions and times."""

    archive: um.UMArchive
    crop: um.Crop
    parts: list[int]
    times: list[datetime]


#: Source types other than the UM, by the module that builds them.
ERA5_TYPES = ("era5_arco", "era5_ecmwf")


def _era5(recipe: Recipe):
    """The ERA5 builder if the recipe is ERA5, else None."""
    kind = recipe.source.get("type")
    if kind == "era5_ecmwf":
        from metbazarr.sources import era5_ecmwf

        era5_ecmwf.not_implemented()
    if kind == "era5_arco":
        from metbazarr import build_era5

        return build_era5
    return None


def interval_hours(recipe: Recipe) -> int:
    """The source's time step, in hours."""
    builder = _era5(recipe)
    return builder.INTERVAL_HOURS if builder else archive_from(recipe).interval_hours


def describe(recipe: Recipe) -> str:
    """One line on what the recipe resolves to (``--step plan``)."""
    builder = _era5(recipe)
    if builder:
        return builder.describe(builder.plan(recipe), recipe)
    p = plan(recipe)
    return (
        f"{recipe.domain.name}: {p.crop.ny} x {p.crop.nx} points, lat "
        f"{p.crop.latitudes[0]}..{p.crop.latitudes[-1]}, lon {p.crop.longitudes[0]}.."
        f"{p.crop.longitudes[-1]}; partitions {p.parts}; {len(p.times)} times "
        f"{p.times[0]} .. {p.times[-1]}; output {recipe.output}"
    )


def archive_from(recipe: Recipe) -> um.UMArchive:
    src = recipe.source
    if src.get("type") != "um_global":
        raise ValueError(f"unsupported source type {src.get('type')!r}")
    return um.UMArchive(
        met_dir=Path(src["met_dir"]),
        file_pattern=src["file_pattern"],
        topography=src["topography"],
        partitions=tuple(src.get("partitions", range(1, 15))),
        interval_hours=int(src.get("interval_hours", 3)),
        mean_hours=int(src.get("mean_hours", 3)),
    )


def plan(recipe: Recipe) -> Plan:
    if recipe.format != glide.FORMAT_NAME:
        raise ValueError(f"unsupported format {recipe.format!r}")
    builder = _era5(recipe)
    if builder:
        return builder.plan(recipe)
    archive = archive_from(recipe)
    crop = um.crop_for_box(archive.grid(), recipe.domain)
    parts = archive.partitions_for(crop)
    return Plan(archive, crop, parts, recipe.times(archive.interval_hours))


def _compressors(recipe: Recipe):
    return (
        zarr.codecs.BloscCodec(
            cname=recipe.codec, clevel=recipe.level, shuffle="shuffle"
        ),
    )


def _encoding(recipe: Recipe, nz: int, ny: int, nx: int) -> dict:
    tile_y, tile_x, lev = (
        min(recipe.tile, ny),
        min(recipe.tile, nx),
        glide.level_chunk(nz),
    )
    chunks = {
        "3d": (1, lev, tile_y, tile_x),
        "2d": (1, tile_y, tile_x),
        glide.GEOPOTENTIAL: (lev, tile_y, tile_x),
        glide.SURFACE_GEOPOTENTIAL: (tile_y, tile_x),
    }
    enc = {}
    for name in glide.REQUIRED:
        key = "3d" if name in glide.THREE_D else "2d" if name in glide.SURFACE else name
        enc[name] = {
            "chunks": chunks[key],
            "compressors": _compressors(recipe),
            "dtype": "float32",
            "_FillValue": np.float32(np.nan),
        }
    return enc


def _source_dataset(recipe: Recipe, nz: int) -> str:
    series = recipe.source.get("series", "unknown series")
    text = (
        f"Met Office global Unified Model (ENDGame), NAME met archive series {series}: "
        f"{nz} levels, partitioned PP files every 3 h, WGDOS-packed at source "
        "(the packing precision of each field is in its PP header)"
    )
    if recipe.source.get("description"):
        text += f"; {recipe.source['description']}"
    return text


def create(recipe: Recipe, *, overwrite: bool = False) -> Path:
    """Create the store: coordinates, attributes, static fields, empty arrays."""
    builder = _era5(recipe)
    if builder:
        return builder.create(recipe, overwrite=overwrite)
    p = plan(recipe)
    out = recipe.output
    if out.exists() and not overwrite:
        raise FileExistsError(f"{out} exists; pass overwrite to replace it")

    t0 = _time.time()
    orog = p.archive.orography(p.crop, p.parts)
    _, levels = p.archive.read_time(p.times[0], p.crop, p.parts, fields=("u", "t"))
    nz, ny, nx = levels.a_theta.size, p.crop.ny, p.crop.nx
    print(
        f"[create] {recipe.domain.name}: {ny} x {nx} points, {nz} levels, "
        f"{len(p.times)} times, partitions {p.parts} ({_time.time() - t0:.0f} s)"
    )

    times = np.array([np.datetime64(t, "ns") for t in p.times])
    coords = {
        glide.TIME: (glide.TIME, times, {"standard_name": "time"}),
        LEVEL: (
            LEVEL,
            np.arange(1, nz + 1, dtype=np.int32),
            {"long_name": "UM theta level number", "positive": "up"},
        ),
        glide.LAT: (
            glide.LAT,
            p.crop.latitudes,
            {"units": "degrees_north", "standard_name": "latitude"},
        ),
        glide.LON: (
            glide.LON,
            p.crop.longitudes,
            {"units": "degrees_east", "standard_name": "longitude"},
        ),
        "level_height": (
            LEVEL,
            levels.a_theta,
            {"units": "m", "long_name": "a in z = a + b * orography (theta levels)"},
        ),
        "level_sigma": (
            LEVEL,
            levels.b_theta,
            {"units": "1", "long_name": "b in z = a + b * orography (theta levels)"},
        ),
    }
    nt = len(p.times)
    data_vars = {}
    for name in glide.THREE_D:
        data_vars[name] = (
            DIMS_3D,
            da.full((nt, nz, ny, nx), np.nan, dtype=np.float32, chunks=(1, nz, ny, nx)),
        )
    for name in glide.SURFACE:
        data_vars[name] = (
            DIMS_2D,
            da.full((nt, ny, nx), np.nan, dtype=np.float32, chunks=(1, ny, nx)),
        )
    data_vars[glide.GEOPOTENTIAL] = (
        (LEVEL, glide.LAT, glide.LON),
        um.geopotential(levels, orog).astype(np.float32),
    )
    data_vars[glide.SURFACE_GEOPOTENTIAL] = (
        (glide.LAT, glide.LON),
        (glide.GRAVITY_M_S2 * orog).astype(np.float32),
    )
    ds = xr.Dataset(data_vars, coords=coords)
    for name in glide.REQUIRED:
        ds[name].attrs["units"] = glide.CANONICAL_UNITS[name]
    # Means over the interval ending at each timestamp (format 2.0, decision 0005):
    # the heat flux, and u* derived from the mean stresses.
    mean_seconds = 3600 * p.archive.mean_hours
    for name in um.MEAN_VARIABLES:
        ds[name].attrs.update(glide.period_attrs("mean", mean_seconds))

    ds.attrs = glide.store_attrs(
        vertical_coordinate="model_level",
        source_dataset=_source_dataset(recipe, nz),
        source_access=um.source_access(p.archive),
        producer_version=producer_version(),
        producer_commit=producer_commit(),
        processing=" | ".join(f"({k}) {s}" for k, s in enumerate(um.PROCESSING, 1)),
        compression=(
            f"lossless: Blosc {recipe.codec} level {recipe.level} with byte shuffle on "
            "float32 (Zarr v3); no scale/offset, no bit-rounding"
        ),
        domain=recipe.domain.name,
        flux_averaging_seconds=3600 * p.archive.mean_hours,
    )
    ds.attrs["recipe"] = Path(recipe.path).name
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


def _open_for_fill(recipe: Recipe, p: Plan, allow_commit_mismatch: bool) -> xr.Dataset:
    ds = xr.open_zarr(recipe.output, consolidated=True)
    commit = producer_commit()
    if ds.attrs.get("producer_commit") != commit and not allow_commit_mismatch:
        raise RuntimeError(
            f"store was created by commit {ds.attrs.get('producer_commit')}, this code is "
            f"{commit}: recreate the store, or fill with the code that created it"
        )
    want = np.array([np.datetime64(t, "ns") for t in p.times])
    if not np.array_equal(ds[glide.TIME].values, want):
        raise RuntimeError("store times differ from the recipe's period")
    if not (
        np.array_equal(ds[glide.LAT].values, p.crop.latitudes)
        and np.array_equal(ds[glide.LON].values, p.crop.longitudes)
    ):
        raise RuntimeError("store grid differs from the recipe's domain")
    return ds


def fill(
    recipe: Recipe,
    indices: range | None = None,
    *,
    allow_commit_mismatch: bool = False,
) -> None:
    """Convert and write the times ``indices`` (all if None) into the store."""
    builder = _era5(recipe)
    if builder:
        return builder.fill(
            recipe, indices, allow_commit_mismatch=allow_commit_mismatch
        )
    p = plan(recipe)
    ds = _open_for_fill(recipe, p, allow_commit_mismatch)
    store_levels = (ds["level_height"].values, ds["level_sigma"].values)
    orog_src = p.archive.orography(p.crop, p.parts)
    stored_phis = ds[glide.SURFACE_GEOPOTENTIAL].values
    if not np.array_equal(
        stored_phis, (glide.GRAVITY_M_S2 * orog_src).astype(np.float32)
    ):
        raise RuntimeError("orography in the store differs from the topography files")
    indices = range(len(p.times)) if indices is None else indices
    for i in indices:
        t0 = _time.time()
        when = p.times[i]
        native, levels = p.archive.read_time(when, p.crop, p.parts)
        if not (
            np.array_equal(levels.a_theta, store_levels[0])
            and np.array_equal(levels.b_theta, store_levels[1])
        ):
            raise um.UMError(f"{when}: theta levels differ from those in the store")
        fields = um.convert(native, levels, orog_src)
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


def missing_times(recipe: Recipe) -> list[int]:
    """Indices of times not yet written (surface pressure NaN everywhere; a
    written time holds at most a few missing source values)."""
    ds = xr.open_zarr(recipe.output, consolidated=True)
    ps = ds["surface_pressure"]
    bad = np.isnan(ps).all(dim=(glide.LAT, glide.LON)).compute().values
    return [int(i) for i in np.flatnonzero(bad)]


def finish(recipe: Recipe, *, full_scan: bool = True, validation_input: bool = False):
    """Check every time was written, apply the format's fill rule to isolated
    missing source values (or stop, listing them), then validate the store."""
    missing = missing_times(recipe)
    if missing:
        raise RuntimeError(
            f"{len(missing)} times not written, e.g. indices {missing[:10]}"
        )
    filled = glide.fill_isolated_missing(recipe.output)
    for e in filled:
        level = f", level {e['level']}" if "level" in e else ""
        print(
            f"[finish] filled {e['variable']} at {e['time']}, "
            f"{e['latitude']:.4f} N, {e['longitude']:.4f} E{level}: "
            f"{e['before']:g}, [{e['filled']:g}], {e['after']:g}",
            flush=True,
        )
    return glide.validate(
        recipe.output, full_scan=full_scan, validation_input=validation_input
    )
