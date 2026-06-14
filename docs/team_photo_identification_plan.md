# Plan: Team-photo player identification via colour codes

> **Status:** design / hand-off document. This is the complete brief for a fresh
> implementation session. It captures *every* decision made so far and the
> reasoning behind it, so the implementer does not need to re-derive anything.
> Nothing in here has been implemented yet.
>
> **Branch:** `claude/team-photo-ai-categorization-q7wp08`

---

## 0. TL;DR for the implementer

Build a **self-contained, independently unit-tested Python module** that maps the
colours a player wears (read from a "shot" photo) to *which player it is*, robustly
against a hidden item or a misread colour.

- Players wear colours across **channels** (wearable slots). **Initially 3 channels:
  shirt, head, armband.**
- Each channel uses a palette of **colours**. **Initially 5 colours.** This gives
  **5² = 25 distinct player identities** using a parity (`[3,2,2]`) code.
- The number of colours, the number of channels, *and* the kind of channel
  (a channel could be shapes instead of colours) must **all be reconfigurable
  without touching the decode logic.** This extensibility is the single most
  important non-functional requirement.
- The actual matching/decoding code must live in its **own module with its own
  unit tests**, decoupled from the database, the web layer, and the vision/LLM
  call.

The chosen guarantee for the initial 3-channel / 5-colour config is:
**correct one erasure (hidden item) OR detect one misread — but not both in the
same photo.** That last gap is a deliberate, accepted compromise (see §2.4),
softened in practice by a GPS prior and confidence-weighted decoding.

---

## 1. Background: how the game works today

Streetfight is a real-world team game. Players "shoot" opponents by taking a
photo. The relevant existing flow:

- `User.submit_shot(image_base64)` (`backend/user_interface.py:249`) stores a
  `Shot` row containing:
  - `image_base64` — the photo,
  - `location_context` — a JSON snapshot of **all users' GPS locations at the
    moment the shot was fired** (`AdminInterface.get_locations(game_id)`),
  - the shooter (`user`/`team`), `shot_damage`, etc.
- An admin later reviews unchecked shots (`AdminInterface.get_unchecked_shots`,
  `backend/admin_interface.py:237`) and **manually** decides who was hit, calling
  `AdminInterface.hit_user(shot_id, target_user_id)` (`backend/admin_interface.py:319`),
  which applies damage and marks the shot checked.
- `Team` has a `name` only (e.g. "Red Team"); sample teams are seeded in
  `backend/reset_db.py` (`TEAM_COLOURS`). **There is no per-player colour data and
  no AI categorisation today.** Both are introduced by this work.

**Where this feature plugs in:** an AI step reads the target's worn colours from
the shot photo, the new module decodes those colours (plus the GPS prior) into a
**ranked list of candidate target players**, and the admin review UI surfaces the
top candidate for one-click confirmation (still calling the existing
`hit_user`). Human-in-the-loop is retained initially (see §2.4 / §8).

### Tech facts that constrain the design
- Backend is FastAPI + SQLAlchemy (`backend/model.py`), Python 3, Pillow.
- **No numpy / scipy / galois libraries are available** (see `flake.nix`
  `pythonReqs`). Keep the core module **pure-Python and dependency-free.**
  Field arithmetic mod a small prime is a few lines.
- Tests use `pytest` (config in `setup.cfg`, `tests/` directory, flat
  `test_*.py` files, fixtures in `tests/shared_fixtures.py`).

---

## 2. The identification concept and the coding-theory decisions

### 2.1 Channels, colours, codewords
- A **channel** is one categorical feature of a player's appearance that the
  vision model can read independently: shirt colour, head colour, armband colour
  (and, in future, left-arm vs right-arm separately, or a *shape* printed on the
  shirt).
- Each channel has an **alphabet** of distinguishable symbols. For colour
  channels the alphabet is the colour palette; for a shape channel it would be a
  set of shapes. **Channels may have different alphabets, but for the algebraic
  code they must share a common cardinality `q`** (see §4 — physical symbols are
  mapped onto `GF(q)` indices).
- A player's identity is a **codeword**: one symbol per channel,
  e.g. `(shirt=red, head=green, armband=blue)`.

### 2.2 The two fault types
- **Erasure** — a channel is hidden/occluded, so the vision model returns
  "unknown" for it. We *know which* channel failed.
- **Misread** — the vision model returns the *wrong* symbol for a channel and we
  don't know it's wrong.

### 2.3 The coding-theory facts (so nobody re-derives them)
- A code with minimum Hamming distance `d` can simultaneously correct `t`
  misreads and `e` erasures **iff `d ≥ 2t + e + 1`**.
- Hamming distance can never exceed the number of channels `n` (`d ≤ n`).
- Singleton bound: number of codewords `≤ q^(n − d + 1)`. MDS codes (parity,
  Reed–Solomon) meet it with equality.

Consequences for `n = 3` channels:
| Requirement | Needs `d` | Possible at n=3? | Codewords at q=5 |
|---|---|---|---|
| Correct 1 misread **and** 1 erasure (both at once) | 4 | **No** (`d ≤ 3`) | — |
| Correct 1 erasure **and** *detect* 1 misread (both at once) | 3 | Yes, but forces a **repetition code** → only `q` codewords (would need 25 *colours* for 25 players) | 5 |
| Correct 1 erasure **OR** detect 1 misread (not both at once) | 2 | Yes — `[3,2,2]` parity code | **25** |

### 2.4 The decision we made (and the compromise)
We are sticking with **3 channels and 5 colours initially**, which means the
**`[3,2,2]` parity code**, `d = 2`, **25 identities**.

- **Erasure alone → corrected.** Any single hidden channel is reconstructed from
  the parity relation.
- **Misread alone (nothing hidden) → detected.** The parity check fails, so we
  know the read is inconsistent (we can't say *which* channel is wrong, so we
  flag rather than auto-correct).
- **Erasure + misread in the same photo → THE COMPROMISE.** With one channel
  hidden we spend the two survivors reconstructing it and have no check left; if
  one survivor is also misread, the module can silently produce the **wrong**
  identity. This is the accepted limitation of staying at 3 channels.

**Mitigations for the compromise** (these are *why* it's acceptable):
1. The **GPS prior** — a reconstructed identity that maps to a player nowhere
   near the shooter is implausible and gets down-weighted.
2. **Confidence-weighted (soft) decoding** — the vision model's per-channel
   confidences feed a likelihood, so a low-confidence survivor doesn't get
   treated as gospel.
3. **Human-in-the-loop** — the admin confirms the top candidate.

### 2.5 The upgrade ladder (must be a drop-in, not a rewrite)
If the compromise proves unacceptable, the fix is to add a channel and/or
colours and swap the code. The module must make this a config change only:

| Config | Code | Guarantee | Capacity |
|---|---|---|---|
| **3 channels × 5 colours** (initial) | `[3,2,2]` parity | correct 1 erasure **or** detect 1 misread | 25 |
| 4 channels × 5 colours | `[4,2,3]` (MDS/RS) | correct 1 erasure **and** detect 1 misread (and correct a lone misread) | 25 |
| 5 channels × 5 colours | `[5,2,4]` (MDS/RS) | correct 1 erasure **and** 1 misread together | 25 |
| 3 channels × 7 colours | `[3,2,2]` parity | same as initial | 49 |

Capacity for an `[n, k]` code is `q^k`. Parity codes have `k = n−1` (capacity
`q^(n−1)`). More colours raise capacity; more channels raise either capacity or
distance depending on which code you pick.

---

## 3. Configuration decisions to bake in (but keep changeable)

| Decision | Initial value | Must be configurable? |
|---|---|---|
| Channels | `shirt`, `head`, `armband` (3) | **Yes** — add/remove/reorder channels |
| Colours per channel | 5: red, yellow, green, blue, purple | **Yes** — add colours (raises `q`) |
| Channel alphabet kind | all colour palettes | **Yes** — e.g. a `shape` channel with a shape alphabet |
| Code | `[3,2,2]` sum-parity over GF(5) | **Yes** — swap to RS/MDS as in §2.5 |
| Player capacity target | 25 | derived from `q^k`; raise via colours/channels |
| Guarantee | correct-1-erasure-or-detect-1-misread | derived from the code's `d` |

> **Prime-field constraint (document it):** the algebraic code uses `GF(q)`
> arithmetic. The simple, dependency-free implementation supports `q` =
> **prime** (5, 7, 11, …). 5 is prime so the initial config is fine. Non-prime
> prime powers (e.g. 4, 8, 9) would need `GF(p^m)` arithmetic — out of scope;
> if you need exactly those counts, either round up to the next prime number of
> colours or implement extension-field arithmetic later. Capacities like 6 →
> use 7 colours.

---

## 4. Architecture — the new pure module (the centrepiece)

Create a package `backend/identity/` containing **only pure logic**: no
SQLAlchemy, no FastAPI, no Pillow, no network. This is what gets independently
unit-tested. Layering (each layer depends only on the ones above it):

```
backend/identity/
  galois.py     # GF(p) prime-field arithmetic (add/sub/mul/inv mod p)
  code.py       # LinearCode: codewords, min distance, encode; factory for parity / MDS
  channels.py   # Channel (name + ordered physical labels) and ChannelSet; label<->index maps
  scheme.py     # IdentityScheme: binds a ChannelSet + a LinearCode + player<->codeword assignment
  observations.py # data types for a per-channel reading (distribution or erasure) + priors
  decoder.py    # soft decoder: observations + prior -> ranked posteriors + ambiguity/inconsistency flag
  config.py     # the initial, declarative config (3 channels, 5 colours, parity) and a factory
```

The crucial abstraction boundary: **the decoder and the scheme depend only on
the abstract `LinearCode` interface (a set of codewords over `GF(q)`) and the
abstract `ChannelSet`.** Swapping the parity code for RS, adding a channel, or
growing `q` constructs a *different* `LinearCode`/`ChannelSet` — the decoder and
all integration code are untouched. That is the extensibility guarantee.

---

## 5. Component specifications

### 5.1 `galois.py`
- Minimal prime-field arithmetic: `add`, `sub`, `mul`, `inv`, `neg` mod a prime
  `p`, validated `p` is prime. Inverse via Fermat (`a^(p−2)`) or extended
  Euclid. ~30 lines, no deps.
- This is all the algebra the parity *and* MDS codes need.

### 5.2 `code.py` — `LinearCode`
- Represents a code over `GF(q)` of length `n`. Public surface:
  - `n`, `q`, `k` (message length), `capacity = q**k`,
  - `codewords()` → iterable of `n`-tuples of ints in `[0, q)`,
  - `min_distance()` → int (compute by brute force over codeword pairs; fine for
    these tiny codes, and lets tests assert the theoretical `d`),
  - `encode(message)` → codeword (message is a `k`-tuple over `GF(q)`),
  - optionally `is_codeword(word)` and `syndrome(word)`.
- **Factory functions:**
  - `parity_code(n, q)` → `[n, n−1, 2]` code: valid iff `sum(symbols) % q == 0`.
    This is the initial code (`parity_code(3, 5)`).
  - `reed_solomon_code(n, k, q)` → `[n, k, n−k+1]` MDS code (evaluation of degree
    `<k` polynomials at `n` distinct points of `GF(q)`; requires `n ≤ q`). Used
    for the `[4,2,3]` and `[5,2,4]` upgrades.
  - A small `build_code(n, q, target_distance)` convenience that returns a parity
    code when `target_distance == 2`, else an RS code, and **raises a clear error
    if the request is infeasible** (e.g. `d=4` at `n=3`, or RS with `n > q`).
- Brute-force `min_distance` doubles as the test oracle (assert `[3,2,2]`→2,
  `[4,2,3]`→3, `[5,2,4]`→4).

### 5.3 `channels.py`
- `Channel`: `name` (e.g. `"shirt"`) + `labels` (ordered list of physical symbol
  names, e.g. `["red","yellow","green","blue","purple"]`). Provides
  `label_to_index` / `index_to_label`. A channel may have **more** labels than
  `q` (uses the first `q`, or validates `len(labels) >= q`); different channels
  may have **different** label lists (colours vs shapes) but must each supply at
  least `q` symbols.
- `ChannelSet`: ordered list of `Channel`s; length must equal the code's `n`.
  Converts a codeword (tuple of `GF(q)` indices) ↔ a dict of
  `{channel_name: label}` ("what the player physically wears").

### 5.4 `scheme.py` — `IdentityScheme`
- Binds a `ChannelSet` + a `LinearCode` + an **assignment** of player IDs to
  codewords. Public surface:
  - `assign(player_ids)` → deterministic mapping `player_id → codeword`
    (raise if more players than `capacity`),
  - `appearance(player_id)` → `{channel_name: label}` (what to tell a player to
    wear / what to print on a costume sheet),
  - `codeword_of(player_id)` and reverse `player_of(codeword)`,
  - hands the codeword set + channel metadata to the decoder.
- **Assignment policy:** store a stable integer "slot" (`0 .. capacity-1`) per
  player and derive the codeword via `encode(slot_as_message)`. Storing the slot
  (not the raw colours) means re-deriving colours if the scheme parameters
  change — but note (see §8) that changing `q`/channels mid-game changes what
  everyone wears, so treat scheme parameters as fixed per game.

### 5.5 `observations.py`
- `ChannelObservation`: per channel, either
  - a **distribution** `{label_or_index: probability}` over that channel's
    alphabet (preferred — this is what a good vision model can emit), or
  - a single best `symbol` + `confidence` (convenience; expand internally to a
    distribution: `confidence` on the symbol, the rest spread over the others), or
  - **erasure** (`None`) — channel unreadable.
- `Reading`: an ordered set of `ChannelObservation`s (one per channel).
- `Prior`: `{player_id: probability}` (from GPS, §8) — optional; defaults to
  uniform over the candidate set.

### 5.6 `decoder.py` — the soft decoder (the heart)
- `decode(reading, candidates, prior=None)` →
  `DecodeResult(ranked=[(player_id, posterior), ...], flags=...)`.
- **Likelihood model.** For a candidate player with codeword `c`:
  `likelihood(c) = ∏_channels L_i`, where for channel `i`:
  - erased → `L_i = 1` (contributes no information),
  - observed as distribution `O_i` → `L_i = O_i[c_i]` (probability the vision
    model assigned to the *true* symbol; use a small floor `ε` to avoid zeros),
  - observed as `(symbol s, confidence p)` → `L_i = p` if `c_i == s` else
    `(1 − p)/(q − 1)`.
- **Posterior:** `posterior(player) ∝ prior(player) · likelihood(codeword)`,
  normalised over candidates.
- **Flags / graceful generalisation of the hard guarantees:**
  - `inconsistent` — no codeword matches a clean (no-erasure) reading well
    (this is "detect a misread"),
  - `ambiguous` — top-2 posteriors within a margin (tie),
  - `confident` — top posterior above a threshold.
  These thresholds are config; the admin UI uses them to decide auto-suggest vs
  flag-for-review.
- The decoder is **completely independent of the vision/LLM and the DB** — tests
  feed `Reading`s and priors directly.

### 5.7 `config.py`
- Declarative initial config + a `default_scheme()` factory:
  - palette = `["red","yellow","green","blue","purple"]`,
  - channels = `shirt`, `head`, `armband` (all using the palette),
  - code = `parity_code(3, 5)`,
  - thresholds for the decoder flags.
- Changing the initial setup = editing this one file (add a colour to the
  palette; add a `Channel`; switch to `reed_solomon_code(...)`).

---

## 6. Worked extensibility scenarios (prove each is a small change)

The implementer should keep these in mind and ideally cover them with
parametrised tests:

1. **Add a 6th/7th colour.** Append labels to the palette; bump `q` to the next
   prime (e.g. 7) in `config.py`. `parity_code(3, 7)` → capacity 49. Decoder,
   scheme, channels unchanged.
2. **Split armband into left + right (4 channels).** Add a `Channel`; change the
   code to `reed_solomon_code(4, 2, 5)` (`[4,2,3]`) for the stronger guarantee,
   or `parity_code(4, 5)` (`[4,3,2]`, capacity 125) to just raise capacity. Only
   `config.py` changes.
3. **Add a "shape" channel.** New `Channel(name="shape",
   labels=["circle","square","triangle","star","cross"])` — a *different*
   alphabet of the same cardinality `q=5`. The vision adapter must learn to read
   shapes for that channel, but the code/scheme/decoder are unchanged because
   they operate on `GF(q)` indices, not on the physical meaning.
4. **Upgrade the guarantee without changing colours/channels count?** Not
   possible at fixed `n` (it's the `d ≤ n` ceiling). Document that the only way to
   buy more fault tolerance is more channels — this is a property of the math,
   surfaced clearly so future-you doesn't fight it.

---

## 7. Testing plan (the explicit "independently unit tested module" requirement)

Tests live in `tests/` (flat `test_identity_*.py`, matching repo convention),
import **only** from `backend.identity`, and use **no DB, no network, no
Pillow** — so the module is provably standalone. Suggested files/cases:

- `test_identity_galois.py` — field axioms: `a + (-a) == 0`, `a * inv(a) == 1`
  for all non-zero `a` in GF(5) (and GF(7)); rejects composite `p`.
- `test_identity_code.py`
  - `parity_code(3,5)`: capacity 25, `min_distance == 2`, every codeword sums to
    0 mod 5, `encode` round-trips.
  - `reed_solomon_code(4,2,5)` → `d == 3`; `(5,2,5)` → `d == 4`.
  - `build_code(3,5,4)` and `reed_solomon_code(6,2,5)` raise clear infeasibility
    errors.
- `test_identity_channels.py` — label↔index round-trips; rejects a channel with
  fewer than `q` labels; supports heterogeneous alphabets (a shape channel).
- `test_identity_scheme.py` — assignment is unique and deterministic; raises when
  players > capacity; `appearance` ↔ `codeword` consistency.
- `test_identity_decoder.py` — the behavioural core, parametrised over configs:
  - clean reading → correct player, posterior ≈ 1.
  - **single erasure** → still the correct player (parity correction).
  - **single misread, no erasure** → `inconsistent` flag raised (detection); for
    the `[4,2,3]` config the same case instead *corrects* to the right player.
  - **erasure + misread together on the parity config** → assert the documented
    limitation (may be wrong / ambiguous), then assert that supplying a GPS-style
    **prior** recovers the correct player. This test *encodes the compromise* so
    it can't regress silently.
  - prior alone breaks a tie when the reading is ambiguous.
  - **Re-run the whole behavioural suite under the 4-channel `[4,2,3]` config** to
    prove the decoder is config-agnostic and the upgrade path works.

---

## 8. Integration plan (separate from the pure module)

Keep all of the following **outside** `backend/identity/` so the module stays
pure. These are follow-on tasks; the pure module + its tests are the priority
deliverable.

### 8.1 Vision adapter (the only externally-dependent piece)
- New module e.g. `backend/identity_vision.py` (note: depends on the Anthropic
  API + Pillow; **not** part of the pure package). Responsibility: given a shot
  image, return a `Reading` (per-channel symbol distributions or erasures).
- Implement behind an interface so the decoder/tests never need it. Provide a
  fake/stub implementation for local dev and tests.
- Prompt design: ask a current **vision-capable Claude model** to report, for
  each named channel (shirt, head, armband), the palette colour it sees *or*
  `"obscured"`, plus a confidence, as structured JSON. Include the palette names
  (and ideally reference swatches) in the prompt. Confirm the exact current model
  ID at implementation time (see the `claude-api` reference) and default to the
  latest, most capable vision Claude model. *(Do not hard-code a model identity
  that may be stale — read it from config/env.)*

### 8.2 Storing each player's identity
- Add a nullable column to `User` (`backend/model.py`) for the player's identity
  **slot** (integer) — the codeword is derived via the scheme, so storing the
  slot keeps the DB decoupled from the colour palette. Expose it in `UserModel`.
- Admin assigns slots when setting up a game; provide a way to print/export each
  player's `appearance` (what to wear) — extend `generate_qr_items.py`-style
  tooling or a simple admin endpoint.
- **Migration/consistency note:** the scheme parameters (palette, channels, code)
  are effectively fixed for the life of a game, because changing them changes
  what every player must physically wear. Treat a parameter change as a new game
  setup, not a live migration.

### 8.3 GPS prior
- Build a `Prior` from the shot's existing `location_context` JSON (already
  stored — no schema change needed): candidate set = **alive players on other
  teams**; weight ∝ a decreasing function of distance from the shooter's recorded
  location (start simple: inverse or Gaussian of metres). Put this helper in the
  integration layer, not the pure module (it knows about `Shot`/`User`).

### 8.4 Admin-assist flow
- When an admin opens an unchecked shot, run: vision adapter → `Reading`; build
  GPS `Prior`; `decoder.decode(...)` → ranked candidates. Surface the top
  candidate (and `flags`) in the admin review UI as a one-click pre-fill for the
  existing `hit_user(shot_id, target_user_id)`. **Keep the human confirm step**
  given the parity code's both-faults gap. Full automation can come later (and is
  safer once on the `[4,2,3]` upgrade).

---

## 9. Out of scope / future / open questions

- **Full automation** of `hit_user` (only after the stronger code + field
  validation).
- **Extension-field `GF(p^m)`** arithmetic (only needed for non-prime colour
  counts like 4/8/9; round to a prime instead for now).
- **Distance-optimised assignment** for arbitrary `(n, q, P)` where no neat
  algebraic code exists (greedy/search packing) — not needed for the initial
  configs.
- **Shooter orientation / aim** as a stronger spatial prior (currently only
  proximity).
- Open question for the implementer to confirm with the product owner: exact
  palette of 5 colours that are maximally distinguishable on camera (the choice
  directly affects the misread rate). Current placeholder:
  red / yellow / green / blue / purple.

---

## 10. Concrete file list & suggested commit sequence

1. `backend/identity/galois.py` + `tests/test_identity_galois.py`
2. `backend/identity/code.py` (parity + RS + factory) + `tests/test_identity_code.py`
3. `backend/identity/channels.py` + `tests/test_identity_channels.py`
4. `backend/identity/observations.py`
5. `backend/identity/scheme.py` + `tests/test_identity_scheme.py`
6. `backend/identity/decoder.py` + `tests/test_identity_decoder.py` (incl. the
   compromise + upgrade-config tests)
7. `backend/identity/config.py` (`default_scheme()`)
8. *(integration, separate PRs)* vision adapter, `User` slot column + model,
   GPS prior helper, admin-assist wiring.

Keep commits 1–7 free of DB/web/vision imports so the module's independence is
self-evident.

---

## 11. Reference: the initial concrete code (`[3,2,2]` over GF(5))

Palette index ↔ colour: `0=red, 1=yellow, 2=green, 3=blue, 4=purple`.

Players pick **shirt** and **head** freely (5 × 5 = 25 identities); the
**armband** is the parity symbol so that `(shirt + head + armband) ≡ 0 (mod 5)`,
i.e. `armband = (−shirt − head) mod 5`. Because the relation is symmetric, **any
single hidden channel** can be reconstructed from the other two.

Armband colour as a function of (shirt = row, head = column):

| shirt ↓ \ head → | red(0) | yellow(1) | green(2) | blue(3) | purple(4) |
|---|---|---|---|---|---|
| **red(0)**    | red    | purple | blue   | green  | yellow |
| **yellow(1)** | purple | blue   | green  | yellow | red    |
| **green(2)**  | blue   | green  | yellow | red    | purple |
| **blue(3)**   | green  | yellow | red    | purple | blue   |
| **purple(4)** | yellow | red    | purple | blue   | green  |

Decode behaviour for this table:
- **All three read, parity holds** → unique player.
- **One channel "obscured"** → reconstruct it via the parity relation → unique
  player (erasure corrected).
- **All three read, parity fails** → a misread happened somewhere → flag
  `inconsistent` (detected, not corrected).
- **One obscured *and* one of the other two misread** → may resolve to the wrong
  player with no warning → this is the accepted compromise; lean on the GPS prior
  and the admin confirm step.

For the upgrade configs (`[4,2,3]`, `[5,2,4]`), construct the code with
`reed_solomon_code(...)`; the same decoder and integration code apply unchanged.
