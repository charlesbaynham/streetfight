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

import logging
import os
from typing import Dict
from typing import Mapping
from typing import Optional
from typing import Tuple

from pydantic import BaseModel

from .dotenv import load_env_vars

logger = logging.getLogger(__name__)

# A landmark supplied by the environment rather than committed here:
# `LANDMARK_CIRCLE0="51.4958,-0.1309"` adds CIRCLE0 to the active venue. This
# repository is public and where the circles close is the one thing about the
# night that has to keep until it happens, so those coordinates live in the
# deployment's env file (nix/streetfight.env.example) instead. Nothing in the
# mechanism is about circles - the drop locations travel the same way.
LANDMARK_ENV_PREFIX = "LANDMARK_"

# A landmark whose name starts with one of these is somewhere the game *puts*
# something, not somewhere that is already there: where a circle closes, where
# a crate is going, where the courier is walking. Players are never sent them
# (`Venue.for_players`) and the map poster does not print them
# (backend/map_poster.py) - which is the whole point of keeping them out of
# the repository as well.
OPERATIONAL_PREFIXES = ("CIRCLE", "DROP_", "COURIER")


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

    def for_players(self) -> "Venue":
        """This venue as `/api/get_venue` serves it: the operational
        landmarks taken out.

        Everything else here is on the printed map anyway, but where the
        circles and drops are going is not, and a session cookie is all it
        would take to read them off the API.
        """
        return self.model_copy(
            update={
                "landmarks": {
                    name: point
                    for name, point in self.landmarks.items()
                    if not name.startswith(OPERATIONAL_PREFIXES)
                }
            }
        )


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


WESTMINSTER = Venue(
    name="Westminster",
    map=VenueMap(
        # Drawn in the Kingston style, but rendered rather than illustrated
        # (roadmap #12, milestone M0.6, 17 Sept 2026):
        # `.claude/skills/draw-venue-map/scripts/render_venue_map.py` draws
        # the OpenStreetMap geometry with a wobbly pen and a handwriting font.
        # Every image model tried resynthesised instead of tracing and got
        # either the roads or the scale wrong, so the geometry is no longer
        # asked of one: it is exact by construction, and every pub is
        # labelled because the renderer labels whatever is in `landmarks`
        # below. Re-run it if that list changes - it was drawn against
        # nineteen pubs and has not been re-run since Blue Boar dropped to
        # eighteen (19 Sept 2026), so the art still names one pub the game no
        # longer plays at.
        #
        # The crop is sized to the markers rather than pinned to one of them.
        # It used to be symmetric about House Absolute, which forced 1300 m
        # because Big Ben is 537 m north of it; the nineteen pubs and four
        # landmarks all fit within 458 m of their own centre, so 575 m leaves
        # every one at least 117 m of drawing room in a 1150 m square. The
        # reference points are that crop's corners, so they are exact by
        # construction rather than measured off the drawing - which is why
        # they only ever change together with the image.
        image="westminster",
        width_px=2000,
        height_px=2000,
        ref_1=MapReferencePoint(x=0, y=0, lat=51.502881, long=-0.139506),
        ref_2=MapReferencePoint(x=2000, y=2000, lat=51.492481, long=-0.122912),
        # Kingston uses 0.115 at 0.51 m/px; this drawing is 0.575 m/px, so the
        # same window on the ground is 0.13. The old 0.2 was compensating for
        # a 1.27 m/px image that had ninety pixels of blur in the corner
        # mini-map; there is nothing left to compensate for.
        corner_width_km=0.13,
    ),
    # The eighteen pubs Charles has actually chosen to play, plus House
    # Absolute and the three landmarks everybody navigates by. Superseded the
    # ten-pub OpenStreetMap survey shortlist on 12 Sept 2026.
    #
    # Coordinates are OpenStreetMap's, not the ones that came with the list:
    # every pub was corroborated by name, street and postcode, and the
    # list's own coordinates turned out to be 4-230 m out (median ~140 m),
    # which is the same order as the location term's own uncertainty.
    #
    # Every one of these is drawn and named on the map, because the map is
    # rendered from this dict (see the note above). Adding a pub here and
    # re-running the renderer is the whole change.
    landmarks={
        # South, around Horseferry Road and Millbank
        "ROYAL_OAK": (51.494215, -0.132538),  # 2 Regency Street
        "LOOSE_BOX": (51.494706, -0.131336),  # 51 Horseferry Road
        "WHITE_HORSE": (51.495027, -0.130857),  # 86 Horseferry Road
        "BARLEY_MOW": (51.495077, -0.131687),  # 104 Horseferry Road
        "MARQUIS_OF_GRANBY": (51.495177, -0.127175),  # 41 Romney Street
        "WINDSOR_CASTLE": (51.495169, -0.137798),  # 23 Francis Street
        "GREENCOAT_BOY": (51.496300, -0.135863),  # Greencoat Place
        "SPEAKER": (51.496905, -0.132260),  # 46 Great Peter Street
        # Middle, around Strutton Ground
        "GRAFTON_ARMS": (51.497468, -0.134108),  # 2 Strutton Ground
        "MUNICH_CRICKET_CLUB": (51.498199, -0.132467),  # 1 Abbey Orchard Street
        # North, around Broadway, Tothill Street and Petty France
        "BUCKINGHAM_ARMS": (51.499159, -0.136793),  # 62 Petty France
        "FEATHERS": (51.499240, -0.132990),  # 18-20 Broadway
        "ADAM_AND_EVE": (51.499460, -0.135622),  # 81 Petty France
        "SANCTUARY_HOUSE": (51.499520, -0.131822),  # 33 Tothill Street
        "OLD_STAR": (51.499940, -0.133724),  # 66 Broadway
        "WESTMINSTER_ARMS": (51.500555, -0.129813),  # 9 Storey's Gate
        "TWO_CHAIRMEN": (51.500631, -0.131621),  # 39 Dartmouth Street
        "ST_STEPHENS_TAVERN": (51.501146, -0.125595),  # 10 Bridge Street
        # Not pubs
        "HOUSE_ABSOLUTE": (51.4958738, -0.1309233),
        "BIG_BEN": (51.50073, -0.12462),
        "WESTMINSTER_ABBEY": (51.49940, -0.12764),
        "PARLIAMENT": (51.49900, -0.12460),
        # Dropped from the pub list on 12 Sept 2026 and commented out rather
        # than deleted, because the committed test world was generated against
        # them: world.json's per-team `start_landmark` still spells these
        # names. Nothing resolves that field against this dict - it is printed
        # by `python -m backend.test_world world`, and the positions
        # themselves were baked into the telemetry - so the demo game and the
        # shot replay are unaffected. Uncommenting one is how a game would be
        # played at it again; that is exactly what happened to Munich Cricket
        # Club, which is back in the list above.
        # "QUEENS_ARMS": (51.492593, -0.139175),
        # "WARWICK": (51.492414, -0.139704),
        # Blue Boar cannot be used after all (Charles and Gabby found this out
        # while handing out pub certificates, 19 Sept 2026, game day itself) -
        # commented out rather than deleted, for the same reason as the two
        # above: `test_world/spec.py`'s TEAM_START_LANDMARKS used to point
        # Victoria here and has been remapped off it, but the committed
        # world.json still spells the old name in its inert `start_landmark`
        # field. Unlike Queen's Arms and Warwick, this one is already drawn
        # and labelled on `westminster.jpg` and printed on the map poster -
        # nothing re-renders that art on its own, so until somebody re-runs
        # `draw-venue-map` the map still shows a pub that the app no longer
        # offers for circles or drops.
        # "BLUE_BOAR": (51.499544, -0.132180),  # 41-47 Tothill Street
    },
)


def landmarks_from_env(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Tuple[float, float]]:
    """Every `LANDMARK_<NAME>="<lat>,<long>"` in the environment.

    A malformed one is logged and skipped rather than raised: this is read at
    import time, and a typo in a secrets file must not be the reason the
    server will not boot during a game. The admin's circle panel says which
    planned circles it could not find, which is where a missing one shows up.
    """
    environ = os.environ if environ is None else environ

    landmarks: Dict[str, Tuple[float, float]] = {}
    for key, value in environ.items():
        if not key.startswith(LANDMARK_ENV_PREFIX):
            continue
        name = key[len(LANDMARK_ENV_PREFIX) :].upper()
        try:
            lat, long = (float(part) for part in value.split(","))
        except ValueError:
            logger.warning(
                'Ignoring %s: expected a "<lat>,<long>" pair, got %r', key, value
            )
            continue
        landmarks[name] = (lat, long)

    return landmarks


VENUES = {
    "kingston": KINGSTON,
    "koyao_resort": KOYAO_RESORT,
    "westminster": WESTMINSTER,
}

ACTIVE_VENUE = VENUES["westminster"]
# ACTIVE_VENUE = VENUES["kingston"]
# The resort was a test venue, so that the map could be exercised against a
# real GPS fix while away; Westminster is where the game is actually headed.
# ACTIVE_VENUE = VENUES["koyao_resort"]

# The secret half of the active venue's landmarks, merged in at import so that
# everything downstream - the admin's landmark dropdown, the circle plan
# (backend/circles.py), the map poster's operational-prefix filter - sees one
# dict and cannot tell which half a name came from.
load_env_vars()
ACTIVE_VENUE.landmarks.update(landmarks_from_env())
