# Knowledge base

What we know, written for engineers (CS / math / EE), not geologists. One line per page; add pages only when needed.

| Page | What's in it |
|---|---|
| [product.md](product.md) | **What we build**: the idea, users, screens, change types, verdict rules, scope |
| [plan.md](plan.md) | **How we build it**: sites, tracks, tasks, who owns which files, milestones, cut order |
| [data-contract.md](data-contract.md) | The data format shared by radar, verdict and app (`app/data/`) |
| [project-context.md](project-context.md) | Challenge, NISAR facts, data timeline, Catalonia + Finland cases, resources |
| [verdict-rules.md](verdict-rules.md) | How a change gets expected / needs review / high concern: rule table, reason codes, records file, CLI |
| [multi-sensor-design.md](multi-sensor-design.md) | **Proposal:** how optical alerts, Sentinel-1 and NISAR detections become one change: merging, dating, confidence, card wording, contract additions, task split |
| [data-sources.md](data-sources.md) | NASA / Copernicus / Catalan datasets: coverage, access, what each is good for |
| [data-nisar-gcov.md](data-nisar-gcov.md) | NISAR GCOV files: HDF5 layout, units, grid, masks, finding granules, reading a window over HTTPS, gotchas |
| [site-barcelona.md](site-barcelona.md) | Barcelona site: window, Sentinel-1 track and bursts read as one mosaic, NISAR frame, dates, measured cost |
| [sar-primer.md](sar-primer.md) | How radar imaging works: backscatter, polarization, speckle, InSAR, L vs C band, products |
| [glossary.md](glossary.md) | Remote-sensing jargon → engineering meaning |
| [submission.md](submission.md) | Space Apps submission: form checklist, demo rules (≤30 s / ≤7 slides), judging criteria, drafts of every field |
| [submission-form.md](submission-form.md) | The paste-ready text for every field of the project form (15 Nov), plus the images to upload and the pre-submit checks |
| [official-rules.md](official-rules.md) | Organizers' emails, guides and forum checked 15 Nov: **Barcelona deadline Sun 16:00**, eligibility traps, team page, awards, the challenge's own questions, questions for 09:00 |
| [demo-strategy.md](demo-strategy.md) | What wins: the one-sentence claim, **the 7-slide deck + 2–3 min talk decision (15 Nov, no 30 s video)**, the live pitch, the project page, what we leave out |
| [past-winners.md](past-winners.md) | What 2025 Global Winners did in their demos (award categories, deck patterns) and what that means for our deck |
| [evidence-check.md](evidence-check.md) | Sceptical check of every demo claim against our results: support, rival explanations, defensible wording, go / no-go per site, fallbacks, what to measure next |
| [report-proxy.md](report-proxy.md) | Cloudflare Worker that writes the AI summary for the PDF report: schema, guard rails, rate limit, deploy and key rotation |
| [report.md](report.md) | The PDF report: contents, the priority rule (also the planned alert trigger), AI vs rule-based summary |
| [mentor-feedback.md](mentor-feedback.md) | Our mentor's eleven points: one row each with what we did and where (PRs), and what we deliberately did not build and why |
| [decisions.md](decisions.md) | One line per team decision + why |

<sub>Written by Claude; agents keep this index current.</sub>
