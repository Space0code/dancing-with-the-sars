# Official rules check: emails, guides, forum

What the organizers told us beyond `submission.md`: the Barcelona schedule, eligibility traps, awards, the challenge's
own questions, and the forum. Last updated 2026-11-15 00:50 (#122). Sources were read in full; forum posts were
skimmed by a sub-agent and the load-bearing ones re-read. To discuss at the Sunday 09:00 team meeting.

## 1. Barcelona schedule (Sun 15 Nov): submit by 16:00
| Time | What | Source |
|---|---|---|
| 09:00 | doors open, hacking | Local Lead email, 12 Nov |
| **16:00** | **"Fecha límite para entregar los proyectos y enviar las presentaciones"** (deadline for projects and presentations) | same email |
| 16:30 | **live presentations to the jury** (format and length not published) | same email |
| 18:50 | winners announced, prizes | same email |
| 23:59 | global form closes ("Submit for Judging") | Project Submission Guide |

- The Barcelona event page (written in August) still says "17:30 Pitch competition"; the 12 Nov email is newer and
  more detailed, so we take 16:00 / 16:30 as binding and confirm with the Local Lead at 09:00.
- Why it matters: "Check with your Local Lead about times for your Local Event's local judging and awards which may
  differ from the global submission times" (Submission Guide); the FAQ says "Submit your project for judging
  according to the ending time of your Local Event". **The local jury picks the Global Nominees**, so it judges what is
  on the project page at 16:00. Edits until 23:59 are still allowed (last save counts for global judging).
- Our `plan.md` has "freeze Sun 16:00 · submit Sun 22:00": the plan needs a submitted page, demo link and a pitch
  ready before 16:00, and the freeze earlier.
- The mentors are on site Sat and Sun; the campus stays open after 20:00.

## 2. Eligibility traps (any one of these = no Global Judging)
- **Every member confirmed for Barcelona**, not waitlisted: the Local Lead's individual confirmation form counted,
  not just the website registration; and every member on the team page's **Members** tab. "Teams will not be able to
  add new members after project submission has closed." Registration and event changes stay open until 15 Nov.
- One team per person, one challenge per team (FAQ).
- **No work before Sat 14 Nov 09:00**: "Working ahead of the hackathon can lead to disqualification. Any awards your
  project wins will be removed" (GO Team, [forum #1871](https://github.com/nasa/spaceapps/discussions/1871),
  [#1827](https://github.com/nasa/spaceapps/discussions/1827)). Our first commit is Sat 14 Nov 11:29; keep it that way
  (no pre-event material in the repo or demo).
- At least one NASA data source **from the challenge's Resources** (GO Team, [#1849](https://github.com/nasa/spaceapps/discussions/1849)):
  NISAR via ASF / Earthdata Search is listed, so we pass.
- Demo limits: video ≤ 30 s or ≤ 7 slides. "Projects that exceed these limits will not be eligible for Global Judging."
- AI images/video: a visible watermark; "crediting AI only on the final slide is not sufficient" (GO Team, quoted
  on the forum). The SI field is **required** in the form even though judges don't see it.
- No images, video or voice of anyone under 18, also not as avatar or on the team page (FAQ).

## 3. Our public team page (judges see it)
- Team name is **"4"**; the description says **"We will win (team 4 is the best)"**. Rename to the team / project name
  and replace the description with the tagline before 16:00.
- Team contact info lives on the About tab ("Team Contact Information", GO Team on the forum).

## 4. Judging and awards beyond `submission.md`
- "The majority of judges' evaluation will be based on your project submission" (the project page); the demo mainly
  lifts Presentation. "The more information you provide on this page, the better the judges can rate your submission."
- Presentation: "pay equal attention to the final criterion"; judges score it from the demo **and** the full project.
- Judges "have been trained to evaluate projects that have been constructed within 2 days" (GO Team, #1871).
- The 30 s video structure the guide suggests: 0:00 who we are + team name · 0:02 the challenge and what inspired us ·
  0:05 project name + tagline · 0:10 how it works, a user's experience, how NASA and partner data make it possible ·
  0:20–0:30 the future. Our shot list (`submission.md` §3) has no names/team intro and no "why we chose it".
- Slides fallback must show team name, members' names and the challenge.
- **Ten Global Awards** (executive judges pick among Global Finalists): Best Use of Science, Best Use of Data, Best Use
  of Technology, Galactic Impact, Best Mission Concept, Most Inspirational, **Best Storytelling** ("creatively
  communicates the potential of open data"), Global Connection, Art & Technology, **Local Impact** ("greatest potential
  for making a difference in their local community").
- Local awards are separate and decided by the Barcelona jury.
- Timeline: Global Nominees 3 Dec 2026 · Global Finalists + Honorable Mentions 17 Dec · Global Winners 26 Jan 2027 ·
  participant survey 30 Nov. Everyone who submits gets a certificate (profile → Participant Information); the name
  comes from "Full Name" in the profile.
- 2026 Space Agency Partners include **ESA** and the **Spanish Space Agency** ("highly encouraged" to use partner
  data). We use Copernicus Sentinel-1/-2 (ESA); name ESA explicitly in the partner-data field.

## 5. What the challenge text asks that our pitch should answer
From the challenge page (statement + "Potential Considerations"):
- "**Hypothesize the physical drivers** behind what you see (or don't see)"; "Which polarizations highlight these
  changes?"; "**What future applications of NISAR are possible?**" → one line each in the description and the pitch.
- "an **open-source**, user-friendly solution … for scientists, resource managers, educators, decision-makers, and the
  public"; time-series animations, change maps, image sliders, story maps are named as examples (we have all three).
- "Show how human drivers (agriculture, industry, etc.) are impacting Earth's natural resources" (Muhos fits).
- "If you are familiar with your study area (e.g. it's your hometown), you can provide personal context": Barcelona.
- Resources also list CSA's RADARSAT Constellation Mission, NISAR StoryMaps, ARSET (English and Spanish).

## 6. Forum (Space Apps Connect = github.com/nasa/spaceapps Discussions)
- 431 threads by 14 Nov (General 189, Find a Team 117, Challenges 43, Submission Help 21, Announcements 5); little spam,
  mostly repeated questions. Nothing about Barcelona or about our challenge from staff.
- Participant tips on NISAR (unverified): validated L-band products released 6 Nov 2026, earlier ones beta/provisional
  ([#1874](https://github.com/nasa/spaceapps/discussions/1874)); GitHub Pages / Netlify links are fine for the final
  project. Website problems on the submission page → web@spaceappschallenge.org (forum #2100).

## 7. Questions for 09:00
1. Move submit-for-judging to ~15:00 (page complete, demo link live), freeze earlier; then polish until 23:59?
2. Who asks the Local Lead at 09:00: pitch length and format at 16:30, is 16:00 the hard local cutoff, screen/HDMI?
3. Who prepares and gives the live pitch (`demo-strategy.md` §4 assumes 3 minutes, unverified)?
4. Rename the team page ("4") and rewrite its description; all three of us confirmed and on Members?
5. Add the guide's 0:00 intro (names, team) and "why this challenge" to the video?
6. Local Impact / a Barcelona jury: a Catalonia section or slide next to Muhos?

<sub>Written by Claude</sub>
