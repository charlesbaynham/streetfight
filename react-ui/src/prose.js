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
  // @section curiosityFooter
  curiosityFooter: {
    linkText: "Interested in what's happening here?",
  },
  // @section fireButton
  fireButton: {
    fireButtonAlt: "Fire button",
    // Said when the server turns a shot down (M1.1). The reason comes from
    // the backend, so it is not in here; this is the frame around it, and the
    // fallback for a refusal that arrived with nothing to say. Both are put
    // on screen by RefusedNotice, which the scanner below shares.
    shotRefused: (reason) => `Shot not taken: ${reason}`,
    shotRefusedUnknown: "Shot not taken. Try again.",
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
    // The essay is long-form, so `content` is a sequence of blocks rather
    // than one string: a "paragraph" is plain text (or JSX, where a sentence
    // needs markup - same rule as everywhere else in this file), and a
    // "figure" names one of the components in HowItWorksFigures.js and
    // carries its caption. The figures are numbered F1-F3 in
    // docs/how_it_works_figures.md, which is also where the briefs for the
    // two commissioned ones live.
    content: [
      {
        type: "paragraph",
        text: "We are using machine vision to figure out who has shot whom based on a photograph of them. But, our photos will be blurry, might be taken in the dark, might be far away, and people will be actively trying not to be photographed. That makes the job hard.",
      },
      {
        type: "figure",
        figure: "cameraRead",
        caption:
          "A real shot from the trial game. The computer is not trying to recognise a face - it is trying to read four colours off you, and here it got one of them wrong and still knew who you were.",
      },
      {
        type: "paragraph",
        text: "To fix this, we try to make the algorithm's life easier by using something that is easier to see: big blocks of colours. You have been asked to choose from 7 possible colours for both your trousers and your shirt. On the night, Gaby and I will also give you a hat and an armband for a total of four different pieces of clothing. That means there's 7^4 = 2401 possible combinations, each of which could identify a single person.",
      },
      {
        type: "paragraph",
        text: "However, we don't have 2401 friends. And, it's not very helpful to pick colours such that even a single mistake is enough to trick the computer into thinking the photo is of someone else. We would prefer to choose particular outfits for everyone, such that even if the computer gets one colour wrong or can't see your hat, it can still figure out who you are.",
      },
      {
        type: "figure",
        figure: "spotTheDifference",
        caption:
          "Two players one garment apart: misread a single hat and the machine names the wrong person. Spread the same two outfits three garments apart and one mistake changes nothing.",
      },
      {
        type: "paragraph",
        text: (
          <>
            This is the field of <em>error correction</em>. Simple "Hamming
            code" error correction was developed in the 50s and was used to
            correct errors in computer memory, which used to go wrong much more
            often back then. The more modern Reed-Solomon algorithm extends this
            to encodings that have more than just two possible symbols (i.e.
            rather than a bit that is 0 or 1, we have a hat that can be one of 7
            colours) and is used from correcting for scratched CDs to sending
            messages to Voyager 1, billions of km away.
          </>
        ),
      },
      {
        type: "paragraph",
        text: 'We are using a [4, 2, 3] Reed-Solomon scheme - n=4 symbols (trousers, shirt, armbands, hat); k=2, meaning any two of your four garments are enough to say who you are and the other two are the safety net; and a d=3 "Hamming distance" - the minimum number of errors that we would need to make to misidentify a player. This means that we can only fit 48 players in our game (49 outfits, one of which is black from head to toe and never handed out), but that we can still identify you even if we can only see two of the four items of clothing.',
      },
      {
        type: "figure",
        figure: "codewordGrid",
        caption:
          "Every outfit anyone could wear, as one cell of a square: across, the hat and armband; down, the shirt and trousers. The 49 we actually use are lit - notice how, because any two garments determine the other two, exactly one is lit in each row and column. Orange marks a player who swapped a garment for something they already owned, which puts them off the pattern; the dotted lines run through you.",
      },
      {
        type: "paragraph",
        text: "That's still not quite enough however: it turns out that colour matching blurry photos is hard, and we often make more than 2 mistakes. To iron out these edge cases, we also use a Bayesian calculation to guess the probability of who the person in the photo is, based on their last known location and proximity to the shooter along with the probability of having made mistakes in the vision. As a final resort, we rank the top candidates in order of probability and then compare the photo against reference photos that we took when you joined the party, using a large language model.",
      },
    ],
    figures: {
      // F1 and F2 are drawn artwork rather than components, so their `alt` is
      // the only description a screen reader gets - the caption says what the
      // figure argues, the alt says what is in it.
      cameraRead: {
        alt: "A photograph of a player, the four colours the machine read off him - black, off-white, burgundy, purple - and the four he registered, which differ only in that his t-shirt is blue.",
      },
      spotTheDifference: {
        alt: "Two players whose outfits differ only in the hat, where one misread hat names the wrong person, and the same two spread three garments apart, where the same misread still names the right one.",
      },
      codewordGrid: {
        across: (garments) => `across: the ${garments} we hand you`,
        youLabel: (name) => name || "you",
        down: (garments) => `down: the ${garments} you chose`,
        alt: (used, total) =>
          `A square of ${total} possible outfits with ${used} of them marked, one in each row and each column.`,
      },
    },
    yourOutfit: {
      heading: "Which brings us to you",
      // The garments are named as they are handed over, not as the database
      // spells them.
      garmentNames: {
        tshirt: "t-shirt",
        trousers: "trousers",
        hat: "hat",
        armbands: "armband",
      },
      garmentName: (name) =>
        prose.howItWorks.yourOutfit.garmentNames[name] || name,
      garment: (name, colour) =>
        `${colour || "?"} ${prose.howItWorks.yourOutfit.garmentNames[name] || name}`,
      weHandYou: "At the door we will hand you:",
      youPicked: "You chose:",
      noneYet:
        "Pick an outfit and this page will tell you which hat and armband you are getting, and how close anyone else comes to wearing what you are.",
      neighboursHeading: "Who is dressed like you?",
      neighbourName: (name) => name || "somebody",
      // The count matters: about half the scheme sits at exactly the minimum
      // distance, so naming three without saying how many share that distance
      // would claim a ranking that does not exist.
      neighboursIntro: (distance, count) =>
        `${count === 1 ? "One player is" : `${count} players are`} ${distance} garments away from you. Somebody would have to get all ${distance} of those colours wrong at once to mistake you for them. Here are your three closest:`,
      apart: (distance) =>
        distance === 1 ? "1 garment apart" : `${distance} garments apart`,
    },
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
    closeMapSymbol: "x",
  },
  // @section nextEvent
  nextEvent: {
    // The strip at the top of every phone: what the game has cued up, and how
    // long is left. The label and the clock are separate entries because the
    // clock is a live component between them, not a value to interpolate.
    circleLabel: "Circle closes in",
    dropLabel: "Drop in",
    // At zero the countdown has run out but the server has not necessarily
    // announced yet, so these say what is happening rather than leaving a
    // stopped 00:00 on screen.
    circleNow: "The circle is closing",
    dropNow: "The courier has set off",
    // Whatever the admin typed about the drop - its contents, in practice -
    // set off from the countdown rather than run into it.
    note: (note) => `— ${note}`,
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
    // The sound check (see useSoundCheck.js). Once it has been tapped the row
    // keeps an instruction rather than congratulating the player: we know they
    // pressed it, we have no idea whether they heard it, and the phone being on
    // silent is the whole failure this is here to catch.
    soundCheck: "Turn your sound on, then tap to test it:",
    soundCheckDone: "Heard that? If not, take your phone off silent.",
    // Lowercase, unlike pickOutfit.channelDisplayNames - this reads as part
    // of a sentence ("white t-shirt"), not a fieldset legend.
    garmentNames: { tshirt: "t-shirt", armbands: "armband" },
    outfitNotChosen: "Outfit not chosen",
    outfitChosen: (summary) => <>Outfit: {summary}</>,
    // The hat and armband, said the way they are handed over - "at the door"
    // and not "provided", since that is where and when the player meets them.
    // The label is its own entry so a test can find the row by it without
    // copying the words out of here.
    doorKitLabel: "At the door:",
    outfitProvided: (summary) => (
      <>
        {prose.onboardingView.doorKitLabel} {summary}
      </>
    ),
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
    // Players supply these two garments themselves, so the name must read as
    // a body part rather than a dress code: somebody in shorts or a skirt
    // needs to know the trousers row is theirs too.
    channelDisplayNames: {
      tshirt: "T-shirt / top",
      trousers: "Trousers / shorts / skirt",
    },
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
    joinProgressAriaLabel: "Join progress",
    progressPercent: (percent) => `${percent}%`,
    noInviteLinkNote: "No invite link found - ask for the sign-up link again.",
    loadingNote: "Loading...",
  },
  // @section popup
  popup: {
    scrollHintLabel: "Scroll down for more",
  },
  // @section qrScanner
  qrScanner: {
    // Said when the game turns a scanned code down. The reason comes from the
    // backend - "This code has been withdrawn", "Medpacks can only be used on
    // knocked-out players", "You have already got this weapon" - so it is not
    // in here; this is the frame around it. Before this the only answer was a
    // flash of red, which told the player that something was wrong and
    // nothing at all about what.
    scanRefused: (reason) => `Not collected: ${reason}`,
    scanRefusedUnknown: "That code was not collected. Try again.",
    // The phone never reached the server. Worth saying: from where the player
    // is standing a card that cannot be submitted looks exactly like a card
    // that does not work.
    scanOffline: "Could not reach the game. Check your signal and try again.",
  },
  // @section radar
  radar: {
    // The band at the top of the screen while a radar card is running. The
    // clock is a live component between the two, not a value to interpolate.
    stripLabel: "Radar",
    stripTail: "left",
    // Beside each contact on the map. The card promises where somebody was
    // last seen and never where they are, so every dot says its own age.
    lastSeen: (minutes) => `${minutes} min ago`,
    justNow: "just now",
    out: "out",
  },
  // @section refusedNotice
  refusedNotice: {
    dismiss: "Dismiss",
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
  // @section teamLeader
  // The leader's checklist. Charles has not supplied his own wording yet, so
  // this is the milestones doc's first draft (M7). Each item is something the
  // leader can look at and answer yes or no to for every member of their team
  // - "knows the rules" is not on the list, because nobody can check it.
  teamLeader: {
    buttonText: "Team leader",
    heading: "You are a team leader",
    intro:
      "Before the game starts, go round your team and check each of these. " +
      "Nobody else is going to.",
    checklist: [
      "Everyone has the app open, with the camera and location allowed.",
      "Everyone has scanned the team card, and the app says the right team.",
      "Hats and armbands are on, and match the colours the app shows.",
      "Everyone has had their photo taken at the desk.",
      "Everyone knows they have to wait between shots, and that a pub code is worth ammo to the whole team.",
    ],
    footer: "Anything you cannot fix, ask the admin before the game starts.",
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
  // @section whatIsThis
  // The landing page somebody who is not in the game gets at "/"
  // (WhatIsThis.js): they scanned a card off a lamppost, or were sent the
  // bare URL. Deliberately a dead end - it explains and it offers the essay,
  // and it has no way into a game, because the people it is written for were
  // not invited.
  whatIsThis: {
    logoAlt: "Streetfight",
    heading: "What is this?",
    intro: [
      "You have probably found a QR code stuck to something, or picked up a card with one on it. It belongs to a game called Streetfight, which a group of friends are playing around this town.",
      'It works roughly like this. Everyone is put into a team and handed a hat and an armband. You "shoot" somebody by photographing them: a computer reads the colours of the clothes in the picture, works out which player it is looking at, and takes a hit point off them. Codes like the one you have found are hidden around the place, and are worth ammunition, armour or a medical kit to whoever scans them first.',
      "It is a private game between friends - a party, really - so there is nothing here to sign up to, and the code you have found will not do anything without an invitation.",
      "If it was hidden rather than handed to you or stuck on a wall, please do put it back where it was. Somebody is out looking for it.",
    ],
    // The essay (HowItWorks.js). Players reach it from the outfit picker and
    // the waiting page instead, through CuriosityFooter.
    mathsLinkText: "How the clothes and the camera work",
    // A mailto link sits inside the sentence, so this is one of the few
    // places a JSX function is the right shape - see the conventions above.
    contact: (emailLink) => (
      <>
        Contact Charles Baynham on {emailLink} if you&rsquo;re interested and
        want to know more.
      </>
    ),
    contactEmail: "charles.baynham@gmail.com",
  },
};

export default prose;
