# Clarity React client

This is the primary browser interface for the cumulative clinic platform. See `../how-to-run.md` for first-time database/user/dummy-data setup and Ollama commands.

From this directory, with the API running on host port 8010:

```sh
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Vite proxies `/api` to the API. For the test API, run `API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev`.

```sh
npm test
npm run build
```

The default Compose `web` service builds and serves this app on http://127.0.0.1:3000 and forwards API requests internally. It does not require a local Node installation. `dist/` is build output; production TLS and other Phase 6 gates are still required before clinic use.

Structure: `main.tsx` owns authentication and navigation; `budgets.tsx` owns saved
plans and autosave; `monthly-plan.tsx`, `revenue-drivers.tsx` and
`revenue-forecast.tsx` provide monthly editing and projection tools. `clarity.tsx`
owns persistent conversations, result attachments and explicit proposed-plan
opening. `api.ts` owns HTTP and exact display formatting; `plots.tsx` is the shared
lazy chart module; `types.ts` owns plan contracts and the explicitly synthetic
fixture; `style.css` holds visual tokens and responsive styles. Migration 009 is
required for the current conversation API. The legacy Streamlit app is not feature
equivalent to React.

No default credentials, simulated authenticated responses, or hidden sample financial data are shipped in the UI. Enable synthetic mode through the existing admin workflow to use the sample budget button. Never store financial inputs or bearer tokens in localStorage.
