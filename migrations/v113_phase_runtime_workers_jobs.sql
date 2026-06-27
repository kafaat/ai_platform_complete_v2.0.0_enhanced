-- v113: Phase runtime worker policies.
-- Runtime app traffic remains tenant-scoped through sahool_app.  Background
-- workers use sahool_jobs and are allowed to process queue tables without using
-- row-level bypass privileges.  This is narrower and auditable compared with broad database privileges.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahool_jobs') THEN
        GRANT SELECT, UPDATE ON runtime_event_outbox TO sahool_jobs;
        GRANT SELECT, UPDATE ON marketplace_plugin_execution_runs TO sahool_jobs;
        GRANT SELECT, UPDATE ON marketplace_plugin_runtime_events TO sahool_jobs;
        GRANT SELECT, UPDATE ON iot_command_dispatch TO sahool_jobs;
        GRANT SELECT, UPDATE ON model_rollback_history_runtime TO sahool_jobs;

        DROP POLICY IF EXISTS runtime_event_outbox_jobs_worker ON runtime_event_outbox;
        CREATE POLICY runtime_event_outbox_jobs_worker ON runtime_event_outbox
            FOR ALL TO sahool_jobs
            USING (true)
            WITH CHECK (true);

        DROP POLICY IF EXISTS marketplace_plugin_execution_jobs_worker ON marketplace_plugin_execution_runs;
        CREATE POLICY marketplace_plugin_execution_jobs_worker ON marketplace_plugin_execution_runs
            FOR ALL TO sahool_jobs
            USING (true)
            WITH CHECK (true);

        DROP POLICY IF EXISTS marketplace_plugin_events_jobs_worker ON marketplace_plugin_runtime_events;
        CREATE POLICY marketplace_plugin_events_jobs_worker ON marketplace_plugin_runtime_events
            FOR ALL TO sahool_jobs
            USING (true)
            WITH CHECK (true);

        DROP POLICY IF EXISTS iot_command_dispatch_jobs_worker ON iot_command_dispatch;
        CREATE POLICY iot_command_dispatch_jobs_worker ON iot_command_dispatch
            FOR ALL TO sahool_jobs
            USING (true)
            WITH CHECK (true);

        DROP POLICY IF EXISTS model_rollback_history_jobs_worker ON model_rollback_history_runtime;
        CREATE POLICY model_rollback_history_jobs_worker ON model_rollback_history_runtime
            FOR ALL TO sahool_jobs
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;
