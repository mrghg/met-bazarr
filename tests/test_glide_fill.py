"""The format 1.0 fill rule for isolated missing values, and the validator's
check of ``glide_filled_values``."""

import json

import numpy as np
import pytest
import xarray as xr
import zarr

from metbazarr.formats import glide
from test_glide_validate import make_store


def holes(*cells):
    """A mutate function that sets each (variable, index tuple) to NaN."""

    def mutate(ds):
        for name, idx in cells:
            ds[name].values[idx] = np.nan
        return ds

    return mutate


def set_attrs(path, **attrs):
    group = zarr.open_group(str(path), mode="r+")
    group.attrs.update(attrs)
    zarr.consolidate_metadata(str(path))


def test_isolated_values_filled_and_recorded(tmp_path):
    path = make_store(
        tmp_path / "s.zarr",
        holes(
            ("specific_humidity", (2, 3, 4, 5)),
            ("surface_sensible_heat_flux", (1, 0, 0)),
        ),
    )
    raw = xr.open_zarr(path).load()
    added = glide.fill_isolated_missing(path)
    assert len(added) == 2
    ds = xr.open_zarr(path, consolidated=True)
    q = ds["specific_humidity"].values
    assert q[2, 3, 4, 5] == np.float32(
        (np.float64(raw.specific_humidity.values[1, 3, 4, 5])
         + raw.specific_humidity.values[3, 3, 4, 5]) / 2
    )  # fmt: skip
    assert np.isfinite(ds["surface_sensible_heat_flux"].values).all()
    entries = json.loads(ds.attrs[glide.FILLED_VALUES_ATTR])
    q_entry = next(e for e in entries if e["variable"] == "specific_humidity")
    assert set(q_entry) == {
        "variable", "time", "latitude", "longitude", "level", "before", "after", "filled"
    }  # fmt: skip
    assert q_entry["level"] == 4 and q_entry["time"] == "2019-01-08T06:00:00Z"
    shf_entry = next(e for e in entries if e["variable"] != "specific_humidity")
    assert "level" not in shf_entry
    assert glide.FILLED_VALUES_ATTR in ds.attrs["processing"]
    report = glide.validate(path)
    assert report.ok, report.format()
    assert any("2 filled values" in m for m in report.info)
    # Idempotent: nothing left to fill, the record is kept.
    assert glide.fill_isolated_missing(path) == []
    assert len(json.loads(xr.open_zarr(path).attrs[glide.FILLED_VALUES_ATTR])) == 2


def test_nothing_missing_adds_no_attribute(tmp_path):
    path = make_store(tmp_path / "s.zarr")
    assert glide.fill_isolated_missing(path) == []
    assert glide.FILLED_VALUES_ATTR not in xr.open_zarr(path).attrs


@pytest.mark.parametrize(
    "cells, expected",
    [
        ((("temperature", (0, 1, 2, 3)),), "at the first time"),
        ((("boundary_layer_height", (3, 2, 3)),), "at the last time"),
        (
            (("surface_pressure", (1, 2, 3)), ("surface_pressure", (2, 2, 3))),
            "longer than one timestep",
        ),
        (
            tuple(("friction_velocity", (1, j, 0)) for j in range(10))
            + (("friction_velocity", (2, 0, 1)),),
            "more than the 10",
        ),
        ((("geopotential", (0, 1, 1)),), "never filled"),
    ],
    ids=["first", "last", "long-gap", "too-many", "geopotential"],
)
def test_unfillable_cases_raise_and_write_nothing(tmp_path, cells, expected):
    cells = cells + (("specific_humidity", (2, 3, 4, 5)),)  # fillable on its own
    path = make_store(tmp_path / "s.zarr", holes(*cells))
    with pytest.raises(glide.FillError, match=expected):
        glide.fill_isolated_missing(path)
    ds = xr.open_zarr(path)
    assert glide.FILLED_VALUES_ATTR not in ds.attrs
    assert np.isnan(ds["specific_humidity"].values[2, 3, 4, 5])


@pytest.fixture
def filled(tmp_path):
    path = make_store(
        tmp_path / "s.zarr",
        holes(("temperature", (1, 2, 3, 4)), ("friction_velocity", (2, 5, 6))),
    )
    glide.fill_isolated_missing(path)
    return path


def _tamper(path, change):
    entries = json.loads(xr.open_zarr(path).attrs[glide.FILLED_VALUES_ATTR])
    set_attrs(path, **{glide.FILLED_VALUES_ATTR: json.dumps(change(entries))})


def _set(entries, **kw):
    entries[0].update(kw)
    return entries


@pytest.mark.parametrize(
    "change, expected",
    [
        (lambda e: _set(e, filled=e[0]["filled"] + 1.0), "differ from the attribute"),
        (lambda e: _set(e, variable="geopotential"), "may not be filled"),
        (lambda e: [{k: v for k, v in e[0].items() if k != "before"}] + e[1:], "keys"),
        (lambda e: _set(e, time="2019-01-08T00:00:00Z"), "first or last time"),
        (lambda e: _set(e, latitude=0.0), "not in the store"),
        (lambda e: e + [e[0]], "listed twice"),
        (lambda e: [], "present but empty"),
    ],
    ids=["value", "variable", "keys", "first-time", "position", "duplicate", "empty"],
)
def test_validator_checks_filled_values(filled, change, expected):
    assert glide.validate(filled).ok
    _tamper(filled, change)
    report = glide.validate(filled)
    assert not report.ok and expected in " | ".join(report.errors), report.format()


def test_validator_checks_fill_attribute_format_and_note(filled):
    set_attrs(filled, processing="none")
    assert "does not note the fill" in " | ".join(glide.validate(filled).errors)
    set_attrs(filled, **{glide.FILLED_VALUES_ATTR: "not json"})
    assert "not valid JSON" in " | ".join(glide.validate(filled).errors)


def test_validator_counts_fills_per_variable(filled):
    def eleven(entries):
        base = next(e for e in entries if e["variable"] == "friction_velocity")
        return [dict(base, longitude=base["longitude"] + i) for i in range(11)]

    _tamper(filled, eleven)
    assert "more than the 10" in " | ".join(glide.validate(filled).errors)
