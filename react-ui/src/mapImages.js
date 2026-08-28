// The one part of a venue (backend/venues.py) that can't live on the server:
// map images have to be imported so webpack bundles them. The server names one
// of these keys in `venue.map.image` and we resolve it here.
//
// Adding a venue means dropping its map into ./images/ and adding a line below.

// TODO: TEMPORARY - test venue only, remove along with KOYAO_RESORT in
// backend/venues.py. Satellite imagery of Koyao Island Resort, Ko Yao Noi,
// Thailand, so the map can be exercised against a real GPS fix while I'm away.
// Imagery (c) Esri, Maxar, Earthstar Geographics and the GIS User Community.
import koyaoResort from "./images/map_koyao_resort.jpg";
import kingston from "./images/map.png";
// Westminster drawn in the Kingston style, traced from OpenStreetMap: 1.3 x
// 1.3 km centred on House Absolute. Placeholder for a hand-drawn map, but the
// streets are accurate. Traced from map data (c) OpenStreetMap contributors,
// ODbL.
import westminster from "./images/map_westminster.jpg";

const MAP_IMAGES = {
  kingston,
  koyao_resort: koyaoResort,
  westminster,
};

export default MAP_IMAGES;
