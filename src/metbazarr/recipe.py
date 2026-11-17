"""Recipes: a YAML file that describes one store.

Example (``recipes/um/EUR-Jan.yaml``)::

    format: glide
    output: /work/scratch-pw5/USER/met-bazarr/EUR-Jan_UMG_Mk10PT.zarr
    domain: {name: EUR, lon_min: -30, lon_max: 40, lat_min: 32, lat_max: 72}
    period: {start: 2018-12-22T00:00, end: 2019-01-15T00:00}
    source:
      type: um_global
      series: UMG_Mk10PT
      met_dir: /gws/ssde/j25a/name/met_archive/Global/UMG_Mk10PT
      file_pattern: "MO{time:%Y%m%d%H%M}.UMG_Mk10_I_L59PT{part}.pp"
      topography: /gws/ssde/j25a/name/data/UMTopogData/TopogUMG_Mk10_PT{part}.pp
    compression: {codec: zstd, level: 5}
    chunks: {tile: 128}

``output`` may use ``{user}`` and environment variables (``$VAR``).
"""

from __future__ import annotations

import getpass
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from metbazarr.sources.um import Box

_TOP_KEYS = {"format", "output", "domain", "period", "source", "compression", "chunks"}


@dataclass(frozen=True)
class Recipe:
    path: Path
    format: str
    output: Path
    domain: Box
    start: datetime
    end: datetime
    source: dict[str, Any]
    codec: str = "zstd"
    level: int = 5
    tile: int = 128
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def times(self, interval_hours: int) -> list[datetime]:
        """Every source time from ``start`` to ``end`` inclusive."""
        step = timedelta(hours=interval_hours)
        if (self.end - self.start) % step:
            raise ValueError(
                f"period is not a whole number of {interval_hours} h steps"
            )
        n = (self.end - self.start) // step + 1
        return [self.start + k * step for k in range(n)]


def _datetime(value: Any, key: str) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"period.{key}: not an ISO date-time: {value!r}") from exc


def load_recipe(path: str | Path) -> Recipe:
    """Read and check a recipe file."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: a recipe is a mapping")
    unknown = set(raw) - _TOP_KEYS
    missing = {"format", "output", "domain", "period", "source"} - set(raw)
    if unknown:
        raise ValueError(f"{path}: unknown keys {sorted(unknown)}")
    if missing:
        raise ValueError(f"{path}: missing keys {sorted(missing)}")

    d = raw["domain"]
    box = Box(
        name=str(d["name"]),
        lon_min=float(d["lon_min"]),
        lon_max=float(d["lon_max"]),
        lat_min=float(d["lat_min"]),
        lat_max=float(d["lat_max"]),
    )
    start = _datetime(raw["period"]["start"], "start")
    end = _datetime(raw["period"]["end"], "end")
    if end < start:
        raise ValueError(f"{path}: period ends before it starts")
    output = os.path.expandvars(str(raw["output"]).format(user=getpass.getuser()))
    comp = raw.get("compression", {}) or {}
    chunks = raw.get("chunks", {}) or {}
    return Recipe(
        path=path,
        format=str(raw["format"]),
        output=Path(output),
        domain=box,
        start=start,
        end=end,
        source=dict(raw["source"]),
        codec=str(comp.get("codec", "zstd")),
        level=int(comp.get("level", 5)),
        tile=int(chunks.get("tile", 128)),
        raw=raw,
    )
