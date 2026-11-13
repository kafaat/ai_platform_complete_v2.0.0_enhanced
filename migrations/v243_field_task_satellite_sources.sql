ALTER TABLE field_tasks ADD COLUMN IF NOT EXISTS satellite_sources jsonb NOT NULL DEFAULT '[]'::jsonb;
