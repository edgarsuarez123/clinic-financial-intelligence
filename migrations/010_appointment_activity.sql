-- Appointment activity is a separate aggregate fact stream.  It never joins
-- financial transactions and it does not retain person-level identifiers.
CREATE TABLE core.appointment_upload (
 upload_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 uploaded_by uuid NOT NULL REFERENCES core.app_user,
 content_hash char(64) NOT NULL UNIQUE CHECK (content_hash ~ '^[0-9a-f]{64}$'),
 source_hash char(64) CHECK (source_hash IS NULL OR source_hash ~ '^[0-9a-f]{64}$'),
 mapping_hash char(64) NOT NULL CHECK (mapping_hash ~ '^[0-9a-f]{64}$'),
 replaces_upload_id uuid REFERENCES core.appointment_upload,
 replacement_claimed_by uuid REFERENCES core.appointment_upload,
 status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','completed','failed')),
 total_rows integer NOT NULL DEFAULT 0 CHECK (total_rows >= 0),
 rows_accepted integer NOT NULL DEFAULT 0 CHECK (rows_accepted >= 0),
 rows_rejected integer NOT NULL DEFAULT 0 CHECK (rows_rejected >= 0),
 rejections jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(rejections)='array'),
 failure_code text,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz,
 CONSTRAINT appointment_upload_counts CHECK (rows_accepted + rows_rejected <= total_rows),
 CONSTRAINT appointment_upload_replacement_self CHECK (replaces_upload_id IS NULL OR replaces_upload_id <> upload_id),
 CONSTRAINT appointment_upload_completed_counts CHECK (status <> 'completed' OR rows_accepted + rows_rejected = total_rows)
);
CREATE INDEX appointment_upload_owner_idx ON core.appointment_upload(uploaded_by,created_at DESC)
 WHERE deleted_at IS NULL;

CREATE TABLE core.appointment_ingestion_job (
 upload_id uuid PRIMARY KEY REFERENCES core.appointment_upload,
 payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='array'),
 config_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(config_snapshot)='object'),
 attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz
);

CREATE TABLE analytics.appointment_category (
 category_key varchar(64) PRIMARY KEY CHECK (category_key ~ '^[a-z][a-z0-9_]{0,63}$'),
 label varchar(100) NOT NULL CHECK (length(trim(label)) > 0),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz
);

CREATE TABLE analytics.appointment_activity (
 activity_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 activity_date date NOT NULL,
 clinic_location varchar(100) NOT NULL CHECK (length(trim(clinic_location)) > 0 AND clinic_location <> 'Unassigned'),
 category_key varchar(64) NOT NULL REFERENCES analytics.appointment_category(category_key),
 appointment_count integer NOT NULL CHECK (appointment_count >= 0),
 billed_amount numeric,
 collected_amount numeric,
 source_upload_id uuid NOT NULL REFERENCES core.appointment_upload,
 source_row integer NOT NULL CHECK (source_row > 0),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz,
 CONSTRAINT appointment_billed_amount_valid CHECK (
   billed_amount IS NULL OR (billed_amount::text NOT IN ('NaN','Infinity','-Infinity')
     AND abs(billed_amount) < 10000000000000000 AND billed_amount = trunc(billed_amount,2))
 ),
 CONSTRAINT appointment_collected_amount_valid CHECK (
   collected_amount IS NULL OR (collected_amount::text NOT IN ('NaN','Infinity','-Infinity')
     AND abs(collected_amount) < 10000000000000000 AND collected_amount = trunc(collected_amount,2))
 ),
 CONSTRAINT appointment_upload_row_unique UNIQUE (source_upload_id,source_row)
);
CREATE INDEX appointment_activity_date_idx ON analytics.appointment_activity(activity_date)
 WHERE deleted_at IS NULL;
CREATE INDEX appointment_activity_clinic_idx ON analytics.appointment_activity(clinic_location,activity_date)
 WHERE deleted_at IS NULL;
CREATE INDEX appointment_activity_category_idx ON analytics.appointment_activity(category_key,activity_date)
 WHERE deleted_at IS NULL;

CREATE TRIGGER touch BEFORE UPDATE ON core.appointment_upload
 FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();
CREATE TRIGGER no_delete BEFORE DELETE ON core.appointment_upload
 FOR EACH ROW EXECUTE FUNCTION core.forbid_removal();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON core.appointment_upload
 FOR EACH STATEMENT EXECUTE FUNCTION core.forbid_removal();
CREATE TRIGGER touch BEFORE UPDATE ON core.appointment_ingestion_job
 FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();
CREATE TRIGGER no_delete BEFORE DELETE ON core.appointment_ingestion_job
 FOR EACH ROW EXECUTE FUNCTION core.forbid_removal();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON core.appointment_ingestion_job
 FOR EACH STATEMENT EXECUTE FUNCTION core.forbid_removal();
CREATE TRIGGER touch BEFORE UPDATE ON analytics.appointment_category
 FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();
CREATE TRIGGER no_delete BEFORE DELETE ON analytics.appointment_category
 FOR EACH ROW EXECUTE FUNCTION core.forbid_removal();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON analytics.appointment_category
 FOR EACH STATEMENT EXECUTE FUNCTION core.forbid_removal();
CREATE TRIGGER touch BEFORE UPDATE ON analytics.appointment_activity
 FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();
CREATE TRIGGER no_delete BEFORE DELETE ON analytics.appointment_activity
 FOR EACH ROW EXECUTE FUNCTION core.forbid_removal();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON analytics.appointment_activity
 FOR EACH STATEMENT EXECUTE FUNCTION core.forbid_removal();

CREATE VIEW analytics.appointment_activity_facts WITH (security_barrier=true) AS
 SELECT a.activity_date, a.clinic_location, a.category_key, c.label AS category_label,
        a.appointment_count, a.billed_amount, a.collected_amount,
        a.source_upload_id, a.source_row
 FROM analytics.appointment_activity a
 JOIN analytics.appointment_category c USING (category_key)
 JOIN core.appointment_upload u ON u.upload_id = a.source_upload_id
 WHERE a.deleted_at IS NULL AND c.deleted_at IS NULL
   AND u.deleted_at IS NULL AND u.status = 'completed';

GRANT USAGE ON SCHEMA analytics TO clinic_app;
GRANT SELECT,INSERT,UPDATE ON core.appointment_upload,core.appointment_ingestion_job TO clinic_app;
GRANT SELECT,INSERT,UPDATE ON analytics.appointment_category TO clinic_app;
GRANT INSERT ON analytics.appointment_activity TO clinic_app;
GRANT SELECT (source_upload_id,deleted_at) ON analytics.appointment_activity TO clinic_app;
GRANT UPDATE (deleted_at) ON analytics.appointment_activity TO clinic_app;
GRANT SELECT ON analytics.appointment_activity_facts TO clinic_app;
