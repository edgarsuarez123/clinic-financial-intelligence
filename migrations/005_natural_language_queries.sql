-- Dedicated read surfaces over the star schema; no raw transaction or budget access.
CREATE VIEW analytics.nl_practice_daily WITH (security_barrier=true) AS
 SELECT d.full_date,d.year,d.month,d.week_start,u.currency,
 sum(CASE WHEN t.type='revenue' THEN t.amount ELSE 0::numeric END) AS revenue,
 sum(CASE WHEN t.type='expense' THEN t.amount ELSE 0::numeric END) AS expense,
 sum(CASE WHEN t.type='expense' AND c.category_type='fixed_cost' THEN t.amount ELSE 0::numeric END) AS fixed_cost,
 sum(CASE WHEN t.type='expense' AND c.category_type='variable_cost' THEN t.amount ELSE 0::numeric END) AS variable_cost
 FROM analytics.transactions t JOIN analytics.dim_date d USING (date_key)
 JOIN analytics.dim_category c USING (category_key) JOIN core.uploads u ON u.upload_id=t.source_upload_id
 WHERE t.deleted_at IS NULL AND u.deleted_at IS NULL AND u.status='completed'
 GROUP BY d.full_date,d.year,d.month,d.week_start,u.currency;
CREATE VIEW analytics.nl_provider_daily WITH (security_barrier=true) AS
 SELECT d.full_date,t.provider_key,u.currency,
 sum(CASE WHEN t.type='revenue' THEN t.amount ELSE 0::numeric END) AS revenue,
 sum(CASE WHEN t.type='expense' THEN t.amount ELSE 0::numeric END) AS expense
 FROM analytics.transactions t JOIN analytics.dim_date d USING (date_key)
 JOIN core.uploads u ON u.upload_id=t.source_upload_id
 WHERE t.deleted_at IS NULL AND u.deleted_at IS NULL AND u.status='completed'
 GROUP BY d.full_date,t.provider_key,u.currency;
CREATE VIEW analytics.nl_data_quality WITH (security_barrier=true) AS
 SELECT d.full_date,u.currency,bool_or((t.type='revenue')<>(c.category_type='revenue')) AS invalid_classification
 FROM analytics.transactions t JOIN analytics.dim_date d USING (date_key)
 JOIN analytics.dim_category c USING (category_key) JOIN core.uploads u ON u.upload_id=t.source_upload_id
 WHERE t.deleted_at IS NULL AND u.deleted_at IS NULL AND u.status='completed'
 GROUP BY d.full_date,u.currency;

CREATE TABLE core.analytics_revision (
 singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
 revision bigint NOT NULL DEFAULT 1
);
INSERT INTO core.analytics_revision DEFAULT VALUES;
CREATE FUNCTION core.bump_analytics_revision() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
 BEGIN UPDATE core.analytics_revision SET revision=revision+1 WHERE singleton; RETURN NULL; END $$;
REVOKE ALL ON FUNCTION core.bump_analytics_revision() FROM PUBLIC;
DO $$ DECLARE relation text; BEGIN
 FOREACH relation IN ARRAY ARRAY['analytics.transactions','core.uploads','analytics.dim_date','analytics.dim_category','analytics.dim_provider'] LOOP
 EXECUTE format('CREATE TRIGGER invalidate_query_cache AFTER INSERT OR UPDATE OR DELETE ON %s FOR EACH STATEMENT EXECUTE FUNCTION core.bump_analytics_revision()',relation);
 END LOOP;
END $$;
GRANT USAGE ON SCHEMA analytics,core TO clinic_query;
GRANT SELECT ON analytics.nl_practice_daily,analytics.nl_provider_daily,analytics.nl_data_quality,core.analytics_revision TO clinic_query;

CREATE TABLE core.nl_rate_limit (
 singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
 window_start timestamptz NOT NULL DEFAULT now(),
 attempts integer NOT NULL DEFAULT 0 CHECK (attempts>=0)
);
INSERT INTO core.nl_rate_limit DEFAULT VALUES;
CREATE TABLE core.query_cache (
 cache_key char(64) PRIMARY KEY,
 actor uuid NOT NULL REFERENCES core.app_user,
 payload jsonb NOT NULL,
 expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 deleted_at timestamptz
);
CREATE TRIGGER touch BEFORE UPDATE ON core.query_cache FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();
CREATE TRIGGER no_delete BEFORE DELETE ON core.query_cache FOR EACH ROW EXECUTE FUNCTION core.forbid_removal();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON core.query_cache FOR EACH STATEMENT EXECUTE FUNCTION core.forbid_removal();
ALTER TABLE core.query_log ADD COLUMN request_id uuid;
ALTER TABLE core.query_log ADD COLUMN parameters jsonb;
ALTER TABLE core.query_log ADD COLUMN cache_hit boolean NOT NULL DEFAULT false;
ALTER TABLE core.query_log ADD COLUMN unknown_usage_calls integer NOT NULL DEFAULT 0;
ALTER TABLE core.query_log ADD COLUMN input_price_per_million numeric;
ALTER TABLE core.query_log ADD COLUMN output_price_per_million numeric;
ALTER TABLE core.query_log ADD COLUMN pricing_currency char(3);
ALTER TABLE core.query_log ADD COLUMN usage_detail jsonb NOT NULL DEFAULT '[]'::jsonb;
CREATE INDEX query_log_created_idx ON core.query_log(created_at) WHERE deleted_at IS NULL;
GRANT SELECT,INSERT,UPDATE ON core.query_log,core.query_cache TO clinic_app;
GRANT SELECT,UPDATE ON core.nl_rate_limit TO clinic_app;
