# PDF report

What the "PDF report" export contains, how the changes are ordered and how the summary is written. Last updated 2026-11-15. Code: `app/js/report.js`. Issue: #119 (package G).

## What it is
An A4 PDF made in the browser with jsPDF 2.5.1 and jspdf-autotable 3.8.2 (cdnjs, loaded only when a report is made). First format in the Export dialog, selected by default, and the only one that carries the **map picture** (`ctx.snapshot()` at the moment of Download, so the picture, marked areas and area outline are as on screen). Order: header (site, selection, view and date on the map, date made), map picture with legend and base-map attribution, key numbers (changes and hectares, total and per label), summary (sections), "Look at these first" (top five), all selected changes (table, flows over pages), numbered sources, footer with page number on every page. Text is mapped to Latin-1 (PDF standard fonts): dashes, arrows, quotes and the greater-or-equal sign become plain characters; Catalan and Finnish letters are kept.

## Priority rule
Sort by (1) label: high concern, needs review, not labelled, expected; (2) size, largest first; (3) recency, newest `last_date` first (then id). Top five go under "Look at these first" (left out when all five are high-concern changes that the summary's high-concern bullets already list; the full table follows anyway; the summary says "N more are in the list below" when it lists fewer high-concern changes than exist); the summary proxy gets up to 10 (6 high concern, 4 needs review first). This same rule is the **planned trigger of a future alert service** (not built).

## Summary
The summary is **four short sections** inside a grey box headed "AI-written summary" (AI path) or "Summary" only (rule-based path), shown only for labels that occur in the selection. It never repeats the totals or hectares per label (the key-numbers table above has them) and carries no disclaimer sentence (the footer does; the AI box has one small line at its end). A box that fits on one page starts on a fresh page instead of being split.
- **High concern**: bullets, at most 6, one per change in the priority order: what it is, size, where the record places it (for example the protected area), when.
- **Needs review**: at most 4 bullets, or 2-3 bullets grouping the changes by main reason with a count when there are more than 4.
- **Expected**: one or two sentences saying why these are expected, only from the reasons the records give.
- **Not labelled yet**: one short line, only if any.

1. **AI-written**: facts only go to the proxy (`kb/report-proxy.md`; site name and country, time frame, bbox rounded to 2 decimals or null, totals per label, `top` (up to 6 high concern, then up to 4 needs review, then the rest in priority order, 10 in all) and `reasons_by_label` (per label, up to 4 most common main reasons with counts; reasons that differ only in numbers, years, sizes or names in brackets count as one, and the text is a generic wording true for the whole group, e.g. "The change is small", "The place lies inside a protected area"; a group whose texts still differ in a number after that is sent as "for example: <first text>"; sizes in `top` are rounded as the report displays them)). The answer is `{high_concern: [..], review: [..], expected, not_labelled}`; the app checks the shape and lengths again.
2. **Rule-based** when the proxy fails, times out (`REPORT_TIMEOUT_MS`, 10 s), `REPORT_API` is empty, or the answer is malformed or contains "illegal" / "unlawful". Same four sections from templates: high concern bullets "Kind, size: main reason; when"; needs review bullets the same, or "N changes: main reason" for the 3 most common reasons; expected "Expected because the records show: <first sentence of the two most common reasons> (N changes); ..." (the generic wording, so a number never belongs to one change only); not labelled "No record has been matched to these yet, so they carry no label."

With no changes the box says: "No land changes were found at SITE for the selection in this report. Radar and optical satellite data were checked."

The "main reason" of a change is the first reason on its card (`reasons[0].text`). The dialog shows "Preparing report…" and disables Download while waiting; a proxy failure is never shown as an error.
