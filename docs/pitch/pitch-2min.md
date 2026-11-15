# Parallax pitch: the 2-minute version (one speaker, 7 slides)

DRAFT for Andrea's review. Not pushed. About 245 spoken words, 2:00 at a calm pace (the animations give you pauses).
The long version with the fact check, the animation list and the open questions is `pitch-full.md`.

**Rules this follows** (`kb/demo-strategy.md`, mentor decision 15 Nov): deck of at most 7 slides, talk 2 to 3 minutes,
1 or 2 clips of at most 10 s each inside the slides, no AI imagery, slide 1 shows project name, tagline, team name,
all members and the challenge.

## The script

| Slide | Time | What you say | What the audience sees |
|---|---|---|---|
| 1. Title | 0:00 to 0:12 | "In spring 2026, a forest in northern Finland was cleared for a data centre: about 330 hectares, as Finnish media reported. That is roughly 460 football fields." | Title slide: **Parallax**, "Know where to look first.", team name, members, challenge. Behind it, a still of the Muhos forest, summer 2025, intact. |
| 2. The six months | 0:12 to 0:40 | "Cutting started in March. On 30 April the developer asked to skip the environmental assessment. In May it was told one was required. The cutting went on. On 6 October the regulator called for a halt. More than six months after the first cut." | **Animation 1, the clock** (slide animation, not a video): a timeline from March to October, a marker moves along it, the flags appear as it passes. |
| 3. The problem | 0:40 to 0:55 | "The regulator needed to know where to look, fast. But optical satellites need clear skies. The optical scene we found for 31 August was 100 percent cloud." | A cloud-covered optical scene fades to the same place seen by radar (two stills, one fade). |
| 4. Why radar | 0:55 to 1:10 | "Radar does not have this problem. It sends its own microwaves, which pass through clouds, day or night. NASA's NISAR and ESA's Sentinel-1 return to the same ground every 12 days or less." | One simple picture: satellite, pulse going through a cloud, ground. Logos or names: NASA NISAR, ESA Sentinel-1. |
| 5. Parallax | 1:10 to 1:35 | "We built Parallax. It turns radar data into a short, explained list of land changes a regulator should check first. In Finland, radar shows the cleared block from April, NASA's alerts confirm 109 hectares by the end of April, and three satellites agree it kept growing in July and August." | **Clip A, 10 s**: the real app on Muhos, Radar view, Play: the date runs April to October, the marked area grows, "Marked so far: N ha" counts up. |
| 6. How it decides | 1:35 to 1:52 | "Every change gets a label: expected, needs review, or high concern. The rules are fixed and visible, no black box. Parallax checks public records, so in Catalonia a new industrial estate in a planned zone comes out as expected, not as an alarm." | **Clip B, 8 s** (optional): a change card opens, the label and the "Why this label?" reasons appear one by one. |
| 7. Try it | 1:52 to 2:00 | "Scan the code to try it. Finland is live; Barcelona and its surroundings run in our demo build. Parallax: know where to look first." | QR code to the live app, the tagline, one line: "Next: any region, and an alert when a change appears." |

## Animations (details in `pitch-full.md`)

1. **The clock (slide 2).** Built with the slide tool's own animation, no video. Timeline March to October. A marker
   travels left to right over about 12 s. Flags drop in when it passes: **Mar** "cutting starts (reported)", **30 Apr**
   "developer asks to skip the assessment", **May** "told it is required", **6 Oct** "regulator calls for a halt". A counter
   under the line counts the months since the first cut up to "6+". Jul and Aug are shaded: "still growing, 3 satellites".
2. **Clip A (slide 5).** A screen capture of the live app: `#site=muhos`, Radar view, press Play. The date label, the
   orange area and the "Marked so far" counter change by themselves. Silent, looping, 10 s at most.
3. **Clip B (slide 6).** A screen capture of a card opening. 8 s at most. Cut it first if the deck looks heavy.
4. **Slides 3 and 4:** plain fades between two stills, nothing more.

## Open before this goes anywhere

See "Open questions" in `pitch-full.md`: the company name, the 109 hectares line, the cloudy picture, and what the public
link shows for Barcelona.
