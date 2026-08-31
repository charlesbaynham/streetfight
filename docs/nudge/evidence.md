# What actually replicates — the honest priors

The single most useful thing a nudge consultant can carry is a calibrated
sense of how big these effects really are. The popular literature is badly
inflated, and an agent that quotes 2010-era headline numbers will confidently
recommend things that do nothing.

Checked against primary sources on 2026-08-31.

---

## The headline correction

**DellaVigna & Linos, "RCTs to Scale: Comprehensive Evidence from Two Nudge
Units", *Econometrica* 90(1):81–116 (2022).**
<https://onlinelibrary.wiley.com/doi/abs/10.3982/ECTA18709>

126 RCTs, 23 million people — every trial run by two of the largest US nudge
units, published or not. That "or not" is the whole point: it removes the
publication filter.

| Sample | Average effect | Relative |
| --- | --- | --- |
| Academic journal papers | **8.7 percentage points** | +33.4% over control |
| The nudge units' full trial portfolio | **1.4 percentage points** | +8.0% over control |

They attribute roughly **70% of the gap to selection in the academic
publication process.** Not fraud, not incompetence — trials that worked got
written up and trials that did nothing did not.

**The number to carry: a well-designed nudge, deployed at scale, moves a
take-up rate by one to two percentage points.** That is a real, worthwhile,
cheap effect. It is not a redesign of human behaviour.

## The more sceptical reading

- **Mertens et al. (2022)**, *PNAS* — meta-analysis of 200+ studies, 440+
  effect sizes, n ≈ 2.1 million. Pooled effect **d = 0.43**, but with large
  heterogeneity and asymmetric effect distribution the authors themselves read
  as moderate publication bias.
- **Maier et al. (2022)**, "No evidence for nudging after adjusting for
  publication bias", *PNAS* 119(31).
  <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9351501/> — re-analyses the
  above with bias-correction methods and finds the pooled effect not
  distinguishable from zero.
- The rebuttals (e.g. Szaszi et al. on left-truncation,
  <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9351476/>) argue the
  correction over-corrects.

**Where this leaves an honest practitioner:** the *aggregate* "does nudging
work" question is contested and probably not the useful question. The
disaggregated picture is much clearer, and it is the one to work from.

---

## The tiers, in descending order of how much to trust them

### Tier 1 — large, robust, boring

**Defaults and auto-enrolment.** The effect that survives every correction.
Opt-out organ donation regimes run at 85.9%–99.98% consent; opt-in at
4.25%–27.5%. Pension auto-enrolment moved participation from 61% to 83%.
These are not 1-percentage-point effects, and the mechanism is not
psychological subtlety — it is that the alternative requires an action nobody
takes.

**Removing steps from a flow.** Not really a "nudge" at all; it is just
usability, and it is the most reliable lever in the set. Every step in a funnel
loses people. Deleting a step reliably gets some of them back.

**Making the required action possible at all.** The dominant cause of a flow
not completing is very often that a segment of users physically cannot complete
it — a dead button, an off-screen control, a permission dialog that never
fires. This will not show up in your framework; it shows up in a device lab or
a real evening with real phones.

### Tier 2 — real but modest and context-dependent

- **Salience / attention** (the car-tax photograph): a few percentage points.
- **Social norms messaging** ("most people pay on time"): a few percentage
  points, and it backfires if the true norm is the undesired behaviour.
- **Timely prompts / reminders**: reliably positive, one of the better-value
  interventions, and the effect decays with repetition.
- **Implementation intentions** ("plan when and how you will do it"): well
  supported, modest.
- **Personalisation** (using someone's name, their case, their vehicle):
  small, cheap, generally positive.

### Tier 3 — treat as unproven; do not build a plan on these

- **Social/behavioural priming** — the epicentre of the replication crisis.
- **Ego / self-image manipulations** as a standalone lever.
- **Most "loss framing beats gain framing" claims** — the direction is
  unstable across domains.
- **Choice-overload / jam-study effects** — the original finding has not
  replicated robustly; more options is sometimes simply better.
- Anything sourced to a single striking study, a TED talk, or a business book
  without a trial behind it.

---

## What this means for a small project

Streetfight is not a government letter campaign with 200,000 recipients where
a 1.4-point lift is worth six figures. It is roughly thirty people on a
Saturday night. That changes the calculus in three ways worth stating
explicitly:

**1. Tier-2 effects are invisible at n=30.** A 3-percentage-point improvement
on thirty players is one person. You will never know whether it worked. So do
not spend design effort on Tier-2 nudges here, and do not claim credit for
them afterwards.

**2. Tier-1 effects are the whole game.** A flow with a silent failure at step
2 does not lose 3% of players, it loses *everyone who hits it*. The 30 August
dry run lost real signups to exactly this (`docs/dry_run_feedback_2026-08-30.md`
item 12). Fixing a dead end is worth more than every clever nudge in the
literature combined, and it is the kind of effect that is plainly visible at
n=30.

**3. Motivation is already solved.** These are friends who have chosen to come
and play. Nobody needs persuading to fire their weapon. Every real problem
here is Capability or Opportunity in COM-B terms — which means *Easy* is
almost always the right limb of EAST, and Attractive/Social/Timely are usually
a distraction.

**The rule of thumb for this repo: if a proposal's mechanism is "and this will
subtly influence them", it is probably not worth doing. If its mechanism is
"and then the thing works", it is.**

---

## How to know whether it worked

At this scale, A/B testing is not available and pretending otherwise is
theatre. What *is* available:

- **Funnel counts from the database.** How many people were handed a join
  link, how many claimed a slot, how many fired a shot? Each of those is a
  countable row. A step where the count halves is a finding.
- **Watching one person do it**, on their own phone, without helping them.
  Five minutes of this beats any amount of heuristic review. The
  `run-mobile-app` skill approximates it; a real guest is better.
- **Counting the support questions.** "How do I…?" asked twice in one evening
  is a design defect, not a user defect.
- **Post-hoc, honestly.** Say what you predicted before the night, and what
  actually happened. See `docs/dry_run_feedback_2026-08-30.md` for the format
  — twelve issues, each investigated against the actual code rather than
  guessed at.

---

## Sources

- DellaVigna & Linos (2022), *Econometrica* — <https://onlinelibrary.wiley.com/doi/abs/10.3982/ECTA18709>
- Mertens et al. (2022), *PNAS* — meta-analysis, d = 0.43
- Maier et al. (2022), *PNAS* — <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9351501/>
- Szaszi et al. (2022), *PNAS* — <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9351476/>
- Behavioural Insights Team, *EAST* (2014) — see `frameworks.md`
