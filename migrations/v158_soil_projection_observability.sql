-- v158 — aggregate projection queue observability without exposing tenant evidence.
CREATE OR REPLACE FUNCTION sahool_soil_projection_queue_stats()
RETURNS TABLE(
    pending bigint,
    running bigint,
    retry bigint,
    completed bigint,
    dead_letter bigint,
    expired_leases bigint,
    oldest_ready_age_seconds double precision
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
  SELECT
    count(*) FILTER (WHERE status='pending'),
    count(*) FILTER (WHERE status='running'),
    count(*) FILTER (WHERE status='retry'),
    count(*) FILTER (WHERE status='completed'),
    count(*) FILTER (WHERE status='dead_letter'),
    count(*) FILTER (WHERE status='running' AND lease_expires_at < NOW()),
    COALESCE(EXTRACT(EPOCH FROM (NOW() - min(available_at) FILTER (
      WHERE status IN ('pending','retry') AND available_at <= NOW()
    ))), 0)::double precision
  FROM soil_profile_projection_jobs;
$$;
REVOKE ALL ON FUNCTION sahool_soil_projection_queue_stats() FROM PUBLIC;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sahool_app') THEN
    GRANT EXECUTE ON FUNCTION sahool_soil_projection_queue_stats() TO sahool_app;
  END IF;
END $$;
COMMENT ON FUNCTION sahool_soil_projection_queue_stats IS 'Aggregate queue health only; no tenant or field identifiers. v158.';
