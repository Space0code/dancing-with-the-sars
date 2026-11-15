// Written by Claude. The Export button and its format dialog. Formats register themselves; this file knows no format.
//
// API
//   registerExportFormat({id, label, note, run})
//       id     unique key, label  the radio row's title, note  one short line under it
//       run(ctx) async; makes the file and hands it to downloadBlob(). ctx = {site, changes, selection, snapshot, kindName}
//           site       the open site's record from sites.json ({id, name, bbox, ...})
//           changes    GeoJSON features after the selection (selection.js) and the list's filters, incl. "Smallest change"
//           selection  {area, from, to}
//           snapshot   () => Promise<PNG data URL> of the map as the user sees it (map.js)
//           kindName   (type) => short readable kind, as in the list
//           status     (text) => shows a short wait message in the dialog while run() works (cleared when it ends)
//       `first: true` on the format puts it on top of the list, selected by default.
//       Registering the same id again replaces the format. Formats appear in registration order.
//   downloadBlob(filename, blob)   shared helper: starts a browser download
//   createExport({getContext, buttons})   main.js only: getContext() -> ctx or null (no site open); buttons = the opener buttons
import { h } from "./format.js";
import { changesCsv } from "./csv.js";
import { describeSelection } from "./selection.js";

const formats = [];

export function registerExportFormat(format) {
  const i = formats.findIndex((f) => f.id === format.id);
  if (i >= 0) formats[i] = format;
  else if (format.first) formats.unshift(format); // `first: true` puts the format on top (and so selected by default)
  else formats.push(format);
}

export function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

registerExportFormat({
  id: "csv", label: "CSV", note: "One row per change, opens in a spreadsheet.",
  run: async (ctx) => downloadBlob(`parallax-${ctx.site.id}-changes.csv`, new Blob([changesCsv(ctx.changes, ctx.kindName)], { type: "text/csv;charset=utf-8" })),
});

export function createExport({ getContext, buttons }) {
  const dialog = h("dialog", { class: "export-dialog", "aria-labelledby": "export-title" });
  document.body.append(dialog);
  let opener = null;

  const close = () => dialog.open && dialog.close();
  dialog.addEventListener("close", () => opener?.isConnected && opener.focus());
  dialog.addEventListener("click", (e) => e.target === dialog && close()); // a click on the backdrop

  function open(button) {
    const ctx = getContext();
    if (!ctx) return;
    opener = button;
    const n = ctx.changes.length;
    const what = `${n} ${n === 1 ? "change" : "changes"} · ${describeSelection() || "whole site · all dates"}`;
    const status = h("p", { class: "export-what", role: "status" });
    const error = h("p", { class: "export-error", role: "alert", hidden: true });
    const go = h("button", { type: "submit", class: "primary" }, "Download");
    const form = h("form", { method: "dialog" },
      h("h2", { id: "export-title" }, "Export"),
      h("div", { class: "format-list", role: "radiogroup", "aria-label": "Format" },
        formats.map((f, i) => h("label", { class: "format-row" },
          h("input", { type: "radio", name: "format", value: f.id, checked: i === 0 }),
          h("span", {}, h("span", { class: "format-name" }, f.label), h("span", { class: "format-note" }, f.note))))),
      h("p", { class: "export-what" }, what),
      status,
      error,
      h("div", { class: "export-actions" }, h("button", { type: "button", onclick: close }, "Cancel"), go));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const format = formats.find((f) => f.id === form.elements.format.value);
      go.disabled = true;
      error.hidden = true;
      try {
        await format.run({ ...ctx, status: (text) => (status.textContent = text ?? "") }); // run() may show a short wait message
        close();
      } catch (err) {
        error.textContent = `Could not make the ${format.label} file: ${err.message}`;
        error.hidden = false;
      } finally {
        status.textContent = "";
        go.disabled = false;
      }
    });
    dialog.replaceChildren(form);
    dialog.showModal();
    form.querySelector("input:checked")?.focus();
  }

  for (const b of buttons) b.addEventListener("click", () => open(b));
  return { open, close };
}
