ALTER TABLE field_tasks ADD COLUMN IF NOT EXISTS terrain_sources jsonb NOT NULL DEFAULT '[]'::jsonb;
