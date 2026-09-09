-- Only administrator-approved payer/code labels are accepted by ingestion.
-- Existing facts remain unclassified; never infer historical classifications.
ALTER TABLE analytics.transactions
 ADD COLUMN medical_insurance varchar(100),
 ADD COLUMN billing_code varchar(100),
 ADD CONSTRAINT revenue_dimensions_only CHECK
   (type='revenue' OR (medical_insurance IS NULL AND billing_code IS NULL));

CREATE VIEW analytics.revenue_facts WITH (security_barrier=true) AS
 SELECT d.full_date,t.amount,t.category_key,t.medical_insurance,t.billing_code,u.currency
 FROM analytics.transactions t
 JOIN analytics.dim_date d USING (date_key)
 JOIN analytics.dim_category c USING (category_key)
 JOIN core.uploads u ON u.upload_id=t.source_upload_id
 WHERE t.type='revenue' AND c.category_type='revenue'
   AND t.deleted_at IS NULL AND u.deleted_at IS NULL AND u.status='completed';
GRANT SELECT ON analytics.revenue_facts TO clinic_app;
-- Deliberately do not add this view to the LLM query role/catalog.
