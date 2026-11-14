# Evidence check: what the video and the pitch may assert

A sceptical read of our results against the claims in `demo-strategy.md`. Last updated 2026-11-14 (#78, final Muhos numbers from PR #95). Sources: **[95]** PR #95 (final Muhos data, `app/data/muhos/story_series.json`) · **[55]** PR #55 (Muhos, NISAR) · **[44]** finding on #44 (optical alerts) · **[57]** PR #57 and **[68]** PR #68 (Agroparc, NISAR and Sentinel-1) · **[46]** dry run on #46 · **[ctx]** `project-context.md` §7. Support: **measured** (our data shows it) · **plausible** (fits, other causes not excluded) · **reported** (press or regulator, not ours) · **not shown**.

## Headline (final Muhos data, [95])
- **Muhos carries the story.** The clearing is 7 changes, one per month of first sighting by NASA's optical alerts, 359 ha by 23 Oct (reported: about 330 ha). The list is short: 19 changes in the window.
- **The three sources still disagree on hectares, so no single number for "how much, when".** Inside the outline at the end of June: optical 176 ha confirmed, Sentinel-1 200 ha flagged, NISAR 308 ha "bare-looking". **All three agree on the direction: the cleared area kept growing in July and August** (optical +112 ha, Sentinel-1 +42 ha, NISAR +60 ha). That sentence is the proof.
- **NISAR adds no change of its own** [95]. Its part is the bare-ground line: 308 ha on 7 Jul, 368 ha on 12 Aug. The time-lapse frames are Sentinel-1, not NISAR; the video must not say or imply otherwise.
- **The regulator was not unaware:** the company asked to skip the assessment on 30 Apr and was told in May it was required [ctx]. "Nobody was looking" is false. The defensible value is **measuring that the cutting went on after the notice**.
- **Agroparc and Catalonia are deferred** (decision on #9); their rows stay for when they come back.

## 1. Claim by claim
| # | Sentence as planned | Support | What else gives the same signal | Wording we can defend |
|---|---|---|---|---|
| 1 | "About 330 ha were cleared, March to August 2026, before the assessment was finished" | **reported** [ctx]; optical alerts: 287 ha by 31 Aug, 359 ha by 23 Oct [95] (within about 10 %) | the outline is drawn from the alerts, not the project boundary | keep, as "reported"; add "NASA's optical alerts show a block of the same size" |
| 2 | "A large part was already cleared when NISAR began watching" | **measured, amount disputed:** at the end of June optical has 176 ha, Sentinel-1 200 ha, NISAR 308 ha bare-looking (of 359) [95] | NISAR counts any ground with a low vegetation echo; optical dates lag behind cloud | "When NISAR began watching in June, about half or more was already cleared". No single number |
| 3 | "It kept growing in July and August" | **measured by all three** [95]: optical 176 → 287 ha (30 Jun → 31 Aug), Sentinel-1 201 → 243 ha (28 Jun → 27 Aug), NISAR 308 → 368 ha (7 Jul → 12 Aug; later passes wobble between 351 and 371) | ordinary forestry next door (11 small cuts, 36 ha, lie outside the outline [95]); the project boundary is not published | "Three satellites show the cleared block still growing in July and August." In writing: "by at least 40 ha" |
| 4 | "This was after the May notice" | dates **reported** [ctx], growth **measured** (row 3). After the end of May: optical +222 ha (137 → 359), Sentinel-1 +71 ha (187 → 257) [95] | an alert date is the first clear view, not the cutting day; Sentinel-1 puts 46 ha of the optical-July ground in April [95], so "half was cut from July on" is **not** defensible | "After the May notice the cleared area kept growing: by at least 70 ha, and by up to about 220 ha going by the optical alerts' first sightings" |
| 5 | "Six weeks before the order to stop" | dates only: 24 Aug to 6 Oct is 43 days. We processed in November; no live detection was shown. The 6 Oct act is a notice calling on the company to suspend [ctx] | — | "The satellite passes that show it were taken six weeks before the regulator called for a halt" |
| 6 | "Radar saw every stage, through clouds and snow" / "works in the dark northern winter" | **not shown.** Sentinel-1 is skipped from 1 Oct to 31 Mar and its April dates are disturbed by wet snow; nothing is dated to a March day (the outline is unchanged up to 23 Mar and darkens from 4 Apr) [95]; NISAR starts 25 Jun | — | "through cloud" only; "radar first sees it in early April". Proof at hand: the optical scene behind the 31 Aug state was 100 % cloud [44] while both radars kept passing |
| 7 | "The vegetation echo drops when forest is cut" (1.5–3 dB at Muhos; slash and stumps) | drop **measured** [55]; the cause is a **hypothesis** | sparse boreal forest gives little contrast to begin with | say "our hypothesis" |
| 8 | "The app checks every change against public records" | Catalonia: **measured**, live lookups, no failures [46]. Muhos: the record was **entered by hand** from the notice [46] | — | "in Catalonia it queries the public registers; for Muhos we entered the regulator's notice by hand" |
| 9 | "A short list" | **measured:** 19 changes at Muhos, 6 high concern and 13 needs review before the last rule changes [95] | — | "a list of 19 places, 7 of them the clearing month by month" (re-read the counts after the final verdict run) |
| 10 | "Earthworks for a 258 ha project; a court partly halted the works" (tour, Agroparc) | project and ruling **reported** [ctx]; works **not shown**: no large earthworks Jun–Nov 2026 [57], nothing in Aug–Sep 2025 [68] | — | drop "earthworks". Use row 11 |
| 11 | "The core of the planned Agroparc was cleared in spring 2026" | **plausible**: vegetation echo flat 2016–2025, then −2 to −3 dB between Feb and May 2026 on about 8.5 ha [68]; optical: 15 ha Jan–Jun 2026 in a patch 0.4 km away [44]. The sector outline is our identification (unverified) [57] | vines pulled up or replanted; ploughing | "Vegetation was removed on about 8 ha of a planned development sector in spring 2026. Radar cannot say whether that is works or farming: needs review" |
| 12 | "New industrial estates since 2017, in planned sectors: expected" | **measured** and large: +11 dB on 22.9 ha in 2017–18, and two more estates [68] | few; a rise this size that lasts for years is buildings | keep. This is the cleanest Catalan evidence we have |

## 2. Three questions a sceptical judge asks, per site
**Muhos**
1. *The regulator knew in May. What does your app add?* It measures, pass by pass, that the clearing went on after the notice: three satellites show it still growing in July and August, by at least 70 ha after the end of May.
2. *How do you know the growth is the data-centre site and not ordinary forestry next door?* We don't have the project boundary; we show one compact block growing at its own edge, and we say "the cleared block", not "the company".
3. *Did the app find this, or did you tell it?* The satellites found and dated it without being told; the label rests on a notice we typed in, because Finland has no register we can query.

**Agroparc**
1. *Is that patch the Agroparc?* It is the planned development sector on the zoning map that matches the project's core; the outline is ours, and the card says so.
2. *Works or farming?* Radar cannot tell; ten flat years followed by a lasting drop is why it says "needs review" and not more.
3. *The press reported works in summer 2025 and you saw nothing. Does the method miss earthworks?* Yes on sparse farmland: moved soil barely changes the vegetation echo, and the optical alerts saw only 14 ha [44]. We state it as a limit.

## 3. Go / no-go
| Site | Video | Pitch | Condition |
|---|---|---|---|
| Muhos | **go**, with the wording of rows 1–6 | **go** | hectares in speech only as "about 330 ha, as reported" or the optical total; no "snow", no "March" as a radar date, no "nobody was looking"; the curve keeps its **three separate lines** [95]; NISAR is named only for what its line shows (rows 2–3) |
| Agroparc core | **no-go** | deferred; later only as row 11 | request 5 below answered |
| Agroparc window, industrial estates | no-go | deferred; later the "expected" card (row 12) | request 4 makes it a validation, not just a picture |
| Catalonia overview (closing shot) | **no-go today**: no data on `main` | no-go today | go once candidates are shown neutral and checked ones labelled; else close on the Agroparc window's ten-year replay |

## 4. Fallbacks
**(a) NISAR shows only a small tail at Muhos.** This is what happened: NISAR flags no change of its own [95]. Story in use: *three satellites, one timeline.* NASA's optical alerts date the clearing by month, Sentinel-1 shows it through cloud from April, and NISAR, flying since June, shows the bare block on every pass and its area still growing into August. Every picture and number on screen comes from a NASA data product (NISAR, OPERA alerts, OPERA Sentinel-1 backscatter, HLS photos): say that sentence.

**(b) Agroparc shows nothing real.** First, cost nothing: rename the site to what the data shows, **"Penedès–Martorell corridor: ten years of change"** (46 changes, estates in planned sectors come out "expected", the spring-2026 sector clearing "needs review") [68]. If a second Catalan site is wanted, in this order:
1. **Gavarres wildfire** (2,200 ha, 3–7 Jul 2026): certain and large in all three sources, inside the NISAR window, and the wildfire lookup already finds it (#47). It shows the app calming an alarm. Cost: a NISAR run with a one-pass baseline [57].
2. **Alcarràs solar** (656 ha, connected Feb–May 2026): built inside the Sentinel-1 and optical years, has a register entry, and is "permitted but questioned". Risks: construction years unverified, panel signal untested [ctx].
3. **Panattoni, Cerdanyola** (6.8 ha, first phase due Q4 2026): inside the NISAR window but small, urban clutter, schedule unverified [ctx].

**(c) Optical alerts and radar disagree at Muhos.** They do, on hectares and on timing (headline; Sentinel-1 sees the July part's echo falling by 22 Jun [95]). Rule: assert only what all three show (a block of roughly the reported size; growth in July and August), keep one line per source with its name, and say the disagreement out loud in the pitch's "why believe it" step: it is the honest limitation to show.

## 5. Still to measure (most valuable first, each under an hour)
Requests 1–3 of the first version (NISAR inside the optical outline, Sentinel-1 for the spring, where the summer growth is) were answered by [95].
1. **One NISAR picture pair for the video:** the block on 7 Jul and on 12 Aug 2026 (vegetation echo, same stretch), so the one sentence that names NISAR has its own picture.
2. **Why NISAR's bare area falls after September** (371 → 351 ha): wet ground, frost or regrowth? One line for the "limits" section.
3. **How much of the outline was open ground before 2026** (summer 2025, Sentinel-1 or photo): explains why NISAR starts at 308 ha where optical has 176.
4. Later, with Catalonia: corridor estates vs the land registry (construction year next to radar first-seen year), and the Agroparc core photo pair.

<sub>Written by Claude</sub>
