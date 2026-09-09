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

Structure: `main.tsx` owns authentication and reporting/import/question views; `budgets.tsx` owns the persistent scenario workflow; `api.ts` owns HTTP and exact display formatting; `plots.tsx` is the shared lazy chart module; `types.ts` owns plan contracts and the explicitly synthetic fixture; `style.css` holds the visual tokens and responsive styles.

No default credentials, simulated authenticated responses, or hidden sample financial data are shipped in the UI. Enable synthetic mode through the existing admin workflow to use the sample budget button. Never store financial inputs or bearer tokens in localStorage.
