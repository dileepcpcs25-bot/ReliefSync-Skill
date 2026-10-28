import math

import pytest

from app.services.geo import bounding_box, coarsen, haversine_km, osm_directions_url, valid_coordinates, within_radius

CHENNAI, BENGALURU, LONDON, NYC = (13.0827, 80.2707), (12.9716, 77.5946), (51.5074, -0.1278), (40.7128, -74.0060)


def test_haversine_known_distances():
    assert haversine_km(*CHENNAI, *CHENNAI) == 0
    assert haversine_km(*CHENNAI, *BENGALURU) == pytest.approx(290, abs=5)  # published great-circle ~290 km
    assert haversine_km(*LONDON, *NYC) == pytest.approx(5570, rel=0.01)
    assert haversine_km(*LONDON, *NYC) == pytest.approx(haversine_km(*NYC, *LONDON))  # symmetric


def test_haversine_across_antimeridian_and_poles():
    assert haversine_km(0, 179.5, 0, -179.5) == pytest.approx(111.2, abs=1)  # 1 degree of longitude at the equator
    assert haversine_km(90, 0, -90, 0) == pytest.approx(math.pi * 6371.0088, rel=1e-6)


@pytest.mark.parametrize("lat,lng", [(91, 0), (-90.1, 0), (0, 180.1), (0, -181), (float("nan"), 0), (0, float("inf")), ("12", 5), (None, 5), (True, 5)])
def test_invalid_coordinates_rejected(lat, lng):
    assert not valid_coordinates(lat, lng)
    with pytest.raises(ValueError):
        haversine_km(lat, lng, 0, 0)
    assert not within_radius(lat, lng, 0, 0, 1000)


def test_boundary_coordinates_are_valid():
    assert valid_coordinates(90, 180) and valid_coordinates(-90, -180) and valid_coordinates(0, 0)


def test_radius_filtering():
    assert within_radius(*CHENNAI, *BENGALURU, 300)
    assert not within_radius(*CHENNAI, *BENGALURU, 250)


def test_bounding_box_contains_circle_points():
    s, w, n, e = bounding_box(*CHENNAI, 50)
    assert s < CHENNAI[0] < n and w < CHENNAI[1] < e
    # points exactly 50 km away in the four cardinal directions must lie inside the box
    dlat = math.degrees(50 / 6371.0088)
    dlng = math.degrees(50 / (6371.0088 * math.cos(math.radians(CHENNAI[0]))))
    assert s <= CHENNAI[0] - dlat and CHENNAI[0] + dlat <= n
    assert w <= CHENNAI[1] - dlng and CHENNAI[1] + dlng <= e
    assert haversine_km(CHENNAI[0] + dlat, CHENNAI[1], *CHENNAI) == pytest.approx(50, abs=0.01)


def test_bounding_box_widens_at_poles_and_antimeridian():
    assert bounding_box(89.9, 10, 100)[1:4:2] == (-180.0, 180.0)
    s, w, n, e = bounding_box(0, 179.9, 50)
    assert (w, e) == (-180.0, 180.0)


def test_coarsen_and_directions_link():
    assert coarsen(13.08271, 80.27069, 1) == (13.1, 80.3)
    assert osm_directions_url(1, 2, 3, 4).startswith("https://www.openstreetmap.org/directions?")
