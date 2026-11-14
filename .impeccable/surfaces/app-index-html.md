---
version: 1
slug: "app-index-html"
primary_target: "app/index.html"
related_targets: []
---

# Surface brief: SARwatch app (design/rings)

Scope and mode: the whole app screen (`app/index.html`), Experience-led first viewport with the Operate working view one click away. Audience: reviewers and video viewers first, regulators for the working view (PRODUCT.md). Task: understand the Muhos clearing in seconds, then inspect any change and its evidence. Constraints: same data and features, 390 px works, no glow or flashing on data change, reduced motion respected, no build step.

## Direction contract

THESIS: the clearing is read like a tree's growth rings: each month of first sighting is one ring on the map, and one monumental number leads. It refuses the category-default arrangement of a floating-card dashboard over a map.

OWN-WORLD: a stained wood thin section on a light table: ground near-white with a faint cool tint, safranin red (rings, active state, High concern stays its own orange) and astra blue (Expected, links), thin hand-drawn-weight ring lines, labels set small and tracked like slide annotations, one display face used large for the headline figure and a plain workhorse sans for text. No cream, no serif, no glow. Recognisable with content removed: concentric stained contours and a ticked strip.

STORY: the visitor understands that satellites saw about 359 ha cleared in seven monthly steps (reported ~330 ha), that it kept growing after an assessment was required, and can open any change to see why it is labelled so. They scrub the strip, open a ring, then the list.

FIRST VIEWPORT: full-bleed map. Top left, no card: the figure "359 ha" at 7 to 9 rem display size, a one-line caption "cleared as seen by NASA optical alerts; ~330 ha reported", a small seven-bar trend. Bottom: a core-sample strip (one tick per ring with its month, event flags, play). The existing controls (site, Radar/Satellite, Compare, Marked areas, Tour, How to read, Changes) sit in one slim top bar in one control style. The story is a narrow right column that opens on demand, not a permanent text wall. Primary action: scrub or play the strip.

FORM: growth rings, position 5 of the grounded list (tree-ring cross-section; list: photorevised topographic overprint, cadastral parcel sheet, Swiss topographic cartography, aeronautical chart, tree-ring section, synoptic weather chart, seismograph drum), seed: seed:1f99202d83988cbf. Signature interaction: scrubbing grows the rings with a damped spring; each ring labels its month at its edge. Motion grammar: rings draw in (stroke-dashoffset) once per site load and per scrub step, numbers change without flashing, panels slide with a short ease-out, nothing loops, all of it off under prefers-reduced-motion.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
