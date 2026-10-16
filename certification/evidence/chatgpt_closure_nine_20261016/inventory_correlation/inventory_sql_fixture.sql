-- Query projection fixture only. Types follow v14/v114/v116/v143/v144/v154;
-- geometry, operational constraints, and unrelated columns are deliberately omitted.
CREATE TABLE raster_assets (id bigint PRIMARY KEY, tenant_id uuid, field_id varchar(50), scene_id varchar(200), index_name varchar(30), provenance jsonb, geometry_revision integer, algorithm_version text, product_identity_key text, acquisition_date date, processing_job_id varchar(100));
CREATE TABLE raster_registry (id uuid PRIMARY KEY, tenant_id uuid, field_id varchar(50), scene_id text, index_type text, metadata jsonb, product_date date);
CREATE TABLE backfill_runs (id bigint PRIMARY KEY, tenant_id uuid, field_id varchar(50), geometry_revision integer, status text, error text);
CREATE TABLE backfill_run_items (id bigint PRIMARY KEY, tenant_id uuid, field_id varchar(50), scene_id text, index_name text, provider text, status text, job_id text, run_id bigint, error text);
CREATE TABLE raster_batch_jobs (job_id text PRIMARY KEY, tenant_id uuid, field_id varchar(50), status text, request_payload jsonb, error_code text);
CREATE TABLE distributed_raster_jobs (id uuid PRIMARY KEY, tenant_id uuid, status text, input jsonb, error text);
