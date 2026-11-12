-- v242: events.entity_type accepts every entity category the platform emits.
--
-- The CHECK (v11, widened once in v51) held 11 values while the platform emits 34: harvest
-- lots, tasks, alerts, calibration overrides, decision records, irrigation plans and more.
-- The database rejected each of those events. Non-critical emits logged and swallowed the
-- failure, so the event never existed; critical ones (HARVEST_LOT_CREATED,
-- CUSTODY_EVENT_RECORDED, YIELD_MAP_INGESTED, CALIBRATION_OVERRIDE_SET) aborted the business
-- write, so the endpoint failed on every call.
--
-- The value set is ALLOWED_ENTITY_TYPES in services/sahool-platform/core/event_schema.py.
-- tests_v9/test_events_entity_type_contract.py fails if this list and that set drift, or if
-- any call site emits a value outside it.
--
-- Re-run safety (MANIFEST is re-applied on every deploy): the constraint is replaced only
-- when it does not already accept every value below, so a re-run neither rescans the events
-- table nor narrows a later, wider constraint. It is added NOT VALID: every new row is checked
-- at once, and no existing row can violate it (each one passed the narrower v51 set). Running
-- VALIDATE CONSTRAINT is an operator step (docs/runbooks/validate_not_valid_constraints.md),
-- never part of a migration.

DO $v242$
DECLARE
    wanted text[] := ARRAY[
        'activity',
        'alert',
        'calibration_audit',
        'calibration_override',
        'crop_rotation',
        'decision_record',
        'dispatch_decision',
        'equipment',
        'equipment_maintenance',
        'farm',
        'field',
        'harvest_lot',
        'inventory_batch',
        'inventory_item',
        'irrigation_execution_plan',
        'irrigation_manual_execution',
        'irrigation_schedule',
        'irrigation_valve',
        'lineage_link',
        'master_data',
        'notification_delivery',
        'operation',
        'outcome_record',
        'recommendation',
        'sample',
        'season',
        'sensor',
        'soil_lab_test',
        'task',
        'tenant',
        'user',
        'well',
        'work_order',
        'yield_map_ingestion'
    ];
    have text;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO have
    FROM pg_constraint
    WHERE conrelid = 'events'::regclass AND conname = 'events_entity_type_check';

    IF have IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM unnest(wanted) AS w(v) WHERE have NOT LIKE '%''' || w.v || '''%'
    ) THEN
        RETURN;
    END IF;

    ALTER TABLE events DROP CONSTRAINT IF EXISTS events_entity_type_check;
    -- An IN list (not ANY of one array literal) so pg_get_constraintdef renders each value
    -- quoted ('harvest_lot'::text): the membership tests above and in v51 read it that way.
    EXECUTE format(
        'ALTER TABLE events ADD CONSTRAINT events_entity_type_check '
        'CHECK (entity_type IN (%s)) NOT VALID',
        (SELECT string_agg(quote_literal(v), ', ' ORDER BY v) FROM unnest(wanted) AS w(v))
    );
END
$v242$;
