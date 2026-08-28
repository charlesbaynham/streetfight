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
// OpenStreetMap tiles of Westminster, zoom 17, 3 x 3 km centred on Monck
// Street. Map data (c) OpenStreetMap contributors, ODbL; tiles from
// openstreetmap.org under CC BY-SA.
import westminster from "./images/map_westminster.jpg";

const MAP_IMAGES = {
  kingston,
  koyao_resort: koyaoResort,
  westminster,
};

export default MAP_IMAGES;
