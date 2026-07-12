# RIV PostgreSQL Lease Runtime Certification — Continuation

Date: 2026-07-12

## Scope

Continuation of Raster–Indicators–Vegetation runtime certification, focused on durable PostgreSQL batch leases, restart behavior, long-running indicators, duplicate callers, and stale-worker fencing.

## Source findings fixed

### 1. Long-running indicator could outlive the lease

The worker previously renewed the durable lease only after each indicator. A single slow indicator could exceed `RASTER_BATCH_LEASE_SECONDS`, allowing another worker to reclaim the same batch while the original worker was still running.

Implemented `_LeaseHeartbeat` in `services/raster-service/raster_job_orchestration.py`:

- verifies ownership before opening the raster;
- renews the PostgreSQL lease periodically in a dedicated daemon thread;
- derives the default interval from one third of the lease duration;
- supports `RASTER_BATCH_HEARTBEAT_SECONDS` override;
- fences the worker when heartbeat ownership is lost;
- stops scheduling additional indicators;
- refuses to write the durable terminal state after lease loss.

New counters:

- `lease_heartbeat_success_total`
- `lease_heartbeat_failure_total`
- `lease_heartbeat_exception_total`
- `lease_lost_total`

### 2. Completed jobs appeared as pending after restart

When process-local job state was empty, a duplicate request for an already completed PostgreSQL job returned `pending`. `DurableClaim` now carries:

- `result_payload`
- `error_code`

The `/process/batch` response now returns the authoritative durable status and result after restart.

### 3. PostgreSQL certification harness

Added `services/raster-service/test_raster_batch_postgres_integration.py`.

When `RASTER_TEST_DATABASE_URL` is configured, it proves:

1. two concurrent workers converge on one `job_id`;
2. only one worker acquires the lease;
3. an expired lease is recoverable;
4. recovery rotates the lease token;
5. the stale worker cannot finish;
6. the current worker can finish;
7. replay returns the persisted result without re-execution.

The test is skipped honestly when no real PostgreSQL test database is configured.

## Configuration

Added to Compose and `.env.example`:

```env
RASTER_BATCH_HEARTBEAT_SECONDS=0
```

`0` means derive the interval automatically from `RASTER_BATCH_LEASE_SECONDS`.

## Verification

Focused and boundary suite:

```text
34 passed
```

PostgreSQL integration harness in this environment:

```text
1 skipped — RASTER_TEST_DATABASE_URL is not configured
```

CI guards:

```text
riv_boundary_gate_ok
raster_production_truth_guard_ok
geospatial_contract_index_ok
indicators_registry_gate_ok
```

Additional checks:

```text
py_compile passed
Docker Compose YAML parse passed
```

## Remaining production certification

The code path and real-PostgreSQL harness are present, but this environment did not provide PostgreSQL, Redis, MinIO, Docker, or Compose runtime binaries. The following must still run in staging:

1. apply migration `v147_raster_product_identity_batch_leases.sql`;
2. run the PostgreSQL integration test with a non-superuser RLS-aware role;
3. run two Raster containers against the same PostgreSQL and Redis;
4. kill the active worker during a real remote-COG operation;
5. prove lease recovery and stale-worker rejection;
6. measure S3/MinIO range requests, memory, throughput, and GDAL cache behavior;
7. verify that no product persistence occurs after a worker is fenced.

## Status

- Long-running lease heartbeat: completed.
- Restart result recovery: completed.
- Stale terminal-write fencing: completed.
- Real PostgreSQL test harness: completed.
- Real staging execution: pending environment availability.

---

## ملحق التكامل (أُضيف عند الدمج على الشجرة المُهبَطة — 2026-07-12)

يُبنى فوق الهويّة الدائمة (v154). قرارات الدمج والإصلاحات:

- **النطاق المأخوذ:** heartbeat الإيجار في خيط daemon (`_LeaseHeartbeat` — يجدّد الإيجار
  دوريّاً لمؤشّر طويل، ثلث مدّة الإيجار افتراضاً، `RASTER_BATCH_HEARTBEAT_SECONDS` تجاوز،
  يسيّج العامل عند فقد الملكيّة ويرفض الكتابة النهائيّة بعد فقد الإيجار) + استرداد النتيجة
  بعد إعادة التشغيل (`DurableClaim` يحمل `result_payload`/`error_code`؛ الطلب المكرَّر
  لوظيفة مكتملة يعيد الحالة السلطويّة لا pending) + عدّادات
  (`lease_heartbeat_*`, `lease_lost_total`) + harness تكامل PostgreSQL + رايات
  compose(v9+fixed)/env.
- **عيبان حقيقيّان أُصلحا على Postgres حقيقيّ (الحزمة لم تُشغّل الـharness على PG قطّ):**
  1. `now()+($6::text||' seconds')` كان يُمرَّر `LEASE_SECONDS` كـint بينما يستنتج
     asyncpg النوع نصّاً من `::text` ⇒ `DataError: invalid input ... expected str, got int`.
     أُصلح بتمرير `str(LEASE_SECONDS)` في مطالبة الادّعاء وheartbeat.
  2. asyncpg يعيد `jsonb` نصّاً خاماً (بلا codec) فـ`dict(result_payload)` يرفع
     `ValueError: dictionary update sequence element #0 has length 1` ⇒ أُصلح بمساعِد
     `_as_obj` (يفكّ النصّ بـ`json.loads`، يقبل dict أيضاً عبر السائقين).
- **برهاني على Postgres حقيقيّ (ما عجزت عنه الحزمة):** شغّلت
  `test_raster_batch_postgres_integration.py` على PG محلّيّ حقيقيّ بعد إنشاء `raster_batch_jobs`
  — **PASSED**: عاملان يتقاربان على job_id واحد، فائز إيجار واحد، استرداد الإيجار المنتهي مع
  تدوير الرمز، رفض العامل البائت، وإعادة التشغيل تُرجِع النتيجة المُثبَتة بلا إعادة تنفيذ.
- **تحقّق:** raster 242 (منها الاستمرار) + 1 متخطّى (harness بلا env) في المسار العاديّ،
  و**PASSED على PG حقيقيّ** عند ضبط `RASTER_TEST_DATABASE_URL`؛ الجرد + manifest (4129) مُجدَّدان.
