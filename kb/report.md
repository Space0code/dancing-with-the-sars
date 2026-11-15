# PDF report

What the "PDF report" export contains, how the changes are ordered and how the summary is written. Last updated 2026-11-15. Code: `app/js/report.js`. Issue: #119 (package G).

## What it is
An A4 PDF made in the browser with jsPDF 2.5.1 and jspdf-autotable 3.8.2 (cdnjs, loaded only when a report is made). First format in the Export dialog, selected by default, and the only one that carries the **map picture** (`ctx.snapshot()` at the moment of Download, so the picture, marked areas and area outline are as on screen). Order: header (site, selection, view and date on the map, date made), map picture with legend and base-map attribution, key numbers (changes and hectares, total and per label), summary, "Look at these first" (top five), all selected changes (table, flows over pages), numbered sources, footer with page number on every page. Text is mapped to Latin-1 (PDF standard fonts): dashes, arrows, quotes and the greater-or-equal sign become plain characters; Catalan and Finnish letters are kept.

## Priority rule
Sort by (1) label: high concern, needs review, not labelled, expected; (2) size, largest first; (3) recency, newest `last_date` first (then id). Top five go under "Look at these first", the first ten go to the summary proxy. This same rule is the **planned trigger of a future alert service** (not built).

## Summary
1. **AI-written**: facts only go to the proxy (`kb/report-proxy.md`; site name and country, time frame, bbox rounded to 2 decimals or null, totals per label, top ten). Shown in a box headed "AI-written summary" with "Written by an AI model from the numbers in this report. Check the list below before acting."
2. **Rule-based** when the proxy fails, times out (`REPORT_TIMEOUT_MS`), `REPORT_API` is empty, or the answer is empty, over 1,500 characters or contains "illegal" / "unlawful". Three templates filled with the same numbers:
   - "Satellite data show N land changes at SITE[, inside the selected area], covering about HA and first seen (between A and B, from A, until B, or on A)."
   - "Of these, N marked high concern (HA), N marked needs review (HA), N not labelled yet (HA), N marked expected (HA)." (zero parts left out)
   - "The K changes listed under "Look at these first" are the best place to start; a label is a prompt for a person to check the records, not a finding about anyone."

   With no changes: "No land changes were found at SITE for the selection in this report. Radar and optical satellite data were checked."

The dialog shows "Preparing report…" and disables Download while waiting; a proxy failure is never shown as an error.
