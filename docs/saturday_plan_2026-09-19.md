# Street Fight — Saturday game plan and required changes

Working document for the game running this Saturday. Sections 1–2 give the reasoning
behind the changes; sections 3–6 are the concrete work. Section 4 is the list a coding
agent should turn into milestones.

---

## 1. Feedback from the previous game

- **Players were too passive.** One life meant that getting shot ended your game, so the
  rational move was to hide. Little risk-taking, few encounters, less fun.
- **Being eliminated is not fun.** Dying and sitting out is the worst outcome for a player,
  and a player killed by someone they never saw gets no story out of it — just a
  notification saying they are dead.
- **The game was confusing.** Players did not know what was coming next: drops and circles
  arrived without warning.
- **Drops were ignored.** Teams did not know what was inside, so they could not judge
  whether the risk was worth it. The contents were in fact very good.
- **Setup was a shambles.** It took about an hour and a half. Charles and Gaby did
  everything themselves while simultaneously fielding questions from everyone.

## 2. Design goals

Optimise for the number of **interactions**, not the number of eliminations. Shooting
someone is fun; being shot is not; being out of the game is worse. So:

- Make players harder to kill, so they will take risks.
- Give out far more ammunition, but slow the rate of fire, so a fight becomes a chase
  rather than an execution.
- Use power-ups to *engineer encounters* (find other players, reach good ground first)
  rather than to help players hide.
- Telegraph everything in advance. A known event that everyone converges on is free
  interaction; a surprise event is just confusion.

---

## 3. Balance changes

| Item | Before | After |
| --- | --- | --- |
| Starting armour | 0 | 1 (two hits before death) |
| Bullets per pub poster | 2 per team member | 5 per team member |
| Default weapon cooldown | ~8 s | **25 s** |
| Fast weapon cooldown | ~4 s | **5 s** |
| Level 1 armour | scarce | scattered freely in pubs |
| Level 2 armour | — | mostly in pub envelopes |

Notes:

- **Five bullets per member** was not feasible before because shots were reviewed manually.
  The vision pipeline now handles review, so the higher volume is affordable.
- **The 25-second cooldown is the counterweight to the extra ammunition.** It gives a player
  who has been shot time to receive the notification and react before the shooter can fire
  again. In practice an ambusher gets one hit, not three, and must chase to finish the job —
  by which point the target has seen them.
- **The fast weapon becomes genuinely valuable.** Going from 25 s to 5 s is a real
  advantage, where 8 s to 4 s was not.
- **Free level 1 armour in pubs** gives a stripped player a route back to two hits, so
  losing armour is not effectively a death sentence.

### Pub economy

Each participating pub carries two things:

1. **A poster** — scannable **once per team**, gives every member of that team 5 bullets.
   Available to every team that reaches the pub.
2. **An envelope** — single use, claimed by the **first team to arrive**. Contains level 2
   armour (most of the level 2 armour in the game lives here), some upgraded weapons, and
   the occasional med pack.

Med packs also appear in drops.

---

## 4. Features to build

Grouped by area. Items marked **NEW** do not exist at all today.

### 4.1 Cooldown enforcement — NEW (backend)

The weapon cooldown is currently enforced only in the front end. At 4–5 seconds that was
harmless. At 25 seconds players will discover that refreshing the app clears the cooldown.
**The cooldown must be enforced server-side.** Assume players will actively try to break
this; several of them will.

### 4.2 Countdown and announcement system — NEW

- A prominent, persistent countdown at the top of the player UI showing the next scheduled
  event and its time remaining.
- Used for both drops and circles, so there is always a clear answer to "what happens next".
- The drop announcement must include **what the drop contains**, so teams can judge whether
  it is worth crossing the map for.

### 4.3 Circle workflow

Circles fire roughly every 45 minutes, alternating with drops, but timing stays under admin
control — nothing hard-coded or scheduled in advance.

- Admin button: **"cue next circle in N minutes"** (default 10).
- On press, the warning circle appears on the map (this already exists) and the countdown
  starts. — **NEW: the countdown.**
- **NEW:** when the countdown reaches zero, the warning circle is automatically promoted to
  an enforced circle and the play area shrinks. Today this transition is manual.

### 4.4 Live drops — NEW

Drops are no longer pre-hidden. Gaby cycles each one out from the house and places it in the
open — the middle of a park, for example — so collecting it carries real exposure.

Flow:

1. Admin presses **"drop in N minutes"** (typically 5). Countdown appears for all players,
   along with the drop's contents.
2. At zero, Gaby sets off by bicycle carrying the crate.
3. **NEW: a courier page in the admin interface** that Gaby opens on her phone and that
   broadcasts her live location.
4. Gaby appears on every player's map with her own icon — her face in an aeroplane. Players
   can watch her cross Westminster and try to guess the destination, which they do not know
   in advance.
5. On arrival, Gaby presses **"place drop here"**, which locks the drop coordinates. She
   chooses the exact spot on the night based on where people are and how the game is going,
   so even the admins do not know the precise location beforehand.
6. Her icon is replaced by a **crate icon** at that location.

Keep the existing blue flashing circle, but add the crate icon alongside it — players in the
last game did not understand what the flashing circle meant.

### 4.5 Game reset to start state — NEW

Needed for the transition out of the warm-up sandbox (see §5). A single admin action that,
with the game paused, sets every player to the starting state:

- wipe all ammunition
- wipe all recorded shots
- reset health and set armour to 1
- reset weapon to the basic default

### 4.6 QR code revocation — NEW

The sandbox posters hand out infinite ammunition. Players **will** photograph them and try
to reuse them once the real game starts. There is currently no way to disable a QR code;
there needs to be.

### 4.7 Radar item — NEW, experimental

Grants the holder the location of all players, including other teams, for a fixed window
(say 5 minutes). Purpose is to enable ambushes and traps.

Known limitation: the server only knows a player's position while their app is open, so the
data will be incomplete and sometimes stale. **Make this explicit in the interface** — show
positions as "last seen" with a timestamp rather than implying live tracking. Ship it, try
it, and drop it if it does not work.

### 4.8 Early circle warning item — NEW

Reveals the next circle's location to the holder before it is announced to everyone else,
giving them time to claim good ground first. Deliberately asymmetric: it does not protect
the holder, it buys them position.

### 4.9 Team leader view — NEW

Each team has a nominated leader responsible for getting their team properly equipped. Give
leaders a distinct view in the app with their own instructions, so they do not have to ask
what "properly equipped" means.

### 4.10 Map corrections

**The current map is wrong.** It shows pubs that are not in play and omits pubs that are.
Redraw it against the real list.

Also programme in the annotated map that Charles and Gaby have prepared, showing the
approximate circle positions and rough drop locations.

---

### 4.11 Sound effects

Replace the current shot sound. It sounds like a real gun, which is unpleasant; it should be
a sci-fi ray gun — a "pew".

Add sounds for the events that currently pass silently:

| Event | Heard by |
| --- | --- |
| You fire | shooter |
| You are shot | target |
| Your shot hit | shooter |
| Your shot missed | shooter |
| You are knocked out | target |
| You knocked someone out | shooter |

The **"you have been shot"** sound is the most important one. The 25-second cooldown (§3)
only works as intended if the target reliably notices the hit and starts moving, so that
alert has to cut through a noisy street and a pocket.

Practical note for implementation: mobile browsers block audio playback until the page has
received a user interaction. The app needs to unlock the audio context on first tap and hold
it for the session, or the sounds will silently fail on exactly the phones that matter.

---

## 5. Day-of workflow

### Physical preparation

- **Reprint the pub posters.** They currently say 2 bullets; they must say 5. This is a
  print job, so do it first.
- Lay out armbands and hats in baskets at The Speaker for players to collect themselves.
- **The Speaker is a playable pub.** It needs the standard 5-bullet poster like everywhere
  else — but ask the bar staff to keep it hidden until the game starts, so nobody grabs it
  during the warm-up.

### Setup, from 14:00

Setup last time consumed 90 minutes because Charles and Gaby did everything and answered
questions at the same time. The fix is to delegate:

- The app tells each player which clothes to wear and which hat and armband to collect.
- Kit is self-serve from the baskets. Putting it on is the **player's** responsibility.
- **Team leaders** are responsible for their team being correctly equipped.
- Charles and Gaby's only setup job is taking the reference photos.

### Warm-up sandbox, 14:00–16:00

Players are asked to meet at **The Speaker** from 14:00. A room is booked for two hours.
Players have been told the game starts at 15:00; realistically it will start at 16:00.

During this window, run an unrestricted free-for-all so people learn the mechanics before
it counts:

- Posters around the room with QR codes giving unlimited ammunition, armour and weapons.
- Unlimited med packs — players who die revive themselves immediately.
- Players shoot each other as much as they like.

This works only because shot review is now automated; the vision pipeline handles the volume
while Charles and Gaby run setup.

### Transition to the real game, ~16:00

1. Press **pause**. All player apps go dark.
2. Run the **reset to start state** action (§4.5): ammunition, shots and health wiped;
   everyone on 1 armour, 0 bullets, basic weapon.
3. **Revoke the sandbox QR codes** (§4.6).
4. Charles and Gaby leave and get clear of the area — about 10 minutes.
5. Send "the game has begun" to the WhatsApp group.
6. Press **start**. Player apps come back live on the base settings.

### Running the game

Circles roughly every 45 minutes, alternating with drops. Both are admin-triggered and both
are announced in advance with a visible countdown.

---

## 6. Roles on the night

**Charles**

- Announcing drops
- Triggering circles
- Reviewing shots escalated by the AI when it cannot judge them

**Gaby**

- Cycling out and placing every drop, via the courier page
- Running challenges — for example, photograph your whole team in a phone box — issued
  through the WhatsApp group. This stays outside the app.
- Minting rewards for completed challenges in the admin page and sending them through the
  private per-team WhatsApp chats. All the mechanics for this already exist.
