"""The ``glide`` validator: a conforming synthetic store passes, and each
deliberately broken one fails with a message naming the problem."""

import numpy as np
import pytest
import xarray as xr

from metbazarr.formats import glide

G = glide.GRAVITY_M_S2


def make_store(path, mutate=None, **attr_changes):
    """Write a small conforming model-level store, optionally broken by
    ``mutate(ds)`` and attribute changes (None deletes the attribute)."""
    nt, nz, ny, nx = 4, 6, 10, 12
    lat = np.linspace(40, 49, ny)
    lon = np.linspace(-5, 17, nx)
    lon2, lat2 = np.meshgrid(lon, lat)
    h = 2500.0 * np.exp(-((lon2 - 6) ** 2 + (lat2 - 45) ** 2) / 10.0)
    a = np.array([20.0, 100.0, 500.0, 2000.0, 8000.0, 26000.0])
    b = np.clip(1.0 - a / 10000.0, 0.0, None) ** 2  # levels never cross
    z = a[:, None, None] + b[:, None, None] * h
    time = np.array("2019-01-08T00", dtype="datetime64[ns]") + np.arange(
        nt
    ) * np.timedelta64(3, "h")
    rng = np.random.default_rng(0)

    def f3(base):
        return (base + 0.01 * rng.standard_normal((nt, nz, ny, nx))).astype(np.float32)

    def f2(base):
        return (base + 0.01 * rng.standard_normal((nt, ny, nx))).astype(np.float32)

    t3 = 288.0 - 0.0065 * np.minimum(z, 11000.0)
    ps = 101325.0 * np.exp(-G * h / (glide.R_DRY_AIR_J_KG_K * 280.0))
    shf = np.where(lon2 < 6, -300.0, 30.0)  # positive down: daytime heating is negative
    ds = xr.Dataset(
        {
            "u_component_of_wind": (
                ("time", "model_level", "latitude", "longitude"),
                f3(5.0),
            ),
            "v_component_of_wind": (
                ("time", "model_level", "latitude", "longitude"),
                f3(-2.0),
            ),
            "vertical_velocity": (
                ("time", "model_level", "latitude", "longitude"),
                f3(0.0),
            ),
            "temperature": (("time", "model_level", "latitude", "longitude"), f3(t3)),
            "specific_humidity": (
                ("time", "model_level", "latitude", "longitude"),
                np.abs(f3(0.005 * np.exp(-z / 2000.0))),
            ),
            "geopotential": (
                ("model_level", "latitude", "longitude"),
                (G * z).astype(np.float32),
            ),
            "boundary_layer_height": (("time", "latitude", "longitude"), f2(800.0)),
            "surface_pressure": (("time", "latitude", "longitude"), f2(ps)),
            "friction_velocity": (("time", "latitude", "longitude"), np.abs(f2(0.3))),
            "surface_sensible_heat_flux": (("time", "latitude", "longitude"), f2(shf)),
            "geopotential_at_surface": (
                ("latitude", "longitude"),
                (G * h).astype(np.float32),
            ),
        },
        coords={
            "time": time,
            "model_level": np.arange(1, nz + 1, dtype=np.int32),
            "latitude": lat,
            "longitude": lon,
        },
    )
    for name in glide.REQUIRED:
        ds[name].attrs["units"] = glide.CANONICAL_UNITS[name]
    # 3-hourly means ending at each timestamp, as in the UM stores (format 2.0).
    for name in ("surface_sensible_heat_flux", "friction_velocity"):
        ds[name].attrs.update(glide.period_attrs("mean", 10800))
    ds.attrs = glide.store_attrs(
        vertical_coordinate="model_level",
        source_dataset="synthetic",
        source_access="tests",
        producer_version="0.0",
        producer_commit="abc123",
        processing="none",
        compression="lossless",
        domain="TEST",
        flux_averaging_seconds=10800,
    )
    if mutate is not None:
        ds = mutate(ds)
    for key, value in attr_changes.items():
        if value is None:
            ds.attrs.pop(key, None)
        else:
            ds.attrs[key] = value
    ds.to_zarr(path, mode="w", consolidated=True, zarr_format=3)
    return path


def _errors(path, **kw):
    report = glide.validate(path, **kw)
    return report, " | ".join(report.errors)


def test_conforming_store_passes(tmp_path):
    report, errors = _errors(make_store(tmp_path / "ok.zarr"))
    assert report.ok, errors


def test_validation_input_rules(tmp_path):
    path = make_store(tmp_path / "dirty.zarr", producer_commit="abc123-dirty")
    assert glide.validate(path).ok
    report, errors = _errors(path, validation_input=True)
    assert "tagged release" in errors


@pytest.mark.parametrize(
    ("mutate", "attrs", "expected"),
    [
        # heat flux written positive-up
        (
            lambda ds: ds.assign(
                surface_sensible_heat_flux=-ds.surface_sensible_heat_flux
            ),
            {},
            "positive-UP",
        ),
        # geopotential height (m) instead of geopotential
        (
            lambda ds: ds.assign(
                geopotential=ds.geopotential / G,
                geopotential_at_surface=ds.geopotential_at_surface / G,
            ),
            {},
            "not in m**2 s**-2",
        ),
        # only the 3-D field in metres
        (
            lambda ds: ds.assign(geopotential=ds.geopotential / G),
            {},
            "below geopotential_at_surface",
        ),
        # untagged model levels
        (None, {"glide_vertical_coordinate": None}, "glide_vertical_coordinate"),
        # model levels tagged as pressure levels
        (None, {"glide_vertical_coordinate": "pressure_level"}, "consecutive integers"),
        # missing provenance
        (None, {"source_dataset": None}, "source_dataset"),
        (None, {"glide_flux_averaging_seconds": None}, "glide_flux_averaging_seconds"),
        (None, {"glide_format_version": "0.9"}, "glide_format_version"),
        # temperature in degrees C
        (
            lambda ds: ds.assign(temperature=ds.temperature - 273.15),
            {},
            "temperature spans",
        ),
        # surface pressure in hPa
        (
            lambda ds: ds.assign(surface_pressure=ds.surface_pressure / 100),
            {},
            "surface_pressure spans",
        ),
        # an extra variable
        (
            lambda ds: ds.assign(air_pressure=ds.temperature * 0 + 1e5),
            {},
            "not in the format",
        ),
        # a missing variable
        (lambda ds: ds.drop_vars("friction_velocity"), {}, "missing required variable"),
        # irregular time
        (
            lambda ds: ds.assign_coords(
                time=ds.time.values + np.array([0, 0, 0, 3600], dtype="timedelta64[s]")
            ),
            {},
            "not uniform",
        ),
        # decreasing longitude
        (lambda ds: ds.isel(longitude=slice(None, None, -1)), {}, "longitude"),
    ],
)
def test_broken_stores_fail(tmp_path, mutate, attrs, expected):
    path = make_store(tmp_path / "bad.zarr", mutate, **attrs)
    report, errors = _errors(path)
    assert not report.ok
    assert expected in errors, errors


def test_missing_and_bad_units(tmp_path):
    def no_units(ds):
        ds["temperature"].attrs.pop("units")
        return ds

    report, errors = _errors(make_store(tmp_path / "a.zarr", no_units))
    assert "temperature has no units" in errors

    def bad_units(ds):
        ds["boundary_layer_height"].attrs["units"] = "km"
        return ds

    report, errors = _errors(make_store(tmp_path / "b.zarr", bad_units))
    assert "unrecognised units 'km'" in errors


def test_non_finite_values_found_by_full_scan(tmp_path):
    def hole(ds):
        ds["specific_humidity"][2, 3, 4, 5] = np.nan
        return ds

    path = make_store(tmp_path / "nan.zarr", hole)
    assert glide.validate(path, full_scan=False).ok
    report, errors = _errors(path, full_scan=True)
    assert "specific_humidity has 1 non-finite" in errors


def test_int16_refused_for_validation_inputs(tmp_path):
    path = make_store(tmp_path / "ok.zarr")
    ds = xr.open_zarr(path).load()
    enc = {"temperature": {"dtype": "int16", "scale_factor": 0.01, "add_offset": 250.0}}
    ds.to_zarr(tmp_path / "int16.zarr", consolidated=True, zarr_format=3, encoding=enc)
    assert glide.validate(tmp_path / "int16.zarr").ok
    report, errors = _errors(tmp_path / "int16.zarr", validation_input=True)
    assert "lossless" in errors


def _relabel(name, **changes):
    """A mutation that changes (None deletes) attributes of one variable."""

    def mutate(ds):
        for key, value in changes.items():
            if value is None:
                ds[name].attrs.pop(key, None)
            else:
                ds[name].attrs[key] = value
        return ds

    return mutate


def test_period_attrs_helper():
    assert glide.period_attrs("mean", 10800) == {
        "cell_methods": "time: mean",
        "glide_period_seconds": 10800,
    }
    assert glide.period_attrs("sum", 3600)["cell_methods"] == "time: sum"
    with pytest.raises(ValueError):
        glide.period_attrs("max", 3600)
    with pytest.raises(ValueError):
        glide.period_attrs("mean", 0)


def test_period_variables_reported(tmp_path):
    report = glide.validate(make_store(tmp_path / "ok.zarr"))
    assert report.ok
    assert any(
        "period variables" in m and "friction_velocity (time: mean, 10800 s)" in m
        for m in report.info
    ), report.info


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        # a period that is not the time step (GLIDE refuses it)
        (
            _relabel("friction_velocity", glide_period_seconds=3600),
            "differs from the store's time step",
        ),
        # one attribute without the other
        (
            _relabel("friction_velocity", glide_period_seconds=None),
            "must come together",
        ),
        # an unknown method
        (_relabel("friction_velocity", cell_methods="time: max"), "expected one of"),
        # a period that is not a whole number of seconds
        (
            _relabel("friction_velocity", glide_period_seconds=10800.5),
            "expected a whole number",
        ),
        # a time-invariant field labelled as a mean
        (
            _relabel("geopotential", **glide.period_attrs("mean", 10800)),
            "cannot be a period variable",
        ),
        # a mean heat flux left unlabelled (format 1.0 style)
        (
            _relabel(
                "surface_sensible_heat_flux",
                cell_methods=None,
                glide_period_seconds=None,
            ),
            "not labelled as a period variable",
        ),
        # a rate labelled as a sum
        (
            _relabel("surface_sensible_heat_flux", cell_methods="time: sum"),
            "must be 'time: mean'",
        ),
    ],
)
def test_bad_period_labels_fail(tmp_path, mutate, expected):
    report, errors = _errors(make_store(tmp_path / "bad.zarr", mutate))
    assert not report.ok
    assert expected in errors, errors


def test_heat_flux_period_must_match_store_attribute(tmp_path):
    path = make_store(tmp_path / "x.zarr", glide_flux_averaging_seconds="3600")
    report, errors = _errors(path)
    assert "differs from glide_flux_averaging_seconds" in errors


def test_accumulated_heat_flux_needs_sum_label(tmp_path):
    def accumulated(ds, method="time: sum"):
        shf = ds["surface_sensible_heat_flux"]
        ds["surface_sensible_heat_flux"] = shf * 10800
        ds["surface_sensible_heat_flux"].attrs = {
            "units": "J m**-2",
            "cell_methods": method,
            "glide_period_seconds": 10800,
        }
        return ds

    attrs = {
        "glide_flux_averaging_seconds": None,
        "glide_flux_accumulation_seconds": "10800",
    }
    ok = make_store(tmp_path / "sum.zarr", accumulated, **attrs)
    report, errors = _errors(ok)
    assert report.ok, errors
    bad = make_store(
        tmp_path / "mean.zarr", lambda ds: accumulated(ds, "time: mean"), **attrs
    )
    report, errors = _errors(bad)
    assert "must be 'time: sum'" in errors


def test_validation_inputs_need_ustar_as_a_mean(tmp_path):
    path = make_store(
        tmp_path / "zust.zarr",
        _relabel("friction_velocity", cell_methods=None, glide_period_seconds=None),
    )
    assert glide.validate(path).ok
    report, errors = _errors(path, validation_input=True)
    assert "friction_velocity is not a period variable" in errors


def test_format_1_0_store_refused(tmp_path):
    report, errors = _errors(
        make_store(tmp_path / "old.zarr", glide_format_version="1.0")
    )
    assert "this validator implements '2.0'" in errors


def test_small_below_ground_offset_is_a_warning(tmp_path):
    # ARCO's ERA5: over high ground the lowest model level can sit up to ~125 m
    # below the surface geopotential. Reported, not an error; a unit mistake
    # (thousands of metres) still fails.
    def sink(ds):
        lowest = int(ds.geopotential.mean(("latitude", "longitude")).argmin())
        ds["geopotential"][lowest] = ds.geopotential_at_surface - 100.0 * G
        return ds

    report = glide.validate(make_store(tmp_path / "sink.zarr", sink))
    assert report.ok, report.format()
    assert any("below geopotential_at_surface" in w for w in report.warnings)
