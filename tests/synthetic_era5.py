"""Small stores shaped like ARCO ERA5's, for testing the ERA5 source.

Two Zarr stores, as on Google Cloud: a model-level one (u, v, omega, T, q,
geopotential on ``hybrid`` levels) and a surface one (boundary-layer height,
surface pressure, surface geopotential, accumulated heat flux and stresses).
Same variable names, units, dimension order and conventions as ARCO: latitude
90..-90, longitude 0..360, hybrid levels 1 (top) .. NZ (bottom), hourly.
The fields are analytic, so a test can recompute any value.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

G = 9.80665
R_D = 287.05
STEP = 5.0
LAT = np.arange(90.0, -90.0 - 1e-9, -STEP).astype(np.float32)
LON = np.arange(0.0, 360.0, STEP).astype(np.float32)
NZ = 6
#: Level numbers, top first; the lowest is ERA5's 137, which the surface
#: geopotential derivation requires (met-bazarr decision 0009).
HYBRID = np.array([1, 50, 90, 114, 130, 137], dtype=np.float32)
#: Height (m) of each hybrid level above the ground, top first.
Z_AGL = np.array([30000.0, 12000.0, 5000.0, 1500.0, 300.0, 10.0])
TIMES = np.array("2019-01-08T00", dtype="datetime64[ns]") + np.arange(
    6
) * np.timedelta64(1, "h")


def wrap180(lon):
    return (np.asarray(lon, np.float64) + 180.0) % 360.0 - 180.0


def orography(lon, lat):
    return 1500.0 * np.exp(-((wrap180(lon) - 10.0) ** 2 + (lat - 45.0) ** 2) / 200.0)


def fields(k_time: int):
    """All fields at time index ``k_time`` on the global grid (float64)."""
    lon2, lat2 = np.meshgrid(LON.astype(np.float64), LAT.astype(np.float64))
    h = orography(lon2, lat2)
    z = Z_AGL[:, None, None] + h  # height above sea level, [nz, ny, nx]
    t = 288.0 - 0.0065 * np.minimum(z, 11000.0) - 0.2 * np.abs(lat2) + 0.1 * k_time
    q = 0.01 * np.exp(-z / 2000.0)
    ps = 101325.0 * np.exp(-G * h / (R_D * 280.0)) + 10.0 * k_time
    # Positive down, as ERA5: daytime heating (negative) over one half.
    shf_rate = np.where(wrap180(lon2) < 0, -250.0, 25.0) + k_time
    return {
        "u_component_of_wind": 5.0 + 0.05 * wrap180(lon2) + 0.002 * z + k_time,
        "v_component_of_wind": -3.0 + 0.1 * lat2 + 0.001 * z - k_time,
        "vertical_velocity": 0.1 * np.sin(np.radians(lon2)) + 0.0 * z,
        "temperature": t,
        "specific_humidity": q,
        "geopotential": G * z,
        "boundary_layer_height": 600.0 + 2.0 * np.abs(lat2) + 10.0 * k_time,
        "surface_pressure": ps,
        "geopotential_at_surface": G * h,
        "surface_sensible_heat_flux": shf_rate * 3600.0,
        "eastward_turbulent_surface_stress": (0.1 + 0.001 * lat2) * 3600.0,
        "northward_turbulent_surface_stress": (-0.05 + 0.0005 * wrap180(lon2)) * 3600.0,
        "friction_velocity": np.full_like(lat2, 0.123),  # zust: must NOT be used
    }


UNITS = {
    "u_component_of_wind": "m s**-1",
    "v_component_of_wind": "m s**-1",
    "vertical_velocity": "Pa s**-1",
    "temperature": "K",
    "specific_humidity": "kg kg**-1",
    "geopotential": "m**2 s**-2",
    "boundary_layer_height": "m",
    "surface_pressure": "Pa",
    "geopotential_at_surface": "m**2 s**-2",
    "surface_sensible_heat_flux": "J m**-2",
    "eastward_turbulent_surface_stress": "N m**-2 s",
    "northward_turbulent_surface_stress": "N m**-2 s",
    "friction_velocity": "m s**-1",
}
MODEL_LEVEL = (
    "u_component_of_wind",
    "v_component_of_wind",
    "vertical_velocity",
    "temperature",
    "specific_humidity",
    "geopotential",
)


def write_stores(root, nan_at=None):
    """Write the two stores under ``root``; return (model_level, surface) paths.

    ``nan_at``: optional (variable, time index, lat index, lon index) to set to
    NaN in the source, as ARCO's heat flux is at one cell on 2018-12-28 21:00.
    """
    per_time = [fields(k) for k in range(TIMES.size)]
    stack = {n: np.stack([f[n] for f in per_time]) for n in per_time[0]}
    if nan_at is not None:
        name, k, j, i = nan_at
        stack[name][k, j, i] = np.nan
    coords = {"time": TIMES, "latitude": LAT, "longitude": LON}
    ml = xr.Dataset(
        {
            n: (
                ("time", "hybrid", "latitude", "longitude"),
                stack[n].astype(np.float32),
            )
            for n in MODEL_LEVEL
        },
        coords={**coords, "hybrid": HYBRID},
    )
    sf = xr.Dataset(
        {
            n: (("time", "latitude", "longitude"), stack[n].astype(np.float32))
            for n in stack
            if n not in MODEL_LEVEL
        },
        coords=coords,
    )
    for ds in (ml, sf):
        for n in ds.data_vars:
            ds[n].attrs["units"] = UNITS[n]
    ml_path, sf_path = root / "arco-ml.zarr", root / "arco-sfc.zarr"
    ml.to_zarr(ml_path, mode="w", consolidated=True, zarr_format=3)
    sf.to_zarr(sf_path, mode="w", consolidated=True, zarr_format=3)
    return ml_path, sf_path
