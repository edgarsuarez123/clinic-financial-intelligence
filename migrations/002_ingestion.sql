ALTER TABLE core.uploads ADD COLUMN profile_hash char(64);
ALTER TABLE core.uploads ADD COLUMN profile_name text;
ALTER TABLE core.uploads ADD COLUMN currency char(3);
ALTER TABLE core.uploads ADD COLUMN total_rows integer NOT NULL DEFAULT 0 CHECK (total_rows>=0);
ALTER TABLE core.uploads ADD COLUMN rejections jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(rejections)='array');
ALTER TABLE core.uploads ADD COLUMN failure_code text;
ALTER TABLE core.uploads ADD CONSTRAINT completed_counts CHECK (status<>'completed' OR rows_accepted+rows_rejected=total_rows);
ALTER TABLE analytics.transactions ADD COLUMN source_row integer CHECK (source_row>0);
ALTER TABLE analytics.transactions ADD CONSTRAINT upload_row_unique UNIQUE (source_upload_id,source_row);
CREATE TABLE core.ingestion_job (
 upload_id uuid PRIMARY KEY REFERENCES core.uploads,
 payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='array'),
 attempts integer NOT NULL DEFAULT 0 CHECK (attempts>=0),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz
);
CREATE TRIGGER touch BEFORE UPDATE ON core.ingestion_job FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();
CREATE TRIGGER no_delete BEFORE DELETE ON core.ingestion_job FOR EACH ROW EXECUTE FUNCTION core.forbid_removal();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON core.ingestion_job FOR EACH STATEMENT EXECUTE FUNCTION core.forbid_removal();
GRANT SELECT,INSERT,UPDATE ON core.uploads,core.ingestion_job TO clinic_app;
GRANT USAGE ON SCHEMA analytics TO clinic_app;
GRANT SELECT,INSERT ON analytics.dim_date TO clinic_app;
GRANT SELECT (provider_key,deleted_at) ON analytics.dim_provider TO clinic_app;
GRANT SELECT (category_key,category_type,deleted_at) ON analytics.dim_category TO clinic_app;
GRANT INSERT ON analytics.transactions TO clinic_app;
-- No SELECT on amounts or compensation and no UPDATE/DELETE of financial facts.
