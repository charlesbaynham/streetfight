// Every piece of prose a *player* sees lives here, one section per component,
// so it can be reviewed and edited in one place (and localised later without
// touching the views). Admin pages are deliberately not included.
//
// Conventions:
//   - plain strings for fixed text;
//   - arrow functions for text with values in it, e.g. `(name) => `Shot by ${name}``;
//   - JSX is allowed where a sentence carries markup that cannot be split
//     without mangling it (this is a .js file under CRA, so JSX compiles).
// Keys are camelCase and describe the *role* of the text, not its wording.

const prose = {
  // @section addToHomeScreen
  addToHomeScreen: {},
  // @section blankScreen
  blankScreen: {},
  // @section bulletCount
  bulletCount: {},
  // @section collectItems
  collectItems: {},
  // @section fireButton
  fireButton: {},
  // @section fullscreenButton
  fullscreenButton: {},
  // @section guideImages
  guideImages: {},
  // @section howItWorks
  howItWorks: {},
  // @section joinFromQueryParams
  joinFromQueryParams: {},
  // @section mapView
  mapView: {},
  // @section myWebcam
  myWebcam: {},
  // @section newItems
  newItems: {},
  // @section onboardingView
  onboardingView: {},
  // @section pickOutfit
  pickOutfit: {},
  // @section popup
  popup: {},
  // @section qrParser
  qrParser: {},
  // @section scoreboard
  scoreboard: {},
  // @section shotHistory
  shotHistory: {},
  // @section shotReceivedOverlay
  shotReceivedOverlay: {},
  // @section swatch
  swatch: {},
  // @section temporaryOverlay
  temporaryOverlay: {},
  // @section tickerView
  tickerView: {},
  // @section updateListener
  updateListener: {},
  // @section userMode
  userMode: {},
  // @section utils
  utils: {},
  // @section weapons
  weapons: {},
  // @section webcamView
  webcamView: {},
};

export default prose;
