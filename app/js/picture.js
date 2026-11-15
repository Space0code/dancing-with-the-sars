// Written by Claude. The big picture on the map: the Radar / Satellite switch, the radar frame
// or colour photo of the slider date (frames.json, latest at or before the date), and the before/after swipe.
// Satellite shows the sharp, undated Imagery base map (no frame) unless "Dated photos" is on: then the 30 m photo of the date.
// Frames are drawn on one canvas that the map shows over the site; neighbouring frames are preloaded so play doesn't flicker.
import { formatDate } from "./format.js";
import { createSwipe } from "./swipe.js";

const PRELOAD_AHEAD = 5;
const NO_LABEL = { radar: "No radar picture", photo: "No photo" };
const IMAGERY_LABEL = "Imagery · undated · may be older";

/** `map`: from map.js. `mapWrap`: the element around the map (the swipe line goes there). `onView`: the view or Dated photos changed. */
export function createPicture(map, mapWrap, { onView } = {}) {
  const $ = (id) => document.getElementById(id);
  const box = $("viewbox");
  const buttons = { radar: $("view-radar"), photo: $("view-photo") };
  const compareBtn = $("compare-btn");
  const photosBtn = $("photos-btn");
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  const images = new Map(); // full url -> Promise<HTMLImageElement | null>

  let base = "";
  let coordinates = null;
  let sets = {}; // "radar" / "photo" -> {caption, frames}
  let view = "radar";
  let photos = false; // Satellite view: dated photos instead of the background imagery
  let date = null;
  let comparing = false;
  let token = 0; // newest render request; older ones that finish late are dropped
  let shown = { before: null, after: null }; // the images on the canvas now

  const swipe = createSwipe(mapWrap, { onMove: () => comparing && draw() });
  map.onMove(() => comparing && draw());

  function load(url) {
    const full = base + url;
    if (!images.has(full)) {
      images.set(full, new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => resolve(null);
        img.src = full;
      }));
    }
    return images.get(full);
  }

  /** The set of dated pictures on the map now: radar, the photos (Satellite with Dated photos on), or none (the imagery). */
  const active = () => (view === "radar" ? sets.radar : photos ? sets.photo : null);

  /** Index of the latest frame on or before `iso`, or -1. */
  function frameIndex(set, iso) {
    let found = -1;
    for (let i = 0; i < (set?.frames.length ?? 0) && set.frames[i].date <= iso; i++) found = i;
    return found;
  }

  /** Which side of the line (as fractions across the picture, at its top and bottom edge) the screen line falls on. */
  function split() {
    const x = swipe.x();
    const [tl, tr, br, bl] = coordinates.map((c) => map.project(c));
    return [(x - tl.x) / (tr.x - tl.x || 1), (x - bl.x) / (br.x - bl.x || 1)];
  }

  function draw() {
    const { before, after } = shown;
    const size = after ?? before;
    if (!size || !coordinates) return map.setFrame(null);
    const w = size.naturalWidth;
    const hgt = size.naturalHeight;
    if (canvas.width !== w || canvas.height !== hgt) [canvas.width, canvas.height] = [w, hgt];
    ctx.clearRect(0, 0, w, hgt);
    if (comparing) {
      if (before) ctx.drawImage(before, 0, 0, w, hgt);
      const [top, bottom] = split();
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(top * w, 0);
      ctx.lineTo(w + 1, 0);
      ctx.lineTo(w + 1, hgt);
      ctx.lineTo(bottom * w, hgt);
      ctx.closePath();
      ctx.clip();
      ctx.clearRect(0, 0, w, hgt);
      if (after) ctx.drawImage(after, 0, 0, w, hgt);
      ctx.restore();
    } else if (after) ctx.drawImage(after, 0, 0, w, hgt);
    map.setFrame(canvas, coordinates);
  }

  function labelFor(frame) {
    if (!frame) return NO_LABEL[view];
    return `${frame.sensor ?? (view === "radar" ? "Radar" : "Photo")} · ${formatDate(frame.date)}`;
  }

  /** "Before: Sentinel-1, 2 Jun 2025" (the two sides can be different satellites). */
  function sideLabel(prefix, frame) {
    return `${prefix}: ${frame.sensor ? `${frame.sensor}, ` : ""}${formatDate(frame.date)}`;
  }

  /** Show the frame(s) for the current view, date and compare state, once their pictures have loaded. */
  async function render() {
    const my = ++token;
    const set = active();
    const i = date ? frameIndex(set, date) : -1;
    const after = i >= 0 ? set.frames[i] : null;
    const before = comparing && set ? set.frames[0] : null;
    if (set) {
      for (let k = Math.max(0, i - 1); k <= Math.min(set.frames.length - 1, i + PRELOAD_AHEAD); k++) load(set.frames[k].url);
      load(set.frames[0].url); // the "before" of the swipe
    }
    const [a, b] = await Promise.all([after && load(after.url), before && load(before.url)]);
    if (my !== token) return;
    shown = { before: b, after: a };
    draw();
    $("frame-label").textContent = set ? labelFor(after) : view === "photo" ? IMAGERY_LABEL : "";
    swipe.setLabels(before ? sideLabel("Before", before) : "", after ? sideLabel("After", after) : "After: no picture");
  }

  function update() {
    for (const [key, btn] of Object.entries(buttons)) btn.setAttribute("aria-checked", String(key === view));
    buttons.radar.disabled = !sets.radar;
    if (!active()) comparing = false;
    photosBtn.hidden = view !== "photo" || !sets.photo;
    photosBtn.setAttribute("aria-pressed", String(photos));
    compareBtn.disabled = !(view === "radar" ? sets.radar : sets.photo); // in Satellite, Compare turns Dated photos on first
    compareBtn.title = view === "photo" && !photos && sets.photo ? "Compare uses the dated photos: this turns them on" : "";
    compareBtn.setAttribute("aria-pressed", String(comparing));
    swipe.show(comparing);
    render();
  }

  for (const [key, btn] of Object.entries(buttons)) btn.addEventListener("click", () => key !== view && api.setView(key));
  compareBtn.addEventListener("click", () => {
    comparing = !comparing;
    if (comparing && !active()) return api.setPhotos(true); // the imagery has no date: compare the dated photos
    update();
  });
  photosBtn.addEventListener("click", () => api.setPhotos(!photos));

  const api = {
    /** A loaded site ({base, frames}), or null for the intro screen (no picture, no switch). */
    setSite(site) {
      token++;
      box.hidden = !site;
      base = site?.base ?? "";
      coordinates = site?.frames?.coordinates ?? null;
      sets = Object.fromEntries((site?.frames?.sets ?? []).filter((s) => s.frames?.length).map((s) => [s.id, s]));
      view = sets.radar ? "radar" : "photo";
      photos = false;
      date = null;
      comparing = false;
      shown = { before: null, after: null };
      map.setFrame(null);
      if (site) update();
      else swipe.show(false);
    },
    /** "radar" or "photo". */
    setView(next) {
      if (box.hidden || next === view || (next === "radar" && !sets.radar)) return;
      view = next;
      update();
      onView?.(view);
    },
    /** Satellite view: show the dated photos (true) or the background imagery (false). Ignored without a photo set. */
    setPhotos(on) {
      const next = Boolean(on) && Boolean(sets.photo);
      if (box.hidden || next === photos) return;
      photos = next;
      update();
      onView?.(view);
    },
    /** The dated pictures on the map as timeline stops [{date, sensor}], or null when none are shown (Satellite imagery). */
    stops() {
      return active()?.frames.map(({ date, sensor }) => ({ date, sensor })) ?? null;
    },
    get view() {
      return view;
    },
    /** Dated photos on (only ever true when the site has a photo set). */
    get photos() {
      return photos;
    },
    /**
     * Which picture the open view shows at `iso`, for the timeline: "picture 12 of 63" on a date that has its own picture,
     * "no new picture" on a date between two pictures (it keeps showing the last one; the label under the switch names it),
     * "no picture yet" before the first, and "" when no dated pictures are shown (the Satellite imagery has no date, so the
     * slider's stops are the site's passes, not pictures). The slider steps through every pass
     * of the site, so its step number is not the picture number.
     */
    position(iso) {
      const set = active();
      if (!set) return "";
      const i = frameIndex(set, iso);
      if (i < 0) return "no picture yet";
      return set.frames[i].date === iso ? `picture ${i + 1} of ${set.frames.length}` : "no new picture";
    },
    setDate(iso) {
      date = iso;
      render();
    },
  };
  return api;
}
