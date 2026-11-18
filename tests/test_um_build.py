"""End to end: a synthetic partitioned UM archive -> a ``glide`` store.

Expected values come from the analytic functions in ``synthetic_um``, put
through the agreed method (decision 0003) written out independently here.
"""

import datetime as dt

import numpy as np
import pytest
import xarray as xr
import yaml

pytest.importorskip("iris")

import synthetic_um as syn  # noqa: E402
from metbazarr import build  # noqa: E402
from metbazarr.formats import glide  # noqa: E402
from metbazarr.recipe import load_recipe  # noqa: E402
from metbazarr.sources import um  # noqa: E402

TIMES = [dt.datetime(2019, 1, 8, h) for h in (0, 3, 6, 9)]
# Crosses 0 degrees and the boundary between latitude bands (partitions 1, 2).
BOX_A = {"name": "A", "lon_min": -30, "lon_max": 40, "lat_min": 20, "lat_max": 70}
# Crosses the longitude boundary between partitions 2 and 3, and bands.
BOX_B = {"name": "B", "lon_min": 60, "lon_max": 120, "lat_min": 30, "lat_max": 70}


@pytest.fixture(scope="module")
def archive(tmp_path_factory):
    return syn.write_archive(tmp_path_factory.mktemp("um"), TIMES)


def write_recipe(tmp_path, archive, box, name="store", times=TIMES):
    recipe = {
        "format": "glide",
        "output": str(tmp_path / f"{name}.zarr"),
        "domain": box,
        "period": {"start": times[0].isoformat(), "end": times[-1].isoformat()},
        "source": {
            "type": "um_global",
            "series": "SYNTHETIC",
            "met_dir": str(archive.met_dir),
            "file_pattern": archive.file_pattern,
            "topography": archive.topography,
            "partitions": sorted(syn.PARTITIONS),
        },
        "compression": {"codec": "zstd", "level": 3},
        "chunks": {"tile": 8},
    }
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(recipe))
    return load_recipe(path)


def build_store(recipe):
    build.create(recipe)
    build.fill(recipe)
    report = build.finish(recipe)
    assert report.ok, report.format()
    return xr.open_zarr(recipe.output, consolidated=True)


def expected_crop(box):
    lat_s = -90.0 + (np.arange(syn.NLAT) + 0.5) * syn.DLAT
    j0 = np.flatnonzero(lat_s <= box["lat_min"])[-1]
    j1 = np.flatnonzero(lat_s >= box["lat_max"])[0]
    lon_s = (np.arange(-syn.NLON, 2 * syn.NLON) + 0.5) * syn.DLON
    i0 = np.flatnonzero(lon_s <= box["lon_min"])[-1]
    i1 = np.flatnonzero(lon_s >= box["lon_max"])[0]
    return lat_s[j0 : j1 + 1], lon_s[i0 : i1 + 1]


def expected_fields(lat, lon, k):
    lon2, lat2 = np.meshgrid(lon, lat)
    h = syn.orography(lon2, lat2)
    z_r = syn.A_RHO[:, None, None] + syn.B_RHO[:, None, None] * h
    z_t = syn.A_THETA[:, None, None] + syn.B_THETA[:, None, None] * h

    def staggered(fn, dlon, dlat):
        """Mean over the two neighbouring u (or v) points on each rho level,
        each at its own point's height, then linear in height onto theta."""
        mids = []
        for lev in range(syn.NZ):
            vals = []
            for s in (-0.5, 0.5):
                lo, la = lon2 + s * dlon, lat2 + s * dlat
                z = syn.A_RHO[lev] + syn.B_RHO[lev] * syn.orography(lo, la)
                vals.append(fn(lo, la, z, k))
            mids.append(0.5 * (vals[0] + vals[1]))
        mid = np.array(mids)
        out = np.empty_like(mid)
        wgt = (z_t[:-1] - z_r[:-1]) / (z_r[1:] - z_r[:-1])
        out[:-1] = mid[:-1] + wgt * (mid[1:] - mid[:-1])
        out[-1] = mid[-1]
        return out

    t1 = syn.t_true(lon2, lat2, z_t[0], k)
    q1 = syn.q_true(lon2, lat2, z_t[0], k)
    ps = syn.ps_true(lon2, lat2, k)
    rho = ps / (287.05 * t1 * (1 + 0.6077 * q1))
    taux = 0.5 * (
        syn.taux_true(lon2 - syn.DLON / 2, lat2, k)
        + syn.taux_true(lon2 + syn.DLON / 2, lat2, k)
    )
    tauy = 0.5 * (
        syn.tauy_true(lon2, lat2 - syn.DLAT / 2, k)
        + syn.tauy_true(lon2, lat2 + syn.DLAT / 2, k)
    )
    return {
        "u_component_of_wind": staggered(syn.u_true, syn.DLON, 0.0),
        "v_component_of_wind": staggered(syn.v_true, 0.0, syn.DLAT),
        "temperature": syn.t_true(lon2, lat2, z_t, k),
        "specific_humidity": syn.q_true(lon2, lat2, z_t, k),
        "vertical_velocity": syn.w_true(lon2, lat2, z_t, k),
        "surface_pressure": ps,
        "boundary_layer_height": syn.blh_true(lon2, lat2, k) * np.ones_like(h),
        "surface_sensible_heat_flux": -syn.shf_up_true(lon2, lat2, k),
        "friction_velocity": np.sqrt(np.hypot(taux, tauy) / rho),
        "geopotential": 9.80665 * z_t,
        "geopotential_at_surface": 9.80665 * h,
    }


@pytest.mark.parametrize("box", [BOX_A, BOX_B], ids=["A", "B"])
def test_store_matches_analytic_fields(tmp_path, archive, box):
    recipe = write_recipe(tmp_path, archive, box)
    ds = build_store(recipe)
    lat, lon = expected_crop(box)
    np.testing.assert_array_equal(ds.latitude.values, lat)
    np.testing.assert_array_equal(ds.longitude.values, lon)
    assert (
        ds.longitude.values[0] <= box["lon_min"]
        and ds.longitude.values[-1] >= box["lon_max"]
    )
    np.testing.assert_array_equal(
        ds.time.values, np.array(TIMES, dtype="datetime64[ns]")
    )
    np.testing.assert_array_equal(ds.level_height.values, syn.A_THETA)

    for k in range(len(TIMES)):
        expected = expected_fields(lat, lon, k)
        for name, want in expected.items():
            got = ds[name]
            if "time" in got.dims:
                got = got.isel(time=k)
            np.testing.assert_allclose(
                got.values, want, rtol=2e-6, atol=2e-6, err_msg=f"{name} at time {k}"
            )
        for name in glide.REQUIRED:
            assert ds[name].dtype == np.float32


def test_store_attributes(tmp_path, archive):
    ds = build_store(write_recipe(tmp_path, archive, BOX_A))
    assert ds.attrs["glide_format"] == "glide"
    assert ds.attrs["glide_format_version"] == "1.0"
    assert ds.attrs["glide_vertical_coordinate"] == "model_level"
    assert ds.attrs["glide_flux_averaging_seconds"] == "10800"
    assert "glide_flux_accumulation_seconds" not in ds.attrs
    assert ds.attrs["domain"] == "A"
    assert ds.attrs["producer"] == "met-bazarr"
    assert "SYNTHETIC" in ds.attrs["source_dataset"]
    assert "theta level 1" in ds.attrs["processing"]
    assert ds.attrs["compression"].startswith("lossless")
    assert "time" not in ds.geopotential.dims


def test_fill_in_blocks_and_finish_detects_gaps(tmp_path, archive):
    recipe = write_recipe(tmp_path, archive, BOX_A)
    build.create(recipe)
    build.fill(recipe, range(0, 2))
    assert build.missing_times(recipe) == [2, 3]
    with pytest.raises(RuntimeError, match="2 times not written"):
        build.finish(recipe)
    build.fill(recipe, range(2, 4))
    assert build.missing_times(recipe) == []
    assert build.finish(recipe).ok


def test_create_refuses_to_overwrite(tmp_path, archive):
    recipe = write_recipe(tmp_path, archive, BOX_A)
    build.create(recipe)
    with pytest.raises(FileExistsError):
        build.create(recipe)
    build.create(recipe, overwrite=True)


def test_fill_refuses_store_from_other_commit(tmp_path, archive):
    recipe = write_recipe(tmp_path, archive, BOX_A)
    build.create(recipe)
    store = xr.open_zarr(recipe.output)
    import zarr

    group = zarr.open_group(recipe.output, mode="r+")
    group.attrs["producer_commit"] = "0000000"
    zarr.consolidate_metadata(recipe.output)
    store.close()
    with pytest.raises(RuntimeError, match="created by commit"):
        build.fill(recipe, range(0, 1))


def test_partition_disagreement_is_an_error(tmp_path):
    bad = syn.write_archive(tmp_path / "bad", TIMES[:1], corrupt_overlap=True)
    recipe = write_recipe(tmp_path, bad, BOX_B, times=TIMES[:1])
    build.create(recipe)
    with pytest.raises(um.UMError, match="disagree"):
        build.fill(recipe)


def test_missing_file_is_an_error(tmp_path, archive):
    later = [dt.datetime(2019, 1, 8, 9), dt.datetime(2019, 1, 8, 12)]
    recipe = write_recipe(tmp_path, archive, BOX_A, times=later)
    build.create(recipe)
    with pytest.raises(um.UMError, match="missing met file"):
        build.fill(recipe)


def test_wrong_mean_period_is_an_error(tmp_path, archive):
    recipe = write_recipe(tmp_path, archive, BOX_A, times=TIMES[:1])
    recipe.source  # noqa: B018
    arch = build.archive_from(recipe)
    arch.mean_hours = 6
    crop = um.crop_for_box(arch.grid(), recipe.domain)
    with pytest.raises(um.UMError, match="expected the 6 h"):
        arch.read_time(TIMES[0], crop, arch.partitions_for(crop))


def test_cli_validate(tmp_path, archive, capsys):
    from metbazarr.cli import main

    recipe = write_recipe(tmp_path, archive, BOX_A)
    assert main(["build", str(recipe.path)]) == 0
    assert main(["validate", "--format", "glide", str(recipe.output)]) == 0
    assert "PASS" in capsys.readouterr().out


# --- isolated missing source values (format 1.0 fill rule) -------------------

# Global indices on each field's own grid. Row 35 is in the overlap of
# partitions 1 and 2, so the missing value is in both files.
PLANTED = (
    (1, "shf", None, 35, 2),  # one value
    (2, "t", 3, 30, 1),  # one value, theta level 4
    (2, "u", 4, 30, 1),  # rho level 5, u point between scalar columns 0 and 1
)


def test_isolated_missing_values_are_filled(tmp_path):
    arch = syn.write_archive(tmp_path / "holes", TIMES, missing=PLANTED)
    recipe = write_recipe(tmp_path, arch, BOX_A)
    ds = build_store(recipe)
    import json

    entries = json.loads(ds.attrs[glide.FILLED_VALUES_ATTR])
    by_var = {}
    for e in entries:
        by_var.setdefault(e["variable"], []).append(e)
    # u from rho level 5 at one u point reaches 2 scalar columns x theta 4, 5.
    assert {k: len(v) for k, v in by_var.items()} == {
        "surface_sensible_heat_flux": 1,
        "temperature": 1,
        "u_component_of_wind": 4,
    }
    assert sorted({e["level"] for e in by_var["u_component_of_wind"]}) == [4, 5]
    assert by_var["temperature"][0]["level"] == 4
    assert by_var["surface_sensible_heat_flux"][0]["time"] == "2019-01-08T03:00:00Z"
    assert glide.FILL_PROCESSING in ds.attrs["processing"]
    # The synthetic fields are linear in time, so the filled values equal the
    # analytic ones: the whole store still matches.
    lat, lon = expected_crop(BOX_A)
    for k in range(len(TIMES)):
        for name, want in expected_fields(lat, lon, k).items():
            got = ds[name].isel(time=k) if "time" in ds[name].dims else ds[name]
            np.testing.assert_allclose(got.values, want, rtol=2e-6, atol=2e-6)


def test_too_many_missing_values_stop_the_fill_step(tmp_path):
    many = tuple((0, "ps", None, 30, c) for c in range(11))
    arch = syn.write_archive(tmp_path / "many", TIMES[:1], missing=many)
    recipe = write_recipe(tmp_path, arch, BOX_A, times=TIMES[:1])
    build.create(recipe)
    with pytest.raises(um.UMError, match="11 missing values, more than the 10"):
        build.fill(recipe)


def test_missing_value_at_the_first_time_stops_finish(tmp_path):
    arch = syn.write_archive(
        tmp_path / "first", TIMES[:2], missing=((0, "blh", None, 30, 1),)
    )
    recipe = write_recipe(tmp_path, arch, BOX_A, times=TIMES[:2])
    build.create(recipe)
    build.fill(recipe)
    assert build.missing_times(recipe) == []
    with pytest.raises(glide.FillError, match="at the first time"):
        build.finish(recipe)
