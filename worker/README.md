# worker/: report proxy

Cloudflare Worker `parallax-report`: `POST /report` takes validated facts and returns a short AI-written summary (Gemini). The key lives only as the Worker secret `GEMINI_API_KEY`. Full description, schema, guard rails and limits: `kb/report-proxy.md`.

```
npx wrangler deploy                          # from this folder
npx wrangler secret put GEMINI_API_KEY       # paste at the prompt
bash test.sh https://<worker-host>           # reruns the checks
```

<sub>Written by Claude</sub>
