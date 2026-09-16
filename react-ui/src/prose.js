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
  fireButton: {
    fireButtonAlt: "Fire button",
  },
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
  howItWorks: {
    heading: "Clothes, colours, and error correction",
    // PLACEHOLDER START - scaffolding awaiting Charles's essay. Unlike the
    // rest of this file, the essay is long-form, so `content` is a sequence
    // of blocks rather than one string: a "paragraph" is plain text (or JSX,
    // where a sentence needs markup - same rule as everywhere else in this
    // file), and a "diagram" carries a JSX figure - an image, an inline SVG,
    // whatever the point needs - plus its caption.
    content: [
      {
        type: "paragraph",
        text: "I haven't written this yet! So you'll have to ask me. Though if you want, you could google Hamming distances and Reed-Solomon codes. And then ask me why I don't get a proper job.",
      },
    ],
    // PLACEHOLDER END
    backToGame: "Back to the game",
  },
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
    // Lowercase, unlike pickOutfit.channelDisplayNames - this reads as part
    // of a sentence ("white t-shirt"), not a fieldset legend.
    garmentNames: { tshirt: "t-shirt" },
    outfitNotChosen: "Outfit not chosen",
    outfitChosen: (summary) => `Outfit: ${summary}`,
    joinTeamPrompt: (hasOutfit) =>
      (hasOutfit ? "Outfit picked. " : "") +
      "Join a team by scanning the QR code on the night...",
    inTeam: (teamName, identitySlot) =>
      `You are in team "${teamName}"` +
      (identitySlot !== null && identitySlot !== undefined
        ? ` — outfit #${identitySlot}`
        : ""),
    waitForGame: "Wait for game to start...",
  },
  // @section pickOutfit
  pickOutfit: {
    channelDisplayNames: { tshirt: "T-shirt" },
    alreadyJoinedNote: "You already joined a team:",
    signUpHeading: "Sign up",
    teamHeading: (teamName) => `Team ${teamName}`,
    wardrobePrompt: "Choose your uniform...",
    wardrobeIntro: () => (
      <>
        <p>
          We need you to wear particular colours on the night, so the game can
          tell who you are. This sign-up page makes sure that you don't clash
          with other players.
        </p>
        <p>
          To give you as many options as possible, please leave ticked{" "}
          <strong>all the colours you could wear</strong>, so you'll be offered
          lots of choices.
        </p>
      </>
    ),
    changeWhatIOwnButton: "Change what I own",
    wardrobeAnythingFallback: "anything",
    recommendedBadge: "preferred",
    notIdealBadge: "not ideal",
    chooseAriaLabel: (description) => `Choose: ${description}`,
    exactMatchHeading: "Exact match",
    coloursDifferentHeading: (count) =>
      `${count} colour${count === 1 ? "" : "s"} different`,
    findingOutfitsButton: "Finding outfits...",
    showMeOutfitsButton: "Show me outfits",
    noOutfitsFoundNote:
      "No outfits found. Are you sure you don't have any more clothes?",
    yesImSureButton: "Yes, I'm sure",
    exhaustedNote:
      "These are the best options we could find - sorry for the limited choice.",
    showMoreOutfitsButton: "Show more outfits",
    previousButton: "Previous",
    nextButton: "Next",
    pageOf: (page, totalPages) => `Page ${page} of ${totalPages}`,
    confirmHeading: "One more step to join",
    confirmIntro: () => <>Your chosen outfit:</>,
    wearCheckboxLabel: "I will wear this on the night.",
    nameRequiredNote: "Enter your name above first.",
    lockingInButton: "Locking in...",
    lockInButton: "Lock in my choice",
    chooseDifferentOutfitButton: "Choose a different outfit",
    resultHeading: "You're set",
    nextStepNote:
      "You're signed up. On the night, scan a team code at the door to join a team.",
    finalNote: "",
    goToGameButton: "Go to the game",
    enterGameNote: "",
    askAdminNote:
      "Please do wear these clothes! Ask Charles if you need to change your outfit",
    curiosityFooter: "Interested in what's happening here?",
    joinProgressAriaLabel: "Join progress",
    progressPercent: (percent) => `${percent}%`,
    noInviteLinkNote: "No invite link found - ask for the sign-up link again.",
    loadingNote: "Loading...",
  },
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
  swatch: {
    unknownTitle: "not in palette",
    unknownSymbol: "?",
  },
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
};

export default prose;
