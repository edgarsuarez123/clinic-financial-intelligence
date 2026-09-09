CREATE SCHEMA core;
CREATE SCHEMA analytics;
CREATE SCHEMA audit;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

CREATE TABLE core.app_user (
 user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 username varchar(100) NOT NULL UNIQUE,
 password_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz
);
CREATE TABLE core.auth_session (
 token_hash char(64) PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
 user_id uuid NOT NULL REFERENCES core.app_user,
 expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz
);
CREATE INDEX session_user_idx ON core.auth_session(user_id);
CREATE TABLE core.login_throttle (
 key char(64) PRIMARY KEY,
 attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
 window_start timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE core.uploads (
 upload_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 filename text NOT NULL,
 uploaded_by uuid NOT NULL REFERENCES core.app_user,
 uploaded_at timestamptz NOT NULL DEFAULT now(),
 content_hash char(64) NOT NULL UNIQUE CHECK (content_hash ~ '^[0-9a-f]{64}$'),
 status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','completed','failed')),
 rows_accepted integer NOT NULL DEFAULT 0 CHECK (rows_accepted >= 0),
 rows_rejected integer NOT NULL DEFAULT 0 CHECK (rows_rejected >= 0),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz
);
CREATE TABLE analytics.dim_date (
 date_key integer PRIMARY KEY,
 full_date date NOT NULL UNIQUE,
 week smallint NOT NULL CHECK (week BETWEEN 1 AND 53),
 week_start date NOT NULL,
 iso_year smallint NOT NULL,
 month smallint NOT NULL CHECK (month BETWEEN 1 AND 12),
 quarter smallint NOT NULL CHECK (quarter BETWEEN 1 AND 4),
 year smallint NOT NULL,
 day_of_week smallint NOT NULL CHECK (day_of_week BETWEEN 1 AND 7)
);
CREATE TABLE analytics.dim_provider (
 provider_key uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 name text NOT NULL,
 role text NOT NULL,
 hire_date date,
 employment_type text,
 compensation_basis text,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz
);
CREATE TABLE analytics.dim_category (
 category_key uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 category_name text NOT NULL UNIQUE,
 category_type text NOT NULL CHECK (category_type IN ('fixed_cost','variable_cost','revenue')),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz
);
CREATE TABLE analytics.transactions (
 transaction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 date_key integer NOT NULL REFERENCES analytics.dim_date,
 provider_key uuid REFERENCES analytics.dim_provider,
 category_key uuid NOT NULL REFERENCES analytics.dim_category,
 type text NOT NULL CHECK (type IN ('revenue','expense')),
 -- Unconstrained NUMERIC plus CHECK avoids silently rounding input to cents.
 amount numeric NOT NULL CHECK (amount::text NOT IN ('NaN','Infinity','-Infinity')
                               AND abs(amount) < 10000000000000000
                               AND amount = trunc(amount,2)),
 source_upload_id uuid NOT NULL REFERENCES core.uploads,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz
);
CREATE INDEX transactions_date_idx ON analytics.transactions(date_key) WHERE deleted_at IS NULL;
CREATE INDEX transactions_provider_idx ON analytics.transactions(provider_key,date_key) WHERE deleted_at IS NULL;
CREATE INDEX transactions_category_idx ON analytics.transactions(category_key,date_key) WHERE deleted_at IS NULL;
CREATE INDEX transactions_upload_idx ON analytics.transactions(source_upload_id);

CREATE TABLE audit.audit_log (
 audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 actor uuid,
 action text NOT NULL,
 target text NOT NULL,
 request_id uuid NOT NULL,
 outcome text NOT NULL CHECK (outcome IN ('success','denied','error')),
 timestamp timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_timestamp_idx ON audit.audit_log(timestamp);
CREATE TABLE core.query_log (
 query_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 actor uuid NOT NULL REFERENCES core.app_user,
 question text NOT NULL,
 generated_sql text,
 execution_outcome text NOT NULL,
 input_tokens integer CHECK (input_tokens >= 0),
 output_tokens integer CHECK (output_tokens >= 0),
 token_cost numeric CHECK (token_cost >= 0 AND token_cost::text NOT IN ('NaN','Infinity')),
 llm_provider text,
 llm_model text,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz
);

CREATE FUNCTION core.touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END $$;
CREATE FUNCTION core.forbid_removal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Physical deletion is disabled; use the approved retention process'; END $$;
CREATE FUNCTION audit.forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Audit records are append-only'; END $$;

DO $$
DECLARE relation text;
BEGIN
 FOREACH relation IN ARRAY ARRAY['core.app_user','core.auth_session','core.uploads',
 'core.query_log','analytics.dim_provider','analytics.dim_category','analytics.transactions'] LOOP
  EXECUTE format('CREATE TRIGGER touch BEFORE UPDATE ON %s FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at()',relation);
  EXECUTE format('CREATE TRIGGER no_delete BEFORE DELETE ON %s FOR EACH ROW EXECUTE FUNCTION core.forbid_removal()',relation);
  EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON %s FOR EACH STATEMENT EXECUTE FUNCTION core.forbid_removal()',relation);
 END LOOP;
END $$;
CREATE TRIGGER audit_no_mutation BEFORE UPDATE OR DELETE ON audit.audit_log
 FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation();
CREATE TRIGGER audit_no_truncate BEFORE TRUNCATE ON audit.audit_log
 FOR EACH STATEMENT EXECUTE FUNCTION audit.forbid_mutation();

GRANT USAGE ON SCHEMA core,audit TO clinic_app;
GRANT SELECT ON core.app_user TO clinic_app;
GRANT SELECT,INSERT,UPDATE ON core.auth_session,core.login_throttle TO clinic_app;
GRANT INSERT ON audit.audit_log TO clinic_app;
GRANT USAGE ON SEQUENCE audit.audit_log_audit_id_seq TO clinic_app;
-- No financial grants exist yet. Phase 2 and the approved RBAC policy must add them explicitly.
-- clinic_query is provisioned but has no schema/table access until Phase 5.
