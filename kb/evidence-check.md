# Evidence check: what the video and the pitch may assert

A sceptical read of our results against the claims in `demo-strategy.md`. Last updated 2026-11-14 (#78). Sources: **[55]** PR #55 (Muhos, NISAR) · **[44]** finding on #44 (optical alerts) · **[57]** PR #57 and **[68]** PR #68 (Agroparc, NISAR and Sentinel-1) · **[46]** dry run on #46 · **[ctx]** `project-context.md` §7. Support: **measured** (our data shows it) · **plausible** (fits, other causes not excluded) · **reported** (press or regulator, not ours) · **not shown**.

## Headline
- **Muhos carries the story, but not with the numbers in `demo-strategy.md`.** "385 ha already bare on 25 Jun" and "+53 ha" come from one NISAR threshold [55] and do not agree with the optical alerts [44], which have 175 ha by the end of June and 358 ha by October. What both sources show is the direction: **the block kept growing through July and August**. Say that; keep hectares out of the narration unless they are the optical ones.
- **The regulator was not unaware:** the company asked to skip the assessment on 30 Apr and was told in May it was required [ctx]. "Nobody was looking" is false. The defensible value is **measuring that the cutting went on after the notice**, not discovering it.
- **Agroparc shows no large works in the NISAR window** [57]. It can appear in the pitch only as a small spring-2026 clearing in a planned sector, labelled "needs review" because radar cannot tell works from farming.

## 1. Claim by claim
| # | Sentence as planned | Support | What else gives the same signal | Wording we can defend |
|---|---|---|---|---|
| 1 | "About 330 ha were cleared, March to August 2026, before the assessment was finished" | **reported** [ctx]; optical alerts: 287 ha in the block by end of August, 358 ha by October [44] (same size within about 10 %) | the alert block is our outline, not the project boundary | keep, as "reported"; add "NASA's optical alerts show a block of the same size" |
| 2 | "About 385 ha were already bare when NISAR began watching" | **not shown.** It is ground with a low vegetation echo inside a 466 ha outline that "includes some older open ground and a piece of the road corridor" [55]; optical has 175 ha by end of June [44] | open bog, fields, old clear-cuts, a road | drop the number. "When NISAR began watching in June, a large part was already cleared" |
| 3 | "It grew by about 53 ha between 19 Jul and 24 Aug" | **measured as a lower bound** [55]: growth sits at the NE edge (spatially compact, so not a moisture shift); pass-to-pass wobble is about 8 ha (peak 446, end 438). Optical: +91 ha first seen in July, +21 in August [44] | ordinary forestry next door (about 220 ha of other confirmed loss in the window in 2026 [44]); the project boundary is not published | "NISAR shows the cleared block still growing in July and August", no hectares in speech |
| 4 | "This was after the May notice" | dates **reported** [ctx], growth **measured** (row 3). Optical: 137 ha by end of May, 358 by October, so 221 ha first seen after May; 183 ha (about half) first seen from July on [44] | an alert date is the first clear view, not the cutting day; clouds push it later [44] | "About half of the block was first seen from July on, two months after the notice" |
| 5 | "Six weeks before the order to stop" | dates only: 24 Aug to 6 Oct is 43 days. We processed in November; no live detection was shown. The 6 Oct act is a notice calling on the company to suspend [ctx] | — | "The satellite passes that show it were taken six weeks before the regulator called for a halt" |
| 6 | "Radar saw every stage, through clouds and snow" / "works in the dark northern winter" | **not shown.** NISAR starts 25 Jun; Sentinel-1 at Muhos is not analysed; the frozen 4 Nov pass had to be dropped [55]; March cutting was under snow [ctx] | — | "through cloud" only. Proof at hand: the optical scene behind the 31 Aug state was 100 % cloud [44] while NISAR kept passing |
| 7 | "The vegetation echo drops when forest is cut" (1.5–3 dB at Muhos; slash and stumps) | drop **measured** [55]; the cause is a **hypothesis** | sparse boreal forest gives little contrast to begin with | say "our hypothesis" |
| 8 | "The app checks every change against public records" | Catalonia: **measured**, live lookups, no failures [46]. Muhos: the record was **entered by hand** from the notice [46] | — | "in Catalonia it queries the public registers; for Muhos we entered the regulator's notice by hand" |
| 9 | "A short list" | **not shown yet.** Untuned: 394 changes at Muhos, 185 at Agroparc with 153 "needs review" [46]. Tuned: 24 [55] and 46 [68], labels not re-run | — | only after the tuned verdict run; else show the list filtered to one label |
| 10 | "Earthworks for a 258 ha project; a court partly halted the works" (tour, Agroparc) | project and ruling **reported** [ctx]; works **not shown**: no large earthworks Jun–Nov 2026 [57], nothing in Aug–Sep 2025 [68] | — | drop "earthworks". Use row 11 |
| 11 | "The core of the planned Agroparc was cleared in spring 2026" | **plausible**: vegetation echo flat 2016–2025, then −2 to −3 dB between Feb and May 2026 on about 8.5 ha [68]; optical: 15 ha Jan–Jun 2026 in a patch 0.4 km away [44]. The sector outline is our identification (unverified) [57] | vines pulled up or replanted; ploughing | "Vegetation was removed on about 8 ha of a planned development sector in spring 2026. Radar cannot say whether that is works or farming: needs review" |
| 12 | "New industrial estates since 2017, in planned sectors: expected" | **measured** and large: +11 dB on 22.9 ha in 2017–18, and two more estates [68] | few; a rise this size that lasts for years is buildings | keep. This is the cleanest Catalan evidence we have |

## 2. Three questions a sceptical judge asks, per site
**Muhos**
1. *The regulator knew in May. What does your app add?* It measures, pass by pass, that the clearing went on after the notice: about half of the block was first seen from July on.
2. *How do you know the growth is the data-centre site and not ordinary forestry next door?* We don't have the project boundary; we show one compact block growing at its own edge, and we say "the cleared block", not "the company".
3. *Did the app find this, or did you tell it?* The satellites found and dated it without being told; the label rests on a notice we typed in, because Finland has no register we can query.

**Agroparc**
1. *Is that patch the Agroparc?* It is the planned development sector on the zoning map that matches the project's core; the outline is ours, and the card says so.
2. *Works or farming?* Radar cannot tell; ten flat years followed by a lasting drop is why it says "needs review" and not more.
3. *The press reported works in summer 2025 and you saw nothing. Does the method miss earthworks?* Yes on sparse farmland: moved soil barely changes the vegetation echo, and the optical alerts saw only 14 ha [44]. We state it as a limit.

## 3. Go / no-go
| Site | Video | Pitch | Condition |
|---|---|---|---|
| Muhos | **go**, with the wording of rows 1–6 | **go** | no hectares from NISAR in speech; no "snow", no "nobody was looking"; the cleared-area picture draws optical and NISAR as **two separate lines**, never one stitched curve (it would jump from 175 to 385 ha) |
| Agroparc core | **no-go** | **go only as row 11** | request 5 below answered; otherwise skip the core |
| Agroparc window, industrial estates | no-go | **go**: the "expected" card (row 12) | request 4 makes it a validation, not just a picture |
| Catalonia overview (closing shot) | **no-go today**: no data on `main` | no-go today | go once candidates are shown neutral and checked ones labelled; else close on the Agroparc window's ten-year replay |

## 4. Fallbacks
**(a) NISAR shows only a small tail at Muhos.** This is already the case: the detector finds 17.6 ha of clearing [55]. Story: *three satellites, one timeline.* NASA's optical alerts date the spring by month; NISAR shows the block through cloud on every pass from June and its edge still moving in July–August. NISAR is cast as the eye that does not wait for clear sky, not as the one that measured the total.

**(b) Agroparc shows nothing real.** First, cost nothing: rename the site to what the data shows, **"Penedès–Martorell corridor: ten years of change"** (46 changes, estates in planned sectors come out "expected", the spring-2026 sector clearing "needs review") [68]. If a second Catalan site is wanted, in this order:
1. **Gavarres wildfire** (2,200 ha, 3–7 Jul 2026): certain and large in all three sources, inside the NISAR window, and the wildfire lookup already finds it (#47). It shows the app calming an alarm. Cost: a NISAR run with a one-pass baseline [57].
2. **Alcarràs solar** (656 ha, connected Feb–May 2026): built inside the Sentinel-1 and optical years, has a register entry, and is "permitted but questioned". Risks: construction years unverified, panel signal untested [ctx].
3. **Panattoni, Cerdanyola** (6.8 ha, first phase due Q4 2026): inside the NISAR window but small, urban clutter, schedule unverified [ctx].

**(c) Optical alerts and radar disagree at Muhos.** They do, on hectares (175 vs 385 at the end of June; +183 vs +53 after it). Rule: assert only what both show (a block of roughly the reported size; growth in July and August), give each source its own line and name, and say the disagreement out loud in the pitch's "why believe it" step: it is the honest limitation to show.

## 5. Still to measure (most valuable first, each under an hour)
1. **Muhos, NISAR inside the optical block:** low-echo hectares per pass restricted to the 450 ha optical outline, and to ground that was forest in 2025. Makes rows 2–3 comparable with [44].
2. **Muhos, Sentinel-1 since May 2025:** vegetation echo per pass inside the block, hectares by month for spring 2026. A radar date for the spring, and a second opinion on optical vs NISAR.
3. **Muhos, where the July–August growth is:** share of NISAR's NE-edge growth that the optical alerts also first saw in July–August, and whether it lies inside the `scope` polygon.
4. **Corridor estates vs the land registry:** for the six largest Sentinel-1 "structure" changes [68], radar first-seen year next to the cadastre construction year. A measured validation for the pitch.
5. **Agroparc core:** overlap of the 8.5 ha Sentinel-1 clearing with the optical patch, plus one photo pair (2025, 2026). Also the label counts per site on the tuned data (row 9).

<sub>Written by Claude</sub>
