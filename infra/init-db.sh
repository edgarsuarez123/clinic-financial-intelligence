#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv app_password APP_DB_PASSWORD
\getenv migration_password MIGRATION_DB_PASSWORD
\getenv query_password QUERY_DB_PASSWORD
SELECT format('CREATE ROLE clinic_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'app_password') \gexec
SELECT format('CREATE ROLE clinic_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'migration_password') \gexec
SELECT format('CREATE ROLE clinic_query LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'query_password') \gexec
ALTER DATABASE clinic OWNER TO clinic_migrator;
REVOKE ALL ON DATABASE clinic FROM PUBLIC;
GRANT CONNECT ON DATABASE clinic TO clinic_app,clinic_query,clinic_migrator;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER ROLE clinic_query SET default_transaction_read_only = on;
ALTER ROLE clinic_query SET statement_timeout = '5s';
SQL
