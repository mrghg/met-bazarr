"""The UM conversion's numerical steps, on synthetic arrays."""

import numpy as np
import pytest

from metbazarr.sources import um


def test_destagger_u_is_exact_for_linear_fields():
    lon_u = np.arange(6) * 2.0  # u points
    u = np.broadcast_to(3.0 + 0.5 * lon_u, (2, 3, 6))
    out = um.destagger_u(u)
    lon_s = lon_u[:-1] + 1.0
    np.testing.assert_allclose(out, np.broadcast_to(3.0 + 0.5 * lon_s, (2, 3, 5)))


def test_destagger_v_is_exact_for_linear_fields():
    lat_v = np.arange(5) * 1.5
    v = np.broadcast_to((-2.0 + 0.25 * lat_v)[:, None], (5, 4))
    out = um.destagger_v(v)
    lat_s = lat_v[:-1] + 0.75
    np.testing.assert_allclose(
        out, np.broadcast_to((-2.0 + 0.25 * lat_s)[:, None], (4, 4))
    )


def _levels(h):
    a_r, b_r = np.array([10.0, 40.0, 100.0, 300.0]), np.array([0.99, 0.95, 0.8, 0.0])
    a_t, b_t = np.array([20.0, 60.0, 150.0, 500.0]), np.array([0.98, 0.9, 0.7, 0.0])
    return um.level_heights(a_r, b_r, h), um.level_heights(a_t, b_t, h)


def test_rho_to_theta_is_exact_for_fields_linear_in_height():
    h = np.array([[0.0, 500.0], [1000.0, 50.0]])
    z_r, z_t = _levels(h)
    out = um.rho_to_theta(2.0 + 0.01 * z_r, z_r, z_t)
    np.testing.assert_allclose(out[:-1], (2.0 + 0.01 * z_t)[:-1], rtol=1e-12)
    # the top theta level is above the top rho level: it takes the top value
    np.testing.assert_allclose(out[-1], 2.0 + 0.01 * z_r[-1])


def test_rho_to_theta_refuses_unbracketed_levels():
    h = np.zeros((1, 1))
    z_r, z_t = _levels(h)
    with pytest.raises(um.UMError, match="between rho levels"):
        um.rho_to_theta(z_r, z_r, z_t[::-1].copy())


def test_density_and_friction_velocity():
    rho = um.air_density(np.array(100000.0), np.array(280.0), np.array(0.0))
    assert rho == pytest.approx(100000.0 / (287.05 * 280.0))
    ustar = um.friction_velocity(np.array(0.3), np.array(0.4), np.array(1.25))
    assert ustar == pytest.approx(np.sqrt(0.5 / 1.25))


def test_geopotential_uses_glide_gravity():
    levels = um.Levels(np.zeros(1), np.zeros(1), np.array([100.0]), np.array([0.5]))
    phi = um.geopotential(levels, np.full((1, 1), 200.0))
    assert phi[0, 0, 0] == pytest.approx(9.80665 * 200.0)


# The real Mk10 grid and the GLIDE validation domains (reference-runs.md §2):
# the expected crops are the ones reported in the B14 assessment.
MK10 = um.GlobalGrid(dlon=0.140625, dlat=0.09375)


def test_crop_eur():
    crop = um.crop_for_box(MK10, um.Box("EUR", -30, 40, 32, 72))
    assert (crop.ny, crop.nx) == (429, 499)
    assert crop.latitudes[0] == 31.921875 and crop.latitudes[-1] == 72.046875
    assert crop.longitudes[0] == -30.0234375 and crop.longitudes[-1] == 40.0078125


def test_crop_nam():
    crop = um.crop_for_box(MK10, um.Box("NAM", -120, -55, 22, 58))
    assert (crop.ny, crop.nx) == (386, 464)
    assert crop.latitudes[0] == 21.984375 and crop.latitudes[-1] == 58.078125
    assert crop.longitudes[0] == -120.0234375 and crop.longitudes[-1] == -54.9140625


def test_crop_keeps_a_point_lying_on_the_edge():
    grid = um.GlobalGrid(dlon=1.0, dlat=1.0)
    crop = um.crop_for_box(grid, um.Box("x", 10.5, 20.5, -4.5, 4.5))
    assert crop.longitudes[0] == 10.5 and crop.longitudes[-1] == 20.5
    assert crop.latitudes[0] == -4.5 and crop.latitudes[-1] == 4.5


def test_crop_staggered_extents():
    grid = um.GlobalGrid(dlon=10.0, dlat=10.0)
    crop = um.crop_for_box(grid, um.Box("x", -20, 20, 0, 30))
    assert crop.cols("u").size == crop.nx + 1
    assert crop.rows("v").size == crop.ny + 1
    assert crop.cols("scalar")[0] == (crop.i0 % grid.nlon)


def test_mosaic_checks_overlaps_and_coverage():
    mosaic = um._Mosaic(np.arange(0, 4), np.arange(0, 6), nlon=36)
    mosaic.add(np.ones((4, 4)), 0, 0, "x")
    mosaic.add(np.ones((4, 3)), 0, 3, "x")  # overlaps column 3, same values
    np.testing.assert_array_equal(mosaic.result("x"), np.ones((4, 6)))
    with pytest.raises(um.UMError, match="disagree"):
        mosaic.add(np.full((4, 3), 2.0), 0, 3, "x")
    partial = um._Mosaic(np.arange(0, 4), np.arange(0, 6), nlon=36)
    partial.add(np.ones((4, 4)), 0, 0, "x")
    with pytest.raises(um.UMError, match="not in any partition"):
        partial.result("x")


def test_mosaic_wraps_longitude():
    cols = np.array([34, 35, 0, 1])  # crop through 0 degrees
    mosaic = um._Mosaic(np.arange(2), cols, nlon=36)
    mosaic.add(
        np.arange(12, dtype=float).reshape(2, 6), 0, 32, "x"
    )  # cols 32..37 -> 32..35, 0, 1
    np.testing.assert_array_equal(mosaic.result("x")[0], [2, 3, 4, 5])
