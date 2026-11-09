# MAPS v2 draft-1 — human-review preparation audit (archived)

Archived 2026-11-07 before the v2.1 corrections. Do not edit. This directory holds the exact
v2 draft-1 scenario files, evidence documents, config and pilot grid that the audit examined.
Everything here was synthetic and in `draft` status (never frozen, never independently validated).

## Verdict
Not ready to freeze. Two root pools failed the independence standard on inspection; several
unintended clues and confounds needed fixing.

## Findings by pair
- **sw (software releases) — roots NOT independent.** The four roots read different events of one
  release pipeline (upload timestamp, announcement date, build completion, signing time):
  causally chained, and the events would not share a date. Disjoint upstream ids hid this.
  Weekday clue: 14 March 2031 is a Friday (true claim); the false-claim ground truth,
  22 June 2031, is a Sunday while the claimed 22 September 2031 is a Monday.
  Entity names "Lumora" (true) vs "Quarrel" (false) carry opposite connotations.
- **biz (business records) — partial.** Registrar filing, payroll-withholding ledger and shift
  rosters (R1, R3, R4) all derive from the company's own HR/payroll data (latent common
  upstream). Only the chamber site-visit count (R2) was observer-generated, and it counts a
  different population. Evidence said "end of fiscal year" while the claim said "end of 2031".
- **sci (observations) — independent instruments, quality uneven.** "Observation night 6"
  undefined; "emitted" vs "detected" ambiguity; a volunteer "Amateur" network is an explicit
  low-credibility cue next to research instruments.
- **geo (geography) — feasibility problems.** Fixed gauge stations and a single-location buoy
  cannot establish a lake's maximum depth; lidar bathymetry does not reach the stated depths.
- **hist (history) — mostly independent.** Two primary and two secondary/downstream witnesses;
  the bell-ringing and envoy records may postdate and depend on news of the signing; year
  conventions undefined; the evidence document was itself an archive catalogue entry, the same
  artifact type as root R1.

## Cross-cutting findings
- Stated origins differed in apparent authority ("Royal Archive of the Crown", "Government
  statistics office" vs "Amateur Network"); length balance did not equalize credibility.
- Pilot rotation used the identity order, so R1 was always the single repeated root.
- Some templates carried authority cues ("Records give", "Surveys put", "According to the
  release history"); in the pilot they appeared only in 4-message conditions.
- Filenames and ids carried the truth label (`-T` / `-F`); a reviewer could not be blind.
- Upstream-id disjointness is a syntactic check: necessary, not sufficient, for independence.
- In false worlds, four accurate-looking methods all err identically (accepted limitation).

## Decisions taken in response (implemented in v2.1)
Replace sw pair; redesign biz, geo roots as direct observation of one precisely defined quantity;
retain sci, hist with tightened definitions; neutral names; weekday-matched dates; uniform
"<Name> Group" stated origins; neutral templates; seeded randomized root/template rotation
(independent of truth labels); blinded review copies with a separate answer key.
