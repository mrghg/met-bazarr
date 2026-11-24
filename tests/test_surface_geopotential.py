"""Decision 0009: ERA5 stores carry a surface geopotential consistent with
their model levels, derived from the lowest level; built stores are repaired in
place; the validator refuses validation inputs whose levels lie below the
surface."""

import json

import numpy as np
import pytest
import xarray as xr
import zarr

import synthetic_era5 as syn
from metbazarr import repair
from metbazarr.formats import glide
from metbazarr.sources import era5_arco
from test_era5_arco import BOX_EUR, build_store, expected_crop

TABLE_B_136 = 0.997630  # ECMWF "L137 model level definitions", half level 136
G = 9.80665


def test_alpha_from_the_l137_table():
    b = TABLE_B_136
    assert (
        pytest.approx(1 - b / (1 - b) * np.log(1 / b), rel=1e-12)
        == era5_arco.ALPHA_LOWEST
    )
    h = era5_arco.ALPHA_LOWEST * era5_arco.R_DRY_AIR_IFS * 280.0 / G
    assert 9.6 < h < 9.8  # the lowest level sits ~10 m above the ground


@pytest.fixture(scope="module")
def arco(tmp_path_factory):
    return syn.write_stores(tmp_path_factory.mktemp("arco"))


def test_built_store_has_consistent_surface(tmp_path, arco):
    recipe, report = build_store(tmp_path, arco, BOX_EUR)
    assert report.ok, report.format()
    ds = xr.open_zarr(recipe.output)
    j, i = expected_crop(BOX_EUR)
    lon_order = np.argsort(syn.wrap180(syn.LON[i]))
    for k in range(ds.sizes["time"]):
        f = syn.fields(k)
        sel = lambda a: a[..., j[:, None], i[lon_order][None, :]]  # noqa: E731
        z1 = sel(f["geopotential"][-1].astype(np.float32).astype(np.float64))
        t1 = sel(f["temperature"][-1].astype(np.float32).astype(np.float64))
        q1 = sel(f["specific_humidity"][-1].astype(np.float32).astype(np.float64))
        want = era5_arco.surface_geopotential_from_lowest_level(z1, t1, q1).astype(
            np.float32
        )
        np.testing.assert_array_equal(ds["geopotential_at_surface"].values[k], want)
    gap = (
        ds["geopotential"].isel(hybrid=-1) - ds["geopotential_at_surface"]
    ).values / G
    assert gap.min() > 8.0  # never below the ground


def _spoil_surface(path, offset_m):
    """Make a store look like one built before decision 0009: surface
    geopotential raised by ``offset_m`` over high ground."""
    ds = xr.open_zarr(path)
    zs = ds["geopotential_at_surface"].values.copy()
    high = zs > G * 500.0
    zs[:, high[0]] += G * offset_m
    xr.Dataset(
        {"geopotential_at_surface": (ds["geopotential_at_surface"].dims, zs)}
    ).to_zarr(path, region={"time": slice(0, zs.shape[0])}, mode="r+")
    zarr.consolidate_metadata(str(path))


def test_validator_refuses_levels_below_surface_for_validation_inputs(tmp_path, arco):
    recipe, _ = build_store(tmp_path, arco, BOX_EUR)
    _spoil_surface(recipe.output, 50.0)
    loose = glide.validate(recipe.output, full_scan=False)
    assert any("same ground" in w for w in loose.warnings)
    # A clean producer commit, so the strict check reaches the physics.
    group = zarr.open_group(str(recipe.output), mode="r+")
    group.attrs["producer_commit"] = "0" * 40
    zarr.consolidate_metadata(str(recipe.output))
    strict = glide.validate(recipe.output, full_scan=False, validation_input=True)
    assert any("same ground" in e for e in strict.errors)


def test_repair_restores_and_records(tmp_path, arco):
    recipe, _ = build_store(tmp_path, arco, BOX_EUR)
    good = xr.open_zarr(recipe.output)["geopotential_at_surface"].values.copy()
    _spoil_surface(recipe.output, 50.0)
    dry = repair.repair_era5_surface_geopotential(recipe.output, dry_run=True)
    assert dry["change_m"]["max"] == pytest.approx(50.0, abs=0.1)
    assert repair.repairs(recipe.output) == []  # dry run writes nothing
    result = repair.repair_era5_surface_geopotential(recipe.output, block=2)
    np.testing.assert_array_equal(
        xr.open_zarr(recipe.output)["geopotential_at_surface"].values, good
    )
    rec = repair.repairs(recipe.output)
    assert len(rec) == 1 and rec[0]["repair"] == repair.ERA5_SURFACE_GEOPOTENTIAL
    assert rec[0] == json.loads(json.dumps(result))
    assert (
        "repair era5-surface-geopotential"
        in xr.open_zarr(recipe.output).attrs["processing"]
    )
    with pytest.raises(ValueError, match="already repaired"):
        repair.repair_era5_surface_geopotential(recipe.output)


def test_repair_refuses_non_era5(tmp_path, arco):
    recipe, _ = build_store(tmp_path, arco, BOX_EUR)
    group = zarr.open_group(str(recipe.output), mode="r+")
    group.attrs["source_dataset"] = "Met Office global Unified Model"
    zarr.consolidate_metadata(str(recipe.output))
    with pytest.raises(ValueError, match="not an ERA5 store"):
        repair.repair_era5_surface_geopotential(recipe.output)
