# Ergonomics and interface heuristics

The other half of the job. Nudge psychology decides *what* to encourage;
ergonomics decides whether a thumb can actually do it. On a phone, at night,
one-handed, this half is usually the binding constraint.

Checked against primary sources on 2026-08-31.

---

## Nielsen's ten usability heuristics

**Source.** Jakob Nielsen, 1994, still the standard.
<https://www.nngroup.com/articles/ten-usability-heuristics/>

Quoted definitions are Nielsen's own.

1. **Visibility of system status.** "The design should always keep users
   informed about what is going on, through appropriate feedback within a
   reasonable amount of time."
2. **Match between the system and the real world.** "Use words, phrases, and
   concepts familiar to the user, rather than internal jargon."
3. **User control and freedom.** "Users often perform actions by mistake. They
   need a clearly marked 'emergency exit'."
4. **Consistency and standards.** "Users should not have to wonder whether
   different words, situations, or actions mean the same thing."
5. **Error prevention.** "Good error messages are important, but the best
   designs carefully prevent problems from occurring in the first place."
6. **Recognition rather than recall.** "Minimize the user's memory load by
   making elements, actions, and options visible."
7. **Flexibility and efficiency of use.** Accelerators for experts, hidden
   from novices.
8. **Aesthetic and minimalist design.** "Interfaces should not contain
   information that is irrelevant or rarely needed."
9. **Help users recognize, diagnose, and recover from errors.** "Expressed in
   plain language (no error codes), precisely indicate the problem, and
   constructively suggest a solution."
10. **Help and documentation.** Best if not needed; searchable and contextual
    if it is.

**The two that do the most work in practice: #1 and #5.** Nearly every
high-severity bug in `docs/dry_run_feedback_2026-08-30.md` is a violation of
one of them — a state the system knew and did not say, or an error it could
have made impossible and instead allowed silently.

---

## The laws worth knowing

From <https://lawsofux.com/>, filtered to the ones that change a decision.

**Fitts's Law.** Time to acquire a target is a function of its distance and
its size. Big targets close to the thumb; the most-used control gets the best
position, not the prettiest one. This is the whole justification for the admin
UI's oversized buttons.

**Hick's Law.** Decision time grows with the number and complexity of choices.
Ten options on one screen is a slower screen than two options twice.

**Miller's Law / working memory.** People hold roughly four to seven items in
working memory. Anything a flow asks someone to *remember* between screens
will be dropped by some of them. Show it instead.

**Doherty Threshold.** Interaction below ~400ms feels like a conversation;
above it, people disengage and start doubting. Anything slower needs a visible
status (heuristic #1) rather than silence.

**Tesler's Law (conservation of complexity).** Every system has irreducible
complexity; you can only decide who absorbs it — the code or the user. Prefer
the code. The player should not do arithmetic the backend could do.

**Peak–End Rule.** An experience is remembered by its most intense moment and
its ending, not its average. For a game night this is worth real attention:
the *end* of the evening is what people describe to other people afterwards.

**Goal-Gradient Effect.** Motivation to finish rises with visible proximity to
the goal. Progress indication is not decoration; a flow that shows "step 2 of
3" finishes more often than the same flow that does not.

**Zeigarnik Effect.** Unfinished tasks stay salient. A visibly incomplete step
nags at people, which is useful — an item that *looks* done but is not gets
abandoned silently, whereas one that visibly isn't done gets finished. This is
the exact mechanism behind the outfit-picking failure: a picked-but-unconfirmed
option looked complete, so nobody felt the itch to finish.

**Jakob's Law.** People expect your thing to work like the other things they
use. Novel interaction is a cost; charge it only where it buys something.

**Von Restorff Effect.** The one element that differs is the one remembered —
so *exactly one* thing on a screen should be the loud one. Two primary buttons
is zero primary buttons.

**Paradox of the Active User.** Nobody reads the instructions; they start
pressing things immediately. Prose explaining how a control works is not a fix
for a control that does not explain itself.

**Aesthetic–Usability Effect.** People rate attractive interfaces as more
usable, which is genuinely useful *and* is a trap: it means a pretty interface
will mask usability problems in testing. Do not let it substitute for the
thing working.

---

## Touch targets and reach

**Standards.**

| Standard | Size | Level |
| --- | --- | --- |
| WCAG 2.2 SC 2.5.8 Target Size (Minimum) | 24×24 CSS px, or 24px spacing between smaller targets | AA |
| WCAG 2.2 SC 2.5.5 Target Size (Enhanced) | 44×44 CSS px, no spacing escape hatch | AAA |
| Apple HIG | 44×44 pt | recommendation |
| Material Design | 48×48 dp | recommendation |

Sources: <https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html>,
<https://tetralogical.com/blog/2022/12/20/foundations-target-size/>

**Practical rule: meet 24px everywhere, hit 44px on anything primary.** The
spacing exception in 2.5.8 exists for inline links in prose, not as permission
to build a row of small buttons.

**The thumb zone.** On a phone held one-handed, the screen divides into an easy
arc (lower-centre, sweeping toward the holding thumb), a stretch zone (upper
centre), and a hard corner (the top corner diagonally opposite the thumb).
Primary actions belong in the easy arc; destructive actions are one of the few
things that legitimately belong *out* of it.

**Conditions multiply the requirement.** Every one of these is present on a
Streetfight game night, and each one makes the numbers above a floor rather
than a target:

- one hand, because the other is holding something
- moving, or at least standing outdoors
- dark, or bright enough that the screen is washed out
- cold hands
- someone talking to them
- a phone that is four years old with a cracked screen protector

---

## Forms and input on a phone

Ranked by how much grief each removes:

1. **Do not ask.** The best field is the one that is not there. Can it be
   derived, defaulted, or deferred?
2. **Never lose what they typed.** Anything typed into a field and then
   navigated away from must survive, or be saved. Silent loss of typed input
   is the single most infuriating failure in mobile forms and it is what item
   3 of the dry-run feedback is.
3. **Save on blur, not only on submit.** Mobile keyboards do not reliably
   present an obvious Enter/Go affordance, and people dismiss the keyboard by
   tapping elsewhere. Treat "tapped away" as "finished typing".
4. **Say that it saved, unmissably.** A colour change on a border is not
   feedback. Words are feedback.
5. **Right keyboard, right autocomplete.** `type`, `inputmode`,
   `autocomplete`, `enterkeyhint` — free, and they remove real friction.
6. **Validate forward, not backward.** Prevent the bad input (heuristic #5)
   rather than rejecting it after submission.

---

## The signature failure: a silent stopping point

Worth naming as its own pattern, because it is the recurring bug in this
codebase and probably in most:

> A step that the user believes completed the task, and that looks complete,
> but that changed nothing on the server.

Both high-severity onboarding failures on 30 August were this shape: a name
typed but never submitted, and an outfit tapped but never confirmed. Neither
showed an error, because from the client's point of view nothing had gone
wrong. Nobody complained, because nobody knew.

**The check.** For every flow, ask: *at what points can a user stop, believing
they are done, while the server disagrees?* Then either

- make that point actually complete the action (best), or
- make the incompleteness impossible to miss — visible, worded, and ideally
  blocking (second best), or
- close the loop later with a prompt that reaches them (fallback).

"Add a line of explanatory copy" is not on that list. See the Paradox of the
Active User.

---

## Progressive disclosure and staged flows

A long flow is not made shorter by hiding parts of it, but it is made
*finishable*. Rules that hold up:

- **One decision per screen** when the decisions are unfamiliar.
- **Say how many steps there are** (goal gradient), and never let the number
  grow while they are in it.
- **Never make step N invalidate step N−1.** Backtracking is where people
  leave.
- **A staged flow needs exactly one live "unfinished" indicator** — the point
  of Zeigarnik is that it only works if the incompleteness is visible.

---

## Sources

- <https://www.nngroup.com/articles/ten-usability-heuristics/>
- <https://lawsofux.com/>
- <https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html>
- <https://tetralogical.com/blog/2022/12/20/foundations-target-size/>
