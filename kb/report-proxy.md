# Report proxy (AI-written summary)

A small Cloudflare Worker that turns the facts of a report into a short plain-English summary with Gemini, so the API key never reaches the browser. Last updated 2026-11-15. Code: `worker/`. Issue: #119 (package E).

## Why
The app is static (GitHub Pages) and the repo is public, so a key in the browser would be public. The Worker holds the key as a Cloudflare secret. The browser sends **facts only**; the Worker writes the prompt itself, so nobody can use it as a general chat endpoint.

Address: `https://parallax-report.slovenija.workers.dev/report` (set in `app/js/config.js`).

## Request: `POST /report`, JSON, at most 8 KB
```json
{
  "site": {"name": "…", "country": "…"},
  "time_frame": {"from": "2026-04-01", "to": "2026-10-26"},
  "area": {"bbox": [26.02, 64.80, 26.20, 64.88]},
  "totals": {"changes": 19, "area_ha": 397.2,
             "by_label": {"high_concern": {"n": 7, "ha": 359.0}, "review": {"n": 3, "ha": 12.1},
                          "expected": {"n": 9, "ha": 26.1}, "none": {"n": 0, "ha": 0}}},
  "top": [{"kind": "clearing", "area_ha": 109.0, "when": "between 21 Oct 2025 and 29 Apr 2026",
           "label": "high_concern", "reason": "…"}]
}
```
`area` may be `null` (whole site); `time_frame.from` / `to` may be `null` (else `YYYY-MM-DD`). Strict: unknown keys, wrong types, non-finite numbers or more than 10 `top` items give 400. Strings are trimmed and cut to 120 characters (`reason` 240); bbox is rounded to 2 decimals.

Responses: `200 {"summary": "...", "model": "..."}`; failures `{"error": "<code>"}`: `forbidden` 403, `not_found` 404, `method_not_allowed` 405, `rate_limited` / `busy` 429, `bad_request` 400, `upstream_error` 502, `upstream_timeout` 504, `bad_summary` 502. No key, upstream error text or stack trace is ever returned; request bodies are not logged.

## Guard rails
- **Origin allow-list:** `https://space0code.github.io`, `http://localhost:<port>`, `http://127.0.0.1:<port>`; anything else or no `Origin` gives 403. CORS headers only for allowed origins.
- **Prompt written in the Worker** (`buildPrompt`): reader is a non-specialist manager at a public authority; at most 180 words, 2 short paragraphs, plain English, no headings, lists or markdown; only the given facts; what, where, when, how much, what to look at first; a label is a prompt to check, never a finding of wrongdoing; no guessing who or why; no company or person names; never "illegal" or "unlawful". Facts go in as a JSON block with a sentence saying its text is data, not instructions.
- **Output check:** empty, over 1,500 characters, containing "illegal" / "unlawful", containing markdown (a line starting with `#`, `*` or `-`, or `**` or backticks) or more than 2 paragraphs gives `bad_summary`. Gemini's `finishReason` must be `STOP`; a length cut-off or safety block counts as a failure of that model (the fallback is tried), never as a summary.
- **Prompt:** numbers are written as digits exactly as given (19, 397.2 ha), not spelled out.
- **Model:** `gemini-flash-latest` (at most 4 s), then `gemini-flash-lite-latest` (at most 4 s) if the first fails or is slow; 8 s in total, so a failing first model doubles the upstream calls. Temperature 0.2, output capped at 700 tokens. `model` in the response says which answered. **In the tests of 15 Nov 2026 every 200 came from `gemini-flash-lite-latest`** (the primary failed or timed out each time), so a request costs two upstream calls.
- **Rate limits** (Cloudflare rate-limiting bindings; `429`): (1) **overall**, one shared key for all callers: 30 per 60 s (`{"error":"busy"}`); (2) per client address (`CF-Connecting-IP`): 10 per 60 s; (3) per address: 4 per 10 s (both `{"error":"rate_limited"}`). Checked before anything else is done, so before the Gemini call. The binding only allows `period` 10 or 60 s, so the configuration is valid. It is **approximate**: each Cloudflare location counts separately, uses a locally cached count and syncs in the background, so a burst can exceed the limit (docs: "Rate Limiting", Accuracy). Measured: 12 sequential requests in about 3 s gave no 429; 30 parallel requests gave 2 to 6 429s, not the ~26 a strict 4 per 10 s would give. Treat the limits as a brake of the right order of magnitude, not a quota; the overall cap is per location too (many locations, higher total). A strict limit would need a Durable Object (not used: no extra resources).

## Before the event (owner)
1. Use a Gemini key from a Google project with **no billing attached** (free tier fails closed as `502 upstream_error`), or set a hard daily quota on the Generative Language API there.
2. Rotate the key: create a new one in Google AI Studio, run `npx wrangler secret put GEMINI_API_KEY` from `worker/`, delete the old key. Rotate again after the event.
3. Switch the proxy off: set `REPORT_API` to an empty string in `app/js/config.js`; the report then uses the rule-based summary.

## Limits to know
- The origin check stops casual reuse from other web pages. It is **not authentication**: any script can send an `Origin` header. The rate limit and the fixed prompt cap the damage (a few short summaries per minute per address; nothing else can be asked).
- **Residual risk, plainly:** a caller who fakes the `Origin` header gets only a short summary from a fixed prompt, cannot choose the question and cannot read the key (it is never sent to the browser or returned). Cost is capped by the limits above plus the key's Google quota or missing billing; the worst case is the AI summary being unavailable for a while (the app falls back to the rule-based text).
- The summary is labelled as AI-written in the app, which keeps a rule-based fallback text.

## Deploy, rotate the key, test
From `worker/` (needs `wrangler login`):
```
npx wrangler deploy
npx wrangler secret put GEMINI_API_KEY      # paste the key at the prompt; never in a file or on a command line
bash test.sh https://parallax-report.slovenija.workers.dev   # status-code checks, one real summary
```
Rotate: create a new key in Google AI Studio, run `secret put` again, then delete the old key there. Local run: `npx wrangler dev` with a `worker/.dev.vars` file (gitignored).
