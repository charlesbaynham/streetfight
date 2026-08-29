# R9 agent walkthrough — raw per-agent findings

Appendices to `docs/r9_agent_walkthrough_2026-08-29.md`, which is the report
to read first. These are each agent's own write-up, unedited, kept for the
reproduction steps and the reasoning behind each verdict.

| File | Checklist lines covered |
| --- | --- |
| `A0-coordinator.md` | Session and identity bugs found while building the harness; scope note |
| `A1.md` | Join via QR/link, `/pick`, badges and the reveal link, name-then-confirm |
| `A2.md` | Clearing an outfit, the identity workbench and overrides, renaming a team |
| `A3.md` | Loot QR codes and all four item types |
| `A4.md` | Taking a shot, the crosshair, the shot status bubble |
| `A5.md` | Screen wake lock (R3), the map and circles (#12), the ticker |
| `A6.md` | Appeals as either party (R8), the contested-shots list |
| `A7.md` | The "CharlesBot, never AI" copy audit (#1, #2) |
| `A8.md` | The reference-photo kit check (R7) |
| `A9.md` | The shot review queue (#3), bystander outcomes |
| `A10.md` | The four `ai_*` toggles, no-re-review, manual escalation (#11) |
| `A11.md` | The per-shot map (R5), shot history and notes, the image zip |
| `A12.md` | Admin nav on a phone, the version footer, the replay workbench (R1) |
| `A13.md` | Reset (`resetdb`) and replay from a clean state |

## Reading these

- **Screenshot paths are dangling** — each agent references PNGs under a
  scratch directory in the container this ran in, which no longer exists. The
  images themselves are preserved in
  **`R9_walkthrough_screenshots.pdf`** (and the same content as `.docx`) in the
  repository root: the report with the screenshots embedded under the findings
  they are evidence for, plus a gallery per checklist line. Open that if you
  want to see what an agent saw.
- **Every CharlesBot verdict quoted came from a local stub**, not a real vision
  model — see the limitations section of the main report. Agents were asked to
  flag this themselves and did.
- Agents were asked to judge sceptically and to distinguish a product bug from
  a container artefact. Where one declined to report something as a bug, the
  reasoning is usually still written down — for example A8's analysis of why
  "2–3 readable channels still names somebody" is *not* the MDS pathology on
  that page, and A10's proof that a per-game toggle does not let one game's
  stuck shot block another's auto-actions.
