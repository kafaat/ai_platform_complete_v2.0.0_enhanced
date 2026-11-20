\set ON_ERROR_STOP on
-- Run only on the disposable test cluster, after applying its manifest.
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOINHERIT', :'writer', :'writer_pass')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'writer') \gexec
SELECT 'CREATE ROLE irr_f01_reader LOGIN PASSWORD ''irr_f01_reader'' NOSUPERUSER NOBYPASSRLS NOINHERIT'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'irr_f01_reader') \gexec
GRANT CONNECT ON DATABASE :"DBNAME" TO :"writer", irr_f01_reader;
GRANT USAGE ON SCHEMA public TO :"writer", irr_f01_reader;
GRANT SELECT ON hydraulic_capacity_evaluations, irrigation_resource_reservations,
    irrigation_resource_reservation_events TO irr_f01_reader;
GRANT SELECT, INSERT ON hydraulic_capacity_evaluations, irrigation_resource_reservations,
    irrigation_resource_reservation_events, events, event_outbox TO :"writer";
GRANT UPDATE (state, released_at, release_reason) ON irrigation_resource_reservations TO :"writer";
GRANT SELECT ON canonical_hydraulic_capabilities TO :"writer";
GRANT USAGE ON SEQUENCE event_outbox_outbox_id_seq TO :"writer";
