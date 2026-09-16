# Figures for the "Clothes, colours, and error correction" essay

The essay lives in `react-ui/src/prose.js` (`prose.howItWorks.content`) and
renders at `/how-it-works`, linked from the outfit picker's footer. Its
audience is the interested layman: a player who has just chosen a t-shirt
colour and wants to know why they were only offered some of them.

Three figures were agreed. **F3 is built and live.** F1 and F2 are
commissioned artwork and render as dashed placeholders until their SVG
arrives (`react-ui/src/HowItWorksFigures.js`, marked `PLACEHOLDER
START/END`).

## Principles the three share

- Draw people and clothes, not axes and symbols.
- The caption carries the punchline as a full sentence. This reader looks at
  the figures and skims the prose between them.
- No jargon inside the picture: "three things would have to go wrong", never
  "d = 3".
- Label every swatch with its colour name — for the colour-blind, and because
  those names are the words the player typed when they picked.
- Dark background (`#000`, white text): the page is the picker's frame.
- Phone first. The column is 130 mm wide at most; assume 320 px.

## F1 — What the camera actually gives us

**Photograph chosen: shot `121f91cb` from the 30 August trial game**, Mermaid
shooting Tom. It and the runners-up are extracted into
`docs/how_it_works_figures/`:

| file                                       | what it is                                                                                        |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| `f1-chosen-square-crop.jpg`                | **the one to hand to Claude Design** - `121f91cb` cropped square about the crosshair, 1080 x 1080 |
| `f1-chosen-one-garment-wrong-121f91cb.jpg` | the same shot uncropped, as the phone took it                                                     |
| `f1-alt-same-mistake-again-c57aa5d1.jpg`   | runner-up: the same player, the same misread, by a different shooter                              |
| `f1-alt-hat-not-visible-4109d545.jpg`      | runner-up: dim hallway, hat unreadable                                                            |
| `f1-alt-nothing-readable-b0cc305d.jpg`     | runner-up: out-of-focus shoulder, nothing readable                                                |
| `f1-alt-perfect-read-3f32def2.jpg`         | runner-up: all four garments read correctly                                                       |
| `f1-alt-jacket-over-shirt-84a94623.jpg`    | runner-up: a jacket over the t-shirt                                                              |

They came out of the archive at
`/home/charles/Nextcloud/Archives/streetfight/streetfight-game-archive-2026-08-30`,
where the photographs are base64 columns in `data/db/data.db`, table `shots`,
keyed by the first four bytes of `id`. The marked-up copies under
`data/logs/images/` are named after the **shooter**, not the person in the
frame, which is an easy way to pick the wrong photograph.

Why this one: all four garments are visible and namable by a reader who has to
check the machine's homework, Tom is looking straight down the lens so it
reads as a photograph of a person rather than a surveillance still, and there
is a second player behind him — which is honestly what the identification
problem looks like. Most usefully, CharlesBot got exactly one garment wrong,
which is the essay's whole argument in a single real example.

| garment  | he registered | CharlesBot read | confidence |
| -------- | ------------- | --------------- | ---------- |
| t-shirt  | **blue**      | **black**       | 0.95       |
| trousers | off-white     | off-white       | 0.90       |
| hat      | burgundy      | burgundy        | 0.95       |
| armband  | purple        | purple          | 0.95       |

Resolved as a hit on him anyway. The escalation pass, which gets the reference
photo taken at the door, called it at 0.99 — "clearly recognizable from his
beard, burgundy cap, and purple armbands".

The misread is a fair one twice over. The shirt is a very dark navy in indoor
light, and the scheme's `blue` swatch is `#0072CE`, a much brighter blue than
the garment he actually owns — so the mistake is partly the room and partly
the width of the word. `c57aa5d1`, a different shooter twenty minutes later,
makes the identical call, which is how we know it is the shirt and not the
photograph.

Runners-up, if a different story is wanted:

- `c57aa5d1` — Jordan shooting Tom. Same one-garment mistake, better lit, and
  he is laughing. Rejected only because the square crop clips the cap and the
  trousers and puts somebody else's lime armband in the foreground, which is
  four garments' worth of confusion in a figure about four garments.
- `4109d545` — a figure at the end of a dim hallway, small in frame, shooting
  back. Three garments read correctly, the hat genuinely not visible. "One
  garment missing costs you nothing."
- `b0cc305d` — an out-of-focus shoulder and a glowing phone. Nothing readable
  at all; the escalation model also said "unsure"; a human ruled it. Funny,
  and the honest illustration of the essay's last paragraph.
- `3f32def2` — all four garments right at 0.95–0.98. The easy case, for
  contrast.
- `84a94623` — she put a jacket on over her t-shirt, so the model read green
  where her shirt is purple. The failure mode is not blur, it is coats.

**Two things to know before using any of them.**

They are photographs of identifiable friends, and this repository is public,
so a file committed here is published whether or not the figure ever ships.
Ask the person first, and prefer somebody who is looking at the camera — a
player posing for the shot has already agreed to be photographed, which a
player caught from behind has not. `9a4904b2` was the original choice here and
was withdrawn on 2026-09-16 for exactly this reason.

And **the registered outfit and the worn outfit disagree in a lot of that
archive**, so check a candidate against the register before building on it.
Two players swapped headwear during the evening: Doug's record says a black
hat and a lime armband, but he is read in a salmon cap in five separate shots
and a burgundy cap plus blue armbands in `76ba95b1`; Dee's record says
burgundy, and he is read in green in `b3a26e2b` and black in `901f3ad7`. Those
are not model errors, and a figure built on one would be wrong. `76ba95b1` is
the trap worth naming: CharlesBot reads all four of Doug's garments
**correctly**, and because he had borrowed the hat and bands, the outfit it
reads is Dee's registered codeword exactly. A human ruled it a hit on Doug by
recognising his face. It is a real and interesting photograph, but it argues
the opposite of what F1 is for.

### Brief for Claude Design

> A figure for a dark-background essay read on a phone, 320 px wide, about
> identifying people in photographs by the colours they wear. One column, three
> stacked panels, no chrome.
>
> Panel 1: the photograph I have supplied, already cropped square. The
> subject is the bearded man in the centre of the frame wearing a backwards
> burgundy cap, a near-black navy shirt, a purple wristband on the raised arm
> and tan cargo trousers - _not_ the man behind his shoulder in the salmon
> cap. Put a thin crosshair at the centre of the frame, which is where the
> shooter aimed; it lands on his chest.
>
> Panel 2: the same person reduced to four labelled colour blocks in a row —
> t-shirt / trousers / hat / armband — as the machine sees him. Each block
> carries the colour name the machine reported: **black**, off-white,
> burgundy, purple. Mark the t-shirt block as the one it got wrong, in a way
> that does not rely on colour alone to say so, since the block itself is a
> colour.
>
> Panel 3: the same four blocks in the colours he registered — **blue**,
> off-white, burgundy, purple — with one short line of text: three of four
> right is enough.
>
> One thing to get right in panel 3: his shirt really is almost black in that
> light, so do not paint a vivid primary blue block that the reader can see
> contradicts the photograph above it. Draw it as the dark navy it is and let
> the _name_ carry the difference. That is the point of the panel — the
> machine and the player used two different words for one garment.
>
> Caption is set by the page, so leave room but do not include it. White text
> on black, one accent colour of your choosing for the "wrong" marker. Deliver
> as a single inline SVG with no external references, no embedded fonts, and
> text as real `<text>` elements rather than paths.

## F2 — Spot the difference

Nothing real to photograph: this one is drawn.

### Brief for Claude Design

> A figure for a dark-background essay read on a phone, 320 px wide, one
> column. It makes one point: if two people's outfits differ by a single
> garment, one mistake confuses them; if they differ by three, no single
> mistake can.
>
> Top half, labelled something like "the obvious way": two simple standing
> figures side by side, each wearing four coloured garments — hat, t-shirt,
> armband, trousers. They are identical except the hat: one green, one navy.
> Beneath them, a dark blurry photograph of one of them and an arrow to the
> _wrong_ name, with a short line: one hat misread, wrong person.
>
> Bottom half, labelled "what we actually do": the same two people, but now
> three of the four garments differ. Same blurry photograph, same single
> mistake, arrow to the right name.
>
> Keep the figures schematic — flat blocks of colour, no faces, no detail.
> Every garment labelled with its colour name. The two halves must read as a
> before and after at a glance on a phone. White text on black. Deliver as a
> single inline SVG, no external references, no embedded fonts, text as real
> `<text>` elements.

## F3 — The 49 safe outfits (built)

`FigureCodewordGrid` in `react-ui/src/HowItWorksFigures.js`, drawn from
`GET /api/how_it_works` (`backend/how_it_works.py`).

A 49 × 49 grid — 2401 cells, one per possible outfit. Rows are the pair the
player chose (t-shirt, trousers), columns the pair we hand out (hat, armband).
The 49 codewords are lit, and because the code is MDS with k = 2, any two
garments determine the other two: exactly one cell is lit in each row and each
column. `tests/test_how_it_works.py` asserts that rather than trusting it.
Slot 0 — black head to toe, never handed out — is drawn hollow.

**Orange cells are players wearing something the codebook never offered**, put
there by an override because they owned no shirt in any colour the scheme
could give them. They are off the constellation by construction, so they get
their own colour rather than being drawn as though they were codewords; they
are anonymous, since this is the whole roster and thirty names would bury the
figure. A player whose override _blanks_ a channel has no single cell to sit
in — they are along a line rather than at a point — and is left out rather than
drawn somewhere untrue. A faint dotted crosshair runs the full width and height
through the reader's own cell: the row is everyone who shares their t-shirt and
trousers, the column everyone who shares their hat and armband.

The reader's own outfit is ringed in yellow and their three nearest
neighbours in grey, each ring labelled with the player's name. Their size is set as an
inline style rather than a `font-size` attribute, because `index.css`'s global
`* { font-size: 12px }` is a CSS declaration and beats any presentation
attribute — the same trap `SpectatorView.js` documents. Those names are placed
by `placeLabels`, which nudges them apart rather than letting two be
drawn through each other and keeps them inside the figure; anything that had to
move gets a leader line back to its ring. That matters because the row of the
grid _is_ the t-shirt and trousers, so two players who nearly clash land on the
same line a few cells apart — the labels collide exactly when the reader most
needs to tell those two apart. (Only one codeword sits in each row, so a
same-row pair means at least one of them has overridden a garment.) A player who
overrode a garment sits on an unlit cell, which is correct and worth noticing
rather than hiding.

**Position on that square says nothing about how alike two outfits are.** The
axes are an ordering of pairs, not a distance: the closest two lit cells on
screen are three garments apart, and so are cells in opposite corners. Worse,
half of every codeword's neighbours sit at exactly the minimum distance — 24 of
the other 48 — so in a thirty-player game roughly fifteen people are equally
the closest, and which three get rings is an arbitrary tiebreak on roster
order. That is why the panel below leads with the _count_
(`closest_count`) rather than presenting three names as a ranking. If the
figure ever reads as "these three are dressed like me and those others are
not", it is lying, and the honest fixes are to ring everyone at the minimum
distance or to ring nobody.

Neighbours are **named** (Charles's call, 2026-09-16). It does tell a player
the outfits of the three people most easily confused with them, which is real
information in a game where everyone is hiding — but knowing who you might be
mistaken for is the part of the scheme a player can act on, and it is what
makes the figure about them rather than about the maths.

## What the page tells a player who has picked

Below F3, `YourOutfit` shows the hat and armband they will be handed at the
door — which nothing else in the app tells them — the t-shirt and trousers
they chose, and how many garments away the nearest other outfit in their game
is.
