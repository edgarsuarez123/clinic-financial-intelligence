# Budget workspace and persistent Clarity verification — 2026-09-11

- Complete Python suite: **209 passed, 53 skipped**. Skips require a disposable
  PostgreSQL server. Two warnings concern the installed Starlette test adapter's
  deprecated httpx/AnyIO interfaces; there were no test failures.
- Complete React suite: **38 passed in 13 files**. Coverage includes current-financial
  review, monthly edits/explicit zero, exact cent operations, autosave while edits
  continue, stable creation IDs after lost responses, revision conflict retention,
  saved-plan URL restoration, persisted chat reopening/follow-ups/retries, explicit
  proposed-plan opening, production diagnostics hiding and stale forecast results.
- Preserved the newer remote commit `9c4cb86` (demo data and longer Ollama waits).
  Afterwards, affected Python checks passed **31 tests, 4 database skips** and
  affected React checks passed **10 tests**. These are subsets, not added to the
  complete-suite totals. The full CSV fixture now reproduces 29,834 billing rows.
- Final `npm run build`: TypeScript and Vite production build passed. Gzip sizes in
  decimal kB: entry **70.18**, budgets **10.53**, Clarity **3.74**, shared charts
  **120.05**, chart wrapper **1.61**, CSS **4.09**. The optional PDF parser is
  **107.61 kB gzip**, above the 80 KiB route target; its worker is 1,375.84 kB raw.
  These bundle figures are not measured page-load or interaction performance.
- PostgreSQL parser accepted migration 009 and all 11 reviewed conversation SQL
  shapes. This proves syntax only, not role grants, view execution or durability.
- New database tests cover private-thread durability/permissions, duplicate and
  expired attempts, late completion after deletion, budget restore revisions,
  audit rollback and query-role denial of private storage. They remain unrun here.
- Pure calculation tests cover units × collected payment, sensitivity, salary
  changes, typed draft immutability, chronological forecast validation and rejection
  of short/missing/negative/incomplete history. Ollama adapter tests use simulated
  HTTP responses; no actual model quality or latency is asserted.
- No Docker/PostgreSQL/Ollama runtime or browser QA was available/executed for this
  update. No migration was applied to a customer database. Accessibility/Web Vitals
  are goals, not certified results; production deployment/Phase 6 remain unfinished.

The remaining entry below is historical.

---

# React and Ollama verification — 2026-09-08

- `python -m pytest -q`: 169 passed, 47 skipped. Skips are PostgreSQL integration tests; existing real-auth lifecycle test will cover migration 006 when run against PostgreSQL.
- `frontend/npm test`: 6 passed in 2 files. Coverage includes exact decimal formatting, same-origin session header, expired-session event, revision-aware budget save and conflict retention.
- `frontend/npm run build`: TypeScript checking and Vite production build succeeded.
- Final gzip sizes (decimal kB): entry 65.90, shared charts 120.04, budget route 5.78, chart wrapper 0.73, CSS 3.34. Shared JS total stays under the 200 KiB target; route-specific code stays below 80 KiB.
- Ollama tests: native response parsing and token usage; local endpoint and synthetic-mode restrictions; production/staging refusal; redirected, oversized, incomplete and failed responses; malicious model SQL rejected before database execution.
- Financial outputs continue to come from backend Decimal calculations. React tables display strings; charts use floating-point coordinates for drawing only.
- No Docker, PostgreSQL server or Ollama binary was available. Container startup, actual migrations, live persistence and genuine model inference were not run. No migration was applied to the user's existing database from this session.
- Browser, Lighthouse, screen-reader and field performance checks were not run. Accessibility and Web Vitals in ADR 028 remain targets, not certified scores.
- No production deployment or Phase 6 completion is claimed.

The source package excludes environment secrets, caches, dependencies and build intermediates. Install using the included dependency lockfiles. The frontend production output is included for inspection; Compose rebuilds from source.
