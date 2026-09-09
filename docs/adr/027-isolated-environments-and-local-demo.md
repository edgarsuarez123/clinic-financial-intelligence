# ADR 027 — Separate development/test environments and a local query demo

Accepted in Phase 5 in response to the user's request for runnable dev/test/production guidance and dummy data.

Keep one source workspace. Each environment gets a separate generated configuration directory, secret file, Compose project name, database volume, internal network and loopback ports. The helper creates independent random credentials, starts with every financial feature disabled and refuses to overwrite an existing environment directory. Generated directories are ignored by Git and excluded from Docker build context. These are deployment boundaries, not logical tenant IDs.

Dev/test dummy setup requires an explicit disposable-database confirmation, an existing test login, an empty transaction table and disabled configuration. It provisions only synthetic dimensions and permissions, then enables imports, analytics, budgets and the local question demo for that test account. It refuses staging/production. The integration test container likewise requires APP_ENV=test and an explicit disposable-test flag. A separate Compose project is required so integration tests never operate against dev or clinic data.

The local question adapter recognizes six fixed demo prompts and returns the same reviewed SQL contract without network calls. Financial arithmetic still runs in PostgreSQL. It is labeled as deterministic demonstration rather than a real LLM. It requires synthetic mode, zero token prices, no remote endpoint, and APP_ENV=dev/test. Production/staging startup rejects that adapter. This lets the user exercise authentication, SQL execution, results, cache, rate limits and saved budgets without external API cost. It does not validate natural-language model accuracy.

Production should ultimately run on a separate host/account with its own secrets, database, encrypted storage, TLS, backups and deployment policy. Current local Compose files and production directory preparation do not complete Phase 6 or deliver the final custom frontend. The run guide states these remaining gates instead of claiming a production-ready deployment.

References: [Compose project isolation](https://docs.docker.com/compose/how-tos/project-name/), [environment interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/), [volume behavior when stopping a project](https://docs.docker.com/reference/cli/docker/compose/down/).
