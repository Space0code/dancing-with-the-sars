// Written by Claude. Timeline slider: one step = one satellite snapshot. Red bars mark where changes first show.
import { formatDate, toDay, h } from "./format.js";

const PLAY_SECONDS = 12; // time to play through all snapshots (each step lasts between MIN_STEP_MS and MAX_STEP_MS)
const MIN_STEP_MS = 250;
const MAX_STEP_MS = 900;
const MAX_TICKS = 80; // with more snapshots the plain ticks would merge into a solid block, so only the red bars stay
const GAP_DAYS = 60; // a longer pause between two snapshots is a gap worth a note
const LEAD_IN = 4; // play from the end starts this many snapshots before the first change, not at the (often quiet) first one

const MONTH_YEAR = new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });

/** Short satellite name for the strip and its line. */
const shortName = (sensor) => (/nisar/i.test(sensor) ? "NISAR radar" : /sentinel-1/i.test(sensor) ? "Sentinel-1 radar" : /dist-alert|optical|hls|sentinel-2/i.test(sensor) ? "Optical alerts" : sensor);

/** "2023" for a start on 1 January (the year is all we know), else "June 2026". */
const whenStarts = (iso) => (iso.slice(5) === "01-01" ? iso.slice(0, 4) : MONTH_YEAR.format(new Date(iso)));

/** The site's snapshots, or (older data) the distinct change dates plus both ends of its time range. */
function snapshotsOf(site, features) {
  if (site.snapshots?.length) return site.snapshots;
  const dates = new Set(site.time_range);
  for (const f of features) dates.add(f.properties.first_date);
  return [...dates].filter((d) => d >= site.time_range[0] && d <= site.time_range[1]).sort().map((date) => ({ date, sensor: "" }));
}

/** `onDate(iso)`: the slider moved to a snapshot. `describe(iso)`: the small text after the date (which picture this is), or "".
 * `pictured()`: false when no dated pictures are on the map (the Satellite imagery): a gap is then one in the passes. */
export function createTimeline({ onDate, describe = () => "", pictured = () => true }) {
  const $ = (id) => document.getElementById(id);
  const slider = $("slider");
  const playBtn = $("play");
  let stops = []; // [{date, sensor}], oldest first: the open view's pictures
  let own = null; // {features, stops}: the open site; `own.stops` = its snapshots (the radar view)
  let playing = false;
  let timer = 0;
  let stopAt = 0; // slider value where playing stops
  let playFrom = 0; // where play starts when the slider is at the end

  let sources = []; // the open site's `sources` (who watches, from when to when), oldest start first; [] = unknown, strip hidden
  const index = () => Number(slider.value);
  const pct = (i) => (stops.length > 1 ? (i / (stops.length - 1)) * 100 : 50);

  /** Index of the last snapshot on or before `iso`; the first one when `iso` is earlier than all of them. */
  function snap(iso) {
    let found = 0;
    for (let i = 0; i < stops.length && stops[i].date <= iso; i++) found = i;
    return found;
  }

  /** Slider position (0 to 100 %) of a date: between two snapshots it sits in between, outside the track it stops at the ends. */
  function pctOfDate(iso) {
    if (stops.length < 2 || iso <= stops[0].date) return 0;
    if (iso >= stops.at(-1).date) return 100;
    const i = snap(iso);
    const [a, b] = [toDay(stops[i].date), toDay(stops[i + 1].date)];
    return pct(i + (toDay(iso) - a) / (b - a));
  }

  /** "Watching on 12 Mar 2021: Sentinel-1 radar. Optical alerts start in 2023, NISAR radar in June 2026." */
  function watchingText(iso) {
    const active = sources.filter((s) => s.start <= iso && (!s.end || s.end >= iso)).map((s) => shortName(s.sensor));
    const later = sources.filter((s) => s.start > iso);
    const parts = [active.length ? `Watching on ${formatDate(iso)}: ${active.length > 1 ? `${active.slice(0, -1).join(", ")} and ${active.at(-1)}` : active[0]}.` : `No satellite record before ${later[0] ? whenStarts(later[0].start) : "now"}.`];
    if (later.length) {
      const [first, ...rest] = later.map((s) => [shortName(s.sensor), whenStarts(s.start)]);
      const verb = /alerts$/.test(first[0]) ? "start" : "starts";
      parts.push([`${first[0]} ${verb} in ${first[1]}`, ...rest.map(([n, w]) => `${n} in ${w}`)].join(", ") + ".");
    }
    return parts.join(" ");
  }

  /** The strip under the slider: one thin bar per source on the slider's own axis, the part before the first record greyed. */
  function drawCoverage() {
    const box = $("coverage");
    box.hidden = !sources.length || !stops.length;
    const rowsBox = box.querySelector(".cov-rows");
    if (box.hidden) return rowsBox.replaceChildren();
    const first = pctOfDate(sources[0].start);
    const rows = sources.map((s) => {
      const left = pctOfDate(s.start);
      const right = s.end ? pctOfDate(s.end) : 100;
      const begins = left > 0 ? `${shortName(s.sensor)} begins ${whenStarts(s.start)}` : "";
      return h("div", { class: "cov-row" }, h("span", { class: `cov-bar${begins ? " cov-begins" : ""}`, style: `left:${left}%;width:${Math.max(right - left, 1)}%`, title: begins || shortName(s.sensor) }, shortName(s.sensor)));
    });
    const grey = first > 0 ? [h("span", { class: "cov-none", style: `width:${first}%` }, `No satellite record here before ${sources[0].start.slice(0, 4)}`)] : [];
    rowsBox.replaceChildren(...grey, ...rows);
  }

  function emit() {
    const stop = stops[index()];
    if (sources.length) $("watching").textContent = watchingText(stop.date);
    const sub = describe(stop.date);
    $("date-label").replaceChildren(formatDate(stop.date), ...(sub ? [h("span", { class: "date-sub" }, ` · ${sub}`)] : [])); // no sub: the date alone (null would print "null")
    // Just stepped past a long gap in the snapshots (winter, left out on purpose): say so instead of silently jumping.
    const prev = stops[index() - 1];
    const gap = prev && toDay(stop.date) - toDay(prev.date) > GAP_DAYS;
    $("gap-note").textContent = gap ? `No ${pictured() ? "pictures" : "satellite passes"} between ${formatDate(prev.date)} and ${formatDate(stop.date)}` : "";
    onDate(stop.date);
  }

  function stop() {
    playing = false;
    clearTimeout(timer);
    playBtn.textContent = "▶";
    playBtn.setAttribute("aria-label", "Play timeline");
  }

  function tick() {
    if (!playing) return;
    slider.value = index() + 1;
    emit();
    if (index() >= stopAt) stop();
    else timer = setTimeout(tick, stepMs());
  }

  const stepMs = () => Math.min(MAX_STEP_MS, Math.max(MIN_STEP_MS, (PLAY_SECONDS * 1000) / stops.length));

  function play(until = stops.length - 1) {
    if (index() >= until) slider.value = playFrom;
    stopAt = until;
    playing = true;
    playBtn.textContent = "❚❚";
    playBtn.setAttribute("aria-label", "Pause timeline");
    emit();
    timer = setTimeout(tick, stepMs());
  }

  function goToIndex(i) {
    stop();
    slider.value = i;
    emit();
  }

  /** Red bars (where changes first show) and, when there are few snapshots, plain ticks. */
  function drawTicks(features) {
    const counts = new Map(); // snapshot index -> number of changes first seen there
    playFrom = 0;
    for (const f of features) {
      let i = stops.findIndex((s) => s.date >= f.properties.first_date); // between two snapshots: the next one
      if (i < 0) i = stops.length - 1;
      counts.set(i, (counts.get(i) ?? 0) + 1);
    }
    const nodes = [];
    if (stops.length <= MAX_TICKS) {
      stops.forEach((s, i) => !counts.has(i) && nodes.push(h("span", { class: "tick", style: `left:${pct(i)}%` })));
    }
    if (counts.size) playFrom = Math.max(0, Math.min(...counts.keys()) - LEAD_IN);
    for (const [i, n] of [...counts].sort((x, y) => x[0] - y[0])) {
      const text = `${formatDate(stops[i].date)}: ${n} new ${n === 1 ? "change" : "changes"}`;
      nodes.push(
        h("button", {
          class: "change-bar", type: "button", style: `left:${pct(i)}%`, title: text, "aria-label": text,
          onclick: () => {
            goToIndex(i);
            $("event-note").textContent = "";
            slider.focus();
          },
        })
      );
    }
    $("ticks").replaceChildren(...nodes);
  }

  /** Index of the stop closest in time to `iso`. */
  function nearest(iso) {
    if (!iso) return 0;
    let best = 0;
    for (let i = 1; i < stops.length; i++) {
      if (Math.abs(toDay(stops[i].date) - toDay(iso)) < Math.abs(toDay(stops[best].date) - toDay(iso))) best = i;
    }
    return best;
  }

  /** Draw the track for the current stops: slider range, end dates, red bars and (if any) event flags. */
  function build() {
    const { features } = own;
    slider.max = stops.length - 1;
    $("range-start").textContent = formatDate(stops[0].date);
    $("range-end").textContent = formatDate(stops[stops.length - 1].date);
    $("event-note").textContent = "";
    drawTicks(features);
    drawCoverage();
  }

  playBtn.addEventListener("click", () => (playing ? stop() : play()));
  slider.addEventListener("input", () => {
    stop();
    $("event-note").textContent = "";
    emit();
  });
  // Arrow keys step one snapshot even when the slider itself is not focused (the slider does it natively when it is).
  document.addEventListener("keydown", (e) => {
    if ((e.key !== "ArrowLeft" && e.key !== "ArrowRight") || slider.disabled || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.target !== document.body) return;
    goToIndex(Math.min(Math.max(index() + (e.key === "ArrowRight" ? 1 : -1), 0), stops.length - 1));
    e.preventDefault();
  });

  return {
    /** The changes the red bars stand for (the Filter's selection; all of them when none is set). Snapshots and slider stay as they are. */
    setChanges(features) {
      if (!own) return;
      own.features = features;
      drawTicks(features);
    },
    /** Open a site: its snapshots, its changes (for the red bars) . The slider starts at the end. */
    setRange(site, features = []) {
      stop();
      stops = snapshotsOf(site, features);
      sources = [...(site.sources ?? [])].sort((a, b) => a.start.localeCompare(b.start));
      own = { features, stops };
      slider.disabled = playBtn.disabled = false;
      slider.max = stops.length - 1;
      slider.value = stops.length - 1;
      build();
      emit();
    },
    /**
     * Step through another list of pictures (the Satellite view's photos) instead of the site's snapshots; null = back to
     * the snapshots. The slider keeps the nearest date and a running play carries on in the new list.
     */
    setStops(list) {
      if (!own) return;
      const iso = stops[index()]?.date;
      const end = own.stops.at(-1); // photos that end before the site's last date: keep that date as a final stop, so no change drops out
      stops = list?.length ? (list.at(-1).date < end.date ? [...list, { date: end.date, sensor: "" }] : list) : own.stops;
      slider.max = stops.length - 1; // before the value: a range input clamps to its old max
      slider.value = nearest(iso);
      build();
      if (playing) {
        stopAt = stops.length - 1; // a running play carries on to the end of the new list
        if (index() >= stopAt) stop();
      }
      emit();
    },
    /** No site open: the timeline is inactive and says so. */
    clear() {
      stop();
      own = null;
      stops = [];
      sources = [];
      $("watching").textContent = "";
      $("coverage").hidden = true;
      slider.disabled = playBtn.disabled = true;
      for (const id of ["range-start", "range-end", "event-note", "gap-note", "total"]) $(id).textContent = "";
      $("ticks").replaceChildren();
      $("date-label").textContent = "Choose a site";
    },
    /** Jump to a date (used by the guided tour and links): the snapshot on or before it; the note explains why we are there. */
    goTo(iso, note = "") {
      goToIndex(snap(iso));
      $("event-note").textContent = note;
    },
    /** Jump to `from`, then play forward to `to` (the tour's "watch it happen" steps). */
    playBetween(from, to, note = "") {
      this.goTo(from, note);
      if (snap(to) > index()) play(snap(to));
    },
    setTotal(text) {
      $("total").textContent = text;
    },
  };
}
