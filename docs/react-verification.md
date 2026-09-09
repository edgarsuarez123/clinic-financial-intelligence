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
