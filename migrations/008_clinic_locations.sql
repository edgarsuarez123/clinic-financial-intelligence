-- One upload belongs to one location within the same isolated practice.
-- NULL preserves unknown attribution for existing uploads.
ALTER TABLE core.uploads ADD COLUMN clinic_location varchar(100);

CREATE OR REPLACE VIEW analytics.dashboard_facts WITH (security_barrier=true) AS
 SELECT d.full_date,t.amount,t.type,t.category_key,c.category_type,u.currency,u.clinic_location
 FROM analytics.transactions t
 JOIN analytics.dim_date d USING (date_key)
 JOIN analytics.dim_category c USING (category_key)
 JOIN core.uploads u ON u.upload_id=t.source_upload_id
 WHERE t.deleted_at IS NULL AND u.deleted_at IS NULL AND u.status='completed';

CREATE OR REPLACE VIEW analytics.provider_facts WITH (security_barrier=true) AS
 SELECT d.full_date,t.amount,t.type,t.category_key,c.category_type,t.provider_key,u.currency,u.clinic_location
 FROM analytics.transactions t
 JOIN analytics.dim_date d USING (date_key)
 JOIN analytics.dim_category c USING (category_key)
 JOIN core.uploads u ON u.upload_id=t.source_upload_id
 WHERE t.deleted_at IS NULL AND u.deleted_at IS NULL AND u.status='completed';

CREATE OR REPLACE VIEW analytics.revenue_facts WITH (security_barrier=true) AS
 SELECT d.full_date,t.amount,t.category_key,t.medical_insurance,t.billing_code,u.currency,u.clinic_location
 FROM analytics.transactions t
 JOIN analytics.dim_date d USING (date_key)
 JOIN analytics.dim_category c USING (category_key)
 JOIN core.uploads u ON u.upload_id=t.source_upload_id
 WHERE t.type='revenue' AND c.category_type='revenue'
   AND t.deleted_at IS NULL AND u.deleted_at IS NULL AND u.status='completed';
