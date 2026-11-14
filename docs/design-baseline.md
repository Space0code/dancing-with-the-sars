# Design baseline: what makes today's screen look generic

Measured 14 Nov 2026 on `main` at `f6bfe0e` (after the restyle PR #106). Tool: Impeccable's detector (v4.9.1, engine 0.1.24),
run with `DO_NOT_TRACK=1`. Pictures: [`desktop 1280`](screenshots/design-baseline-desktop.jpg), [`phone 390`](screenshots/design-baseline-phone.jpg).

## The five things

| # | What | Evidence | Where |
|---|---|---|---|
| 1 | **Side-tab accent border**: a thick coloured left edge on a rounded card, "the most recognizable tell of AI-generated UIs" | detector `side-tab`, twice (source scan) | `app/css/style.css:175` (`border-left: 4px solid var(--error)`), `app/index.html` (`border-left: 4px` + `border-radius: 12px`) |
| 2 | **Flat type hierarchy**: body, `h2` and `h3` are all 16 px (largest step 1.00 : 1, target 1.25 : 1), only weight differs, so the side panel reads as one grey text wall | detector `flat-type-hierarchy` (advisory) and the pictures | `app/index.html`, `app/css/style.css` |
| 3 | **Monotonous spacing**: one 4 px step is 64 % (source) to 77 % (rendered page) of all spacing, so nothing groups and nothing breathes | detector `monotonous-spacing`, in both scans | `app/css/style.css` |
| 4 | **Endless nudge animation** on the swipe hint (infinite horizontal loop) | detector `marquee` | `.swipe-hint` in `app/css/style.css` |
| 5 | **Floating white cards on the map** (controls + caption top left, legend bottom left) with five different button styles (pill, segmented, toggle, green, outlined) in one toolbar: the "SaaS dashboard" look, and the cards cover the data | **my visual judgement from the pictures, not a detector result**: replace this one if you name a better fifth | `app/index.html`, `app/css/style.css` |

## How the redesign is verified

Same data and features; only look and interaction change. A redesign passes when **all** of these hold:

1. `impeccable detect --json app` returns **0 findings** (baseline: 5), and the rendered-page scan `impeccable detect --json http://127.0.0.1:8770/` returns **0** (baseline: 1). Run with `DO_NOT_TRACK=1`; serve with `python3 -m http.server 8770 -d app`.
2. `python -m pytest -q` and `python -m sarwatch.contract app/data` give the same result as on `main` (data untouched: `git diff --stat main -- app/data src` is empty).
3. No console or page errors at 1280 px and at 390 px on `#site=muhos` and `#site=agroparc`.
4. Pictures at 1280 and 390 px in the PR; no glow or flashing when data changes (the rule from #106 stays).
5. Every control that exists on `main` still exists and works (intro, site menu, Radar/Satellite, Compare, Marked areas, Changes tab and CSV, a card, play, tour, shareable link). The checklist is Tomi's #41 comment.
6. The humans judge the pictures against the five things above.

Baseline detector output: 4 `warning` + 1 `advisory` in the source scan; 1 `warning` in the rendered scan.
