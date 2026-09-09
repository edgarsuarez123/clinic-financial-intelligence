# ADR 028 — React client over the existing versioned API

Accepted 2026-09-08. The user selected React as the primary product interface; Streamlit becomes an optional legacy demo profile.

Use Vite, React and TypeScript in `frontend/`, deployed by the existing Compose project through an unprivileged Nginx container. This preserves the single cumulative workspace and per-clinic FastAPI/PostgreSQL isolation. A static hosted frontend alone cannot operate this private Docker backend; no separate hosted demo or replacement database was created.

Browser requests use same-origin `/api/v1` through Nginx (Vite proxy for hot reload). No API credentials are compiled into JavaScript. Expiring bearer tokens live in memory, are revoked on logout, and are cleared on 401. Refreshing the browser requires login; saved budgets remain in PostgreSQL. This avoids introducing an unrelated identity provider or browser persistence for financial records.

All financial calculations stay in the existing Decimal backend. Forms submit decimal strings. Chart coordinates convert to numbers only for visualization; exact result tables retain the API strings. Currency display uses BigInt cent rounding. Server permission checks remain authoritative, with feature availability reflected in navigation content. Revision conflicts preserve editor inputs.

UI direction: quiet green clinic workspace, warm neutral background, compact side navigation, explicit empty/error/loading states, line and bar charts with corresponding exact tables, editable staffing and operating-cost forms, and adjacent assumption disclosures. No decorative image is needed for this quantitative app.

Working frontend skill assumptions: desktop on a corporate/broadband network; authenticated SPA with no SEO need; design tokens in `frontend/src/style.css`; WCAG AA target. Accessibility implementation responsibility for this iteration: coding agent; ongoing owner: unassigned. Targets (not measured): p75 LCP <=2500 ms, INP <=200 ms, CLS <=0.1; Lighthouse accessibility >=95 and performance >=90. JS budget: <=200 KiB gzip shared/initial and <=80 KiB route-specific. Charts are shared and loaded separately; budgets are lazy loaded. Field data and Lighthouse remain unmeasured.

The uploaded skill references scripts, forcing questions and specialist agents that were not attached. Its available React, accessibility and performance guidance was applied directly using the user's chosen framework and the known authenticated desktop use case; missing helper tooling was not invented. Keyboard/screen-reader and browser layout review remain outstanding.
