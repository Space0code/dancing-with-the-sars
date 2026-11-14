# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
Existing code, kept: static HTML, CSS and ES modules, no build step (`app/`), MapLibre GL 4.7.1 from unpkg, one self-hosted font (`app/fonts/`). Deployed as GitHub Pages from `main`.

## Users
- **Regulators and decision makers** (regional environment and planning departments, municipal planners, rural and forest agents). Not radar experts: every screen explains the data in plain language. They work through a list of detected changes, open one, judge the label and its reasons, and look at the evidence.
- **NASA Space Apps reviewers and video viewers** (confirmed by the team on 14 Nov 2026): they see the first screen for seconds and judge whether the idea is clear and credible. For this redesign the first screen serves them (the story in seconds) while the regulator's working view stays one click away.

## Product Purpose
SARwatch uses radar satellites (NISAR and Sentinel-1) to detect land-surface changes (forest clearing, new buildings, earthworks, ground motion) and to say, in plain language, which changes look expected and which need a regulator's review, with the evidence. Success: a non-expert understands within seconds what changed, when, how big, why it is labelled so, and can open the evidence.

## Positioning
Radar sees through cloud and at night, so the record of change continues in bad weather; each label comes with its reasons and source links, and nothing is hidden behind a score.

## Operating Context
- Pilot sites: Muhos, Finland (the clearing for a planned data centre, reported ~330 ha) and Catalonia (Agroparc corridor). Muhos is the test case shown first.
- Demo: a short video plus the live site; reviewers open it in a browser, often on a phone.
- Data contract in `kb/data-contract.md`; the app only reads `app/data/`.

## Capabilities and Constraints
- Same features as `main` must remain: site menu, Radar and Satellite pictures, Compare before and after, Marked areas switch, timeline slider with play, change list (filters, smallest-change slider, CSV download), change cards with "Why this label?", story panel with the cleared-area chart, guided tour, shareable links (`#site=…&date=…&change=…`).
- Must work at 390 px phone width.
- No glow, flashing or pulsing when data changes (decided in PR #106).
- Labels are exactly: Expected, Needs review, High concern, Not judged yet. Never present a first-seen date as the day of cutting; never add hectares from different satellites together.
- The data and its contract are not changed by design work.

## Brand Commitments
Name: SARwatch. Plain-language voice, short sentences, no jargon without explanation. No hype about daily coverage ("every few days, whatever the weather").

## Evidence on Hand
Real data in `app/data/muhos/` and `app/data/agroparc/` (changes with reasons and sources, frames, stories, cleared-area series). Press and agency sources are linked in each story. No testimonials, customers or benchmarks exist; do not invent any.

## Product Principles
1. Show the evidence, not a score: every label has visible reasons and a source.
2. Explain in plain language first; technical detail is one step deeper.
3. The map and the change are the subject; interface chrome recedes.
4. Honest about limits: dates are "first seen", hectares from different satellites are never summed.
5. Calm under changing data: no flashing, motion only where it explains change over time.

## Accessibility & Inclusion
Usable on a phone; text contrast must hold over the map; motion respects `prefers-reduced-motion`; colour is never the only carrier of a label (Expected / Needs review / High concern also appear as words).
