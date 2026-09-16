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

import React from "react";

const prose = {
  // @section addToHomeScreen
  addToHomeScreen: {
    appName: "Streetfight",
  },
  // @section bulletCount
  bulletCount: {
    ammoLabel: "Ammo:",
    armourLabel: "Armour:",
    appealsRemaining: (n) => `Appeals: ${n}`,
  },
  // @section fireButton
  fireButton: {},
  // @section fullscreenButton
  fullscreenButton: {
    fullscreenAlt: "Fullscreen",
    fullscreenHintAlt: "This app is better in fullscreen",
  },
  // @section guideImages
  guideImages: {
    deadAlt: "You Died",
    knockedOutTitle: "You are knocked out",
    medkitWarning: "Get a medkit quick! You will die in:",
  },
  // @section howItWorks
  howItWorks: {},
  // @section joinFromQueryParams
  joinFromQueryParams: {
    joinFailed: "Could not join the game",
  },
  // @section mapView
  mapView: {
    mapAlt: "Map",
    closeMapLabel: "Close map",
    closeMapSymbol: "×",
  },
  // @section myWebcam
  myWebcam: {},
  // @section onboardingView
  onboardingView: {
    logoAlt: "Streetfight, by Charles and Gaby",
    namePlaceholder: "Enter your name...",
    webcamPermission: "Grant webcam permission:",
    locationSkipped: "Location skipped — no map",
    locationPermission: "Grant location permission:",
    locationError:
      "Couldn't get your location — check Settings > Privacy > Location Services, then tap again.",
    compassPermission: "Grant compass permission:",
    joinTeamPrompt: (hasOutfit) =>
      (hasOutfit ? "Outfit picked. " : "") +
      "At the door, scan a team's QR code with your camera app to join a team...",
    inTeam: (teamName, identitySlot) =>
      `You are in team "${teamName}"` +
      (identitySlot !== null && identitySlot !== undefined
        ? ` — outfit #${identitySlot}`
        : ""),
    waitForGame: "Wait for game to start...",
  },
  // @section pickOutfit
  pickOutfit: {},
  // @section popup
  popup: {
    scrollHintLabel: "Scroll down for more",
  },
  // @section scoreboard
  scoreboard: {
    playerHeader: "Player",
    teamHeader: "Team",
    armourHeader: "Armour",
    damageHeader: "Damage",
    showScoresButton: "Show scores >>",
  },
  // @section shotHistory
  shotHistory: {
    hudLabel: "My shots >>",
    listTitle: "My shots",
    backButton: "<< All shots",
    yourShotAlt: "Your shot",
    appealReasonsFired: [
      ["actually_hit", "It actually hit"],
      ["wrong_target", "It hit someone else"],
    ],
    appealReasonsReceived: [
      ["missed", "It missed me"],
      ["wrong_target", "That wasn't me"],
      ["not_a_player", "That's not a player"],
      ["already_out", "I was already out"],
    ],
    appealOpenLabel: "Under appeal",
    appealUpheldLabel: "Appeal upheld",
    appealRejectedLabel: "Appeal rejected",
    hitYouLabel: (shooterName) =>
      `Hit you!${shooterName ? ` - shot by ${shooterName}` : ""}`,
    shotAtYouLabel: (shooterName) =>
      `Shot at you${shooterName ? ` - shot by ${shooterName}` : ""}`,
    hitLabel: (targetName) => (targetName ? `Hit ${targetName}!` : "Hit!"),
    ammoRefunded: "Ammo refunded",
    invalidated: "Invalidated",
    invalidatedSublabel:
      "You were knocked out before this shot could be checked",
    shotBystander: "You shot a bystander!",
    shotBystanderSublabel: "Not a player - no damage done",
    missed: "Missed",
    charlesBotThinks: (suggestion) => `CharlesBot thinks: ${suggestion}`,
    charlesBotHitOn: (targetName) => `CharlesBot thinks: hit on ${targetName}`,
    charlesBotHitUnknown: "CharlesBot thinks: hit - can't tell who",
    escalatedSublabel: "Escalated to referee",
    notReviewed: "Not reviewed yet",
    firedWith: (weapon) => `Fired with ${weapon}`,
    youAppealed: (reasonText) => `You appealed: ${reasonText}`,
    appealButtonLabel: "Appeal",
    noAppealsLeftLabel: "No appeals left",
    appealPromptTitle: "What was wrong with it?",
    appealsLeftText: (remaining, total) =>
      `Are you sure? You have ${
        remaining === null ? "..." : remaining
      } of ${total} appeals left.`,
    appealsRefundNote: "Successful appeals are refunded.",
    appealSubmitFailed: "That appeal could not be lodged",
    appealConfirmButton: "Appeal this shot",
    appealCancelButton: "Cancel",
  },
  // @section shotReceivedOverlay
  shotReceivedOverlay: {
    knockedOut: "You are knocked out",
    dead: "You are dead",
    hitPointsLeft: (points) =>
      `${points} hit point${points === 1 ? "" : "s"} left`,
    headline: "You have been shot",
    shooterBy: (shooterName) => `by ${shooterName}`,
    okButton: "OK",
    appealButton: "Appeal this shot",
  },
  // @section swatch
  swatch: {},
  // @section userMode
  userMode: {
    loading: "Loading...",
  },
  // @section weapons
  weapons: {
    noWeapon: "No weapon",
    pewster: "Pewster",
    trackaTracka: "Tracka-Tracka",
    omg: "OMG",
    eatABullet: "Eat-a-bullet",
  },
  // @section webcamView
  webcamView: {},
};

export default prose;
