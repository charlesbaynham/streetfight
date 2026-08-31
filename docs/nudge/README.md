# Nudge psychology and UX ergonomics — reference library

The reference material for the **`nudge-ux` agent**
(`.claude/agents/nudge-ux.md`), which is the consultant for behavioural design
and interaction ergonomics: designing flows people actually finish, and
steering them towards the right thing without manipulating them.

These four files are distilled from primary sources rather than from summaries
of summaries, and every claim carries the URL it came from. They were checked
against source on **2026-08-31**.

| File | Contents |
| --- | --- |
| [`frameworks.md`](frameworks.md) | EAST (verbatim from the BIT executive summary), MINDSPACE (verbatim from the Institute for Government report), COM-B and the Behaviour Change Wheel, Fogg's B = MAP — and how the four fit together |
| [`evidence.md`](evidence.md) | How big these effects really are. DellaVigna & Linos on publication bias, the Mertens/Maier dispute, and a three-tier ranking of what to trust. **Read this before quoting an effect size.** |
| [`ergonomics.md`](ergonomics.md) | Nielsen's ten heuristics, the laws of UX worth knowing, touch targets and the thumb zone, mobile form design, and the *silent stopping point* — the failure shape that keeps costing this project real players |
| [`ethics.md`](ethics.md) | Sludge and sludge audits, when friction is correct, the FORGOOD ethics check, and Brignull's deceptive-pattern catalogue with the legitimate twin of each |

## The short version

If you read nothing else:

1. **Make it easy beats make it motivating.** Ability is stable; motivation is
   not. Remove a step before you improve a sentence.
2. **The published effect sizes are roughly six times too big.** Academic
   papers report an 8.7-point average lift; the same nudge units' full trial
   portfolios deliver 1.4. Expect one to two points from a good Tier-2 nudge,
   and note that on thirty players that is unmeasurable.
3. **Defaults and deletions are the real levers.** They are boring and they
   are the only things with reliably large effects.
4. **Hunt for silent stopping points first** — a step the user believes
   finished the job, that looks finished, and that changed nothing on the
   server. No error, no complaint, no ticket. Two of these cost Streetfight
   real signups on 30 August.
5. **Friction is a tool; the test is whose interest it serves.** Protecting a
   user from an irreversible mistake is good design. Protecting your numbers
   from their intentions is sludge.
6. **If it stops working when you explain it, it is manipulation.** That is
   the whole ethics test, and it is cheap to apply.

## Local evidence

`docs/dry_run_feedback_2026-08-30.md` is the real corpus: twelve failures
found by ~10 guests on their own phones on 30 August 2026, each investigated
against the code. Ten remain open as **R13** in `docs/roadmap.md`, and the
high-severity ones are all behavioural-design failures rather than bugs. It is
worth more than any of the literature below, because it is about these players
on these phones.
