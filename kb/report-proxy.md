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

Responses: `200 {"summary": "...", "model": "..."}`; failures `{"error": "<code>"}`: `forbidden` 403, `not_found` 404, `method_not_allowed` 405, `rate_limited` 429, `bad_request` 400, `upstream_error` 502, `upstream_timeout` 504, `bad_summary` 502. No key, upstream error text or stack trace is ever returned; request bodies are not logged.

## Guard rails
- **Origin allow-list:** `https://space0code.github.io`, `http://localhost:<port>`, `http://127.0.0.1:<port>`; anything else or no `Origin` gives 403. CORS headers only for allowed origins.
- **Prompt written in the Worker** (`buildPrompt`): reader is a non-specialist manager at a public authority; at most 180 words, 2 short paragraphs, plain English, no headings, lists or markdown; only the given facts; what, where, when, how much, what to look at first; a label is a prompt to check, never a finding of wrongdoing; no guessing who or why; no company or person names; never "illegal" or "unlawful". Facts go in as a JSON block with a sentence saying its text is data, not instructions.
- **Output check:** empty, over 1,500 characters, or containing "illegal" / "unlawful" (any case) gives `bad_summary`.
- **Model:** `gemini-flash-latest` (5 s), then `gemini-flash-lite-latest` (up to 3 s) if the first is overloaded or slow (it returned 503 and timeouts on the night of 14 Nov 2026). Temperature 0.2, output capped at 700 tokens, 8 s in total. `model` in the response says which answered.
- **Rate limit:** Cloudflare Workers rate-limiting bindings, per client address (`CF-Connecting-IP`): 10 per 60 s and 4 per 10 s. The binding is approximate and counts per Cloudflare location (docs: "Rate Limiting", Accuracy), so it caps bursts and sustained abuse but is not a strict quota. A strict limit would need a Durable Object (not used: no extra resources).

## Limits to know
- The origin check stops casual reuse from other web pages. It is **not authentication**: any script can send an `Origin` header. The rate limit and the fixed prompt cap the damage (a few short summaries per minute per address; nothing else can be asked).
- The summary is labelled as AI-written in the app, which keeps a rule-based fallback text.

## Deploy, rotate the key, test
From `worker/` (needs `wrangler login`):
```
npx wrangler deploy
npx wrangler secret put GEMINI_API_KEY      # paste the key at the prompt; never in a file or on a command line
bash test.sh https://parallax-report.slovenija.workers.dev   # status-code checks, one real summary
```
Rotate: create a new key in Google AI Studio, run `secret put` again, then delete the old key there. Local run: `npx wrangler dev` with a `worker/.dev.vars` file (gitignored).
