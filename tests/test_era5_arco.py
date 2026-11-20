"""End to end: synthetic ARCO-shaped ERA5 stores -> a ``glide`` store.

Every copied field must equal the source at the cropped points; u* must come
from the stresses (not ``zust``) by the formula in decision 0006; the heat flux
and u* must carry their format 2.0 labels; and the store must validate.
"""

import json

import numpy as np
import pytest
import xarray as xr
import yaml

import synthetic_era5 as syn
from metbazarr import build, build_era5
from metbazarr.formats import glide
from metbazarr.recipe import load_recipe
from metbazarr.sources import era5_arco, era5_ecmwf

# Crosses 0 E: longitudes come out in -180..180.
BOX_EUR = {"name": "EUR", "lon_min": -30, "lon_max": 40, "lat_min": 30, "lat_max": 70}
# Does not cross 0 E: longitudes stay in 0..360, as ARCO gives them.
BOX_NAM = {"name": "NAM", "lon_min": -120, "lon_max": -55, "lat_min": 20, "lat_max": 60}
START, END = "2019-01-08T00:00", "2019-01-08T05:00"


@pytest.fixture(scope="module")
def arco(tmp_path_factory):
    return syn.write_stores(tmp_path_factory.mktemp("arco"))


def write_recipe(tmp_path, stores, box, name="store", kind="era5_arco"):
    ml, sf = stores
    recipe = {
        "format": "glide",
        "output": str(tmp_path / f"{name}.zarr"),
        "domain": box,
        "period": {"start": START, "end": END},
        "source": {
            "type": kind,
            "model_level_store": str(ml),
            "surface_store": str(sf),
            "anonymous": False,
        },
    }
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(recipe))
    return load_recipe(path)


def build_store(tmp_path, stores, box, name="store"):
    recipe = write_recipe(tmp_path, stores, box, name)
    build.create(recipe)
    build.fill(recipe)
    report = build.finish(recipe)
    return recipe, report


def expected_crop(box):
    lat = syn.LAT.astype(np.float64)
    lon180 = syn.wrap180(syn.LON)
    j = np.flatnonzero((lat >= box["lat_min"]) & (lat <= box["lat_max"]))
    i = np.flatnonzero((lon180 >= box["lon_min"]) & (lon180 <= box["lon_max"]))
    return j, i


def test_crop_crossing_greenwich():
    box = era5_arco.crop_for_box(
        syn.LAT, syn.LON, load_box(BOX_EUR)
    )  # -30..40 E crosses 0
    assert box.longitudes[0] == -30 and box.longitudes[-1] == 40
    assert np.all(np.diff(box.longitudes) > 0)
    assert box.latitudes[0] == 70 and box.latitudes[-1] == 30  # north to south


def test_crop_not_crossing_keeps_0_360():
    box = era5_arco.crop_for_box(syn.LAT, syn.LON, load_box(BOX_NAM))
    assert box.longitudes[0] == 240 and box.longitudes[-1] == 305


def load_box(d):
    from metbazarr.sources.um import Box

    return Box(**d)


@pytest.mark.parametrize("box", [BOX_EUR, BOX_NAM], ids=["EUR", "NAM"])
def test_store_matches_source(tmp_path, arco, box):
    recipe, report = build_store(tmp_path, arco, box)
    assert report.ok, report.format()
    ds = xr.open_zarr(recipe.output)
    j, i = expected_crop(box)
    assert ds.sizes["latitude"] == j.size and ds.sizes["longitude"] == i.size
    assert ds.sizes["time"] == 6 and ds.sizes["hybrid"] == syn.NZ

    src_ml, src_sf = (xr.open_zarr(p) for p in arco)
    lon_order = np.argsort(syn.wrap180(syn.LON[i])) if box is BOX_EUR else slice(None)
    for name in era5_arco.MODEL_LEVEL_VARS:
        want = src_ml[name].isel(latitude=j, longitude=i[lon_order]).values
        np.testing.assert_array_equal(ds[name].values, want, err_msg=name)
    for name in era5_arco.SURFACE_VARS:
        want = src_sf[name].isel(latitude=j, longitude=i[lon_order]).values
        np.testing.assert_array_equal(ds[name].values, want, err_msg=name)


def test_friction_velocity_from_stresses(tmp_path, arco):
    recipe, report = build_store(tmp_path, arco, BOX_NAM)
    ds = xr.open_zarr(recipe.output)
    j, i = expected_crop(BOX_NAM)
    for k in range(6):
        f = syn.fields(k)
        tau = (
            np.hypot(
                f["eastward_turbulent_surface_stress"]
                .astype(np.float32)
                .astype(np.float64),
                f["northward_turbulent_surface_stress"]
                .astype(np.float32)
                .astype(np.float64),
            )
            / 3600.0
        )
        t = f["temperature"][-1].astype(np.float32).astype(np.float64)
        q = f["specific_humidity"][-1].astype(np.float32).astype(np.float64)
        ps = f["surface_pressure"].astype(np.float32).astype(np.float64)
        rho = ps / (287.05 * t * (1.0 + 0.6077 * q))
        want = np.sqrt(tau / rho).astype(np.float32)[np.ix_(j, i)]
        np.testing.assert_array_equal(ds["friction_velocity"].values[k], want)
    # not ERA5's own zust
    assert not np.any(np.isclose(ds["friction_velocity"].values, 0.123))


def test_labels_and_attributes(tmp_path, arco):
    recipe, report = build_store(tmp_path, arco, BOX_EUR)
    ds = xr.open_zarr(recipe.output)
    assert ds.attrs["glide_format_version"] == glide.FORMAT_VERSION == "2.0"
    assert ds.attrs["glide_vertical_coordinate"] == "model_level"
    assert ds.attrs["glide_flux_accumulation_seconds"] == "3600"
    assert "glide_flux_averaging_seconds" not in ds.attrs
    assert ds.attrs["source_dataset"].startswith("ERA5 hourly reanalysis (ECMWF), ARCO")
    assert ds.attrs["recipe_text"] == recipe.path.read_text()
    shf, ustar = ds["surface_sensible_heat_flux"], ds["friction_velocity"]
    assert shf.attrs["cell_methods"] == "time: sum"
    assert shf.attrs["units"] == "J m**-2"
    assert ustar.attrs["cell_methods"] == "time: mean"
    for v in (shf, ustar):
        assert v.attrs["glide_period_seconds"] == 3600
    for name in ("temperature", "boundary_layer_height", "geopotential"):
        assert "cell_methods" not in ds[name].attrs
    assert ds["vertical_velocity"].attrs["units"] == "Pa s**-1"  # omega, as ARCO
    assert any("friction_velocity (time: mean, 3600 s)" in m for m in report.info)


def test_isolated_missing_value_filled(tmp_path):
    # The case met in ARCO: one heat-flux value missing at one cell and hour.
    j, i = expected_crop(BOX_EUR)
    jj, ii = int(j[2]), int(i[3])
    stores = syn.write_stores(
        tmp_path / "src", nan_at=("surface_sensible_heat_flux", 2, jj, ii)
    )
    (tmp_path / "src").mkdir(exist_ok=True)
    recipe, report = build_store(tmp_path, stores, BOX_EUR)
    assert report.ok, report.format()
    ds = xr.open_zarr(recipe.output)
    entries = json.loads(ds.attrs[glide.FILLED_VALUES_ATTR])
    assert len(entries) == 1
    e = entries[0]
    assert e["variable"] == "surface_sensible_heat_flux"
    assert e["time"] == "2019-01-08T02:00:00Z"
    assert e["filled"] == np.float32((e["before"] + e["after"]) / 2)


def test_plan_and_interval(tmp_path, arco):
    recipe = write_recipe(tmp_path, arco, BOX_EUR)
    assert build.interval_hours(recipe) == 1
    text = build.describe(recipe)
    assert "EUR:" in text and "6 levels" in text and "6 times" in text
    p = build.plan(recipe)
    assert isinstance(p, build_era5.Plan)


def test_ecmwf_direct_not_yet(tmp_path, arco):
    recipe = write_recipe(tmp_path, arco, BOX_EUR, kind="era5_ecmwf")
    with pytest.raises(era5_ecmwf.Era5EcmwfNotImplemented, match="MARS"):
        build.create(recipe)


def test_unset_output_variable_refused(tmp_path, monkeypatch):
    monkeypatch.delenv("METBAZARR_OUT_TEST", raising=False)
    path = tmp_path / "r.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "format": "glide",
                "output": "$METBAZARR_OUT_TEST/x.zarr",
                "domain": BOX_EUR,
                "period": {"start": START, "end": END},
                "source": {"type": "era5_arco"},
            }
        )
    )
    with pytest.raises(ValueError, match="not set"):
        load_recipe(path)


def test_request_timeout_reaches_gcsfs():
    src = era5_arco.ArcoSource(request_timeout_s=30.0)
    opened = {}
    import xarray

    def fake_open(uri, **kw):
        opened.update(kw)
        raise RuntimeError("stop")

    orig, xarray.open_zarr = xarray.open_zarr, fake_open
    try:
        with pytest.raises(RuntimeError):
            src._open("gs://bucket/store.zarr")
    finally:
        xarray.open_zarr = orig
    assert opened["storage_options"] == {"requests_timeout": 30.0, "token": "anon"}


def test_fill_missing_only_resumes(tmp_path, arco):
    from metbazarr.cli import main

    recipe = write_recipe(tmp_path, arco, BOX_NAM)
    build.create(recipe)
    build.fill(recipe, range(0, 3))
    assert build.missing_times(recipe) == [3, 4, 5]
    assert main(["build", str(recipe.path), "--step", "fill", "--missing-only"]) == 0
    assert build.missing_times(recipe) == []
