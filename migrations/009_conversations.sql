-- Durable private conversations; no patient/source documents or arbitrary model SQL.
CREATE TABLE core.conversation (
 conversation_id uuid PRIMARY KEY,
 owner_id uuid NOT NULL REFERENCES core.app_user(user_id),
 title varchar(100) NOT NULL CHECK(length(trim(title))>0),
 revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
 requires_provider_access boolean NOT NULL DEFAULT false,
 requires_simulation_access boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz
);
CREATE INDEX conversation_owner_idx ON core.conversation(owner_id,updated_at DESC,conversation_id) WHERE deleted_at IS NULL;
CREATE TABLE core.conversation_turn (
 turn_id uuid PRIMARY KEY,
 conversation_id uuid NOT NULL REFERENCES core.conversation,
 position integer NOT NULL CHECK(position>0),
 question varchar(2000) NOT NULL CHECK(length(trim(question))>0),
 context jsonb NOT NULL CHECK(jsonb_typeof(context)='object'),
 input_hash char(64) NOT NULL,
 response jsonb,
 status varchar(20) NOT NULL CHECK(status IN ('running','answered','refused','unavailable','rate_limited')),
 attempt_id uuid NOT NULL,
 started_at timestamptz NOT NULL DEFAULT now(),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz,
 UNIQUE(conversation_id,position)
);
CREATE TRIGGER touch BEFORE UPDATE ON core.conversation FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();
CREATE TRIGGER touch BEFORE UPDATE ON core.conversation_turn FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();
CREATE TRIGGER no_delete BEFORE DELETE ON core.conversation FOR EACH ROW EXECUTE FUNCTION core.forbid_removal();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON core.conversation FOR EACH STATEMENT EXECUTE FUNCTION core.forbid_removal();
CREATE TRIGGER no_delete BEFORE DELETE ON core.conversation_turn FOR EACH ROW EXECUTE FUNCTION core.forbid_removal();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON core.conversation_turn FOR EACH STATEMENT EXECUTE FUNCTION core.forbid_removal();
GRANT SELECT,INSERT,UPDATE ON core.conversation,core.conversation_turn TO clinic_app;
-- clinic_query deliberately has no conversation or saved-budget access.

CREATE VIEW analytics.nl_location_daily WITH (security_barrier=true) AS
 SELECT full_date,currency,coalesce(clinic_location,'Unassigned') AS clinic_location,
 sum(CASE WHEN type='revenue' THEN amount ELSE 0::numeric END) AS revenue,
 sum(CASE WHEN type='expense' THEN amount ELSE 0::numeric END) AS expense,
 sum(CASE WHEN type='expense' AND category_type='fixed_cost' THEN amount ELSE 0::numeric END) AS fixed_cost,
 sum(CASE WHEN type='expense' AND category_type='variable_cost' THEN amount ELSE 0::numeric END) AS variable_cost
 FROM analytics.dashboard_facts GROUP BY full_date,currency,clinic_location;
CREATE VIEW analytics.nl_insurance_daily WITH (security_barrier=true) AS
 SELECT full_date,currency,coalesce(clinic_location,'Unassigned') AS clinic_location,
 coalesce(medical_insurance,'Unclassified') AS medical_insurance,coalesce(billing_code,'Unclassified') AS billing_code,
 sum(amount) AS revenue FROM analytics.revenue_facts
 GROUP BY full_date,currency,clinic_location,medical_insurance,billing_code;
GRANT SELECT ON analytics.nl_location_daily,analytics.nl_insurance_daily TO clinic_query;
CREATE VIEW analytics.nl_provider_location_daily WITH (security_barrier=true) AS
 SELECT full_date,currency,coalesce(clinic_location,'Unassigned') AS clinic_location,provider_key,
 sum(CASE WHEN type='revenue' THEN amount ELSE 0::numeric END) AS revenue,
 sum(CASE WHEN type='expense' THEN amount ELSE 0::numeric END) AS expense
 FROM analytics.provider_facts GROUP BY full_date,currency,clinic_location,provider_key;
GRANT SELECT ON analytics.nl_provider_location_daily TO clinic_query;
