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
  mount.append(
    h("div", { class: "tool-row" },
      h("span", { class: "tool-label" }, "Dates"),
      h("label", { class: "date-field", for: "tf-from" }, "From", from),
      h("label", { class: "date-field", for: "tf-to" }, "To", to))
  );

  let range = null;
  const clamp = (value) => {
    const v = validDate(value);
    if (!v || !range) return v;
    return v < range[0] ? range[0] : v > range[1] ? range[1] : v;
  };

  function show({ from: a, to: b }) {
    from.value = a ?? "";
    to.value = b ?? "";
    from.max = to.value || range?.[1] || "";
    to.min = from.value || range?.[0] || "";
  }

  function changed(source) {
    let a = clamp(from.value);
    let b = clamp(to.value);
    if (a && b && a > b) (source === from ? (b = null) : (a = null)); // the field just edited wins
    setTimeFrame(a, b);
    show(getSelection()); // also writes the clamped values back
  }
  from.addEventListener("change", () => changed(from));
  to.addEventListener("change", () => changed(to));
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
    /** From a link: both ends are ignored unless every given value is a valid date and from <= to. */
    fromParams(params) {
      const a = validDate(params.get("from"));
      const b = validDate(params.get("to"));
      const bad = (params.get("from") && !a) || (params.get("to") && !b) || (a && b && a > b);
      setTimeFrame(bad ? null : clamp(a), bad ? null : clamp(b));
    },
  };
}
