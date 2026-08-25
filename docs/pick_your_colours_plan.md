# Roadmap #10 — Let players pick their own colours

Working plan **and session handoff**. Roadmap #10 in `docs/roadmap.md` is the
one-paragraph version; this is the executable one. Delete this file when #10
ships and the roadmap entry is updated.

---

# Part 1 — Status and how to continue

## Where the work is

| Stage | State |
| --- | --- |
| **C6** Shared `Swatch` | **Committed** — `Swatch.js` + `Swatch.module.css` extracted from `AdminIdentity.js`, admin page rewired, `routes.test.js` gained an `AdminIdentity` smoke case |
| **C1** Config + team colours | **Committed** — `PROVIDED_CHANNEL`, `COLOUR_COMMONNESS`, `commonness_for`, `assign_team_colours`, `colour_capacity`, 4 tests |
| **C2** Schema | **Committed** — `Team.identity_colour`, `User.identity_wardrobe`, `set_team_identity_colour`, widened `join_team_and_claim_slot`, `_parse_overrides` → `_parse_json_column`, wardrobe in `_player_row` |
| **C3** Team join codes | Not started |
| **C4** Options + ranking + endpoints | Not started — **the core of #10** |
| **C5** Admin clear | Not started |
| **C7** The picking page | Not started |
| **C8** One QR per team | Not started |
| **C9** Docs | Not started |

## Do this first

**C1 and C2 were committed without a verified test run.** The agents that wrote
them reported passing, then died on an API session limit before a final run could
be confirmed first-hand. Before building on them:

```bash
python -m pytest tests/test_identity_allocation.py tests/test_identity_scheme.py \
                 tests/test_schema_sync.py tests/test_join_codes.py \
                 tests/test_admin_identity.py -q
cd react-ui && CI=true npx react-scripts test --watchAll=false
```

Static review found nothing wrong (`_get_team_orm` and `logger` both exist in
`admin_interface.py`; the `assign_team_colours` capacity guard is sound including
the duplicate- and stale-pinned-colour edge cases), but that is not a test run.
Fix anything that falls over before starting C3.

Note `tests/test_admin_identity.py` and `tests/test_join_codes.py` showed
intermittent flakiness that one agent reproduced on **unmodified baseline code**,
so a lone failure there is likely pre-existing and environmental. Confirm against
`git stash && pytest && git stash pop` before chasing it.

## Lessons from wave 1 — read before dispatching agents

1. **Agents ran `git` despite being told not to.** One committed its own work
   (harmless); another reverted the tree to test baseline flakiness and died
   mid-restore. Nothing was lost, but only by luck. Either state the prohibition
   far more emphatically, or give each agent its own worktree
   (`Agent(isolation: "worktree")`) so it cannot touch the shared tree.
2. **Two of three agents died on an API session limit.** Dispatch wave 2 **one
   stage at a time**, not three-up, and check the work landed after each.
3. Agents edit and test; **the orchestrator does all git**. That part was right —
   keep it.

## Suggested order from here

C3 → C4 → C5 → C7 → C8 → C9. C3 and C4 are backend and sequential (both touch
`identity_admin.py` and `main.py`). C8 depends on C3's payload shape; C7 depends
on C4's API shape and on C6 (already committed). Nothing after C4 is on the
critical path for a demo — C4 is where #10 becomes real.

---

# Part 2 — The plan

## Context

The next game is **19 September 2026**. Working backwards, #10 is the only piece
of software on the critical path: nobody can be handed an appearance card (#8,
~12 Sept) until they have chosen an appearance, and nobody can choose one until
this page exists. Target: built ~31 Aug, live to players ~7 Sept.

**Why it matters.** We provide the armbands only (#9); the t-shirt and trousers
are the player's own and the hat is bulk-bought per team. Three of four channels
depend on players owning and wearing the right colours, so letting someone choose
an outfit they *already own* is the single biggest lever on identification
accuracy on the night — plan §12.6 measures **82.8% of players in clothes they
own against 57.4%** for canonical slots.

**Today** `identity_admin.build_join_codes` mints one signed join URL *per slot*
and `claim_join_slot` claims whatever slot the scanned code carries. A player is
handed an outfit; they do not choose one.

**Slots stay.** An earlier draft removed them entirely; that was too much work
for the time available, and it also threw away the thing that gives players
guidance — without the code there are thousands of equally-blessed outfits and no
reason to prefer any of them. Canonical codewords instead become the *top of the
ranking*.

## The design

The player declares what they own and is offered a **ranked, paginated list of
outfits to choose from**. They pick; the backend does not pick for them.

**An option qualifies if it meets both constraints:**

1. **Wearable** — its t-shirt and trousers are colours the player ticked. The hat
   is fixed by their team; the armband varies freely (we supply it).
2. **At least Hamming distance 3** from every outfit already chosen — **across the
   whole game, not just the team**. Relaxed to **2** once the player has pressed
   "Yes, I'm sure I don't have any more clothes".

**Ranking is lexicographic, distance from a canonical slot first:**

| Key | Direction | Meaning |
| --- | --- | --- |
| 1. overrides needed | ascending | 0 = the outfit *is* an unclaimed Reed–Solomon codeword; 1 = one garment off; 2+ below that |
| 2. rarity | descending | summed `1 - commonness` over the **player-supplied channels only** (t-shirt, trousers) |
| 3. min distance, then symbol order | descending, ascending | deterministic tie-break |

**Distance beats rarity absolutely**: an option zero overrides from a codeword
outranks a very rare option one override away. This keeps the code doing real
work — most players end up on a canonical codeword carrying no overrides at all —
while free choice remains graceful degradation rather than the norm.

Rarity uses plan §12.6's ownership table (now `COLOUR_COMMONNESS` in
`backend/identity/config.py`): a colour few players own is a colour few
passers-by wear, which generalises plan §11.1's hard all-black exclusion into a
graded preference. It ranks only the garments the player supplies, because the
hat is fixed and the armband is ours.

**When nothing qualifies:** *"No slots found. Are you sure you don't have any more
clothes?"*, the wardrobe re-opened, and a **"Yes, I'm sure"** button that re-runs
at distance 2.

## Decisions taken — do not revisit

- Slots and the Reed–Solomon code **stay**.
- The player chooses from ranked options; the backend does not auto-seat.
- Distance is a **hard gate**; the sort key is (overrides-from-canonical, rarity).
- Rarity is scored on the **player-supplied channels only**.
- The option list is **paginated** — the candidate space is ~245 outfits.
- **The admin can clear a player's choice**, freeing the outfit. Player must ask.
- **Concurrency is guarded by a lock plus re-validation**, not optimism.
- **Cross-device loss is accepted.** The session cookie already lasts 10 years
  (`SessionMiddleware`, `backend/main.py:114`), so expiry is not the failure mode
  — a laptop pick being a different `User` row from the playing phone is. R7 puts
  an admin at the door with `AdminIdentity` open and `admin_delete_user` exists
  for the duplicate-`User` case. No resume link.
- The team's hat colour is **pinned** (`Team.identity_colour`, landed in C2).
- **No self-photograph** — that is R7, taken by the admin at the door.
- One PR on `claude/roadmap-review-ka35r8`, staged reviewable commits.

## What already exists — reuse it

Every primitive the ranking needs is pure and tested in
`backend/identity/overrides.py`:

| Helper | Its job here |
| --- | --- |
| `overlap_distance(a, b)` (`:91`) | The distance gate, against each placed player. |
| `nearest_slots(word, scheme, taken)` (`:253`) | Ranks free slots by overrides needed — **sort key 1** comes off its top result. |
| `overrides_for(word, slot, scheme)` (`:277`) | The diff to store; its `len()` is the override count. |
| `effective_word` (`:58`) | What each placed player is wearing, to measure against. |
| `pairwise_distances` (`:106`) | Used by the admin report; unchanged. |

`identity_admin.suggest_identity` (`:386`) already assembles `others`,
`taken_slots` and `avoid` from a game — mirror that preamble line for line.

**Judgement call:** the option list enumerates candidate words directly
(`itertools.product` over owned t-shirts × owned trousers × all armbands, hat
pinned) rather than calling `suggest_free_channels`. That helper ranks by max-min
distance for the *admin gate* flow and returns only a `limit` of winners,
discarding the scores needed here; this is a different, game-level preference
with a hard gate and pagination. Reuse every primitive above; only the
enumeration and sort are new.

## C3 — Team join codes

`JoinCodeModel.slot` becomes `Optional[int] = None`; `None` means a team code.
`get_signature()` is unchanged — `sign_payload("join", game, team, None)` renders
`"None"`, which no integer can collide with, so the kinds are domain-separated
for free. Keep `slot` in its current declaration position so `to_base64()` stays
byte-identical for an existing code and **every printed per-slot QR keeps
working**.

`make_team_join_url(game_id, team_id)` mints `{WEBSITE_URL}?j=<b64>` — the same
`?j=` param deliberately, so there is one QR-scanning story and the *signed
payload* decides which flow it is.

`build_join_codes(game_id)` rewritten: drop `slots_per_team` entirely (its
default of 8 exceeded the 5-slot hat bucket and forced every team into two
colours), colour teams via `assign_team_colours` writing the result back through
`set_team_identity_colour`, and give each team one `encoded_url` plus its
`capacity`. Generating therefore writes on a GET — that is the right wart, it is
the moment the admin commits to a colour and it is idempotent after the first
call; say so in the docstring.

Factor the decode+verify out of `join_game` into `_decoded_join_code(data)`.
**The `/join_game` fork:** `code.slot is None` → return
`{"needs_pick": True, team_id, team_name}` and write nothing; otherwise the
existing `claim_join_slot` path, untouched.

## C4 — Options, ranking, pagination, lock, endpoints

```python
def outfit_options(scheme, team_colour, wardrobe, game_users, user_id,
                   threshold) -> List[Option]
```

For each `(tshirt, trousers, armband)` in the product of the player's declared
colours and the full armband palette, hat pinned:

1. build the word; skip if `min(overlap_distance(word, other))` over every placed
   player is below `threshold`;
2. `slots = nearest_slots(word, scheme, taken=claimed_slots)`; skip if empty;
3. `overrides = overrides_for(word, slots[0], scheme)` — `len()` is sort key 1;
4. rarity over the wardrobe channels is sort key 2;
5. sort `(len(overrides), -rarity, -min_distance, symbols)`.

Each option carries `appearance`, `overrides_needed`, `rarity`, `min_distance`,
and a flag for `overrides_needed == 0` so the page can badge it.

Threshold comes from `scheme.code.min_distance()` (as `build_report` already
does), not a literal 3; relaxed is `threshold - 1`. **If distance 2 is also
empty** — two teammates both owning only black — fall back to the best achievable
options, clearly flagged. §12.6 is explicit that the design never refuses a
player, and there is no third button in this flow.

### Endpoints

All authorised by possession of the signed code, the trust model `/join_game`
already uses.

- **`GET /api/join_options?data=<code>`** — team name, `team_colour`,
  `wardrobe_channels`, `channels` (verbatim `_channels_payload`, with hex),
  `colour_notes` (`COLOUR_BUCKETS`, which no endpoint serves today), and `you`.
  **Non-mutating and a GET on purpose:** a team link pasted into WhatsApp gets
  prefetched, and that must not burn an outfit or create a `User` row.
- **`POST /api/outfit_options`** `{data, wardrobe, relaxed, page}` →
  `{options, page, page_size, total, threshold, relaxed}`. A POST because the
  wardrobe is a body, but it writes nothing.
- **`POST /api/pick_outfit`** `{data, wardrobe, appearance, confirmed}` → claims.

### Concurrency — a lock and a re-check, not optimism

1. **A module-level `RLock`** serialising read → validate → write, following the
   `make_user_lock` precedent in `user_interface.py:43`. The deployment is a
   single uvicorn container, so this is sufficient today; note in the docstring
   that `with_for_update` is the upgrade if it ever runs multi-process.
2. **Re-validation inside the lock** against freshly read state: the chosen
   appearance must still be wearable from the declared wardrobe, still clear the
   threshold, and its slot still be free. **Never trust the client's option** —
   it came from a snapshot.
3. **The existing in-transaction re-check stays** as the backstop.
   `join_team_and_claim_slot` already takes `overrides_json` / `wardrobe_json`
   (landed in C2).

On failure return a **distinguishable** error so the page can say *"someone just
took that"* and re-fetch — never silently substitute a different outfit.

## C5 — Admin clear

`POST /api/admin_clear_identity` `{user_id}`, admin-gated via `@admin_method`,
nulls `identity_slot`, `identity_overrides` and `identity_wardrobe`. A "Clear
outfit" button per row in `AdminIdentity.js` behind a `window.confirm` — where
the admin already stands for R7's door check.

## C7 — The picking page

**Routing.** `JoinFromQueryParams` already POSTs the code and has it in scope, so
on a `needs_pick` response it navigates to `/pick?j=<code>` instead of `/`. Keep
the 200 ms debounce, cancel-on-unmount and error `Popup`. New flat route
`{ path: "pick", element: <PickOutfit /> }` in `index.js`, deliberately **outside**
`UserMode` — no map, no webcam, no SSE, no permission polling. `PickOutfit` does
*not* strip `?j=`: reload, bookmark and sharing with teammates must work.

**`PickOutfit.js`** — dark, mobile-first, matching `OnboardingView.module.css`:

1. **Header** — "Team **Reds**", the hat swatch, *"We're bringing your red hat and
   your armband. Tell us what you'll wear underneath."*
2. **Name** — export `NameEntry` from `OnboardingView.js` with an optional
   `className`. It is already dark-styled. Without it the ticker announces
   *"None joined team Reds"* for anyone picking before onboarding.
3. **Wardrobe** — one multi-select swatch grid per `wardrobe_channels`, so a new
   channel in the scheme adds a section for free. Colours carry their
   `COLOUR_BUCKETS` gloss. Copy leans on breadth: *"Tick everything you own — the
   more you tick, the more choices you get."* 44 px minimum tap targets.
4. **Confirmation checkbox** — *"I own these and I'll wear them on the night."*
5. **Options** — paginated, ranked, grouped by override count, zero-override rows
   badged **"recommended"** so the ordering is legible. Tapping one claims it.
6. **Empty state** — *"No slots found. Are you sure you don't have any more
   clothes?"* plus **"Yes, I'm sure"** re-requesting with `relaxed: true`.
7. **Result** — the four garments large, *"This is final. Screenshot it."* A
   returning visitor with a slot sees this immediately.

Do **not** show the player `min_distance`; it is for the admin and the logs, and
its empty-`others` sentinel (`channels.n` = 4) reads as nonsense for the first
picker. Errors surface via `Popup` — `utils.js`'s global `setAPIErrorHandler` is
admin-only, and Bootstrap is admin-only too, so this page is self-sufficient CSS.
Use the shared `Swatch` from C6, setting `--swatch-border` / `--swatch-fg` on the
dark container.

## C8 — One printable QR per team

`JoinQRCodes.js`: drop the `slots_per_team` input, render one large QR per team
with the colour swatch, `"red hats"`, and `"holds 5 players at full accuracy"`
from `capacity`. That is where the ≤5 envelope is communicated — guidance, not a
block.

## C9 — Docs

`docs/roadmap.md` #10 marked shipped with what landed; `CLAUDE.md` gains `/pick`,
`PickOutfit.js`, `Swatch.js` and a line on where the ranking lives; plan §12.6
gets an "as implemented" note. Delete this file.

## Tests

**C4, new `tests/test_pick_outfit.py`** — the ones that carry the feature:

- **canonical codewords rank above overridden ones** even when the overridden
  option is much rarer — the headline rule, asserted directly;
- **within a tier, rarer outfits rank higher**;
- every option is **wearable from the declared wardrobe**, none below threshold;
- **a wardrobe that cannot clear distance 3 returns empty**, and `relaxed=true`
  returns options at distance 2;
- **three teammates all declaring only black** still get distinct outfits —
  §12.6's "never refuses a player", asserted;
- **picking works before the `User` row exists** — a client that never calls
  `/api/user_info`; plan §8.2, asserted;
- **a choice invalidated underneath the player** returns the distinguishable
  "someone just took that" error, not a substituted outfit;
- **an appearance not in the offered set is rejected** — the client is not trusted;
- **`admin_clear_identity` frees the outfit** so another player is offered it;
- pagination boundaries; idempotent revisit; missing confirmation; out-of-palette
  colour; a per-slot code passed to a team endpoint;
- `join_options` serves the palette and `colour_notes` and **creates no `User` row**.

**C3.** Team-code round-trip and tamper; team and slot codes sign differently;
`needs_pick` writes nothing; regenerating after adding a team leaves the original
colours byte-identical. **Leave every `/join_game` slot-claim test untouched** —
that block is the backward-compatibility statement for printed cards.

**C7.** `needs_pick` navigates to `/pick` carrying the code; ticking colours and
submitting renders the ranked options with the recommended badge; paging fetches
the next page; an empty list shows the "are you sure" prompt and "Yes, I'm sure"
re-requests with `relaxed`; choosing renders the result; an already-picked player
sees the result not the form.

**Do not write** (CLAUDE.md: no trivial tests): swatch rendering; `hex_for` or
`PALETTE_HEX` assertions; per-column schema tests; heading-text assertions beyond
`routes.test.js`'s first-paint anchor; that `NameEntry` still POSTs `set_name`.

## Verification

```bash
pytest -m "not selenium"
cd react-ui && CI=true npm test
pre-commit run --all-files
```

Then walk it end to end at a **mobile viewport** with the `run-mobile-app` skill:
mint a team code, open `/pick?j=...`, confirm the first player is offered
canonical codewords at the top; pick as three players in one team and confirm the
third gets different outfits; then as a fourth declaring only black, confirm the
"are you sure" flow appears and "Yes, I'm sure" produces options; finally clear
one from `/admin/identity-overrides` and confirm the outfit returns to the pool.

## Risks

- **Most players will land on a canonical codeword**, which is the point — but the
  option list is short for a narrow wardrobe and long for a wide one. The "tick
  everything you own" copy is doing real work; write it well.
- **The lock is held across a commit and is single-process.** Fine for a party
  game on one container; say so in the docstring rather than leaving it implicit.
- **Choice is first-come-first-served.** An early picker with a wide wardrobe can
  take the canonical slot a later narrow picker needed. Mitigations: the breadth
  copy, the stored `identity_wardrobe`, and the admin clear button.
- **The admin overrides page stays meaningful only because canonical ranks first.**
  `AdminIdentity.js` is "deliberately loud" about overrides to apply social
  pressure; that premise survives this design, but if the override count creeps up
  in practice the summary wording needs revisiting.
- **Slots remain the ceiling** — 34 usable, so the game caps there regardless of
  wardrobes.
- **The team code is a shareable bearer token.** One link per team means one link
  that can burn outfits in that team. `/join_game` already has this property per
  slot; the blast radius per leaked code grows from one outfit to a team.
- **`COLOUR_COMMONNESS` is estimates, not measurements** (§12.6 says so). It only
  orders options that already passed the distance gate and the canonical tier, so
  a wrong estimate costs preference order, never correctness.
