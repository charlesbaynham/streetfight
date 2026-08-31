# Ethics: sludge, friction, and the line into manipulation

A nudge consultant who cannot say where the line is will eventually walk over
it, because every deceptive pattern in the catalogue below started life as a
perfectly reasonable-sounding conversion optimisation. This file is the
boundary.

Checked against primary sources on 2026-08-31.

---

## Sludge

**Source.** Cass Sunstein, *Sludge: What Stops Us From Getting Things Done and
What to Do About It* (2021); OECD, *Fixing Frictions: 'Sludge audits' around
the world* (2024),
<https://www.oecd.org/content/dam/oecd/en/publications/reports/2024/06/fixing-frictions-sludge-audits-around-the-world_1b4bbf1a/5e9bb35c-en.pdf>

**Sludge** is excessive or unjustified friction — paperwork, waiting,
repetition, unclear requirements — that costs people time or money and can be
frustrating, stigmatising or humiliating, and that can deprive them of things
they are entitled to.

The important asymmetry: **sludge is usually easier to find and worth more to
remove than a nudge is to invent.** Nudging is adding something clever;
de-sludging is deleting something stupid. The second has better odds (see
`evidence.md` — removing steps is a Tier-1 effect).

### Running a sludge audit

A structured walk through a real flow, counting the burden rather than judging
it aesthetically. For each step, record:

- **What is demanded** — a tap, a decision, a piece of typed information, a
  permission, a physical act, a wait.
- **Why** — what breaks if this step is removed? If nobody can answer, that is
  the finding.
- **Who bears it** — burden is not evenly distributed. A step that is trivial
  for the person who built it may be impossible for someone on an old phone,
  in bad light, or arriving late and alone.
- **What it costs** — seconds, taps, and crucially *drop-out*: the share of
  people who do not come out the other side.
- **The psychological cost** — confusion, embarrassment, the feeling of being
  tested. This is real burden and it is what makes people give up rather than
  ask.

Then rank by cost × frequency and delete from the top.

**The three moves, in order of preference:** *automate* it (the system does
it), *default* it (it happens unless they object), *simplify* it (they still
do it, but it is one tap). Only when all three fail does "explain it better"
become the answer.

---

## Good friction

Friction is not the enemy; *unjustified* friction is. Deliberate friction is
correct when the action is:

- **irreversible** — a deletion, a wipe, a ruling that cannot be un-ruled;
- **consequential to someone else** — an action taken on another person's
  behalf or against their interest;
- **easy to trigger by accident** — a large target next to a destructive one;
- **prone to being done in haste** — where a two-second pause changes the
  answer.

Two live examples in this repo, both correct:

- **The shot queue's two-tap ruling** (`react-ui/src/ShotQueue.js`): selecting
  a candidate row and ruling a hit are deliberately separate actions, "so a
  stray thumb on a name cannot decide a shot." That is friction protecting a
  third party from a misfire.
- **`demo_game.refuse_if_live`**: the demo button drops every table, so it
  refuses to run if the database holds anyone else's players or games, and the
  guard is asked twice. That is friction protecting an irreversible act.

**The test that separates good friction from sludge:** *whose interest does
this step serve?* Friction that protects the user, or a third party, from a
mistake is good. Friction that protects the operator's metrics from the user's
intentions is sludge. Friction that exists because nobody has got round to
removing it is also sludge, just unintentional.

Note the symmetry rule as well: **it should never be harder to stop than to
start.** If joining is one tap, leaving should be about one tap.

---

## FORGOOD — the ethics check

**Source.** Lades & Delaney, "Nudge FORGOOD", *Behavioural Public Policy*
(2022). <https://www.cambridge.org/core/journals/behavioural-public-policy/article/abs/nudge-forgood/06BC9E9032521954E8325798390A998A>,
<https://www.forgoodframework.com/>

Seven dimensions to run any proposed intervention through:

| | Dimension | The question |
| --- | --- | --- |
| **F** | Fairness | Does it burden or benefit some people more than others? Who loses? |
| **O** | Openness | Would it still work if you explained it to them? Would they mind that you did it? |
| **R** | Respect | Does it treat them as capable adults, or as objects to be steered? |
| **G** | Goals | Whose goals does it serve — theirs, or yours? |
| **O** | Opinions | What would the people affected actually say about it? |
| **O** | Options | Does it preserve their ability to choose otherwise, cheaply? |
| **D** | Delegation | Are you the right party to be making this choice for them? |

**Openness is the sharpest of the seven and the cheapest to apply.** A nudge
that stops working the moment you describe it out loud is manipulation. A
default that people are happy to have had set for them is a nudge. If in doubt,
imagine printing the mechanism next to the button.

---

## Deceptive patterns — the catalogue to never build

**Source.** Harry Brignull, <https://www.deceptive.design/types> (the current
canonical list; the term of art moved from "dark patterns" to "deceptive
patterns"), plus Gray et al.'s three-level ontology, which organises 5
high-level strategies over ~25 meso-level and ~35 low-level patterns.

The five high-level strategies (Gray et al.): **interface interference,
forced action, social engineering, sneaking, obstruction.**

Brignull's current types, with his definitions:

| Pattern | Definition |
| --- | --- |
| **Forced action** | The user wants to do something, but is required to do something else undesirable in return |
| **Sneaking** | Drawn into a transaction on false pretences, because information is hidden or delayed |
| **Hard to cancel** | Easy to sign up, very hard to leave |
| **Preselection** | A default already selected in order to influence the decision |
| **Obstruction** | Barriers and hurdles that make a task or information hard to reach |
| **Hidden subscription** | Unknowingly enrolled in a recurring payment |
| **Hidden costs** | Low advertised price; unexpected fees at checkout |
| **Trick wording** | Misled by confusing or misleading language |
| **Visual interference** | Information hidden, obscured or disguised |
| **Fake social proof** | Fake reviews, testimonials or activity messages |
| **Fake urgency** | Pressured by a fake time limit |
| **Nagging** | Persistently interrupted by requests contrary to their interests |
| **Confirmshaming** | Emotionally manipulated into doing something they would not have done |
| **Fake scarcity** | Pressured by a fake indication of limited supply |
| **Disguised ads** | An advert dressed as an interface element |
| **Comparison prevention** | Made hard to compare options |
| **Addictive design** | Exploiting psychological vulnerabilities to foster compulsive use |
| **Currency confusion** | Real spending obscured by a virtual currency |

### Where the honest version sits next to the dishonest one

The catalogue is dangerous precisely because most entries have a legitimate
twin, and the difference is one of intent and truthfulness rather than
mechanism:

| Legitimate | Deceptive twin | What changed |
| --- | --- | --- |
| A sensible default (`Defaults`, EAST) | **Preselection** | Whether it serves them or you, and whether it is visible |
| A genuine deadline ("the game starts at 8") | **Fake urgency** | Whether the deadline is real |
| A true norm ("most people ticked more than one") | **Fake social proof** | Whether the claim is true |
| A useful reminder | **Nagging** | Whether it stops when they say no |
| Confirming a destructive action | **Obstruction** | Whose interest the friction serves |
| Warm, human copy | **Confirmshaming** | Whether declining is made to feel shameful |

**So the rule is not "never use defaults" — defaults are the strongest tool in
the box. The rule is: the honest and the deceptive version of a pattern differ
in whether the claim is true and whose interest it serves. Get those two right
and the pattern is fine.**

### Regulatory context

Not directly binding on a personal game between friends, but worth knowing the
direction of travel:

- **EU Digital Services Act, Article 25** prohibits interfaces that deceive,
  manipulate, or distort/impair users' ability to make free decisions, on very
  large platforms.
- **FTC** treats deceptive patterns as deceptive practices under Section 5;
  the 2024 click-to-cancel rule was vacated on procedural grounds in July 2025,
  with cancellation symmetry still enforced under Section 5, ROSCA and state
  auto-renewal statutes.

---

## The standing rules for this repo

1. **Never design a deceptive pattern**, even a mild one, even as a joke, even
   if asked. Say plainly that it is one, name it, and offer the honest version
   that gets the same outcome — there almost always is one.
2. **Never make a claim in the UI that is not true.** No fake counts, no fake
   urgency, no invented social proof. This is a game among friends; a lie in
   the interface is worse than useless.
3. **Prefer deleting to adding.** De-sludge before you nudge.
4. **Apply the Openness test to every recommendation** before writing it down.
5. **The player's interest wins.** Where a nudge would serve the game's
   mechanics at the player's expense — say, making it hard to see you have
   been shot — the player wins.
6. **Say when a friction is deliberate**, in the code and in the writeup, so
   the next person does not "optimise" it away. The two-tap ruling in
   `ShotQueue.js` is documented in `CLAUDE.md` for exactly this reason.

---

## Sources

- Sunstein, *Sludge* (2021); OECD, *Fixing Frictions* (2024)
- Lades & Delaney, "Nudge FORGOOD", *Behavioural Public Policy* (2022)
- Brignull, <https://www.deceptive.design/types>; *Deceptive Patterns* (2023)
- Gray et al., "An Ontology of Dark Patterns" (2024)
- EU Digital Services Act, Art. 25 — <https://www.europarl.europa.eu/RegData/etudes/ATAG/2025/767191/EPRS_ATA(2025)767191_EN.pdf>
