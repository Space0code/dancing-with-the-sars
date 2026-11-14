// Written by Claude. Timeline slider: one step = one satellite snapshot. Red bars mark where changes first show.
import { formatDate, toDay, h } from "./format.js";

const PLAY_SECONDS = 12; // time to play through all snapshots (each step lasts between MIN_STEP_MS and MAX_STEP_MS)
const MIN_STEP_MS = 250;
const MAX_STEP_MS = 900;
const MAX_TICKS = 80; // with more snapshots the plain ticks would merge into a solid block, so only the red bars stay
const GAP_DAYS = 60; // a longer pause between two snapshots is a gap worth a note
const LEAD_IN = 4; // play from the end starts this many snapshots before the first change, not at the (often quiet) first one

/** The site's snapshots, or (older data) the distinct change dates plus both ends of its time range. */
function snapshotsOf(site, features) {
  if (site.snapshots?.length) return site.snapshots;
  const dates = new Set(site.time_range);
  for (const f of features) dates.add(f.properties.first_date);
  return [...dates].filter((d) => d >= site.time_range[0] && d <= site.time_range[1]).sort().map((date) => ({ date, sensor: "" }));
}

/** `onDate(iso)`: the slider moved to a snapshot. */
export function createTimeline({ onDate }) {
  const $ = (id) => document.getElementById(id);
  const slider = $("slider");
  const playBtn = $("play");
  let stops = []; // [{date, sensor}], oldest first: the open view's pictures
  let own = null; // {features, stops}: the open site; `own.stops` = its snapshots (the radar view)
  let playing = false;
  let timer = 0;
  let stopAt = 0; // slider value where playing stops
  let playFrom = 0; // where play starts when the slider is at the end

  const index = () => Number(slider.value);
  const pct = (i) => (stops.length > 1 ? (i / (stops.length - 1)) * 100 : 50);

  /** Index of the last snapshot on or before `iso`; the first one when `iso` is earlier than all of them. */
  function snap(iso) {
    let found = 0;
    for (let i = 0; i < stops.length && stops[i].date <= iso; i++) found = i;
    return found;
  }

  function emit() {
    const stop = stops[index()];
    $("date-label").replaceChildren(formatDate(stop.date), h("span", { class: "date-sub" }, ` · image ${index() + 1} of ${stops.length}`));
    // Just stepped past a long gap in the snapshots (winter, left out on purpose): say so instead of silently jumping.
    const prev = stops[index() - 1];
    const gap = prev && toDay(stop.date) - toDay(prev.date) > GAP_DAYS;
    $("gap-note").textContent = gap ? `No pictures between ${formatDate(prev.date)} and ${formatDate(stop.date)}` : "";
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
    /** Open a site: its snapshots, its changes (for the red bars) . The slider starts at the end. */
    setRange(site, features = []) {
      stop();
      stops = snapshotsOf(site, features);
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
      stops = list?.length ? list : own.stops;
      slider.value = nearest(iso);
      build();
      if (playing && index() >= stops.length - 1) stop();
      emit();
    },
    /** No site open: the timeline is inactive and says so. */
    clear() {
      stop();
      own = null;
      stops = [];
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
