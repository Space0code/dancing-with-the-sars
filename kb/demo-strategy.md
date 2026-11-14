# Demo strategy: what wins, and what we show

The claim, the 30-second video, the 3-minute live pitch, the project page and what we leave out. Last updated 2026-11-14 (#49). Rules and form fields: `submission.md` §1. Numbers marked `[check]` come from PR #55 and must be re-read from the final data before recording.

## 1. What decides the score
- Five criteria, 1–5 each, equal weight: Impact, Creativity, Validity, Relevance, Presentation. Global judges see **the project page and a ≤ 30 s video**, among hundreds of projects. The page carries most of the score; the video decides whether the page gets read.
- Every team in this challenge shows a NISAR change map. **A change map is the entry ticket, not the win.** Our difference is the step after it: a short, explained list for one named user (a regulator), with the public record checked and the uncertainty said out loud.
- Where the points are still open for us:
  | Criterion | Risk today | What earns the point |
  |---|---|---|
  | Relevance | Muhos is mostly dated by optical alerts and Sentinel-1, so NISAR can look like decoration | one moment only NISAR gives: the L-band picture of the clearing **growing after 25 Jun** |
  | Validity | a map full of false "structure" shapes (harvested fields) sinks us with any radar scientist | few, checked changes on screen; one limitation shown on purpose; physics stated as a hypothesis |
  | Impact | "monitoring" is abstract | one real case with dates, one user, one sentence on what they do on Monday morning |
  | Creativity | "expected / needs review" sounds like a filter | show a change the app **calms down** (a recorded wildfire, a planned sector), not only alarms |
  | Presentation | three sites in 30 s is a blur | one story (Muhos), one card, one wide shot |

## 2. The claim
**One sentence:** *SARwatch turns what radar satellites see into a short, explained list of land changes a regulator should look at first.* Tagline: **"Know where to look first."**

**The proof, one sentence:** at Muhos, NASA's NISAR radar shows the clearing growing by about 53 ha between 19 Jul and 24 Aug 2026 `[check]`, after the May notice that an assessment was required and about six weeks before the stop order of 6 Oct.

**How the three sources are cast** (so NISAR is the core, honestly): NISAR is the sharp eye from June 2026 on (L-band reaches trunks and branches, so cut forest is unmistakable; it works in cloud and in the dark northern winter). Sentinel-1 and the optical alerts are the **memory** of the years before NISAR flew. Say "NISAR sees it now; older satellites tell us what came before".

**We do not claim:** that NISAR saw all ~330 ha (it began watching when about 385 ha were already bare `[check]`) · that the app would have prevented anything · "daily" or "real time" · any accuracy figure we did not measure · anything about who is at fault.

## 3. The 30-second video (Muhos only, about 65 spoken words)
| Time | On screen | Narration |
|---|---|---|
| 0–5 s | Cold open, no title card: Muhos, the timeline playing, forest turning dark in the radar picture. Corner label all the way through: "SARwatch · <team> · NASA Space Apps 2026" | "Summer 2026, northern Finland. A forest is being cleared for a data centre." |
| 5–11 s | Timeline markers light up: "May: assessment required" … "6 Oct: ordered to stop". A counter: cleared hectares per NISAR pass | "The environmental assessment wasn't finished. The order to stop came in October." |
| 11–17 s | Before / after swipe, then the signal chart stepping down | "NASA's NISAR radar watched it grow, pass after pass, through the clouds." |
| 17–25 s | The change card: label, the two top reasons, "between … and …" | "SARwatch checks every change against public records and says, in plain words, which ones need a person to look." |
| 25–28 s | Cut to Catalonia: the overview with a handful of coloured changes | "The same method, here in Catalonia." |
| 28–30 s | End card: name, tagline, link | "Know where to look first." |

Own voices, English captions burned in, no music with lyrics, no AI imagery (no watermark needed). Record at 1080p from the tour so it is repeatable. Cut to 29 s: over 30 s means no global judging.

## 4. The 3-minute live pitch (local judges; the tour drives it, a recorded copy is the fallback)
| Time | Step | Must be on screen | The line that matters |
|---|---|---|---|
| 0:00–0:25 | Hook | Muhos year photo, forest intact; three dated facts | "All of this was visible from orbit for months. Nobody was looking." |
| 0:25–1:10 | Muhos replay | timeline playing, cleared-area curve with the May and 6 Oct markers, then the card | "NISAR shows it growing six weeks before the order to stop." The "When" row reads honestly: already under way when NISAR began watching |
| 1:10–1:45 | Why believe it | signal chart; the frozen 4 Nov pass we threw out | "Cut forest stops scattering the radar back: the vegetation echo drops. Frozen ground does the same, so the app drops that pass and says so." |
| 1:45–2:25 | Catalonia, close up | Agroparc with record layers on; one **needs review** card, then one **expected** card | "It also tells you what you can ignore, and why." |
| 2:25–2:50 | The regulator's list | Catalonia overview, the inbox sorted by label, share link | "This is the list an inspector opens on Monday." |
| 2:50–3:00 | Close | end card | the claim sentence; one line on what comes next (whole region, every 12 days) |

Three questions to expect: *How do you know it isn't harvest or snow?* (two sources with unrelated blind spots, a confidence grade, risky seasons lowered: `multi-sensor-design.md`) · *Why NISAR and not Sentinel-1?* (L-band sees forest structure, C-band mostly leaves; we use both, Sentinel-1 for the past) · *Isn't a wrong flag dangerous?* (labels are reasons to look, never findings; no names; every reason links to its record).

## 5. The project page (most of the score)
- **First screen:** the claim, one Muhos before / after picture with dates, the video, the link to the live app. A judge who stops here should already be able to score Impact and Presentation.
- **Then one short section per criterion, in the judges' order**, each opening with its strongest sentence. Under Relevance: a table "what NISAR does / what the other data does". Under Validity: **"Limits, stated plainly"** (NISAR's record starts June 2026; fields after harvest can look like buildings; frozen passes are dropped) and **"What the radar physics says"**: the challenge asks for hypotheses on physical drivers, so answer it by name: cross-pol (HV) falls when canopy goes; it fell by only 1.5–3 dB at Muhos, our hypothesis being that logging slash and stumps still scatter `[check]`; co-pol (HH) rises on new walls; what a full year of NISAR would add.
- Pictures: four at most (Muhos replay, a card, record layers, Catalonia), each with a one-line caption that says what to see.

## 6. Deliberately left out
| Left out | Why |
|---|---|
| The company's name in the video and the pitch (it stays in the cited sources) | the story is the regulator's blind spot; naming a firm invites the wrong argument (`product.md` anti-goals) |
| Agroparc in the video | our data does not yet show works inside the project outline; it is a live-pitch step only if it does by Sunday noon |
| Ground sinking / rising, ships | not built; mentioning them invites questions we cannot answer |
| How it is built (pipeline, agents, AI workflow) | not scored; one line under "Tools", the AI field is not shown to judges |
| Counts of raw detections, any unchecked Catalonia change with a strong label | false alarms on screen cost Validity; the overview shows candidates as neutral until checked |
| dB, polarisation names, "backscatter" in narration | plain words in speech; the terms live in the chart labels and the page's physics section |

## 7. What this asks of the build (in priority order, before the freeze)
1. **Muhos cleared-area curve:** hectares cleared over time (optical alerts for spring, NISAR per pass from June) with the May and 6 Oct markers, in the Muhos story panel. This is the picture the whole demo hangs on. One task, Sonnet, ≤ 1 h, numbers from `explore/muhos/clearing_scope.py` and #44.
2. **A clean Muhos map:** only changes inside or next to the clearing outline keep a strong label; the harvested-field "structures" are tuned out or shown low.
3. **One "expected" card worth showing** in Catalonia (a recorded wildfire or a planned sector) next to one "needs review".
4. **`app/tour.json` follows section 4** step for step, with real dates and change ids, so the tour *is* the pitch and the video is a screen recording of its first steps.
5. Nice to have, not demo-critical: CSV download, minimum-size slider, the full multi-sensor merge outside Muhos.

<sub>Written by Claude</sub>
