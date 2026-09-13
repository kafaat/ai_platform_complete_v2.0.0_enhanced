# PostgreSQL 16 recovery

Logical exports and physical point-in-time recovery are separate procedures.
`pg_restore --list` proves that an archive catalog is readable; it does not prove
that the database can be restored, that all rows are intact, or that an RPO/RTO
has been met. No live restore drill was performed for the September 13 patch.

## Provisioning

Use PostgreSQL 16 client tools matching the server major version. Supply the
existing `PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE`, and credentials through the
operator's secret mechanism. The backup role needs the replication privileges
required by `pg_basebackup`; application credentials are not a replacement.

The server must have `wal_level=replica`, `archive_mode=on`, and a durable WAL
archive. Install the script and its `scripts/lib/pg_conn_defaults.sh` dependency
on the database host/container. A PostgreSQL `archive_command` example is:

```conf
archive_command = 'BACKUP_DIR=/var/backups/sahool /scripts/backup_postgres.sh wal_archive "%p" "%f"'
```

This is a server callback for each completed segment, not a periodic cron job.
Size `archive_timeout` from an approved RPO and measure the resulting archive
lag and storage cost. Keep WAL and physical bases together on durable storage
and replicate them off the database host. If S3 upload is configured, a failed
WAL upload fails the callback, including when the local segment already exists;
PostgreSQL can retry it. A repeated segment with different bytes is rejected.

The scripts do not automatically enable archiving or provision backup storage.
The repository's default Compose database is not evidence of an active PITR
archive. Before claiming readiness, inspect `pg_stat_archiver`, confirm a forced
WAL switch is archived, and restore an isolated copy.

## Backup and prepare recovery

```bash
bash scripts/backup_postgres.sh full
bash scripts/backup_postgres.sh base

bash scripts/restore_postgres.sh --pitr /var/backups/sahool/base/base_TIMESTAMP \
  --target-dir /var/lib/postgresql/recovery-drill \
  --wal-dir /var/backups/sahool/wal \
  --target-time '2026-09-13 10:00:00+00' --dry-run
```

`full` creates a custom-format logical export for `pg_restore`. `base` uses
`pg_basebackup --wal-method=stream` and `pg_verifybackup`, and only renames a
verified base out of its `.partial` directory. This implementation rejects
external tablespaces; they require an explicit storage mapping procedure.

Remove `--dry-run` to prepare a **new or empty** target directory. The script
verifies the physical manifest, copies the base, and writes PostgreSQL 16
`recovery.signal`, `restore_command`, `recovery_target_time`, and a pause action.
It does not start PostgreSQL, replace an existing data directory, or promote a
server. Start the copy as its OS owner using a separate port and isolated
network, with outbound workers and actuator access disabled. Confirm in server
logs that the requested target was reached and recovery paused. Check known
before/after marker rows, tenant isolation, required relations, and relevant
application receipts before considering promotion or a production cutover.

A `.dump` file cannot be used as a physical base for WAL replay. Logical restore
continues to use the existing `restore_postgres.sh <archive.dump>` flow and its
confirmation. `pg_restore --exit-on-error` prevents SQL errors from being
silently treated as a successful restore.

## Retention and evidence

Local age-based cleanup applies only to completed logical `full/sahool_*.dump`
files. The scripts intentionally retain physical bases and WAL until an operator
has established and verified the oldest recoverable boundary. S3 lifecycle rules
must preserve every segment required by the retained bases; a blanket WAL TTL
can destroy a recovery chain. `RETENTION_DAYS_S3` is not an enforced lifecycle
policy. Monitor archive volume growth and provision storage accordingly.

| Store | Required recovery evidence | Measured RPO | Measured RTO |
|---|---|---|---|
| PostgreSQL | Verified base, continuous WAL, timed isolated restore, tenant checks | NOT_MEASURED | NOT_MEASURED |
| NATS JetStream | Stream/consumer configuration plus a snapshot restore and replay test | NOT_MEASURED | NOT_MEASURED |
| Object/COG storage | Versioned objects and restored content checksums | NOT_MEASURED | NOT_MEASURED |
| Redis | Persistence policy and recovery of required durable keys/queues | NOT_MEASURED | NOT_MEASURED |
| Qdrant | Snapshot restore, collection schema and vector/count checks | NOT_MEASURED | NOT_MEASURED |
| Knowledge graph SQLite | Consistent SQLite backup on persistent storage and query replay | NOT_MEASURED | NOT_MEASURED |

Record the exact source/image versions, dataset scale, archive lag, target and
observed recovery time, integrity checks, and evidence locations in the
canonical runtime evidence ledger. A passing shell test with simulated clients
does not replace these measurements.
