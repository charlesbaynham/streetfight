# A0 — coordinator findings (found while standing the harness up)

These were not on anyone's checklist. They surfaced while building the test
harness, and both are session/identity bugs that R9's per-feature list would
not have caught because they only appear with **more than one client at once**
— which is exactly the condition on the night.

## Cuts across everything: the player's browser session

### Finding: every cookieless client shares one player identity

**Severity:** blocker
**What happens:** `backend/user_id.py` keys its `no_cookie_clients` dict on
`request.client.host` — the TCP peer IP. Ten independent browser contexts,
each with its own empty cookie jar, all hitting the app at once were assigned
**the same** player UUID:

```
ctx0..ctx9  ->  b0234858-a04a-4bd3-8747-8cb012e9e4ba   (distinct: 1 of 10)
```

They are not ten players; they are one player with ten screens. Whoever's
`set_name` lands last wins, they share ammo, HP, appeals and shot history.

**How to reproduce:** ten fresh Playwright contexts, `goto /api/hello`, then
`GET /api/my_id` concurrently. Script and output in
`$S/driver` (see the coordinator transcript).

**Where:** `backend/user_id.py:13` (`temporary_id = request_or_ws.client.host`)
and `assign_new_ID` at the bottom of the same file. The comment there
explains the intent — hold one UUID for concurrent cookieless requests *from
one client* — and the mechanism is right; the **key** is wrong.

**Why this is not just a container artefact:** it is worse in production, not
better. Every deployment puts Caddy in front and proxies `/api/*` to
`127.0.0.1:<port>` (`Caddyfile:8`, `nix/streetfight.nix:45`), and uvicorn is
started **without** `--proxy-headers` / `--forwarded-allow-ips` in all three
launch paths (`flake.nix:165`, `nix/streetfight.nix:211`, `package.json:7`).
There is no `ProxyHeadersMiddleware` in `backend/main.py`. So `client.host` is
the literal string `127.0.0.1` for *every* player on the night, and the dict
has exactly one key for the whole game.

**Why it matters for the 19th:** every player's first request is cookieless.
The window is only as long as it takes a client to come back with its cookie,
but at kick-off that is exactly when everybody loads the app at once. Two
players who overlap in that window become the same player, and there is no
error — the game just quietly misbehaves for them all night. Worth noting the
dry run on 30 August is the first realistic chance to hit this, and with a
handful of people starting at slightly different moments it may well *not*
reproduce, which is what makes it worth fixing rather than watching for.

### Finding: an in-flight request silently logs the admin back out

**Severity:** major
**What happens:** the session is a signed cookie
(`SessionMiddleware`, `backend/main.py:122`). A request that was already in
flight when `admin_authenticate` succeeded carries the *pre-login* session and
its response writes that older session straight back over the cookie,
discarding `admin_authed`. Logging in on the running React app — which polls
`user_info`, `my_id` and the ticker continuously — therefore fails
intermittently: `admin_authenticate` returns `true`, the `Set-Cookie` carries
`{"admin_authed": "true"}`, and the very next `admin_is_authed` returns
`false`.

**How to reproduce:** open the app at `/`, and *immediately* (before boot
requests settle) `POST /api/admin_authenticate?password=password`, then
`GET /api/admin_is_authed`. Observed `false` with the cookie visibly set to
the authed value. Doing the same on a bare same-origin page (`/api/hello`),
with no app polling, is reliably `true` — that is the workaround the harness
uses (`harness.js` `newAdmin`).

**Where:** `backend/admin_auth.py` `mark_admin_authed`, plus every endpoint
that writes to `request.session` (`backend/user_id.py` `assign_new_ID` does
too — same root cause as the finding above: last writer wins on a
cookie-backed session).

**Why it matters for the 19th:** the admin logs in on a phone, appears to
succeed, and then every admin page 403s until they try again. Recoverable, but
maddening mid-game with a queue backing up — and the same last-writer-wins
mechanism is what makes the identity bug above sharp.

---

## Note on scope of this walkthrough

There is no `OPENROUTER_API_KEY` in this container, so **no CharlesBot verdict
anywhere in this report came from a real vision model**. A local stub
(`$S/stub_openrouter.py`) returned fabricated, schema-conforming replies, with
`backend.vision_client.OPENROUTER_URL` rebound in the launching process only
(`$S/run_backend.py`) — no repository file was changed. Everything downstream
of the model (queue annotation, ranking display, auto-actions, escalation,
appeals, replay) is therefore genuinely exercised; the model's *accuracy* is
not, and remains what roadmap #4 and R1/R2 are for.

The camera is Chromium's fake device (a green test pattern), so no shot photo
in this pass contains a person. Colour readings are whatever the stub was told
to say.

---

## Follow-up: a greyscale photo poisons the admin queue and the zip

Agent A6 hit an `admin_get_shot` 500 on another agent's shot and reported it as
not-mine. It reproduces deterministically and is worth a line of its own.

### Finding: a greyscale (mode "L") shot image 500s the admin's shot view and the zip download

**Severity:** major
**What happens:** `backend/image_processing.py` `draw_cross_on_image` (:248)
and `annotate_image_with_stats` (:60) both hardcode an RGB fill,
`line_color = (255, 255, 255)`, and hand it to PIL's `draw.line` / `draw.text`.
On a single-channel image PIL raises
`TypeError: color must be int or single-element tuple`. `load_image` (:36)
never normalises the mode, so whatever the shot was stored as is what gets
drawn on.

Reproduced directly against the repo's own functions, no server involved:

```
RGB   draw_cross_on_image        OK
RGB   annotate_image_with_stats  OK
L     draw_cross_on_image        TypeError: color must be int or single-element tuple
L     annotate_image_with_stats  TypeError: color must be int or single-element tuple
CMYK  draw_cross_on_image        OK
```

**Blast radius, and why it is not one shot's problem:**
- `admin_get_shot` (`backend/main.py:564` → `markup_shot_model`,
  `backend/admin_interface.py:942`) 500s. A6 observed the resulting CRA error
  overlay **blocking every click on `/admin/shots`** — so one bad shot takes
  the whole review queue down, not just its own row.
- `annotate_image_with_stats` is what burns the caption into each image in the
  zip, so the same photo also breaks **`admin_dump_images` for everyone** —
  which is independently the second way A11 found to kill that download (the
  other being a `/` in a player's name).
- 614 tracebacks in `$S/backend.log` from this run.

**Honest note on the trigger:** the image that caused it in this run was
synthetic, injected by an agent, not produced by a phone. Phone cameras shoot
colour JPEG, so this is unlikely on the night. It is reported as major anyway
because the cost is asymmetric: one greyscale frame from one handset takes out
the admin queue page *and* the image dump for the whole game, and the guard is
one line. Note also that three sibling functions in the same file
(`:103`, `:174`, `:212`) explicitly branch on `image.mode not in ("RGB", "L")`
— the file already anticipates greyscale input; these two functions just did
not get the same treatment.
