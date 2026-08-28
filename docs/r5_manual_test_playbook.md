# R5 manual test playbook — telemetry capture on a real phone

A live-fire checklist for the R5 work (PR #154): GPS accuracy, compass heading,
and the admin shot map. It is written to be run **as a pair**: Charles on a real
phone against the live instance, Claude watching the same instance from the
inside (database and admin API) and confirming what actually landed. The
automated tests already cover the plumbing; what they cannot cover is the real
sensor path — Playwright cannot fake a compass — so that is what this playbook
is for.

**Time:** ~20 minutes with one phone; +10 per extra device.
**Best devices:** one iPhone (Safari, ideally also installed to the home
screen) and one Android (Chrome). The two platforms take entirely different
code paths to a heading, so one of each is worth far more than two of either.

---

## 0. Setup (before touching the phone)

1. Deploy the branch (or merged master) to the live instance. **The schema
   changed** (`User.location_accuracy`, `Shot.heading`) and there are no
   migrations — the instance must have run `resetdb` (or `RESET_DATABASE`)
   since deploying.
2. Claude confirms from inside: both columns exist and are empty, a game and
   at least one team exist, and a join link is ready.
3. Charles: phone in hand, outdoors or near a window (GPS), no VPN weirdness,
   and know roughly which way north is (a compass app or the sun will do).

**Claude watches throughout via:** the `users` table (`location_accuracy`,
`location_timestamp`), the `shots` table (`heading`, `location_context`),
`GET /api/get_locations`, and the admin shot payloads.

---

## A. GPS accuracy (R5a)

| # | Charles does | Charles should see | Claude checks |
|---|---|---|---|
| A1 | Join the game on the phone; grant camera + location when the onboarding asks. | Onboarding proceeds as always. | `users.location_accuracy` becomes non-null within a few seconds of the map appearing; plausible magnitude (~3–30 m outdoors, worse indoors). |
| A2 | Walk indoors / stand by a window for a minute, then back out. | Nothing visible — this is capture-only. | Accuracy value changes with conditions (bigger indoors). Confirms it's live, not a one-shot. |
| A3 | — | — | `get_locations` returns `accuracy` for the player — this is the field that serialises into `location_context`, so it's the one that matters. |

**Failure signatures:** always null → the query param isn't being sent or
stored; frozen at first value → only set on first fix.

## B. Compass permission (R5b onboarding)

| # | Charles does | Charles should see | Claude checks |
|---|---|---|---|
| B1 | **iPhone, fresh state** (Safari → clear website data, or a private tab): run onboarding. | A third rung, "Grant compass permission", after location. Tapping it raises the native motion-and-orientation prompt. Grant it. | Nothing server-side — this is client-only. Charles confirms the rung marks itself done. |
| B2 | Reload the page. | The compass rung stays satisfied (the grant is remembered in localStorage — iOS can't be queried for it). | — |
| B3 | **iPhone, deny path** (clear data again): this time tap the rung and **deny**. | Onboarding still lets you continue — the compass rung must **not** gate joining. You can reach the game and fire. | The shot fired under denial has `heading = NULL` and everything else normal. This is the "telemetry never blocks firing" guarantee. |
| B4 | **Android Chrome:** run onboarding. | The rung should satisfy without a native prompt (no permission needed for `deviceorientationabsolute`). | — |

## C. Heading at the moment of the shot (R5b capture)

Do these **standing still** — that's the whole point of using the compass
rather than GPS travel heading.

| # | Charles does | Charles should see | Claude checks |
|---|---|---|---|
| C1 | Face a **known bearing** (e.g. due north, checked against a compass app), open the shoot view, fire at anything. | Shot submits normally. | `shots.heading` non-null and within ~±20° of the known bearing (phone compasses are honestly about that good; a consistent small offset is magnetic-vs-true north and fine). |
| C2 | Rotate ~90° clockwise, fire again. | — | New heading ≈ previous + 90° (mod 360). **The delta is the real test** — it cancels calibration offset. If the delta is −90°, the sign/inversion is wrong (E and W swapped). |
| C3 | Fire immediately after opening the camera (don't linger). | No delay or freeze waiting for a sensor. | Heading present (the watch runs while the camera is mounted, so the first reading should beat the shutter) — or null, which is acceptable; what's not acceptable is the shot blocking. |
| C4 | Repeat C1 on the second platform (iOS vs Android). | — | Both platforms produce sane headings. They use different events (`webkitCompassHeading` vs inverted `alpha`), so a bug here shows as one platform mirrored or offset 180° from the other. |

## D. Admin shot map

Open the admin shot queue on a laptop while the phone shots from part C are in it.

| # | Look at | Pass looks like |
|---|---|---|
| D1 | Any C-part shot | A map thumbnail next to the photo: venue map, dot where Charles was actually standing (compare against where he remembers standing — this is also the first live check of the Westminster/venue georeferencing at real coordinates). |
| D2 | The heading cone | Points the way Charles was facing when he fired (C1: the known bearing; C2: rotated 90°). Caption reads `±X m · facing NNN°` and both numbers match the DB values Claude reads. |
| D3 | The accuracy circle | Radius visibly larger for an indoors shot than an outdoors one (fire one of each if A2 showed a difference). |
| D4 | The B3 denied-compass shot | Dot and accuracy only, "no heading", no cone — and no crash. |
| D5 | A shot with no fix at all (Claude can null a test user's location in the DB, then fire) | Widget degrades to its placeholder; queue still renders. |

## E. Nothing consumes it (sanity)

| # | Check | How |
|---|---|---|
| E1 | Identification/auto-actions behave identically to before | Claude confirms the CharlesBot review payloads on the C-part shots contain no accuracy/heading terms and that verdicts are unaffected. This is the "capture only, deliberately" contract — R5 must be invisible to gameplay. |

---

## Results

Fill in as we go; anything not-passed gets a row in the notes with the failure
signature and the device.

| Section | iPhone | Android | Notes |
|---|---|---|---|
| A accuracy | ☐ | ☐ | |
| B permission (grant / remembered / deny / no-prompt) | ☐ | ☐ | |
| C heading (bearing / delta / no-block) | ☐ | ☐ | |
| D admin map (dot / cone / circle / degradation) | ☐ | ☐ | |
| E no consumption | ☐ | ☐ | |

**Known limits going in:** phone compasses drift near metal and need the
occasional figure-of-eight calibration wave; headings are magnetic (London
declination ≈ +1°, ignorable); an iOS grant lives in localStorage, so clearing
site data re-asks. None of these are bugs — a *consistent* mirror or 180°
error is.
