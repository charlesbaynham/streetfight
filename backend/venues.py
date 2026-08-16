"""Everything that ties a game to a particular place.

A `Venue` bundles the map image, the georeferencing that pins that image to
the ground, and the landmarks that circles can be dropped at. Playing
somewhere new therefore means adding one entry to `VENUES` below, rather than
editing a Python file for the landmarks and a JavaScript one for the map.

The one piece that can't live here is the map image itself, since webpack has
to bundle it: `VenueMap.image` names a key in react-ui/src/mapImages.js, and
the frontend fetches the rest of this from /api/get_venue.

Exactly one venue is in play at a time - comment / uncomment `ACTIVE_VENUE` at
the bottom to switch. When games grow a venue of their own, this module is
already the registry to resolve it against, and the API endpoint can start
taking a game id.
"""

from typing import Dict
from typing import Tuple

from pydantic import BaseModel


class MapReferencePoint(BaseModel):
    """A point whose position is known both on the map image, in pixels from
    its top left corner, and on the ground."""

    x: float
    y: float
    lat: float
    long: float


class VenueMap(BaseModel):
    """A map image plus enough information to place it on the globe.

    Two reference points are enough because the image is assumed to be
    north-up and linear in latitude / longitude, which is close enough over
    the couple of km a game covers.
    """

    # Key into MAP_IMAGES in react-ui/src/mapImages.js
    image: str

    width_px: float
    height_px: float

    ref_1: MapReferencePoint
    ref_2: MapReferencePoint

    # How much of the map the mini map in the corner of the player's screen
    # shows, measured across. The whole map is far too much to read at that
    # size, so this is a zoomed-in window that follows the player.
    corner_width_km: float

    @property
    def bounds(self) -> "MapBounds":
        """The patch of the world this map covers.

        The frontend does the same sum to draw the map (see mapGeometry in
        react-ui/src/venue.js); this side wants it to check that a venue's
        landmarks actually land on its map.
        """
        long_per_px = (self.ref_2.long - self.ref_1.long) / (
            self.ref_2.x - self.ref_1.x
        )
        lat_per_px = (self.ref_2.lat - self.ref_1.lat) / (self.ref_2.y - self.ref_1.y)

        return MapBounds(
            west=self.ref_1.long - self.ref_1.x * long_per_px,
            east=self.ref_1.long + (self.width_px - self.ref_1.x) * long_per_px,
            south=self.ref_1.lat + (self.height_px - self.ref_1.y) * lat_per_px,
            north=self.ref_1.lat - self.ref_1.y * lat_per_px,
        )


class MapBounds(BaseModel):
    north: float
    south: float
    east: float
    west: float

    def contains(self, lat: float, long: float) -> bool:
        return self.south <= lat <= self.north and self.west <= long <= self.east


class Venue(BaseModel):
    """A place a game can be played: its map, and the landmarks in it."""

    name: str
    map: VenueMap

    # name -> (latitude, longitude). Admins place circles by picking one of
    # these, so the names are player-facing: use what people call the place.
    landmarks: Dict[str, Tuple[float, float]]


KINGSTON = Venue(
    name="Kingston upon Thames",
    map=VenueMap(
        # Based on calculations and markup in "map alignment.svg"
        image="kingston",
        width_px=2273.28,
        height_px=2206.72,
        ref_1=MapReferencePoint(
            x=695.4, y=1745.2, lat=51.4076739525208, long=-0.30754164680355806
        ),
        ref_2=MapReferencePoint(
            x=1650.3, y=398.9, lat=51.41383263398225, long=-0.30056843291595964
        ),
        corner_width_km=0.115,
    ),
    landmarks={
        "FORESTERS": (51.41304458075581, -0.3114802607226005),
        "SWAN": (51.41251815899422, -0.3108130395038778),
        "WHITE_HART": (51.411735226937104, -0.311537235944058),
        "BISHOP": (51.410287561454254, -0.30802021153922127),
        "GAZEBO": (51.409935101508935, -0.3083293139535659),
        "WOODYS": (51.40838921232607, -0.30834540720907166),
        "CHADWICKS": (51.40896474425693, -0.30687019224361667),
        "RAM": (51.40817505902859, -0.30769631262710195),
        "DRUIDS_HEAD": (51.40925250751722, -0.3064732253185496),
        "ONEILLS": (51.40905174264659, -0.30550763006496473),
        "WHEELWRIGHTS": (51.41054741978796, -0.3016559779176603),
        "CORNERSTONE": (51.41197445761035, -0.30019685622453496),
        "COCOANUT": (51.40682319343919, -0.29840514058732764),
        "MILL": (51.407000544357025, -0.3082273900127819),
        "WHELANS": (51.4129531154658, -0.30052945014521426),
        "HOUSE_ABSOLUTE": (51.41394346243026, -0.3001002966991766),
        "SPOONS": (51.411374997955264, -0.3007246028148721),
        "ALBION": (51.409136523603394, -0.29792437645324277),
        "FIGHTING_COCKS": (51.410615468068926, -0.2982569703905028),
        "GREY_HORSE": (51.41423566875311, -0.300628043344843),
        "HAWKERS": (51.41366354890716, -0.3054131038444269),
        "CIRCLE1": (51.409, -0.303),
        "CIRCLE2": (51.409, -0.3033),
        "CIRCLE3": (51.410300725650906, -0.30607777442454853),
        "CIRCLE4": (51.41091303903816, -0.30495124665767204),
        "DROP_PLAYGROUND": (51.409344, -0.298515),
        "DROP_BRIDGE": (51.411212, -0.310517),
        "DROP_RIVER": (51.409878, -0.308430),
        "DROP_MARKET": (51.409901, -0.306344),
        "DROP_POSTBOXES": (51.410784, -0.300363),
        "DROP_FINAL": (51.411000, -0.304620),
        "DROP_ALLEY": (51.413291, -0.305065),
    },
)


KOYAO_RESORT = Venue(
    name="Koyao Island Resort",
    map=VenueMap(
        # Cropped out of satellite imagery stitched from whole web mercator
        # tiles at zoom 18 (~0.6 m/px, the deepest imagery available over Ko
        # Yao Noi), so these reference points are exact rather than measured by
        # eye: ref 1 is the top left pixel of the image, ref 2 the bottom
        # right. The crop is the bounding box of the landmarks below plus a
        # 10% margin on each side, i.e. 162 x 211 m of resort and beach.
        image="koyao_resort",
        width_px=274,
        height_px=359,
        ref_1=MapReferencePoint(
            x=0, y=0, lat=8.117544995814134, long=98.62420856952667
        ),
        ref_2=MapReferencePoint(
            x=274, y=359, lat=8.11563846109953, long=98.62567842006683
        ),
        # Half the map: a tenth of somewhere this small would show nothing but
        # the player's own dot.
        corner_width_km=0.08,
    ),
    landmarks={
        "HOUSE_ABSOLUTE": (8.115796, 98.624333),
        "STAIRS": (8.115823, 98.624660),
        "SWING": (8.115904, 98.624796),
        "POOL": (8.116686, 98.625068),
        "THE_BAR": (8.117009, 98.624823),
        "THE_CAT": (8.117171, 98.625313),
        "THE_COVE": (8.117386, 98.625558),
    },
)


VENUES = {
    "kingston": KINGSTON,
    "koyao_resort": KOYAO_RESORT,
}

# TODO: TEMPORARY - the resort is a test venue, so that the map can be
# exercised against a real GPS fix somewhere I actually am. Swap back to
# Kingston before this is played for real.
ACTIVE_VENUE = VENUES["koyao_resort"]
# ACTIVE_VENUE = VENUES["kingston"]
