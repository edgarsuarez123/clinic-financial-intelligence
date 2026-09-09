-- Read surfaces omit source file content, credentials and query logs.
-- Current category classification applies to retained historical facts.
CREATE VIEW analytics.dashboard_facts WITH (security_barrier=true) AS
 SELECT d.full_date,t.amount,t.type,t.category_key,c.category_type,u.currency
 FROM analytics.transactions t
 JOIN analytics.dim_date d USING (date_key)
 JOIN analytics.dim_category c USING (category_key)
 JOIN core.uploads u ON u.upload_id=t.source_upload_id
 WHERE t.deleted_at IS NULL AND u.deleted_at IS NULL AND u.status='completed';
CREATE VIEW analytics.provider_facts WITH (security_barrier=true) AS
 SELECT d.full_date,t.amount,t.type,t.category_key,c.category_type,t.provider_key,u.currency
 FROM analytics.transactions t
 JOIN analytics.dim_date d USING (date_key)
 JOIN analytics.dim_category c USING (category_key)
 JOIN core.uploads u ON u.upload_id=t.source_upload_id
 WHERE t.deleted_at IS NULL AND u.deleted_at IS NULL AND u.status='completed';
GRANT SELECT ON analytics.dashboard_facts,analytics.provider_facts TO clinic_app;
-- HTTP permissions separately gate provider_facts; no base-table SELECT is added.
