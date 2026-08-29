"""Named places inside the Westminster crop, for saying where a shot happened.

An encounter is a pair of coordinates; a scene description needs a *place* --
"on Strutton Ground" rather than "at 51.4977, -0.1345" -- both because the
image model needs to know what the background looks like and because the
required distribution of scenes is expressed in these terms (six street, three
park or open ground, one forecourt).

Coordinates are approximate, to perhaps fifty metres. That is deliberate and
sufficient: they are used to attach the nearest name to an encounter, never to
position anything. ``backend.venues`` remains the authority on anything the
game itself measures.
"""

from typing import Dict
from typing import List
from typing import NamedTuple

from backend.test_world import geo


class Locale(NamedTuple):
    name: str
    kind: str  # "street" | "park" | "forecourt"
    lat: float
    long: float
    description: str


LOCALES: List[Locale] = [
    # --- streets -----------------------------------------------------------
    Locale("Horseferry Road", "street", 51.4953, -0.1330,
           "a wide four-storey street of offices and mansion blocks, plane trees at the kerb"),
    Locale("Marsham Street", "street", 51.4952, -0.1290,
           "a broad street under the coloured glass slabs of the Home Office"),
    Locale("Great Peter Street", "street", 51.4970, -0.1300,
           "a narrow brick street of Victorian workshops turned offices"),
    Locale("Strutton Ground", "street", 51.4977, -0.1345,
           "a short pedestrianised market street, shutters down, stall frames stacked"),
    Locale("Victoria Street", "street", 51.4980, -0.1350,
           "a wide glass-fronted commercial street, buses and a broad pavement"),
    Locale("Vauxhall Bridge Road", "street", 51.4930, -0.1398,
           "a busy arterial road, four lanes, railings along the pavement"),
    Locale("Regency Street", "street", 51.4930, -0.1330,
           "a quiet residential street of red-brick estate blocks"),
    Locale("Page Street", "street", 51.4938, -0.1300,
           "the chequerboard black-and-white Grosvenor Estate blocks"),
    Locale("Rochester Row", "street", 51.4948, -0.1370,
           "a modest high street of small shops and a church"),
    Locale("Tothill Street", "street", 51.4995, -0.1330,
           "a canyon of pale stone office frontages near the park"),
    Locale("Millbank", "street", 51.4955, -0.1250,
           "the riverside road, wide pavement, the Thames wall on one side"),
    # --- parks and open ground --------------------------------------------
    Locale("Vincent Square", "park", 51.4930, -0.1370,
           "a large flat playing field ringed by railings and plane trees"),
    Locale("Victoria Tower Gardens", "park", 51.4975, -0.1245,
           "a riverside park of mown grass and london planes, the Thames beyond"),
    Locale("St John's Gardens", "park", 51.4948, -0.1315,
           "a small enclosed churchyard garden, benches and dense shrubs"),
    Locale("Christchurch Gardens", "park", 51.4985, -0.1355,
           "a pocket park of gravel paths and old headstones set against a wall"),
    Locale("Parliament Square", "park", 51.5006, -0.1265,
           "a wide grass square ringed by statues and heavy traffic"),
    # --- forecourts --------------------------------------------------------
    Locale("Westminster Abbey forecourt", "forecourt", 51.4995, -0.1275,
           "a paved forecourt under the abbey's west towers, railings and floodlights"),
    Locale("Methodist Central Hall forecourt", "forecourt", 51.4998, -0.1295,
           "a stone-flagged forecourt below a domed neoclassical hall, steps up to columns"),
    Locale("Home Office forecourt", "forecourt", 51.4945, -0.1295,
           "a hard-landscaped plaza with low planters and security bollards"),
    Locale("Channel 4 forecourt", "forecourt", 51.4948, -0.1322,
           "a glass-and-steel corporate forecourt, polished paving, a sculptural canopy"),
]

BY_KIND: Dict[str, List[Locale]] = {}
for _locale in LOCALES:
    BY_KIND.setdefault(_locale.kind, []).append(_locale)

_POINTS = [geo.to_m(loc.lat, loc.long) for loc in LOCALES]
_EAST = [float(p[0]) for p in _POINTS]
_NORTH = [float(p[1]) for p in _POINTS]


def nearest(east: float, north: float) -> Locale:
    """The named place an encounter at these metres-coordinates happened at."""
    best = min(
        range(len(LOCALES)),
        key=lambda i: (east - _EAST[i]) ** 2 + (north - _NORTH[i]) ** 2,
    )
    return LOCALES[best]


def distance_to_nearest_m(east: float, north: float) -> float:
    """How far the nearest named place is -- a sanity check, not a filter."""
    import math

    loc = nearest(east, north)
    index = LOCALES.index(loc)
    return math.hypot(east - _EAST[index], north - _NORTH[index])
