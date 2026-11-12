-- Preserve unknown ground spacing on new registry writes. Existing 10 m rows
-- cannot be distinguished from measured values and are left intact.
ALTER TABLE raster_registry ALTER COLUMN resolution_m DROP DEFAULT;
