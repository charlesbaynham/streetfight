"""Local flat-earth conversion between metres and degrees.

The play area is 1.3 km across, so a tangent-plane approximation about its
centre is accurate to well under a metre -- far below the fix noise this world
is built to model. Working in metres internally keeps the movement code
readable; the conversion back to lat/long happens once, at the edge.

``backend.shot_identification.haversine_m`` stays the authority for distances
that the game itself computes. This is only for *building* the world.
"""

import math

import numpy as np

from backend.venues import ACTIVE_VENUE

EARTH_R = 6371000.0

_bounds = ACTIVE_VENUE.map.bounds
ORIGIN_LAT = (_bounds.north + _bounds.south) / 2
ORIGIN_LONG = (_bounds.east + _bounds.west) / 2

_M_PER_DEG_LAT = math.pi * EARTH_R / 180.0
_M_PER_DEG_LONG = _M_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))


def to_m(lat, long):
    """(lat, long) in degrees -> (east, north) metres from the venue centre."""
    east = (np.asarray(long) - ORIGIN_LONG) * _M_PER_DEG_LONG
    north = (np.asarray(lat) - ORIGIN_LAT) * _M_PER_DEG_LAT
    return east, north


def to_latlong(east, north):
    """(east, north) metres -> (lat, long) degrees."""
    lat = np.asarray(north) / _M_PER_DEG_LAT + ORIGIN_LAT
    long = np.asarray(east) / _M_PER_DEG_LONG + ORIGIN_LONG
    return lat, long


def landmark_m(name: str):
    """A venue landmark as (east, north) metres."""
    lat, long = ACTIVE_VENUE.landmarks[name]
    east, north = to_m(lat, long)
    return float(east), float(north)


def bearing_deg(from_east, from_north, to_east, to_north):
    """Compass bearing from one point to another, degrees clockwise from north."""
    return np.degrees(np.arctan2(to_east - from_east, to_north - from_north)) % 360.0
