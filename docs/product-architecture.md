# Product architecture and cumulative workspace

The application is maintained in **one cumulative workspace and one Git history**.
Each phase extends the same FastAPI application, PostgreSQL schema and migration
sequence, tests, deployment files and documentation. A phase-numbered ZIP is a
snapshot of the whole workspace, not a separate application or microservice fork.

## User clarification during Phase 3

Streamlit is the temporary local testing and demonstration interface. It is a
browser-based app, but it is **not the intended final product frontend**.

The required final product is a custom web application containing authentication,
financial dashboards, all visualizations, analytics, staffing simulations and
natural-language financial questions in one browser interface. FastAPI exposes
the business capabilities and authentication; PostgreSQL remains the source of
financial records. The production frontend framework has not been selected.

Phase 3 calculations are pure Python and do not import FastAPI, PostgreSQL drivers,
Pydantic, Streamlit or a plotting library. The analytics routes have versioned
OpenAPI response contracts. Provider authorization happens in the API, so it
cannot be bypassed by replacing or manipulating the frontend.

## Release milestones

- Phases 1–3: foundation, ingestion and analytics source implemented; outstanding
  PostgreSQL/Docker validation remains explicitly documented.
- Phase 4: staffing simulation, after user confirmation.
- Phase 5: text-to-SQL, after user confirmation.
- Production frontend: required before launch, consuming the same API. This is
  additional release work following the user's clarification, not satisfied by
  the Streamlit demo.
- Phase 6: security and operational hardening, with the production frontend also
  included in end-to-end release verification.

Do not describe the demo or current source package as a deployed production app.
Do not start subsequent phases without the requested phase confirmation.
