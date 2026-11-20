"""ERA5 from the Analysis-Ready, Cloud-Optimised copy on Google Cloud (ARCO).

This is the **ARCO workstream**: ERA5 read anonymously from the public Zarr
stores on Google Cloud Storage. ERA5 taken directly from ECMWF (MARS or the
Copernicus Climate Data Store) is a separate source, ``era5_ecmwf``
(:mod:`metbazarr.sources.era5_ecmwf`), so stores from the two can never be
mistaken for each other: they carry different ``source_dataset`` attributes and
different name suffixes (``_ERA5-ARCO`` and ``_ERA5-ECMWF``).

Two ARCO stores are read:

- the **model-level** store: u, v, omega, T, q and geopotential on ERA5's 137
  hybrid levels;
- the **surface** store (the unified pressure-level/surface store, used only for
  its surface fields): boundary-layer height, surface pressure, surface
  geopotential, and the hourly accumulated sensible heat flux and surface
  stresses.

Conversion (GLIDE format 2.0, met-bazarr decision 0006):

- every field except the friction velocity is copied unchanged (float32, ARCO's
  own units), cropped to the ERA5 grid points inside the domain box; this
  reproduces GLIDE's own downloader (``scripts/download_sample_cube.py``) value
  for value;
- **sensible heat flux**: ERA5's accumulation over the hour ending at the
  timestamp (J m-2), labelled ``time: sum``, 3600 s, with
  ``glide_flux_accumulation_seconds = 3600``;
- **friction velocity**: from the surface stresses, as NAME and FLEXPART derive
  it, not ERA5's own ``zust``: u* = sqrt(|tau| / rho), with tau the hourly
  accumulated stresses divided by 3600 s (the mean stress over the hour ending
  at the timestamp) and rho = ps / (R_d T (1 + 0.6077 q)) from T and q on the
  lowest model level at the timestamp. Labelled ``time: mean``, 3600 s.
"""

from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import xarray as xr

from metbazarr.formats.glide import R_DRY_AIR_J_KG_K, TV_COEFF

MODEL_LEVEL_STORE = "gs://gcp-public-data-arco-era5/ar/model-level-1h-0p25deg.zarr-v1"
SURFACE_STORE = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"

LEVEL = "hybrid"
#: GLIDE variable -> ARCO variable, model-level store.
MODEL_LEVEL_VARS = {
    "u_component_of_wind": "u_component_of_wind",
    "v_component_of_wind": "v_component_of_wind",
    "vertical_velocity": "vertical_velocity",
    "temperature": "temperature",
    "specific_humidity": "specific_humidity",
    "geopotential": "geopotential",
}
#: GLIDE variable -> ARCO variable, surface store (copied unchanged).
SURFACE_VARS = {
    "boundary_layer_height": "boundary_layer_height",
    "surface_pressure": "surface_pressure",
    "geopotential_at_surface": "geopotential_at_surface",
    "surface_sensible_heat_flux": "surface_sensible_heat_flux",
}
#: ARCO surface stresses, hourly accumulations (N m-2 s), for u*.
STRESS_VARS = (
    "eastward_turbulent_surface_stress",
    "northward_turbulent_surface_stress",
)

#: ERA5's accumulation period, and so the period of the heat flux and u*.
ACCUMULATION_SECONDS = 3600

PROCESSING = [
    "Read anonymously from ARCO ERA5 on Google Cloud Storage: 3-D fields from the "
    "model-level store, surface fields from the unified pressure-level/surface store.",
    "Cropped to the ERA5 grid points inside the domain box (edges included). "
    "Latitude kept north to south as in ARCO; longitude kept in 0..360 unless the "
    "box crosses 0 E, then given in -180..180 and ascending.",
    "u_component_of_wind, v_component_of_wind, vertical_velocity (omega, Pa s-1), "
    "temperature, specific_humidity, geopotential (time-varying), "
    "boundary_layer_height, surface_pressure, geopotential_at_surface: unchanged.",
    "surface_sensible_heat_flux: ERA5's accumulation over the hour ending at the "
    "timestamp (J m-2, positive down), unchanged; labelled cell_methods 'time: sum', "
    "glide_period_seconds 3600.",
    "friction_velocity = sqrt(|tau|/rho), not ERA5's zust: tau = hypot(ewss, nsss) / "
    "3600 s, the mean surface stress over the hour ending at the timestamp; rho = "
    "surface_pressure / (287.05 * T * (1 + 0.6077 q)) with T, q on the lowest model "
    "level (hybrid 137) at the timestamp. Labelled cell_methods 'time: mean', "
    "glide_period_seconds 3600.",
    "Computed in float64 where derived, stored as float32. No interpolation in time "
    "or space.",
]


class Era5ArcoError(RuntimeError):
    """The ARCO stores are not what the converter expects."""


@dataclass(frozen=True)
class Crop:
    """The ERA5 grid points of a domain box, and the coordinates written."""

    lat_index: np.ndarray
    lon_index: np.ndarray
    latitudes: np.ndarray
    longitudes: np.ndarray

    @property
    def ny(self) -> int:
        return self.lat_index.size

    @property
    def nx(self) -> int:
        return self.lon_index.size


def crop_for_box(lat: np.ndarray, lon: np.ndarray, box) -> Crop:
    """The grid points inside ``box`` (edges included, to 1e-6 degrees).

    ``lat`` and ``lon`` are ARCO's: latitude 90..-90, longitude 0..360. Latitude
    order is kept. Longitude is given in 0..360 if the selected points are a
    single ascending run there, and otherwise (the box crosses 0 E) in -180..180,
    ascending, as GLIDE's own downloader writes it.
    """
    eps = 1e-6
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)
    lat_index = np.flatnonzero((lat >= box.lat_min - eps) & (lat <= box.lat_max + eps))
    lon180 = (lon + 180.0) % 360.0 - 180.0
    lo = (box.lon_min + 180.0) % 360.0 - 180.0
    hi = (box.lon_max + 180.0) % 360.0 - 180.0
    if lo <= hi:
        inside = (lon180 >= lo - eps) & (lon180 <= hi + eps)
    else:  # box crosses the 180 E meridian
        inside = (lon180 >= lo - eps) | (lon180 <= hi + eps)
    lon_index = np.flatnonzero(inside)
    if lat_index.size == 0 or lon_index.size == 0:
        raise Era5ArcoError(f"no ERA5 grid points inside the box {box}")
    if np.all(np.diff(lon_index) == 1):
        out_lon = lon[lon_index]  # one ascending run in 0..360
    else:
        order = np.argsort(lon180[lon_index], kind="stable")
        lon_index = lon_index[order]
        out_lon = lon180[lon_index]
        if not np.all(np.diff(out_lon) > 0):
            raise Era5ArcoError("the box's longitudes do not form one ascending run")
    return Crop(lat_index, lon_index, lat[lat_index], out_lon)


def _runs(index: np.ndarray) -> list[slice]:
    """Split ascending-by-one runs of an index array into slices."""
    breaks = np.flatnonzero(np.diff(index) != 1) + 1
    return [slice(int(r[0]), int(r[-1]) + 1) for r in np.split(index, breaks)]


def _take(da: xr.DataArray, crop: Crop) -> np.ndarray:
    """``da`` (one time) on the crop's points, read by contiguous slices."""
    lat_runs, lon_runs = _runs(crop.lat_index), _runs(crop.lon_index)
    if len(lat_runs) != 1:
        raise Era5ArcoError("the crop's latitudes are not one contiguous run")
    parts = [
        da.isel(latitude=lat_runs[0], longitude=lon_slice).values
        for lon_slice in lon_runs
    ]
    return parts[0] if len(parts) == 1 else np.concatenate(parts, axis=-1)


def friction_velocity(
    ewss: np.ndarray,
    nsss: np.ndarray,
    ps: np.ndarray,
    t: np.ndarray,
    q: np.ndarray,
    period_seconds: int = ACCUMULATION_SECONDS,
) -> np.ndarray:
    """u* (m s-1) from accumulated surface stresses (N m-2 s) over
    ``period_seconds``, and the air density from surface pressure (Pa), T (K)
    and q (kg kg-1) at the lowest model level."""
    tau = np.hypot(np.asarray(ewss, np.float64), np.asarray(nsss, np.float64))
    tau /= float(period_seconds)
    rho = np.asarray(ps, np.float64) / (
        R_DRY_AIR_J_KG_K
        * np.asarray(t, np.float64)
        * (1.0 + TV_COEFF * np.asarray(q, np.float64))
    )
    return np.sqrt(tau / rho)


@dataclass
class ArcoSource:
    """The two ARCO stores, opened lazily."""

    model_level_store: str = MODEL_LEVEL_STORE
    surface_store: str = SURFACE_STORE
    anonymous: bool = True
    #: Variables read at once (13 in all).
    read_threads: int = 13
    #: Seconds before a Google Cloud request is abandoned and retried (gcsfs
    #: retries up to 6 times). Without it, a stalled request can hang a fill
    #: process indefinitely (seen 19-20 Nov 2026: three of eight processes
    #: stopped until the job's time limit).
    request_timeout_s: float = 120.0

    def __post_init__(self) -> None:
        self._ml: xr.Dataset | None = None
        self._sf: xr.Dataset | None = None

    def _open(self, uri: str) -> xr.Dataset:
        opts = None
        if uri.startswith("gs://"):
            opts = {"requests_timeout": self.request_timeout_s}
            if self.anonymous:
                opts["token"] = "anon"
        return xr.open_zarr(uri, consolidated=True, chunks=None, storage_options=opts)

    @property
    def model_levels(self) -> xr.Dataset:
        if self._ml is None:
            self._ml = self._open(self.model_level_store)
            missing = set(MODEL_LEVEL_VARS.values()) - set(self._ml.data_vars)
            if missing:
                raise Era5ArcoError(f"{self.model_level_store} lacks {sorted(missing)}")
        return self._ml

    @property
    def surface(self) -> xr.Dataset:
        if self._sf is None:
            self._sf = self._open(self.surface_store)
            missing = (set(SURFACE_VARS.values()) | set(STRESS_VARS)) - set(
                self._sf.data_vars
            )
            if missing:
                raise Era5ArcoError(f"{self.surface_store} lacks {sorted(missing)}")
        return self._sf

    def grid(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(latitude, longitude, hybrid level) of the model-level store, after
        checking the surface store has the same horizontal grid."""
        ml, sf = self.model_levels, self.surface
        lat, lon = ml["latitude"].values, ml["longitude"].values
        if not (
            np.array_equal(lat, sf["latitude"].values)
            and np.array_equal(lon, sf["longitude"].values)
        ):
            raise Era5ArcoError("the two ARCO stores are on different grids")
        return lat, lon, ml[LEVEL].values

    def units(self) -> dict[str, str]:
        """GLIDE variable -> units, as ARCO gives them (u* is derived)."""
        out = {
            g: str(self.model_levels[a].attrs.get("units", ""))
            for g, a in MODEL_LEVEL_VARS.items()
        }
        out |= {
            g: str(self.surface[a].attrs.get("units", ""))
            for g, a in SURFACE_VARS.items()
        }
        out["friction_velocity"] = "m s**-1"
        return out

    def read_time(self, when: datetime, crop: Crop) -> dict[str, np.ndarray]:
        """Every GLIDE variable at one time, cropped, as float32 arrays.

        The stores are opened without dask (``chunks=None``): building dask
        graphs over ARCO's whole 1900-2050 time axis costs far more than the
        read. Each variable is read by contiguous slices (two when the box
        crosses 0 E), and the variables are read in parallel threads
        (``read_threads``); memory stays near one source chunk per thread.
        """
        t = np.datetime64(when, "ns")
        jobs = {g: (self.model_levels, a) for g, a in MODEL_LEVEL_VARS.items()}
        jobs |= {g: (self.surface, a) for g, a in SURFACE_VARS.items()}
        jobs |= {a: (self.surface, a) for a in STRESS_VARS}
        with ThreadPoolExecutor(max_workers=self.read_threads) as pool:
            futures = {
                k: pool.submit(_take, ds[a].sel(time=t), crop)
                for k, (ds, a) in jobs.items()
            }
            out = {k: f.result() for k, f in futures.items()}
        stress = [out.pop(a) for a in STRESS_VARS]
        lowest = int(np.argmax(self.model_levels[LEVEL].values))  # hybrid 137
        out["friction_velocity"] = friction_velocity(
            stress[0],
            stress[1],
            out["surface_pressure"],
            out["temperature"][lowest],
            out["specific_humidity"][lowest],
        )
        return {k: np.asarray(v, dtype=np.float32) for k, v in out.items()}

    def source_dataset(self, n_levels: int) -> str:
        return (
            f"ERA5 hourly reanalysis (ECMWF), ARCO copy on Google Cloud: {n_levels} "
            f"model levels from {self.model_level_store}; surface fields from "
            f"{self.surface_store}"
        )

    def source_access(self) -> str:
        from metbazarr.provenance import utc_now

        try:
            import gcsfs

            via = f"gcsfs {gcsfs.__version__}"
        except ImportError:
            via = "local paths"
        anon = "anonymous " if self.anonymous else ""
        return (
            f"{anon}read via {via} on {socket.getfqdn()}; xarray {xr.__version__}; "
            f"store created {utc_now()}"
        )
