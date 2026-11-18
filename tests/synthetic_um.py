"""A small synthetic UM archive with the structure of NAME's ``UMG_Mk10PT``.

No Met Office data: every value comes from the analytic functions below, so
tests can check the converter's output exactly. What it copies from the real
archive is structure only:

- ENDGame C grid: scalar points at ((i + 1/2) dlon, -90 + (j + 1/2) dlat),
  u at (i dlon, scalar lat), v at (scalar lon, -90 + j dlat), one more v row;
- latitude bands, the middle band split in longitude, neighbouring partitions
  overlapping by one row or column;
- heights z = a + b * orography (PP vertical code 65, a in blev, b in bhlev),
  rho levels interleaved below theta levels, the top theta level above the top
  rho level;
- one ``_I_`` file per time: instantaneous fields valid at the time (analysis
  at 00/06/12/18Z, T+3 forecast otherwise) and 3-h means (lbproc 128) over
  the interval ending at the time; extra fields the converter must skip;
- topography in its own partitioned files (STASH 0/33).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np

NLON, NLAT = 64, 48
DLON, DLAT = 360.0 / NLON, 180.0 / NLAT
A_TOP = 5000.0
A_THETA = np.array([20.0, 60.0, 150.0, 400.0, 1000.0, 3000.0, 8000.0, 20000.0])
A_RHO = np.array([10.0, 40.0, 100.0, 275.0, 700.0, 2000.0, 5500.0, 14000.0])
NZ = A_THETA.size
MDI = -1073741824.0
FILE_PATTERN = "MO{time:%Y%m%d%H%M}.SYN_I_L8PT{part}.pp"
TOPOG_PATTERN = "TopogSYN_PT{part}.pp"

# Partitions: (first scalar row, last scalar row, first column, column count).
# Rows 0..47 south to north; the middle band is split in two longitude halves
# with one overlapping column each side; bands overlap by one row.
PARTITIONS = {
    1: (35, 47, 0, NLON),
    2: (12, 35, 47, 34),  # columns 47..63, 0..16 (wraps through 0 degrees)
    3: (12, 35, 15, 34),  # columns 15..48
    4: (0, 12, 0, NLON),
}

STASH = {
    "u": (0, 2),
    "v": (0, 3),
    "w": (0, 150),
    "t": (16, 4),
    "q": (0, 10),
    "p_theta": (0, 408),
    "ps": (0, 409),
    "blh": (0, 25),
    "shf": (3, 217),
    "taux": (3, 219),
    "tauy": (3, 220),
    "pmsl": (16, 222),  # a field the converter does not read
    "orog": (0, 33),
}


def b_of(a: np.ndarray) -> np.ndarray:
    """b coefficient: (1 - a / A_TOP)**2 below A_TOP, 0 above."""
    return np.where(a < A_TOP, (1.0 - a / A_TOP) ** 2, 0.0)


B_THETA, B_RHO = b_of(A_THETA), b_of(A_RHO)


def wrap180(lon: np.ndarray) -> np.ndarray:
    return (np.asarray(lon) + 180.0) % 360.0 - 180.0


# --- analytic fields; lon in degrees (-180..180 frame), lat degrees, z metres ---


def orography(lon, lat):
    lon = wrap180(lon)
    return 2000.0 * np.exp(-((lon - 10.0) ** 2 + (lat - 46.0) ** 2) / 60.0)


def u_true(lon, lat, z, k):
    return 5.0 + 0.05 * wrap180(lon) + 0.1 * lat + 0.002 * z + 0.5 * k


def v_true(lon, lat, z, k):
    return -3.0 + 0.02 * wrap180(lon) + 0.2 * lat + 0.001 * z - 0.25 * k


def t_true(lon, lat, z, k):
    return 288.0 - 0.0065 * np.minimum(z, 11000.0) - 0.3 * np.abs(lat - 20.0) + 0.1 * k


def q_true(lon, lat, z, k):
    return 0.01 * np.exp(-z / 2000.0) * (1.0 + 0.001 * k)


def w_true(lon, lat, z, k):
    return (
        0.01
        * np.sin(np.radians(wrap180(lon)))
        * np.cos(np.radians(lat))
        * (1 + z / 1e4)
    )


def ps_true(lon, lat, k):
    h = orography(lon, lat)
    return 101325.0 * np.exp(-9.80665 * h / (287.05 * 280.0)) - 200.0 * k + 5.0 * lat


def blh_true(lon, lat, k):
    return 600.0 + 5.0 * np.abs(lat) + 50.0 * k


def shf_up_true(lon, lat, k):
    """Positive-up flux: strong daytime-like heating west of 20 E."""
    return np.where(wrap180(lon) < 20.0, 350.0, -40.0) + 0.0 * lat + 10.0 * k


def taux_true(lon, lat, k):
    return 0.10 + 0.002 * wrap180(lon) + 0.001 * lat + 0.01 * k


def tauy_true(lon, lat, k):
    return 0.05 + 0.001 * wrap180(lon) + 0.002 * lat


# --- grids -------------------------------------------------------------------

OFFSETS = {"scalar": (0.5, 0.5), "u": (0.0, 0.5), "v": (0.5, 0.0)}
GRID_OF = {"u": "u", "taux": "u", "v": "v", "tauy": "v"}


def points(kind: str, part: int):
    """(lon0, lat0, nrow, ncol, lons[ncol], lats[nrow]) of a partition field."""
    r0, r1, c0, nc = PARTITIONS[part]
    lon_off, lat_off = OFFSETS[kind]
    nrow = r1 - r0 + 1 + (1 if kind == "v" else 0)
    lons = (c0 + np.arange(nc) + lon_off) * DLON
    lats = -90.0 + (r0 + np.arange(nrow) + lat_off) * DLAT
    return lons[0], lats[0], nrow, nc, lons, lats


def _pp_field(
    name, data, lon0, lat0, *, t1, t2, lbtim, lbft, lbproc, lbvc, lblev, blev, bhlev
):
    import iris.fileformats.pp as pp

    f = pp.PPField3(header=tuple([0] * 45 + [0.0] * 19))
    f.t1, f.t2 = t1, t2
    f.lbtim, f.lbft, f.lbproc = lbtim, lbft, lbproc
    f.lbcode, f.lbpack, f.lbrel = 1, 0, 3
    f.lbrow, f.lbnpt = data.shape
    f.lbvc, f.lblev, f.blev, f.bhlev = lbvc, lblev, float(blev), float(bhlev)
    section, item = STASH[name]
    f.lbuser = [1, 0, 0, section * 1000 + item, 0, 0, 1]
    f.bplat, f.bplon = 90.0, 0.0
    f.bdx, f.bdy = DLON, DLAT
    f.bzx, f.bzy = lon0 - DLON, lat0 - DLAT
    f.bmdi, f.bmks = MDI, 1.0
    f.data = np.ascontiguousarray(data, dtype=np.float32)
    return f


@dataclass
class SyntheticArchive:
    met_dir: Path
    topography: str  # pattern with {part}
    file_pattern: str
    times: list[dt.datetime]


def _punch(data, name, part, k, lev, missing):
    """Set the planted missing values that fall in this partition field to MDI.
    ``missing`` items are (time index, field, level index or None, global row,
    global column), indices on the field's own grid."""
    r0, _, c0, _ = PARTITIONS[part]
    for mk, mname, mlev, row, col in missing:
        if (mk, mname, mlev) != (k, name, lev):
            continue
        lr, lc = row - r0, (col - c0) % NLON
        if 0 <= lr < data.shape[0] and 0 <= lc < data.shape[1]:
            data[lr, lc] = MDI


def write_archive(
    root: Path,
    times: list[dt.datetime],
    *,
    corrupt_overlap: bool = False,
    missing: tuple = (),
) -> SyntheticArchive:
    """Write topography and met files for ``times`` under ``root``, with MDI at
    the points listed in ``missing`` (see :func:`_punch`)."""
    root.mkdir(parents=True, exist_ok=True)
    for part in PARTITIONS:
        lon0, lat0, nrow, ncol, lons, lats = points("scalar", part)
        h = orography(lons[None, :], lats[:, None])
        f = _pp_field(
            "orog", h, lon0, lat0, t1=dt.datetime(2017, 1, 1), t2=dt.datetime(2017, 1, 1),
            lbtim=0, lbft=0, lbproc=0, lbvc=129, lblev=9999, blev=0.0, bhlev=0.0,
        )  # fmt: skip
        with open(root / TOPOG_PATTERN.format(part=part), "wb") as fh:
            f.save(fh)

    for k, when in enumerate(times):
        analysis = when.hour % 6 == 0
        ref = when if analysis else when - dt.timedelta(hours=3)
        inst = dict(t1=when, t2=ref, lbtim=11, lbft=0 if analysis else 3, lbproc=0)
        mean = dict(
            t1=when - dt.timedelta(hours=3), t2=when, lbtim=121, lbft=3, lbproc=128
        )
        for part in PARTITIONS:
            fields = []
            for name in ("u", "v", "w", "t", "q", "p_theta"):
                kind = GRID_OF.get(name, "scalar")
                lon0, lat0, nrow, ncol, lons, lats = points(kind, part)
                # heights use the orography at the field's own points
                h = orography(lons[None, :], lats[:, None])
                a, b = (A_RHO, B_RHO) if name in ("u", "v") else (A_THETA, B_THETA)
                fn = {"u": u_true, "v": v_true, "w": w_true, "t": t_true, "q": q_true,
                      "p_theta": lambda lo, la, z, k: 1e5 * np.exp(-z / 8000.0)}[name]  # fmt: skip
                for lev in range(NZ):
                    z = a[lev] + b[lev] * h
                    data = fn(lons[None, :], lats[:, None], z, k)
                    _punch(data, name, part, k, lev, missing)
                    fields.append(_pp_field(
                        name, data, lon0, lat0, **inst, lbvc=65, lblev=lev + 1,
                        blev=a[lev], bhlev=b[lev],
                    ))  # fmt: skip
            for name, fn, kw in (
                ("ps", ps_true, inst),
                ("blh", blh_true, inst),
                ("pmsl", ps_true, inst),
                ("shf", shf_up_true, mean),
                ("taux", taux_true, mean),
                ("tauy", tauy_true, mean),
            ):
                kind = GRID_OF.get(name, "scalar")
                lon0, lat0, nrow, ncol, lons, lats = points(kind, part)
                data = fn(lons[None, :], lats[:, None], k) * np.ones((nrow, ncol))
                if corrupt_overlap and name == "ps" and part == 2:
                    data[:, -1] += 1.0  # last column overlaps partition 3
                _punch(data, name, part, k, None, missing)
                fields.append(_pp_field(
                    name, data, lon0, lat0, **kw, lbvc=129, lblev=9999, blev=0.0, bhlev=0.0,
                ))  # fmt: skip
            with open(root / FILE_PATTERN.format(time=when, part=part), "wb") as fh:
                for f in fields:
                    f.save(fh)
    return SyntheticArchive(
        met_dir=root,
        topography=str(root / TOPOG_PATTERN),
        file_pattern=FILE_PATTERN,
        times=list(times),
    )
