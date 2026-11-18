"""Met Office global Unified Model (ENDGame) fields from NAME's met archive.

Reads the partitioned PP files that NAME uses (series ``UMG_Mk10PT``: 59 levels,
14 latitude-longitude partitions, an ``_I_`` file per 3-hourly time) and
converts them to one grid, as agreed for GLIDE task B14
(``docs/decisions/0003-um-to-glide-conversion.md``):

- **Target grid:** the scalar (cell-centre) points horizontally and the theta
  levels vertically, where T, q, w, surface pressure, boundary-layer depth,
  heat flux and orography already are.
- **u, v:** mean of the two neighbouring u (v) points onto the scalar point,
  then linear in height from rho levels k, k+1 onto theta level k; the top
  theta level, above the top rho level, takes the top rho value.
- **Geopotential:** g0 * (a + b * orography) on theta levels (time-invariant).
- **Friction velocity:** sqrt(|tau| / rho) with the 3-h mean surface stresses
  destaggered like u and v, and rho = ps / (R_d T_v) from T and q on theta
  level 1.
- **Sensible heat flux:** negated (UM positive up, GLIDE positive down); a mean
  over the 3 h ending at the timestamp.

The numerical steps are plain numpy functions so that they can be tested on
synthetic arrays; :class:`UMArchive` does the file handling. ``iris`` (with
``mo_pack`` for WGDOS-packed files) is imported only when files are read.
"""

from __future__ import annotations

import math
import socket
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from metbazarr.formats.glide import (
    GRAVITY_M_S2,
    MAX_FILLED_PER_VARIABLE,
    R_DRY_AIR_J_KG_K,
    TV_COEFF,
)

#: STASH codes read from the instantaneous (``_I_``) files.
STASH = {
    "u": "m01s00i002",
    "v": "m01s00i003",
    "w": "m01s00i150",
    "t": "m01s16i004",
    "q": "m01s00i010",
    "p_theta": "m01s00i408",
    "ps": "m01s00i409",
    "blh": "m01s00i025",
    "shf": "m01s03i217",
    "taux": "m01s03i219",
    "tauy": "m01s03i220",
    "orog": "m01s00i033",
}
THREE_D_RHO = ("u", "v")
THREE_D_THETA = ("w", "t", "q", "p_theta")
MEANS = ("shf", "taux", "tauy")

#: Where each field sits on the C grid: (longitude offset, latitude offset) of
#: its points, in grid lengths, relative to i * dlon and -90 + j * dlat.
STAGGER = {
    "scalar": (0.5, 0.5),
    "u": (0.0, 0.5),
    "v": (0.5, 0.0),
}
FIELD_GRID = {
    "u": "u",
    "taux": "u",
    "v": "v",
    "tauy": "v",
}  # everything else is on the scalar grid

#: Meaning of the PP vertical coordinate code 65: z = a + b * orography, with
#: a in ``blev`` and b in ``bhlev``.
LBVC_HEIGHT = 65
LBPROC_MEAN = 128


class UMError(RuntimeError):
    """The UM files are not what the converter expects."""


# ---------------------------------------------------------------------------
# Domain and grid
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Box:
    """A latitude-longitude box. Longitudes in any frame with west < east."""

    name: str
    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float

    def __post_init__(self) -> None:
        if not self.lon_min < self.lon_max:
            raise ValueError("lon_min must be less than lon_max")
        if not -90 <= self.lat_min < self.lat_max <= 90:
            raise ValueError("need -90 <= lat_min < lat_max <= 90")
        if self.lon_max - self.lon_min > 360:
            raise ValueError("box is wider than 360 degrees")


@dataclass(frozen=True)
class GlobalGrid:
    """A regular global ENDGame grid: ``nlon`` x ``nlat`` scalar points."""

    dlon: float
    dlat: float

    @property
    def nlon(self) -> int:
        return round(360.0 / self.dlon)

    @property
    def nlat(self) -> int:
        return round(180.0 / self.dlat)


@dataclass(frozen=True)
class Crop:
    """The scalar points kept: one point on or beyond each edge of a box.

    ``j0..j1`` are global scalar row indices (south to north); ``i0..i1`` are
    *unwrapped* global column indices (take them modulo ``nlon`` for the file
    index), so that the longitudes come out in the box's own frame.
    """

    grid: GlobalGrid
    j0: int
    j1: int
    i0: int
    i1: int

    @property
    def ny(self) -> int:
        return self.j1 - self.j0 + 1

    @property
    def nx(self) -> int:
        return self.i1 - self.i0 + 1

    @property
    def latitudes(self) -> np.ndarray:
        return -90.0 + (np.arange(self.j0, self.j1 + 1) + 0.5) * self.grid.dlat

    @property
    def longitudes(self) -> np.ndarray:
        lon = (np.arange(self.i0, self.i1 + 1) + 0.5) * self.grid.dlon
        if lon[0] < -180.0 or lon[-1] > 360.0 or (lon[0] < 0.0 and lon[-1] > 180.0):
            raise UMError(
                f"crop longitudes {lon[0]}..{lon[-1]} fit neither -180..180 nor 0..360"
            )
        return lon

    def rows(self, kind: str) -> np.ndarray:
        """Global row indices of grid ``kind`` needed to fill the crop."""
        extra = 1 if kind == "v" else 0  # scalar j lies between v rows j and j + 1
        return np.arange(self.j0, self.j1 + 1 + extra)

    def cols(self, kind: str) -> np.ndarray:
        """Global (wrapped) column indices of grid ``kind`` needed."""
        extra = 1 if kind == "u" else 0  # scalar i lies between u cols i and i + 1
        return np.arange(self.i0, self.i1 + 1 + extra) % self.grid.nlon


def crop_for_box(grid: GlobalGrid, box: Box) -> Crop:
    """The scalar points covering ``box`` with one point on or beyond each edge."""

    def index(coord: float, origin: float, step: float) -> float:
        # Fractional index of a coordinate on the scalar grid, rounded so that
        # a point lying on the edge is recognised as on it.
        return round((coord - origin) / step - 0.5, 9)

    j0 = math.floor(index(box.lat_min, -90.0, grid.dlat))
    j1 = math.ceil(index(box.lat_max, -90.0, grid.dlat))
    i0 = math.floor(index(box.lon_min, 0.0, grid.dlon))
    i1 = math.ceil(index(box.lon_max, 0.0, grid.dlon))
    j0, j1 = max(j0, 0), min(j1, grid.nlat - 1)
    return Crop(grid, j0, j1, i0, i1)


# ---------------------------------------------------------------------------
# Numerical steps (pure numpy)
# ---------------------------------------------------------------------------


def destagger_u(u: np.ndarray) -> np.ndarray:
    """u-point field ``[..., ny, nx + 1]`` to scalar points ``[..., ny, nx]``:
    the mean of the two u points either side in longitude."""
    return 0.5 * (u[..., :-1] + u[..., 1:])


def destagger_v(v: np.ndarray) -> np.ndarray:
    """v-point field ``[..., ny + 1, nx]`` to scalar points ``[..., ny, nx]``:
    the mean of the two v rows either side in latitude."""
    return 0.5 * (v[..., :-1, :] + v[..., 1:, :])


def level_heights(a: np.ndarray, b: np.ndarray, orography: np.ndarray) -> np.ndarray:
    """Heights above sea level ``z = a + b * h``, ``[nz, ny, nx]`` in metres."""
    return a[:, None, None] + b[:, None, None] * orography[None, :, :]


def rho_to_theta(
    x_rho: np.ndarray, z_rho: np.ndarray, z_theta: np.ndarray
) -> np.ndarray:
    """Interpolate a rho-level field onto theta levels, linear in height.

    Theta level k lies between rho levels k and k + 1 (0-based), except the top
    theta level, which lies above the top rho level and takes its value.

    Args:
        x_rho: ``[nz, ny, nx]`` field on rho levels.
        z_rho: ``[nz, ny, nx]`` rho-level heights (m).
        z_theta: ``[nz, ny, nx]`` theta-level heights (m).

    Raises:
        UMError: if any theta level is not bracketed as expected.
    """
    nz = x_rho.shape[0]
    if z_rho.shape[0] != nz or z_theta.shape[0] != nz:
        raise UMError("rho and theta level counts differ")
    weight = (z_theta[:-1] - z_rho[:-1]) / (z_rho[1:] - z_rho[:-1])
    if not (np.all(weight >= 0.0) and np.all(weight <= 1.0)):
        raise UMError("a theta level does not lie between rho levels k and k+1")
    if np.any(z_theta[-1] < z_rho[-1]):
        raise UMError("top theta level is below the top rho level")
    out = np.empty(x_rho.shape, dtype=np.float64)
    out[:-1] = x_rho[:-1] + weight * (x_rho[1:] - x_rho[:-1])
    out[-1] = x_rho[-1]
    return out


def air_density(ps: np.ndarray, t: np.ndarray, q: np.ndarray) -> np.ndarray:
    """rho = ps / (R_d T_v), T_v = T (1 + 0.6077 q), in kg m-3."""
    return ps / (R_DRY_AIR_J_KG_K * t * (1.0 + TV_COEFF * q))


def friction_velocity(
    taux: np.ndarray, tauy: np.ndarray, rho: np.ndarray
) -> np.ndarray:
    """u* = sqrt(|tau| / rho), m s-1, from stress components on scalar points."""
    return np.sqrt(np.hypot(taux, tauy) / rho)


@dataclass(frozen=True)
class Levels:
    """The ``z = a + b * h`` definition of the rho and theta levels."""

    a_rho: np.ndarray
    b_rho: np.ndarray
    a_theta: np.ndarray
    b_theta: np.ndarray

    def same_as(self, other: Levels) -> bool:
        return all(
            np.array_equal(getattr(self, n), getattr(other, n))
            for n in ("a_rho", "b_rho", "a_theta", "b_theta")
        )


def geopotential(levels: Levels, orography: np.ndarray) -> np.ndarray:
    """Geopotential of the theta levels, g0 * (a + b * h), ``[nz, ny, nx]``."""
    return GRAVITY_M_S2 * level_heights(levels.a_theta, levels.b_theta, orography)


def convert(
    native: dict[str, np.ndarray], levels: Levels, orography: np.ndarray
) -> dict:
    """Convert one time of native UM fields to GLIDE variables on the target grid.

    Args:
        native: arrays on their native grids, cropped as :class:`Crop` requires:
            ``u`` ``[nz, ny, nx+1]``, ``v`` ``[nz, ny+1, nx]``, ``w``/``t``/``q``
            ``[nz, ny, nx]``, ``ps``/``blh``/``shf`` ``[ny, nx]``, ``taux``
            ``[ny, nx+1]``, ``tauy`` ``[ny+1, nx]``.
        levels: The level definition.
        orography: ``[ny, nx]`` surface height (m) on scalar points.

    Returns:
        GLIDE variable name -> float32 array.
    """
    f64 = {k: np.asarray(v, dtype=np.float64) for k, v in native.items()}
    h = np.asarray(orography, dtype=np.float64)
    z_rho = level_heights(levels.a_rho, levels.b_rho, h)
    z_theta = level_heights(levels.a_theta, levels.b_theta, h)
    u = rho_to_theta(destagger_u(f64["u"]), z_rho, z_theta)
    v = rho_to_theta(destagger_v(f64["v"]), z_rho, z_theta)
    rho = air_density(f64["ps"], f64["t"][0], f64["q"][0])
    ustar = friction_velocity(destagger_u(f64["taux"]), destagger_v(f64["tauy"]), rho)
    out = {
        "u_component_of_wind": u,
        "v_component_of_wind": v,
        "vertical_velocity": f64["w"],
        "temperature": f64["t"],
        "specific_humidity": f64["q"],
        "boundary_layer_height": f64["blh"],
        "surface_pressure": f64["ps"],
        "friction_velocity": ustar,
        "surface_sensible_heat_flux": -f64["shf"],
    }
    return {k: v.astype(np.float32) for k, v in out.items()}


PROCESSING = [
    "Read UM fields from partitioned PP files with iris (WGDOS unpacked by mo_pack) "
    "and joined across partitions; values in partition overlaps checked identical.",
    "Cropped to the scalar (cell-centre) points covering the domain box with one "
    "point on or beyond each edge.",
    "Target grid: scalar points horizontally, theta levels vertically "
    "(model_level = theta level number 1..59).",
    "temperature = STASH 16/4; specific_humidity = 0/10; vertical_velocity = 0/150 "
    "(geometric w, m s-1); surface_pressure = 0/409; boundary_layer_height = 0/25: "
    "native on the target grid, unchanged.",
    "u_component_of_wind (0/2), v_component_of_wind (0/3): mean of the two "
    "neighbouring u (v) points onto the scalar point, then linear in height "
    "z = a + b*orography from rho levels k and k+1 onto theta level k; theta level "
    "59 (above rho level 59) takes the rho-59 value.",
    "geopotential = 9.80665 * (a_theta + b_theta * orography), orography = STASH "
    "0/33 from the series topography file; time-invariant, no time dimension.",
    "geopotential_at_surface = 9.80665 * orography.",
    "friction_velocity = sqrt(|tau|/rho): tau from the surface stresses 3/219 and "
    "3/220 (3-h means ending at the timestamp), each destaggered to scalar points "
    "as u and v; rho = surface_pressure / (287.05 * T * (1 + 0.6077 q)) with T, q "
    "on theta level 1 at the timestamp.",
    "surface_sensible_heat_flux = -(STASH 3/217): sign changed from the UM's "
    "positive-up to positive-down; a mean over the 3 h ending at the timestamp "
    "(glide_flux_averaging_seconds = 10800).",
    "Computed in float64, stored as float32. No interpolation in time.",
]


# ---------------------------------------------------------------------------
# File handling
# ---------------------------------------------------------------------------


def _iris_pp():
    try:
        import iris.fileformats.pp as pp
    except ImportError as exc:  # pragma: no cover - environment problem
        raise ImportError(
            "Reading UM files needs iris (and mo_pack for WGDOS-packed files): "
            "see docs/setup.md, 'Met Office UM on JASMIN'."
        ) from exc
    return pp


def _to_datetime(t) -> datetime:
    return datetime(t.year, t.month, t.day, t.hour, t.minute, t.second)


#: Most missing values one source field may hold: the fill rule's limit per
#: variable per store.
MAX_MISSING_PER_FIELD = MAX_FILLED_PER_VARIABLE


@dataclass
class _Mosaic:
    """Assembles a cropped array from partition fields, checking overlaps."""

    rows: np.ndarray  # global row indices wanted
    cols: np.ndarray  # global (wrapped) column indices wanted
    nlon: int
    data: np.ndarray = field(init=False)
    filled: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.data = np.full((self.rows.size, self.cols.size), np.nan, dtype=np.float64)
        self.filled = np.zeros(self.data.shape, dtype=bool)
        self._row_pos = {int(r): k for k, r in enumerate(self.rows)}
        self._col_pos = np.full(self.nlon, -1, dtype=np.int64)
        self._col_pos[self.cols] = np.arange(self.cols.size)

    def add(self, values: np.ndarray, row0: int, col0: int, label: str) -> None:
        nrow, ncol = values.shape
        frows = np.arange(row0, row0 + nrow)
        trows = np.array([self._row_pos.get(int(r), -1) for r in frows])
        tcols = self._col_pos[(col0 + np.arange(ncol)) % self.nlon]
        vr, vc = trows >= 0, tcols >= 0
        if not vr.any() or not vc.any():
            return
        block = values[np.ix_(vr, vc)]
        tr, tc = trows[vr], tcols[vc]
        already = self.filled[np.ix_(tr, tc)]
        if already.any():
            old = self.data[np.ix_(tr, tc)][already]
            if not np.array_equal(old, block[already], equal_nan=True):
                raise UMError(f"{label}: partitions disagree where they overlap")
        self.data[np.ix_(tr, tc)] = block
        self.filled[np.ix_(tr, tc)] = True

    def result(self, label: str) -> np.ndarray:
        if not self.filled.all():
            raise UMError(
                f"{label}: {int((~self.filled).sum())} crop points not in any partition"
            )
        return self.data


@dataclass
class UMArchive:
    """Partitioned UM files of one series, as NAME's met archive holds them.

    Args:
        met_dir: Folder of the met files.
        file_pattern: Name of one file, with ``{time}`` (a datetime) and
            ``{part}`` (partition number) fields.
        topography: Path of one topography file, with a ``{part}`` field.
        partitions: Partition numbers.
        interval_hours: Spacing of the files in time.
        mean_hours: Length of the averaging period of the mean fields.
    """

    met_dir: Path
    file_pattern: str
    topography: str
    partitions: Sequence[int] = tuple(range(1, 15))
    interval_hours: int = 3
    mean_hours: int = 3

    def met_file(self, time: datetime, part: int) -> Path:
        return Path(self.met_dir) / self.file_pattern.format(time=time, part=part)

    def topography_file(self, part: int) -> Path:
        return Path(self.topography.format(part=part))

    # -- geometry ----------------------------------------------------------

    def grid(self) -> GlobalGrid:
        """Grid spacing, from the first partition's topography header."""
        pp = _iris_pp()
        fld = next(iter(pp.load(str(self.topography_file(self.partitions[0])))))
        return GlobalGrid(dlon=float(fld.bdx), dlat=float(fld.bdy))

    def partitions_for(self, crop: Crop) -> list[int]:
        """Partitions whose scalar points touch the crop (with a 2-point margin)."""
        pp = _iris_pp()
        grid = crop.grid
        want_rows = set(range(crop.j0 - 2, crop.j1 + 3))
        want_cols = set((np.arange(crop.i0 - 2, crop.i1 + 3) % grid.nlon).tolist())
        parts = []
        for part in self.partitions:
            fld = next(iter(pp.load(str(self.topography_file(part)))))
            row0, col0 = _origin(fld, grid, "scalar")
            rows = set(range(row0, row0 + int(fld.lbrow)))
            cols = set(((col0 + np.arange(int(fld.lbnpt))) % grid.nlon).tolist())
            if rows & want_rows and cols & want_cols:
                parts.append(part)
        if not parts:
            raise UMError("no partition covers the domain")
        return parts

    # -- reading -----------------------------------------------------------

    def orography(self, crop: Crop, parts: Iterable[int]) -> np.ndarray:
        """Orography (m) on the crop's scalar points."""
        pp = _iris_pp()
        mosaic = _Mosaic(crop.rows("scalar"), crop.cols("scalar"), crop.grid.nlon)
        for part in parts:
            for fld in pp.load(str(self.topography_file(part))):
                if str(fld.stash) == STASH["orog"]:
                    _check_grid(fld, crop.grid, "scalar", "orography")
                    row0, col0 = _origin(fld, crop.grid, "scalar")
                    mosaic.add(
                        _values(fld, "orography", max_missing=0),
                        row0,
                        col0,
                        "orography",
                    )
        return mosaic.result("orography")

    def read_time(
        self,
        time: datetime,
        crop: Crop,
        parts: Iterable[int],
        fields: Sequence[str] = (
            "u",
            "v",
            "w",
            "t",
            "q",
            "ps",
            "blh",
            "shf",
            "taux",
            "tauy",
        ),
    ) -> tuple[dict[str, np.ndarray], Levels]:
        """Read one time's fields, cropped on their native grids.

        Returns:
            Field name -> array (3-D ``[nz, rows, cols]``, 2-D ``[rows, cols]``),
            and the level definition found in the headers.
        """
        pp = _iris_pp()
        by_stash = {STASH[n]: n for n in fields}
        mosaics: dict[str, dict[int, _Mosaic]] = {n: {} for n in fields}
        level_ab: dict[str, dict[int, tuple[float, float]]] = {n: {} for n in fields}
        for part in parts:
            path = self.met_file(time, part)
            if not path.exists():
                raise UMError(f"missing met file {path}")
            for fld in pp.load(str(path)):
                name = by_stash.get(str(fld.stash))
                if name is None:
                    continue
                label = f"{name} ({fld.stash}) in {path.name}"
                self._check_time(fld, time, name, label)
                kind = FIELD_GRID.get(name, "scalar")
                _check_grid(fld, crop.grid, kind, label)
                lev = int(fld.lblev) if name in THREE_D_RHO + THREE_D_THETA else 0
                if lev:
                    if int(fld.lbvc) != LBVC_HEIGHT:
                        raise UMError(
                            f"{label}: vertical coordinate code {fld.lbvc}, expected 65"
                        )
                    ab = (float(fld.blev), float(fld.bhlev))
                    if level_ab[name].setdefault(lev, ab) != ab:
                        raise UMError(
                            f"{label}: level {lev} defined differently across files"
                        )
                mosaic = mosaics[name].get(lev)
                if mosaic is None:
                    mosaic = _Mosaic(crop.rows(kind), crop.cols(kind), crop.grid.nlon)
                    mosaics[name][lev] = mosaic
                row0, col0 = _origin(fld, crop.grid, kind)
                mosaic.add(_values(fld, label), row0, col0, label)

        out: dict[str, np.ndarray] = {}
        for name in fields:
            levs = sorted(mosaics[name])
            if not levs:
                raise UMError(
                    f"{name} ({STASH[name]}) not found at {time:%Y-%m-%d %H:%M}"
                )
            if name in THREE_D_RHO + THREE_D_THETA:
                if levs != list(range(1, len(levs) + 1)):
                    raise UMError(f"{name}: levels {levs[0]}..{levs[-1]} are not 1..n")
                out[name] = np.stack([mosaics[name][k].result(name) for k in levs])
            else:
                out[name] = mosaics[name][0].result(name)
        levels = _levels_from(level_ab)
        return out, levels

    def _check_time(self, fld, time: datetime, name: str, label: str) -> None:
        t1, t2 = _to_datetime(fld.t1), _to_datetime(fld.t2)
        is_mean = int(fld.lbproc) == LBPROC_MEAN
        if name in MEANS:
            if not is_mean:
                raise UMError(
                    f"{label}: expected a time mean (lbproc 128), got {fld.lbproc}"
                )
            if t2 != time or t2 - t1 != timedelta(hours=self.mean_hours):
                raise UMError(
                    f"{label}: mean over {t1}..{t2}, expected the {self.mean_hours} h "
                    f"ending at {time}"
                )
        else:
            if int(fld.lbproc) != 0:
                raise UMError(
                    f"{label}: expected an instantaneous field, lbproc {fld.lbproc}"
                )
            if t1 != time:
                raise UMError(f"{label}: valid at {t1}, expected {time}")


def _values(fld, label: str, max_missing: int = MAX_MISSING_PER_FIELD) -> np.ndarray:
    """Field values as float64, missing data (the field's MDI) as NaN.

    A few missing values pass through as NaN, for the format's fill rule to
    deal with once every time is written (``metbazarr build --step finish``).
    More than ``max_missing`` in one field is more than the rule could ever
    fill, so it stops the conversion here.
    """
    data = np.ma.filled(np.ma.asarray(fld.data, dtype=np.float64), np.nan)
    data[data == float(fld.bmdi)] = np.nan
    n_missing = int(np.isnan(data).sum())
    if n_missing > max_missing:
        raise UMError(
            f"{label}: {n_missing} missing values"
            + (
                f", more than the {max_missing} the fill rule could fill"
                if max_missing
                else " (never filled)"
            )
        )
    return data


def _origin(fld, grid: GlobalGrid, kind: str) -> tuple[int, int]:
    """Global (row, column) index of a field's first point."""
    lon_off, lat_off = STAGGER[kind]
    lon0 = float(fld.bzx) + float(fld.bdx)
    lat0 = float(fld.bzy) + float(fld.bdy)
    col = round(lon0 / grid.dlon - lon_off) % grid.nlon
    row = round((lat0 + 90.0) / grid.dlat - lat_off)
    return row, col


def _check_grid(fld, grid: GlobalGrid, kind: str, label: str) -> None:
    if not (
        math.isclose(float(fld.bdx), grid.dlon, rel_tol=1e-6)
        and math.isclose(float(fld.bdy), grid.dlat, rel_tol=1e-6)
    ):
        raise UMError(
            f"{label}: grid spacing {fld.bdx} x {fld.bdy} differs from the series"
        )
    lon_off, lat_off = STAGGER[kind]
    lon0 = float(fld.bzx) + float(fld.bdx)
    lat0 = float(fld.bzy) + float(fld.bdy)
    fx = lon0 / grid.dlon - lon_off
    fy = (lat0 + 90.0) / grid.dlat - lat_off
    if abs(fx - round(fx)) > 1e-3 or abs(fy - round(fy)) > 1e-3:
        raise UMError(f"{label}: points are not where a {kind}-grid field's should be")


def _levels_from(level_ab: dict[str, dict[int, tuple[float, float]]]) -> Levels:
    def ab(name: str) -> tuple[np.ndarray, np.ndarray] | None:
        if not level_ab.get(name):
            return None
        pairs = [level_ab[name][k] for k in sorted(level_ab[name])]
        return np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])

    rho = [ab(n) for n in THREE_D_RHO if ab(n) is not None]
    theta = [ab(n) for n in THREE_D_THETA if ab(n) is not None]
    for group, label in ((rho, "rho"), (theta, "theta")):
        for other in group[1:]:
            if not (
                np.array_equal(group[0][0], other[0])
                and np.array_equal(group[0][1], other[1])
            ):
                raise UMError(
                    f"fields on {label} levels disagree about the level heights"
                )
    if not rho or not theta:
        return Levels(np.array([]), np.array([]), np.array([]), np.array([]))
    return Levels(rho[0][0], rho[0][1], theta[0][0], theta[0][1])


def source_access(archive: UMArchive) -> str:
    """Where the files were read from, by what, and when."""
    from metbazarr.provenance import utc_now

    try:
        import iris

        versions = f"iris {iris.__version__}"
        try:
            import mo_pack

            versions += f", mo_pack {getattr(mo_pack, '__version__', 'unknown')}"
        except ImportError:
            versions += ", no mo_pack"
    except ImportError:
        versions = "iris unavailable"
    return (
        f"{socket.getfqdn()}:{archive.met_dir} ({archive.file_pattern}); topography "
        f"{archive.topography}; read with {versions}; store created {utc_now()}"
    )
