// Written by Claude. The "Time frame" row of the Filter block: two date fields (From, To), limited to the site's own range.
// Either may stay empty. Changing them calls setTimeFrame() (selection.js), which filters the changes everywhere.
import { h } from "./format.js";
import { getSelection, setTimeFrame, onSelectionChange } from "./selection.js";

const ISO = /^\d{4}-\d{2}-\d{2}$/;
/** A "YYYY-MM-DD" that is a real calendar day, or null. */
export const validDate = (value) => (ISO.test(value ?? "") && !Number.isNaN(Date.parse(value)) ? value : null);

export function createTimeFrame(mount) {
  const from = h("input", { type: "date", id: "tf-from", "aria-label": "From date" });
  const to = h("input", { type: "date", id: "tf-to", "aria-label": "To date" });
  const note = h("p", { class: "tool-msg", role: "status", hidden: true });
  mount.append(
    h("div", { class: "tool-row" },
      h("span", { class: "tool-label" }, "Dates"),
      h("label", { class: "date-field", for: "tf-from" }, "From", from),
      h("label", { class: "date-field", for: "tf-to" }, "To", to)),
    note
  );
  const say = (text) => {
    note.textContent = text ?? "";
    note.hidden = !text;
  };

  let range = null;
  const clamp = (value) => {
    const v = validDate(value);
    if (!v || !range) return v;
    return v < range[0] ? range[0] : v > range[1] ? range[1] : v;
  };
  /** One line when the dates lie wholly outside the site's range: nothing is applied, so an empty list is never unexplained. */
  const outside = (a, b) => {
    if (!range) return null;
    if (b && b < range[0]) return `No changes before ${range[0]}. Change the To date.`;
    if (a && a > range[1]) return `No changes after ${range[1]}. Change the From date.`;
    return null;
  };

  function show({ from: a, to: b }) {
    from.value = a ?? "";
    to.value = b ?? "";
    say(null);
  }

  function changed() {
    const typed = outside(validDate(from.value), validDate(to.value));
    if (typed) { // keep what was typed, apply nothing (the earlier filter stays), say why
      say(typed);
      return;
    }
    const a = clamp(from.value);
    const b = clamp(to.value);
    const moved = (validDate(from.value) && a !== from.value) || (validDate(to.value) && b !== to.value);
    if (a && b && a > b) { // impossible range: keep what was typed, apply nothing yet
      say("From is after To. Change one of the dates.");
      return;
    }
    setTimeFrame(a, b);
    show(getSelection()); // also writes the clamped values back
    if (moved) say(`A date outside the site's range (${range[0]} to ${range[1]}) was moved to its nearest end.`);
  }
  from.addEventListener("change", () => changed());
  to.addEventListener("change", () => changed());
  onSelectionChange(show);

  return {
    /** The open site's range ("YYYY-MM-DD" pair), or null on the intro screen. */
    setSite(site) {
      range = site?.time_range ?? null;
      from.min = to.min = range?.[0] ?? "";
      from.max = to.max = range?.[1] ?? "";
      show(getSelection());
    },
    /** Link parameters: from= and to= when set. */
    toParams(params) {
      const { from: a, to: b } = getSelection();
      if (a) params.set("from", a);
      if (b) params.set("to", b);
    },
    /** From a link: both ends are ignored unless every given value is a valid date and from <= to. A pair wholly outside
     * the site's range is shown with the one-line message and filters nothing. */
    fromParams(params) {
      const a = validDate(params.get("from"));
      const b = validDate(params.get("to"));
      const bad = (params.get("from") && !a) || (params.get("to") && !b) || (a && b && a > b);
      const why = bad ? null : outside(a, b);
      setTimeFrame(bad || why ? null : clamp(a), bad || why ? null : clamp(b));
      if (why) {
        from.value = a ?? "";
        to.value = b ?? "";
        say(why);
      }
    },
  };
}
