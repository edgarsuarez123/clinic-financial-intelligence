-- Exact, versioned budget documents, isolated by application owner permissions.
CREATE TABLE core.saved_budget (
 budget_id uuid PRIMARY KEY,
 owner_id uuid NOT NULL REFERENCES core.app_user(user_id),
 name varchar(100) NOT NULL CHECK (length(trim(name)) > 0),
 revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
 plan jsonb NOT NULL CHECK (jsonb_typeof(plan)='object'),
 result jsonb NOT NULL CHECK (jsonb_typeof(result)='object'),
 model_version text NOT NULL,
 requires_provider_access boolean NOT NULL,
 input_hash char(64) NOT NULL CHECK (input_hash ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz
);
CREATE INDEX saved_budget_owner_idx ON core.saved_budget(owner_id,updated_at DESC,budget_id) WHERE deleted_at IS NULL;
CREATE TRIGGER touch BEFORE UPDATE ON core.saved_budget FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();
CREATE TRIGGER no_delete BEFORE DELETE ON core.saved_budget FOR EACH ROW EXECUTE FUNCTION core.forbid_removal();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON core.saved_budget FOR EACH STATEMENT EXECUTE FUNCTION core.forbid_removal();
GRANT SELECT,INSERT,UPDATE ON core.saved_budget TO clinic_app;
-- No grant to clinic_query: saved budgets contain modeled compensation.
