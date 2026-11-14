// Written by Claude. Timeline slider (one step = one day) with play button and story-event markers.
import { toDay, fromDay, formatDate, h } from "./format.js";

const PLAY_SECONDS = 12; // time to play through the whole range

export function createTimeline({ onDate }) {
  const $ = (id) => document.getElementById(id);
  const slider = $("slider");
  const playBtn = $("play");
  let startDay = 0;
  let playing = false;
  let position = 0; // fractional day while playing
  let lastFrame = 0;

  function emit() {
    const iso = fromDay(startDay + Number(slider.value));
    $("date-label").textContent = formatDate(iso);
    onDate(iso);
  }

  function stop() {
    playing = false;
    playBtn.textContent = "▶";
    playBtn.setAttribute("aria-label", "Play timeline");
  }

  function frame(now) {
    if (!playing) return;
    const max = Number(slider.max);
    position = Math.min(max, position + ((now - lastFrame) / 1000) * (max / PLAY_SECONDS));
    lastFrame = now;
    if (Math.floor(position) !== Number(slider.value)) {
      slider.value = Math.floor(position);
      emit();
    }
    if (position >= max) stop();
    else requestAnimationFrame(frame);
  }

  function play() {
    if (Number(slider.value) >= Number(slider.max)) slider.value = 0;
    position = Number(slider.value);
    playing = true;
    playBtn.textContent = "❚❚";
    playBtn.setAttribute("aria-label", "Pause timeline");
    emit();
    lastFrame = performance.now();
    requestAnimationFrame(frame);
  }

  function goTo(iso) {
    stop();
    slider.value = Math.min(Math.max(toDay(iso) - startDay, 0), Number(slider.max));
    emit();
  }

  playBtn.addEventListener("click", () => (playing ? stop() : play()));
  slider.addEventListener("input", () => {
    stop();
    $("event-note").textContent = "";
    emit();
  });

  return {
    /** Set the site's date range and its story events; the slider starts at the end so everything is visible. */
    setRange([start, end], events = []) {
      stop();
      startDay = toDay(start);
      const days = toDay(end) - startDay;
      slider.max = days;
      slider.value = days;
      $("range-start").textContent = formatDate(start);
      $("range-end").textContent = formatDate(end);
      $("event-note").textContent = "";
      $("events").replaceChildren(
        ...events
          .filter((e) => e.date >= start && e.date <= end)
          .map((e) =>
            h("button", {
              class: "event-marker", type: "button", style: `left:${((toDay(e.date) - startDay) / (days || 1)) * 100}%`,
              title: `${formatDate(e.date)}: ${e.label}`, "aria-label": `Event on ${formatDate(e.date)}: ${e.label}`,
              onclick: () => {
                goTo(e.date);
                $("event-note").textContent = `${formatDate(e.date)}: ${e.label}`;
              },
            }, "▲")
          )
      );
      emit();
    },
    setTotal(text) {
      $("total").textContent = text;
    },
  };
}
