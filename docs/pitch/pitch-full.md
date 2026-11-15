# Parallax pitch: the full version (one speaker, 7 slides, no time budget)

DRAFT for Andrea's review. Not pushed. About 335 spoken words (about 2:30 at a calm pace), no longer than the original
draft (about 330 words). The 2-minute cut is `pitch-2min.md`. This file also holds the fact check, the animation list and the open questions.

**Rules this follows** (`kb/demo-strategy.md`, mentor decision 15 Nov): at most 7 slides, talk of 2 to 3 minutes, 1 or 2
clips of at most 10 s each inside the slides, no AI imagery, slide 1 shows project name, tagline, team name, all members
and the challenge, deck submitted before 16:00.

## 1. The script

**Slide 1: title** (backdrop: the Muhos forest in summer 2025, intact)
> In spring 2026, a forest in northern Finland was cleared for a data centre. About 330 hectares, as Finnish media
> reported: roughly 460 football fields. It was cut before the required environmental assessment was finished.

**Slide 2: the six months** (Animation 1, the clock)
> Cutting started in March. On 30 April the developer asked to skip the environmental assessment. In May it was told one
> was required. The cutting went on through the summer. On 6 October the regulator called for a halt: more than six
> months after the first cut.

**Slide 3: the problem** (cloudy optical scene fades to radar)
> An inspector needs to know where to look, and soon. But optical satellite images depend on clear skies. The optical
> scene we found for 31 August was 100 percent cloud. Both radars kept passing.

**Slide 4: why radar** (one simple picture)
> Radar sends its own microwaves. Their wavelength is centimetres, far larger than cloud droplets, so clouds do not stop
> them, and they work at night. NASA's NISAR, launched in July 2025, and ESA's Sentinel-1 return to the same ground
> every 12 days or less.

**Slide 5: Parallax** (Clip A)
> So we built Parallax, for the people who decide where to inspect. It finds substantial changes in the land surface and
> lists them. In Finland, radar first shows the cleared block on 4 April. NASA's optical alerts confirm 109 hectares by
> the end of April and 359 by October, close to the 330 reported. Three satellites agree it was still growing in July and
> August.

**Slide 6: how it decides** (Clip B, optional)
> Each change gets one of three labels: expected, needs review, high concern. The labels come from fixed, visible
> rules, not a black box. Parallax then checks public records: in Catalonia, zoning, land registry and protected areas, so
> a new industrial estate in a planned zone comes out as expected, not as an alarm. In Finland we entered the regulator's
> notice by hand.

**Slide 7: try it** (QR code)
> Finland is live at this link. Barcelona and its surroundings run in our demo build. The same approach can be set up
> for any region: choose an area and dates, get a report. Next: an alert when a new change appears. Parallax: know where
> to look first.

## 2. Animations: what changes on screen, and what it adds

The pitch stays short because the animations carry the context. Only two are clips of the real app (10 s each at most, as
the mentor allowed); the rest are normal slide animations, so nothing in the deck is a long video.

**Animation 1: the clock (slide 2). Slide animation, no video.**
- A horizontal timeline, March to October 2026, on a dark strip across the slide. A small date label sits on the marker.
- The marker moves left to right in about 12 s while you speak. Flags drop in as it passes, one per sentence:
  **March** "cutting starts (reported)" · **30 Apr** "developer asks to skip the assessment" · **May** "told it is
  required" · **6 Oct** "regulator calls for a halt".
- Under the line a counter runs: "months since the first cut: 1, 2, 3 ... 6+". July and August are shaded with the note
  "still growing: 3 satellites".
- Adds: the audience feels the length of the delay without a number on the slide.

**Slide 3: two stills with a fade.** The cloudy optical scene, then the same place in the radar view. Adds: why optical
alone fails here. Needs a real picture (see open questions).

**Slide 4: one diagram, built in three steps.** Satellite, a pulse going down, the cloud layer drawn as no obstacle,
the ground and the echo coming back. Adds: the one-sentence reason radar works through clouds.

**Clip A (slide 5), 10 s at most, silent, looping.** A screen capture of the live app on Muhos: `#site=muhos`, Radar
view, press Play. The date label runs April to October, the orange marked area grows month by month, the "Marked so far:
N ha" counter counts up and the May flag passes. Adds: the same timeline as slide 2, now with the real data on a map.

**Clip B (slide 6), 8 s at most, optional.** A screen capture of a change card opening: the label first, then the
"Why this label?" reasons appearing one at a time. Adds: the answer to "how do you know?". Cut this one first if the deck
feels heavy.

**Slide 7:** the QR code and the tagline only.

## 3. Fact check

Sources: `kb/project-context.md` §7, `kb/evidence-check.md`, `kb/demo-strategy.md`, `kb/data-sources.md`, `kb/sar-primer.md`.
**Reported** = press or regulator, not measured by us. **Measured** = our data shows it.

| Statement in the script | Status | Note |
|---|---|---|
| About 330 ha cleared at Muhos | reported (HS/Kaleva) | say "as reported"; our own alerts show 359 ha by 23 Oct |
| 460 football fields | arithmetic | 330 ha / 0.71 ha (105 x 68 m) = about 460 |
| Cutting started in March | reported | our radar first shows the block on 4 Apr; we say "March" only as reported |
| 30 Apr: the developer asked to skip the assessment; May: told it is required; kept cutting | reported (project-context §7) | |
| 6 Oct: the regulator called for a halt | reported (LVV press release; Yle dates it 7 to 8 Oct) | it is a notice calling on the company to suspend, not a court order |
| "More than six months after the first cut" | true on either start | 4 Apr to 6 Oct is 6 months, March to 6 Oct is about 7 |
| Cutting went on through the summer | **measured** | three satellites show the block still growing in July and August |
| The optical scene for 31 Aug was 100 percent cloud, both radars kept passing | **measured** (finding on #44) | |
| Microwaves pass through clouds, work at night | physics (`sar-primer.md` §1) | clouds and night only: we do not claim snow |
| NISAR launched July 2025; every 12 days; Sentinel-1 6 to 12 days | verified (`project-context.md`) | NISAR launched 30 Jul 2025 |
| Radar first shows the block on 4 April | **measured** | the previous usable pass is Sep 2025; April passes can be disturbed by wet snow, so "first shows", not "first cut" |
| 109 ha confirmed by 29 Apr; 359 ha by 23 Oct (NASA optical alerts) | **measured** | optical alerts are the first clear view, not the cutting day |
| Three satellites agree it kept growing in July and August | **measured** | optical +112 ha, Sentinel-1 +42 ha, NISAR +60 ha; they disagree on total hectares (176 / 200 / 308 ha at the end of June) |
| Three labels: expected, needs review, high concern | implemented | rules in `src/sarwatch/verdict.py` and `kb/verdict-rules.md`; no machine-learning classifier |
| Checks public records (zoning, land registry, protected areas) in Catalonia | implemented, measured | lookups ran without failures; the Barcelona record layers are on the `overnight` branch |
| In Finland the record is typed in by hand | true | no register we can query |
| New industrial estate in a planned zone comes out as expected | measured (Agroparc corridor, 46 changes) | |
| Finland live at the link | true | the Pages site serves `main` |
| Barcelona and its surroundings in the demo build | true, **not on the public link yet** | PR #140 (`overnight` to `main`) carries it as a hidden, link-only site |
| Choose an area and dates, get a report | implemented on `overnight` (PR #140), not on `main` yet | draw box / upload file, date filter, PDF report |
| Any region | **future** | the pipeline runs per site today; an alert when a change appears is future work (mentor point 10) |

## 4. What I changed from your draft, and why

1. **"Google" and "a court".** The repo's own rule (`demo-strategy.md` §6) keeps the company's name out of the pitch,
   and the halt came from a regulator (the Finnish permit and supervisory agency, LVV), not a court. I wrote "the
   developer" and "the regulator". If you want "Google" back it is one word on slides 1 and 2.
2. **"They found out they started without permission."** The regulator already knew in May: the developer asked on 30 Apr
   and was told in May that an assessment was required. What is reported is that the cutting went on before the
   assessment was done. I wrote that, and moved the 6 Oct halt to the end.
3. **"After 7 months."** Six months and a few days from our first radar sighting (4 Apr), about seven from March. I wrote
   "more than six months" so it holds either way.
4. **"The area was hidden, not easy to reach."** No source in the repo. Removed. Say it only if you can cite one.
5. **Clouds.** I replaced "clouds etc." with the one case we measured: the 31 Aug optical scene was 100 percent cloud.
6. **"How long Parallax took to detect it."** We processed the data in November, nothing ran live, so any "detected in X
   days" would be false. The defensible version is the one on slide 5: the radar shows the block from 4 April, six months
   before the halt.
7. **"A model with deterministic rules."** It is rules only, no trained model. The only AI in the product is the text
   summary in the PDF report, which I left out of the pitch.
8. **Exact dates before the cutting** (when the company decided to build). No source, so slide 2 starts at the cutting.

## 5. Open questions (answers change the slides)

1. **Name the company or not?** Default in this draft: not named, per the team rule.
2. **Slide 5 uses "109 hectares by the end of April" and "359 by October".** Both are in `evidence-check.md`, but the final
   numbers should be re-read from `app/data/muhos/` once more before the deck is sent.
3. **The cloudy picture for slide 3.** I have no image of the 100 percent cloud scene. We need one from the optical
   data (ask Tian's agent for the file), or a labelled example scene with its credit.
4. **Barcelona on the public link.** Today it is in the `overnight` branch, hidden, link only. If PR #140 is merged
   before 16:00 the sentence on slide 7 can say "live"; if not, keep "demo build".
5. **Clips count.** The mentor said 1 or 2 clips of 10 s at most. You mentioned GIFs: I count each GIF as a clip, so
   Clip A and Clip B are the whole budget. Is that your reading too?
6. **Slide 1 content.** Needs team name (Parallax), all members' names and the challenge title, in the deck itself.
