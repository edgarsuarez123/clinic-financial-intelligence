# Primary technical references consulted

- FastAPI security and Argon2 password hashing:
  https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
  This implementation uses opaque database sessions, not that example's JWT design.
- PostgreSQL privileges and default PUBLIC permissions:
  https://www.postgresql.org/docs/17/ddl-priv.html
- PostgreSQL schema privileges:
  https://www.postgresql.org/docs/17/ddl-schemas.html

These references inform implementation details; the supplied SRD governs scope.

Phase 2 primary implementation references:

- Streamlit fragments and periodic progress updates:
  https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment
- pdfplumber structured table extraction:
  https://github.com/jsvine/pdfplumber/blob/stable/README.md
- PostgreSQL queue locking behavior:
  https://www.postgresql.org/docs/17/sql-select.html

Phase 3 primary technical references:

- Decimal arithmetic and local contexts: https://docs.python.org/3/library/decimal.html
- PostgreSQL view privileges: https://www.postgresql.org/docs/17/sql-createview.html
- Streamlit chart API: https://docs.streamlit.io/develop/api-reference/charts/st.altair_chart


## Phase 5 and environment guidance

- https://www.postgresql.org/docs/17/sql-set-transaction.html — read-only transaction scope.
- https://www.postgresql.org/docs/17/ddl-priv.html — grants as the database boundary.
- https://www.psycopg.org/psycopg3/docs/basic/params.html — separately bound SQL parameters.
- https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create — compatible HTTP message/JSON response contract; no specific provider/model was activated.
- https://docs.docker.com/compose/how-tos/project-name/ — project isolation.
- https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/ — env-file usage and shell precedence.
- https://docs.docker.com/reference/cli/docker/compose/down/ — persistent volume behavior.
