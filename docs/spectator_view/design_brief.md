# Spectator screen — design brief

> **Fulfilled, 2026-08-29.** The design session answered this brief and its
> `SpectatorView.module.css` is what ships. Kept as the record of what was
> asked for, and as the starting point if the screen is ever redesigned.
>
> What came back went past a repaint, and the page grew to match it:
>
> - **The white map** (hazard 1) is handled by toning the *page* towards the
>   map — a warm, low-chroma dark that reads as shadow around a lit table, the
>   map knocked back a stop and vignetted. Nothing inverted.
> - **Burgundy vs rust** (hazard 3) is handled with a team letter inside each
>   dot (`data-letter`). The letters have to be *distinct*, which is why
>   `teamLetters()` is not simply `name[0]`: with Blue holding "B", Burgundy
>   takes something else.
> - **Two new faces.** A **shot takeover** — a new shot's photograph gets the
>   room, holds while CharlesBot works, and leaves two seconds after the first
>   conclusion ("escalating" counts) — and a **gallery** of the recent shots
>   large. The screen alternates map (90s) and gallery (45s); the takeover
>   overlays either.
>
> Screenshots of all three faces are in this directory:
> `spectator_screen.jpg`, `shot_takeover.jpg`, `gallery_face.jpg`.
>
> Two things the brief could not have told the designer, found on integration:
>
> - `index.css` carries a global `* { font-family: ...; font-size: 12px }`. A
>   universal selector beats inheritance, so every element taking its face or
>   size from an ancestor rendered as 12px Lucida. There is now a scoped
>   integration shim at the top of the module. **A redesign will still need
>   it**, and it is the first thing to suspect if type comes out wrong.
> - The takeover frame is 600×900, so `THUMBNAIL_MAX_DIMENSION` went from 320
>   to 900. Anything smaller upscales and goes soft on a television.
>
> Everything below is the brief as it was sent.

---

**This file is a prompt.** Paste the whole thing into a Claude design session.
Everything below the rule is addressed to that session; everything above it is
notes for whoever is doing the pasting.

The page is built and working (`react-ui/src/SpectatorView.js`, route
`/admin/spectator`). What it does not have is a considered visual design — it
was styled plainly enough to be legible and no further, deliberately, so that
the design could be done properly somewhere else.

The page is structured so a restyle is **one file**:
`react-ui/src/SpectatorView.module.css`. The JSX emits semantic class names and
carries no layout of its own. A design session should hand back a replacement
for that file (and nothing else).

`spectator_screen.jpg` in this directory is the current state, captured at
1920×1080 against a seeded 26-player game.

---

## What this is

A live dashboard for a game of Streetfight — a real-life, team-based, mobile
game played around a town. Players photograph each other to "shoot"; an admin
(and increasingly an AI called **CharlesBot**) adjudicates the photographs.

This particular page is for the people **not** playing: players who have been
knocked out, and friends who came along to watch. It runs on a laptop wired to
a big TV in a pub, logged in as admin, and then **left alone for the whole
evening**. Nobody touches it. Nobody scrolls it. It has to be readable from
about three metres away, in a room that is probably dim, for four hours.

It is read-only. Nothing on it is clickable and nothing it does changes the
game.

## The five things on it

| Region | What it is |
| --- | --- |
| **Headline** | Wall clock, and how many players are still alive out of the total. A "Paused" flag when the game is not running. |
| **Map** | The venue map with a dot per player, moving as they move. Dots are coloured by team and go grey when the player is out. Game circles (exclusion / next / drop) are drawn on it. |
| **Shot feed** | The last six shots, newest first. Each has the photograph the shooter actually took, who fired, and a sentence saying where its adjudication has got to. |
| **Roster** | Every player: team colour, name, armour, ammo, weapon, and score. Living players first, then knocked-out (with a countdown to revival), then dead. Above it, per-team totals. |
| **Ticker** | The game's own announcements — "Bob was knocked out", drops, admin messages. |

## Rules that are not yours to change

These carry meaning, not taste:

1. **State is said in words, never by colour or icon alone.** "CharlesBot
   looking…", "Hit on Bob", "back in 6:22". A colour may reinforce a word; it
   may not replace one.
2. **Green and red are answers. Amber is the machine being unsure.** This is
   consistent across the whole admin surface and people rely on it. In the CSS
   these are `.good`, `.bad`, `.warn`. There is also `.thinking` (currently
   blue) for "still in progress" — in-flight, not uncertain.
3. **A team's colour on the map and in the roster must be the same colour.**
   Reading a dot back to a name is the main thing the screen is for. Both come
   from one resolver in the JS; don't let the CSS diverge them.
4. **Nothing may require interaction to be seen.** No hover, no tooltips, no
   scrolling, no tabs, no carousel. If it does not fit, it must shrink or be
   cut deliberately — see the roster hazard below.

## The known hazards

These are the things that will actually bite. They are the brief.

**1. The map is a huge white rectangle.** This is the biggest visual problem
on the page and the most interesting thing to solve. The venue map is
hand-drawn black-line-on-white artwork (`react-ui/src/images/`), and it is
about 60% of the screen. On a dark page in a dim pub it glares. Options
include toning the page toward the map rather than away from it, treating the
map panel as a deliberate light "table" the dark UI sits around, filtering the
image, or something better. It should not simply be inverted — it is nice
artwork and it is the real venue.

**2. The roster is the piece most likely to overflow.** A real game is up to
about 30 players. It is currently two CSS columns, which fits 26 at 1080p with
little room to spare. It cannot scroll, because nobody is there to scroll it.
Decide what happens at 30, at 40: smaller type, three columns, or showing only
the living and counting the rest. A silent clip is the one unacceptable
outcome.

**3. Two teams' colours can be nearly the same.** Team colours come from the
hat each team wears, and the hat palette is measured from real kit rather than
designed for contrast — burgundy and rust are 14.2 ΔE2000 apart and will read
alike across a room. Every dot currently gets a ring to lift it off its
background, but that does not separate burgundy from rust. A shape, a letter,
or a pattern per team would.

**4. Long names and long words.** Player names are free text. Weapon names
include "Tracka-Tracka" and "Eat-a-bullet" and are currently truncated to 7
characters, which is ugly. CharlesBot's verdict sentences can run long
("CharlesBot thinks: hit - probably Alice (0.7) or Bob (0.6)").

**5. The empty states are what it looks like for the first hour.** Before
anything happens: no shots fired, nobody dead, every score zero, players
trickling in. It should look intentional then, not broken.

## Data shapes

Realistic values, so nothing is designed against fiction.

- **Alive count**: 23 of 26. Early on, 26 of 26.
- **Player row**: name `"Alice"`, `2 armour`, `0 ammo`, weapon `"OMG"`, score `5`.
  Armour is 0–3 and usually 0 or 1. Ammo is 0–9. Score is total damage dealt,
  usually 0–12. Weapons: `No weapon`, `Pewster`, `Tracka-Tracka`, `OMG`,
  `Eat-a-bullet`.
- **Team totals**: `Red Team · 6 alive · 5 dmg`. Four to six teams of about five.
- **Knocked out**: shows `back in 6:22` counting down from ten minutes, instead
  of stats. Then `dead`.
- **Shot feed statuses**, in the order a shot passes through them:
  - `CharlesBot looking...` (`.thinking`)
  - `Escalated to the stronger model...` (`.thinking`)
  - `CharlesBot thinks: hit on Bob` (`.thinking`)
  - `Waiting for the admin` (`.warn`)
  - `CharlesBot errored - over to the admin` (`.warn`)
  - `Hit on Bob` (`.good`) — the resolved verdict
  - `Miss` / `Bystander` (`.bad`), `Refunded` (`.warn`)
- **Shot thumbnails**: 320px JPEGs of phone photos, often dark, blurry and
  badly framed. Sometimes the target is tiny.
- **Ticker line**: `"Zeb has joined team Yellow Team"`, `"Alice killed Bob!"`.

## The CSS contract

Rewrite `react-ui/src/SpectatorView.module.css`. The class names below are what
the JS emits; keep them all. The file currently opens with a token block on
`.screen` (`--bg`, `--panel-bg`, `--panel-border`, `--ink`, `--ink-dim`,
`--good`, `--bad`, `--warn`, `--thinking`, `--font`, the `--size-*` scale,
`--gap`, `--radius`) — keep that idea, change the values freely.

```
.screen                                   the whole viewport
  .headline
    .headlineTitle .headlineClock .headlineAlive .headlinePaused
  .body
    .mapPanel                             the map fills this box
    .sidebar
      .panel > .panelTitle                (used twice)
        .shotList > .shot
          .shotThumb | .shotThumbPlaceholder
          .shotBody > .shotWho > .shotShooter .shotArrow .shotTarget
                    > .shotStatus + one of .good .bad .warn .thinking
        .teamTotals > .teamTotal > .teamDot .teamName .teamStat
        .roster > .rosterRow + one of .alive .knockedOut .dead .waiting
                   > .teamDot .rosterName .stat .statWeapon .rosterState .score
  .ticker > ul > li
  .empty                                  "No shots fired yet." etc.
```

Constraints on the markup: `.teamDot` takes its colour from an inline
`background` set in JS, so style everything about it *except* the fill.
`.mapPanel` contains a third-party pan/zoom component that expects to fill its
box. Target 1920×1080 as the design size; it does not need to be responsive
below about 1280 wide.

## Out of scope

The layout regions and what data appears in them were settled with the
project's owner and should stay. What is open is everything about how it looks:
palette, type, density, hierarchy, the map treatment, how a shot card is
composed, how the roster is arranged, whether the ticker is a strip or
something else.

One thing genuinely absent rather than undesigned: there is **no elapsed game
clock**, because a game records neither a name nor a start time. The headline
shows the wall clock instead. If a design wants "2:14 into the game", say so
and it can be added — it needs a schema change, which is deliberate work
against a live database rather than a styling decision.
